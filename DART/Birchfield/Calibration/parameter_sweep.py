"""Parameter sweep for calibrating Dartboard topology to match Texas-7k.

Runs TopologyGenerator on Texas-7k bus positions with varied parameter
combinations and records structural metrics vs the Texas-7k reference for
each experiment.  All outputs go to Calibration/outputs/sweep_*.

Target metrics (Texas-7k reference):
  345 kV:  259 nodes, 402 edges, m/n=1.552, mean_deg=3.10, intersect=10.45%
  138 kV: 3270 nodes, 4191 edges, m/n=1.282, mean_deg=2.56, intersect=23.72%
"""

from __future__ import annotations

import csv
import itertools
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

from core.topology_generation import TopologyConfig, TopologyGenerator
from .network_io import (
    build_texas7k_substation_nodes_for_topology,
    load_texas7k_network,
    Network,
    NetworkEdge,
)
from .network_stats import compute_network_stats, NetworkStats


REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "Calibration", "outputs")

# ── Texas-7k reference targets ──────────────────────────────────────────
TARGETS: Dict[str, Dict[str, float]] = {
    "345": {
        "mn_ratio": 1.552,
        "mean_degree": 3.10,
        "max_degree": 12,
        "mean_length_km": 38.10,
        "median_length_km": 29.74,
        "intersection_rate": 0.1045,
        "meshedness": 0.2807,
        "deg1_frac": 0.0656,
        "deg3plus_frac": 0.5290,
    },
    "138": {
        "mn_ratio": 1.282,
        "mean_degree": 2.56,
        "max_degree": 10,
        "mean_length_km": 13.10,
        "median_length_km": 9.75,
        "intersection_rate": 0.2372,
        "meshedness": 0.1411,
        "deg1_frac": 0.0765,
        "deg3plus_frac": 0.4076,
    },
}


@dataclass
class ExperimentConfig:
    """One experiment = one parameter combination for one voltage level."""
    name: str
    voltage_kv: int  # generator voltage (345 or 115)
    target_mn_ratio: float
    w_intersect: float
    w_dist: float
    distance_prune_percentile: float
    w_conn_v: float = 300.0
    w_conn_overall: float = 1000.0
    # Experiment 1: Degree-aware scoring
    w_deg1_bonus: float = 0.0
    w_hub_penalty: float = 0.0
    max_preferred_degree: int = 5
    # Experiment 2: Quota overrides
    quota_mst: float = 0.50
    quota_delaunay: float = 0.20
    quota_neighbor_2: float = 0.25
    quota_neighbor_3: float = 0.05
    w_cat: float = 200.0
    # Experiment 3: Distance exponent
    dist_exponent: float = 1.0
    # Experiment 4: Connectivity decay
    conn_decay_factor: float = 1.0  # 1.0 = no decay
    conn_floor_v: float = 300.0
    conn_floor_overall: float = 1000.0
    # Experiment 5: K override
    K_per_iteration: int = 5


def _build_topology_config(exp: ExperimentConfig, disable_dc: bool = False) -> TopologyConfig:
    cfg = TopologyConfig()
    cfg.target_mn_ratio = exp.target_mn_ratio
    cfg.w_intersect = exp.w_intersect
    cfg.w_dist = exp.w_dist
    cfg.distance_prune_percentile = exp.distance_prune_percentile
    cfg.w_conn_v = exp.w_conn_v
    cfg.w_conn_overall = exp.w_conn_overall
    # Keep intersection-rate ceiling high so the generator never self-stops
    cfg.max_intersection_rate = 1.0
    # Disable DC flow scoring when running large networks (huge speedup)
    if disable_dc:
        cfg.w_dc = 0.0
    # Experiment 1: Degree-aware scoring
    cfg.w_deg1_bonus = exp.w_deg1_bonus
    cfg.w_hub_penalty = exp.w_hub_penalty
    cfg.max_preferred_degree = exp.max_preferred_degree
    # Experiment 2: Quota overrides
    cfg.quota_mst = exp.quota_mst
    cfg.quota_delaunay = exp.quota_delaunay
    cfg.quota_neighbor_2 = exp.quota_neighbor_2
    cfg.quota_neighbor_3 = exp.quota_neighbor_3
    cfg.w_cat = exp.w_cat
    # Experiment 3: Distance exponent
    cfg.dist_exponent = exp.dist_exponent
    # Experiment 4: Connectivity decay
    cfg.conn_decay_factor = exp.conn_decay_factor
    cfg.conn_floor_v = exp.conn_floor_v
    cfg.conn_floor_overall = exp.conn_floor_overall
    # Experiment 5: K override
    cfg.K_per_iteration = exp.K_per_iteration
    return cfg


def _network_from_lines(lines, substations) -> Network:
    """Convert TopologyGenerator output to a Network for stats computation."""
    sub_map = {s.sub_id: (s.lat, s.lng) for s in substations}
    nodes: Dict[int, Tuple[float, float]] = {}
    edges: List[NetworkEdge] = []
    for line in lines:
        nodes[line.from_sub] = sub_map[line.from_sub]
        nodes[line.to_sub] = sub_map[line.to_sub]
        edges.append(NetworkEdge(from_id=line.from_sub, to_id=line.to_sub,
                                 length_km=line.length_km))
    return Network(nodes=nodes, edges=edges)


def _score_vs_target(stats: NetworkStats, target_key: str) -> float:
    """Compute a simple normalized-error score vs the Texas-7k target.

    Lower is better.  Each metric contributes |actual-target|/target.
    Shape metrics (meshedness, deg1_frac, deg3plus_frac) weighted 2x.
    """
    t = TARGETS[target_key]
    errors = []
    if t["mn_ratio"] > 0:
        errors.append(abs(stats.mn_ratio - t["mn_ratio"]) / t["mn_ratio"])
    if t["mean_degree"] > 0:
        errors.append(abs(stats.degree_stats.mean_degree - t["mean_degree"]) / t["mean_degree"])
    if t["mean_length_km"] > 0:
        errors.append(abs(stats.length_stats.mean_km - t["mean_length_km"]) / t["mean_length_km"])
    if t["intersection_rate"] > 0:
        errors.append(abs(stats.intersection_rate - t["intersection_rate"]) / t["intersection_rate"])
    # Shape metrics weighted 2x
    if t.get("meshedness", 0) > 0:
        errors.append(2.0 * abs(stats.meshedness - t["meshedness"]) / t["meshedness"])
    if t.get("deg1_frac", 0) > 0:
        errors.append(2.0 * abs(stats.deg1_frac - t["deg1_frac"]) / t["deg1_frac"])
    if t.get("deg3plus_frac", 0) > 0:
        errors.append(2.0 * abs(stats.deg3plus_frac - t["deg3plus_frac"]) / t["deg3plus_frac"])
    return sum(errors) / len(errors) if errors else 999.0


def _save_lines(exp_name: str, voltage_kv: int, lines) -> str:
    sweep_dir = os.path.join(OUTPUT_DIR, "sweep_lines")
    os.makedirs(sweep_dir, exist_ok=True)
    path = os.path.join(sweep_dir, f"{exp_name}_{voltage_kv}kv.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["from_sub", "to_sub", "voltage_kv", "length_km",
                          "category", "circuits", "X_pu", "MVAmax", "intersects"])
        for line in lines:
            writer.writerow([line.from_sub, line.to_sub, line.voltage_kv,
                             line.length_km, line.category, 1,
                             line.X_pu, line.MVAmax, line.intersects])
    return path


# ── Experiment definitions ──────────────────────────────────────────────

def build_experiments(voltage_filter: int | None = None) -> List[ExperimentConfig]:
    """Define the sweep grid.

    Parameters
    ----------
    voltage_filter : int or None
        If set, only return experiments for this voltage (345 or 115).
    """
    experiments: List[ExperimentConfig] = []

    # ── 345 kV experiments (259 nodes → fast) ──
    if voltage_filter is None or voltage_filter == 345:
        # Baseline
        experiments.append(ExperimentConfig(
            name="baseline",
            voltage_kv=345, target_mn_ratio=1.22,
            w_intersect=500, w_dist=1.242, distance_prune_percentile=95.0,
        ))
        # Sweep target_mn_ratio toward Texas-7k's 1.552
        for mn in [1.35, 1.45, 1.55]:
            for w_int in [500, 100, 25, 0]:
                for w_d in [1.242, 0.8]:
                    for prune in [95.0, 98.0]:
                        tag = f"mn{mn}_wint{w_int}_wd{w_d}_pr{prune}"
                        experiments.append(ExperimentConfig(
                            name=tag,
                            voltage_kv=345,
                            target_mn_ratio=mn,
                            w_intersect=w_int,
                            w_dist=w_d,
                            distance_prune_percentile=prune,
                        ))

    # ── 115 kV experiments (3270 nodes → very slow; minimal sweep) ──
    if voltage_filter is None or voltage_filter == 115:
        # Baseline
        experiments.append(ExperimentConfig(
            name="baseline",
            voltage_kv=115, target_mn_ratio=1.22,
            w_intersect=500, w_dist=1.242, distance_prune_percentile=95.0,
        ))
        # Only the most promising configs from 345 kV findings:
        # w_int=25 + w_d=1.242 was the clear winner at 345 kV.
        # Also test w_int=0 (no penalty) to see if natural intersections
        # can reach the 23.7% target.
        for mn in [1.28]:
            for w_int in [25, 0]:
                tag = f"mn{mn}_wint{w_int}_wd1.242"
                experiments.append(ExperimentConfig(
                    name=tag,
                    voltage_kv=115,
                    target_mn_ratio=mn,
                    w_intersect=w_int,
                    w_dist=1.242,
                    distance_prune_percentile=95.0,
                ))

    return experiments


def main() -> None:
    import sys

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Accept optional voltage filter from CLI: python -m Calibration.parameter_sweep [345|115]
    voltage_filter = None
    if len(sys.argv) > 1:
        voltage_filter = int(sys.argv[1])
        print(f"Filtering to {voltage_filter} kV experiments only.")

    print("Loading Texas-7k substations for topology generator...")
    substations = build_texas7k_substation_nodes_for_topology()

    experiments = build_experiments(voltage_filter=voltage_filter)

    # Group by voltage for efficient substation filtering
    by_voltage: Dict[int, List[ExperimentConfig]] = {}
    for exp in experiments:
        by_voltage.setdefault(exp.voltage_kv, []).append(exp)

    results_rows: List[dict] = []
    total = len(experiments)
    done = 0

    for voltage_kv, exps in sorted(by_voltage.items()):
        target_key = "345" if voltage_kv == 345 else "138"
        # Disable DC flow for 115 kV to avoid O(n^3) matrix solves
        disable_dc = (voltage_kv == 115)
        print(f"\n{'='*70}")
        print(f"Voltage: {voltage_kv} kV  ({len(exps)} experiments)"
              f"{'  [DC flow DISABLED for speed]' if disable_dc else ''}")
        print(f"{'='*70}")

        for exp in exps:
            done += 1
            print(f"\n[{done}/{total}] {exp.name} @ {voltage_kv} kV")
            print(f"  mn={exp.target_mn_ratio}, w_int={exp.w_intersect}, "
                  f"w_d={exp.w_dist}, prune={exp.distance_prune_percentile}")

            cfg = _build_topology_config(exp, disable_dc=disable_dc)
            t0 = time.time()

            gen = TopologyGenerator(
                substations=substations,
                voltage_kv=voltage_kv,
                config=cfg,
                verbose=False,
            )
            lines = gen.run()
            elapsed = time.time() - t0

            net = _network_from_lines(lines, substations)
            stats = compute_network_stats(net)
            score = _score_vs_target(stats, target_key)

            # Save lines for best-scoring runs
            _save_lines(exp.name, voltage_kv, lines)

            row = {
                "experiment": exp.name,
                "voltage_kv": voltage_kv,
                "target_mn_ratio": exp.target_mn_ratio,
                "w_intersect": exp.w_intersect,
                "w_dist": exp.w_dist,
                "distance_prune_pct": exp.distance_prune_percentile,
                "nodes": stats.num_nodes,
                "edges": stats.num_edges,
                "mn_ratio": round(stats.mn_ratio, 4),
                "mean_degree": round(stats.degree_stats.mean_degree, 2),
                "max_degree": stats.degree_stats.max_degree,
                "mean_length_km": round(stats.length_stats.mean_km, 2),
                "median_length_km": round(stats.length_stats.median_km, 2),
                "max_length_km": round(stats.length_stats.max_km, 2),
                "intersection_rate_pct": round(stats.intersection_rate * 100, 2),
                "meshedness": round(stats.meshedness, 4),
                "deg1_frac": round(stats.deg1_frac, 4),
                "deg2_frac": round(stats.deg2_frac, 4),
                "deg3plus_frac": round(stats.deg3plus_frac, 4),
                "degree_entropy": round(stats.degree_entropy, 4),
                "error_score": round(score, 4),
                "elapsed_s": round(elapsed, 1),
            }
            results_rows.append(row)

            print(f"  → m/n={stats.mn_ratio:.3f}, mean_deg={stats.degree_stats.mean_degree:.2f}, "
                  f"intersect={stats.intersection_rate*100:.1f}%, "
                  f"mean_len={stats.length_stats.mean_km:.1f}km, "
                  f"mesh={stats.meshedness:.3f}, d1={stats.deg1_frac:.3f}, d3+={stats.deg3plus_frac:.3f}, "
                  f"error={score:.3f}, {elapsed:.0f}s")

    # Write master results CSV
    csv_path = os.path.join(OUTPUT_DIR, "sweep_results.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results_rows[0].keys())
        writer.writeheader()
        writer.writerows(results_rows)

    print(f"\n{'='*70}")
    print(f"Sweep complete. {len(results_rows)} experiments saved to {csv_path}")
    print(f"{'='*70}")

    # Print top-5 per voltage
    for vkv in [345, 115]:
        vrows = [r for r in results_rows if r["voltage_kv"] == vkv]
        vrows.sort(key=lambda r: r["error_score"])
        target_key = "345" if vkv == 345 else "138"
        t = TARGETS[target_key]
        print(f"\nTop 5 for {vkv} kV (target: m/n={t['mn_ratio']}, "
              f"mean_deg={t['mean_degree']}, intersect={t['intersection_rate']*100:.1f}%):")
        for i, r in enumerate(vrows[:5], 1):
            print(f"  {i}. {r['experiment']:40s}  m/n={r['mn_ratio']:.3f}  "
                  f"deg={r['mean_degree']:.2f}  int={r['intersection_rate_pct']:.1f}%  "
                  f"len={r['mean_length_km']:.1f}km  err={r['error_score']:.3f}")


if __name__ == "__main__":
    main()
