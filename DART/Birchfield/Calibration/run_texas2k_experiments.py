"""Run hypothesis experiments on Texas2k_series2025 substations.

Tests Hypotheses 2 (radial threshold) and 4 (biconnectivity bonus)
from Calibration/plans/hypotheses.md against Birchfield's own 2000-bus case.

Experiments:
  1. Baseline (default Birchfield params)
  2. Radial fix: degree threshold 0 → 1
  3. Biconnectivity fix: w_conn_overall on articulation points
  4. Combined (2 + 3)
  5. Combined + DC flow at 115 kV
  6. Combined + DC + K=1 at 115 kV

Usage:
    python -m Calibration.run_texas2k_experiments
    python -m Calibration.run_texas2k_experiments --exp 1      # run specific experiment
    python -m Calibration.run_texas2k_experiments --only-500kv  # skip 115 kV runs
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from core.topology_generation import TopologyConfig, TopologyGenerator
from .texas2k_io import load_texas2k_substations, load_texas2k_reference_network
from .network_io import Network, NetworkEdge
from .network_stats import compute_network_stats, NetworkStats

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "Calibration", "outputs", "texas2k_hypotheses")


# ── Reference targets ────────────────────────────────────────────────────

TARGETS = {
    "500kv": {
        "mn_ratio": 1.544,
        "deg1_frac": 0.132,
        "deg3plus_frac": 0.582,
        "meshedness": 0.279,
        "mean_length_km": 55.7,
        "median_length_km": 42.0,
    },
    "115kv": {
        "mn_ratio": 1.657,
        "deg1_frac": 0.066,
        "deg3plus_frac": 0.644,
        "meshedness": 0.329,
        "mean_length_km": 17.1,
        "median_length_km": 13.2,
    },
}


# ── Experiment definitions ───────────────────────────────────────────────

@dataclass
class ExperimentDef:
    name: str
    description: str
    radial_degree_threshold: int = 0
    use_biconnectivity_bonus: bool = False
    w_dc_500kv: float = 0.5
    w_dc_115kv: float = 0.5
    K_per_iteration_500kv: int = 5
    K_per_iteration_115kv: int = 5
    skip_115kv: bool = False


EXPERIMENTS = [
    ExperimentDef(
        name="1_baseline",
        description="Default Birchfield params, DC enabled",
    ),
    ExperimentDef(
        name="2_radial_fix",
        description="Hypothesis 2: radial threshold = 1 (degree <= 1 gets bonus)",
        radial_degree_threshold=1,
    ),
    ExperimentDef(
        name="3_biconn_fix",
        description="Hypothesis 4: w_conn_overall on articulation points only",
        use_biconnectivity_bonus=True,
    ),
    ExperimentDef(
        name="4_combined",
        description="Hypotheses 2+4: radial fix + biconnectivity fix",
        radial_degree_threshold=1,
        use_biconnectivity_bonus=True,
    ),
    ExperimentDef(
        name="5_combined_dc115",
        description="Combined + DC flow enabled at 115 kV, K=5",
        radial_degree_threshold=1,
        use_biconnectivity_bonus=True,
        w_dc_115kv=0.5,
        K_per_iteration_115kv=5,
    ),
    ExperimentDef(
        name="6_combined_dc115_k1",
        description="Combined + DC flow at 115 kV + K=1",
        radial_degree_threshold=1,
        use_biconnectivity_bonus=True,
        w_dc_115kv=0.5,
        K_per_iteration_115kv=1,
    ),
]


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_config(exp: ExperimentDef, voltage_class: str) -> TopologyConfig:
    """Build TopologyConfig for an experiment and voltage class."""
    cfg = TopologyConfig()

    if voltage_class == "500kv":
        cfg.target_mn_ratio = TARGETS["500kv"]["mn_ratio"]
        cfg.w_dc = exp.w_dc_500kv
        cfg.K_per_iteration = exp.K_per_iteration_500kv
    else:  # 115kv
        cfg.target_mn_ratio = TARGETS["115kv"]["mn_ratio"]
        cfg.w_dc = exp.w_dc_115kv
        cfg.K_per_iteration = exp.K_per_iteration_115kv

    cfg.radial_degree_threshold = exp.radial_degree_threshold
    cfg.use_biconnectivity_bonus = exp.use_biconnectivity_bonus

    # Relax intersection constraint (Texas2k has higher intersection rates)
    cfg.max_intersection_rate = 1.0

    return cfg


def _network_from_lines(lines, substations) -> Network:
    sub_map = {s.sub_id: (s.lat, s.lng) for s in substations}
    nodes: Dict[int, tuple] = {}
    edges: List[NetworkEdge] = []
    for line in lines:
        nodes[line.from_sub] = sub_map[line.from_sub]
        nodes[line.to_sub] = sub_map[line.to_sub]
        edges.append(NetworkEdge(from_id=line.from_sub, to_id=line.to_sub,
                                 length_km=line.length_km))
    return Network(nodes=nodes, edges=edges)


def _compute_error(stats: NetworkStats, targets: dict) -> float:
    """Weighted relative error vs targets. Shape metrics weighted 2x."""
    shape_metrics = {"deg1_frac", "deg3plus_frac"}
    total = 0.0
    count = 0
    for key, target_val in targets.items():
        if target_val == 0:
            continue
        if key == "mn_ratio":
            gen_val = stats.mn_ratio
        elif key == "deg1_frac":
            gen_val = stats.deg1_frac
        elif key == "deg3plus_frac":
            gen_val = stats.deg3plus_frac
        elif key == "meshedness":
            gen_val = stats.meshedness
        elif key == "mean_length_km":
            gen_val = stats.length_stats.mean_km
        elif key == "median_length_km":
            gen_val = stats.length_stats.median_km
        else:
            continue
        rel_err = abs(gen_val - target_val) / target_val
        weight = 2.0 if key in shape_metrics else 1.0
        total += weight * rel_err
        count += weight
    return total / count if count else 0.0


def _stats_to_dict(stats: NetworkStats, error: float) -> dict:
    return {
        "num_nodes": stats.num_nodes,
        "num_edges": stats.num_edges,
        "mn_ratio": round(stats.mn_ratio, 4),
        "mean_degree": round(stats.degree_stats.mean_degree, 3),
        "meshedness": round(stats.meshedness, 4),
        "deg1_frac": round(stats.deg1_frac, 4),
        "deg2_frac": round(stats.deg2_frac, 4),
        "deg3plus_frac": round(stats.deg3plus_frac, 4),
        "mean_length_km": round(stats.length_stats.mean_km, 2),
        "median_length_km": round(stats.length_stats.median_km, 2),
        "intersection_rate": round(stats.intersection_rate, 4),
        "composite_error": round(error, 4),
    }


# ── Run one experiment ───────────────────────────────────────────────────

def run_experiment(exp: ExperimentDef, substations, voltage_class: str,
                   verbose: bool = False) -> dict:
    """Run one experiment, return stats dict."""
    cfg = _make_config(exp, voltage_class)
    voltage_kv = 345 if voltage_class == "500kv" else 115

    t0 = time.time()
    gen = TopologyGenerator(substations=substations, voltage_kv=voltage_kv,
                            config=cfg, verbose=verbose)
    lines = gen.run()
    elapsed = time.time() - t0

    net = _network_from_lines(lines, substations)
    stats = compute_network_stats(net)
    error = _compute_error(stats, TARGETS[voltage_class])

    result = _stats_to_dict(stats, error)
    result["experiment"] = exp.name
    result["voltage_class"] = voltage_class
    result["elapsed_sec"] = round(elapsed, 1)
    result["description"] = exp.description
    return result


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run Texas2k hypothesis experiments")
    parser.add_argument("--exp", type=int, help="Run only this experiment number (1-6)")
    parser.add_argument("--only-500kv", action="store_true",
                        help="Only run 500 kV experiments (skip 115 kV)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Loading Texas2k substations...")
    substations = load_texas2k_substations(hv_class="500kv")
    hv_count = sum(1 for s in substations if s.has_345kv)
    lv_count = sum(1 for s in substations if s.has_115kv)
    print(f"  HV (500 kV): {hv_count} substations")
    print(f"  LV (115 kV): {lv_count} substations")

    # Determine which experiments to run
    if args.exp:
        exps = [EXPERIMENTS[args.exp - 1]]
    else:
        exps = EXPERIMENTS

    all_results: List[dict] = []

    for exp in exps:
        print(f"\n{'='*60}")
        print(f"Experiment: {exp.name}")
        print(f"  {exp.description}")
        print(f"{'='*60}")

        # 500 kV
        print(f"\n  Running 500 kV...")
        result = run_experiment(exp, substations, "500kv", verbose=args.verbose)
        all_results.append(result)
        _print_result(result)

        # Save per-experiment JSON
        json_path = os.path.join(OUTPUT_DIR, f"{exp.name}_500kv_stats.json")
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2)

        # 115 kV
        if not args.only_500kv and not exp.skip_115kv:
            print(f"\n  Running 115 kV...")
            result = run_experiment(exp, substations, "115kv", verbose=args.verbose)
            all_results.append(result)
            _print_result(result)

            json_path = os.path.join(OUTPUT_DIR, f"{exp.name}_115kv_stats.json")
            with open(json_path, "w") as f:
                json.dump(result, f, indent=2)

    # Write summary CSV
    if all_results:
        csv_path = os.path.join(OUTPUT_DIR, "summary_table.csv")
        fields = list(all_results[0].keys())
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(all_results)
        print(f"\nSummary saved to {csv_path}")

    # Print comparison table
    _print_summary_table(all_results)


def _print_result(result: dict):
    """Print one result line."""
    print(f"    m/n={result['mn_ratio']:.3f}  deg1={result['deg1_frac']:.3f}  "
          f"deg3+={result['deg3plus_frac']:.3f}  mesh={result['meshedness']:.3f}  "
          f"<len>={result['mean_length_km']:.1f}km  "
          f"error={result['composite_error']:.4f}  ({result['elapsed_sec']:.0f}s)")


def _print_summary_table(results: List[dict]):
    """Print formatted summary comparing all experiments."""
    if not results:
        return

    print(f"\n{'='*90}")
    print("SUMMARY: Texas2k Hypothesis Experiments")
    print(f"{'='*90}")

    # Group by voltage
    for vc in ["500kv", "115kv"]:
        vc_results = [r for r in results if r["voltage_class"] == vc]
        if not vc_results:
            continue

        targets = TARGETS[vc]
        print(f"\n{vc.upper()} (targets: m/n={targets['mn_ratio']:.3f} "
              f"deg1={targets['deg1_frac']:.3f} deg3+={targets['deg3plus_frac']:.3f} "
              f"mesh={targets['meshedness']:.3f} <len>={targets['mean_length_km']:.1f}km)")
        print(f"  {'Experiment':<25s} {'m/n':>6s} {'deg1%':>6s} {'deg3+%':>6s} "
              f"{'mesh':>6s} {'<len>':>6s} {'error':>7s} {'time':>5s}")
        print(f"  {'-'*25} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*5}")

        for r in vc_results:
            print(f"  {r['experiment']:<25s} {r['mn_ratio']:6.3f} "
                  f"{r['deg1_frac']*100:5.1f}% {r['deg3plus_frac']*100:5.1f}% "
                  f"{r['meshedness']:6.3f} {r['mean_length_km']:5.1f}k "
                  f"{r['composite_error']:7.4f} {r['elapsed_sec']:4.0f}s")


if __name__ == "__main__":
    main()
