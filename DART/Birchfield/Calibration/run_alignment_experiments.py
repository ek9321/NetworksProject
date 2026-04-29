"""Run all alignment experiments from SaturdaysAlignmentPlan.md.

Executes experiments 0-5 sequentially at 345 kV, picking the best config
from each experiment as the base for the next. Final winner runs at 138 kV.

Usage:
    python -m Calibration.run_alignment_experiments
"""

from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from core.topology_generation import TopologyConfig, TopologyGenerator
from .network_io import build_texas7k_substation_nodes_for_topology, Network, NetworkEdge
from .network_stats import compute_network_stats, NetworkStats

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "Calibration", "outputs", "alignment")

# Texas-7k reference targets (with shape metrics)
TARGETS_345 = {
    "mn_ratio": 1.552,
    "mean_degree": 3.10,
    "mean_length_km": 38.10,
    "intersection_rate": 0.1045,
    "meshedness": 0.2807,
    "deg1_frac": 0.0656,
    "deg3plus_frac": 0.5290,
}

TARGETS_138 = {
    "mn_ratio": 1.282,
    "mean_degree": 2.56,
    "mean_length_km": 13.10,
    "intersection_rate": 0.2372,
    "meshedness": 0.1411,
    "deg1_frac": 0.0765,
    "deg3plus_frac": 0.4076,
}


def score_vs_target(stats: NetworkStats, targets: dict) -> float:
    """Normalized error score. Lower is better. Shape metrics weighted 2x."""
    t = targets
    errors = []
    if t["mn_ratio"] > 0:
        errors.append(abs(stats.mn_ratio - t["mn_ratio"]) / t["mn_ratio"])
    if t["mean_degree"] > 0:
        errors.append(abs(stats.degree_stats.mean_degree - t["mean_degree"]) / t["mean_degree"])
    if t["mean_length_km"] > 0:
        errors.append(abs(stats.length_stats.mean_km - t["mean_length_km"]) / t["mean_length_km"])
    if t["intersection_rate"] > 0:
        errors.append(abs(stats.intersection_rate - t["intersection_rate"]) / t["intersection_rate"])
    if t.get("meshedness", 0) > 0:
        errors.append(2.0 * abs(stats.meshedness - t["meshedness"]) / t["meshedness"])
    if t.get("deg1_frac", 0) > 0:
        errors.append(2.0 * abs(stats.deg1_frac - t["deg1_frac"]) / t["deg1_frac"])
    if t.get("deg3plus_frac", 0) > 0:
        errors.append(2.0 * abs(stats.deg3plus_frac - t["deg3plus_frac"]) / t["deg3plus_frac"])
    return sum(errors) / len(errors) if errors else 999.0


def network_from_lines(lines, substations) -> Network:
    sub_map = {s.sub_id: (s.lat, s.lng) for s in substations}
    nodes: Dict[int, Tuple[float, float]] = {}
    edges: List[NetworkEdge] = []
    for line in lines:
        nodes[line.from_sub] = sub_map[line.from_sub]
        nodes[line.to_sub] = sub_map[line.to_sub]
        edges.append(NetworkEdge(from_id=line.from_sub, to_id=line.to_sub,
                                 length_km=line.length_km))
    return Network(nodes=nodes, edges=edges)


def run_one(name: str, substations, voltage_kv: int, cfg: TopologyConfig,
            targets: dict) -> Tuple[dict, float]:
    """Run one topology generation and return (row_dict, error_score)."""
    t0 = time.time()
    gen = TopologyGenerator(substations=substations, voltage_kv=voltage_kv,
                            config=cfg, verbose=False)
    lines = gen.run()
    elapsed = time.time() - t0

    net = network_from_lines(lines, substations)
    stats = compute_network_stats(net)
    score = score_vs_target(stats, targets)

    row = {
        "experiment": name,
        "voltage_kv": voltage_kv,
        "nodes": stats.num_nodes,
        "edges": stats.num_edges,
        "mn_ratio": round(stats.mn_ratio, 4),
        "mean_degree": round(stats.degree_stats.mean_degree, 2),
        "max_degree": stats.degree_stats.max_degree,
        "mean_length_km": round(stats.length_stats.mean_km, 2),
        "median_length_km": round(stats.length_stats.median_km, 2),
        "intersection_rate_pct": round(stats.intersection_rate * 100, 2),
        "meshedness": round(stats.meshedness, 4),
        "deg1_frac": round(stats.deg1_frac, 4),
        "deg2_frac": round(stats.deg2_frac, 4),
        "deg3plus_frac": round(stats.deg3plus_frac, 4),
        "degree_entropy": round(stats.degree_entropy, 4),
        "error_score": round(score, 4),
        "elapsed_s": round(elapsed, 1),
    }

    print(f"  {name:50s} m/n={stats.mn_ratio:.3f} deg={stats.degree_stats.mean_degree:.2f} "
          f"mesh={stats.meshedness:.3f} d1={stats.deg1_frac:.3f} d3+={stats.deg3plus_frac:.3f} "
          f"len={stats.length_stats.mean_km:.1f}km int={stats.intersection_rate*100:.1f}% "
          f"err={score:.3f} {elapsed:.0f}s")

    return row, score


def make_config(base: Optional[dict] = None, **overrides) -> TopologyConfig:
    """Build TopologyConfig from base dict + overrides (overrides win)."""
    cfg = TopologyConfig()
    cfg.max_intersection_rate = 1.0  # never self-stop
    merged = dict(base or {})
    merged.update(overrides)
    for k, v in merged.items():
        setattr(cfg, k, v)
    return cfg


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_rows: List[dict] = []

    print("Loading Texas-7k substations...")
    substations = build_texas7k_substation_nodes_for_topology()

    # ═══════════════════════════════════════════════════════════════
    # Experiment 0: Baseline with extended metrics
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("EXPERIMENT 0: Baseline measurement with extended metrics")
    print(f"{'='*70}")

    base_cfg = make_config(base=None, target_mn_ratio=1.55, w_intersect=25, w_dist=1.242,
                           distance_prune_percentile=95.0)
    row, baseline_score = run_one("exp0_baseline", substations, 345, base_cfg, TARGETS_345)
    all_rows.append(row)
    baseline_row = row
    print(f"\n  Baseline error: {baseline_score:.4f}")

    # Best config state (accumulated across experiments)
    best = dict(target_mn_ratio=1.55, w_intersect=25, w_dist=1.242,
                distance_prune_percentile=95.0)

    # ═══════════════════════════════════════════════════════════════
    # Experiment 1: Degree-aware scoring
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("EXPERIMENT 1: Degree-aware scoring (27 configs)")
    print(f"{'='*70}")

    exp1_best_score = baseline_score
    exp1_best_name = "exp0_baseline"
    exp1_best_params = {}

    for w_deg1 in [50, 100, 200]:
        for w_hub in [50, 100, 200]:
            for max_deg in [4, 5, 6]:
                name = f"exp1_d1b{w_deg1}_hub{w_hub}_md{max_deg}"
                cfg = make_config(base=best, w_deg1_bonus=w_deg1, w_hub_penalty=w_hub,
                                  max_preferred_degree=max_deg)
                row, score = run_one(name, substations, 345, cfg, TARGETS_345)
                all_rows.append(row)
                if score < exp1_best_score:
                    exp1_best_score = score
                    exp1_best_name = name
                    exp1_best_params = dict(w_deg1_bonus=w_deg1, w_hub_penalty=w_hub,
                                            max_preferred_degree=max_deg)

    print(f"\n  Exp1 best: {exp1_best_name} (error={exp1_best_score:.4f})")
    best.update(exp1_best_params)

    # ═══════════════════════════════════════════════════════════════
    # Experiment 2: Quota rebalancing
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("EXPERIMENT 2: Quota rebalancing (5 configs)")
    print(f"{'='*70}")

    quota_configs = [
        ("shift1", dict(quota_mst=0.35, quota_delaunay=0.30, quota_neighbor_2=0.30, quota_neighbor_3=0.05)),
        ("shift2", dict(quota_mst=0.25, quota_delaunay=0.35, quota_neighbor_2=0.30, quota_neighbor_3=0.10)),
        ("shift3", dict(quota_mst=0.20, quota_delaunay=0.40, quota_neighbor_2=0.30, quota_neighbor_3=0.10)),
        ("no_cat", dict(w_cat=0.0)),
        ("baseline_q", dict()),  # keep original quotas with exp1 best degree params
    ]

    exp2_best_score = exp1_best_score
    exp2_best_name = exp1_best_name
    exp2_best_params = {}

    for tag, overrides in quota_configs:
        name = f"exp2_{tag}"
        cfg = make_config(base=best, **overrides)
        row, score = run_one(name, substations, 345, cfg, TARGETS_345)
        all_rows.append(row)
        if score < exp2_best_score:
            exp2_best_score = score
            exp2_best_name = name
            exp2_best_params = overrides

    print(f"\n  Exp2 best: {exp2_best_name} (error={exp2_best_score:.4f})")
    best.update(exp2_best_params)

    # ═══════════════════════════════════════════════════════════════
    # Experiment 3: Distance weight tuning
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("EXPERIMENT 3: Distance weight tuning")
    print(f"{'='*70}")

    exp3_best_score = exp2_best_score
    exp3_best_name = exp2_best_name
    exp3_best_params = {}

    # Approach A: just reduce w_dist
    for w_d in [0.4, 0.6, 0.8, 1.0, 1.242]:
        name = f"exp3a_wd{w_d}"
        cfg = make_config(base=best, w_dist=w_d)
        row, score = run_one(name, substations, 345, cfg, TARGETS_345)
        all_rows.append(row)
        if score < exp3_best_score:
            exp3_best_score = score
            exp3_best_name = name
            exp3_best_params = dict(w_dist=w_d)

    # Approach B: sublinear exponent (only with the best w_dist from A, plus 1.242)
    best_wd = exp3_best_params.get("w_dist", best.get("w_dist", 1.242))
    for exp_val in [0.5, 0.7]:
        for w_d in [best_wd, 1.242]:
            name = f"exp3b_wd{w_d}_exp{exp_val}"
            cfg = make_config(base=best, w_dist=w_d, dist_exponent=exp_val)
            row, score = run_one(name, substations, 345, cfg, TARGETS_345)
            all_rows.append(row)
            if score < exp3_best_score:
                exp3_best_score = score
                exp3_best_name = name
                exp3_best_params = dict(w_dist=w_d, dist_exponent=exp_val)

    print(f"\n  Exp3 best: {exp3_best_name} (error={exp3_best_score:.4f})")
    best.update(exp3_best_params)

    # ═══════════════════════════════════════════════════════════════
    # Experiment 4: Connectivity bonus decay
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("EXPERIMENT 4: Connectivity bonus decay (9 configs)")
    print(f"{'='*70}")

    exp4_best_score = exp3_best_score
    exp4_best_name = exp3_best_name
    exp4_best_params = {}

    for decay in [0.3, 0.5, 0.7]:
        for floor_v, floor_o in [(0, 0), (25, 50), (50, 100)]:
            name = f"exp4_decay{decay}_fv{floor_v}_fo{floor_o}"
            cfg = make_config(base=best, conn_decay_factor=decay,
                              conn_floor_v=float(floor_v),
                              conn_floor_overall=float(floor_o))
            row, score = run_one(name, substations, 345, cfg, TARGETS_345)
            all_rows.append(row)
            if score < exp4_best_score:
                exp4_best_score = score
                exp4_best_name = name
                exp4_best_params = dict(conn_decay_factor=decay,
                                        conn_floor_v=float(floor_v),
                                        conn_floor_overall=float(floor_o))

    print(f"\n  Exp4 best: {exp4_best_name} (error={exp4_best_score:.4f})")
    best.update(exp4_best_params)

    # ═══════════════════════════════════════════════════════════════
    # Experiment 5: Distance prune + K tuning
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("EXPERIMENT 5: Distance prune + K tuning (16 configs)")
    print(f"{'='*70}")

    exp5_best_score = exp4_best_score
    exp5_best_name = exp4_best_name
    exp5_best_params = {}

    for prune in [90, 95, 98, 100]:
        for K in [1, 3, 5, 10]:
            name = f"exp5_pr{prune}_K{K}"
            cfg = make_config(base=best, distance_prune_percentile=float(prune),
                              K_per_iteration=K)
            row, score = run_one(name, substations, 345, cfg, TARGETS_345)
            all_rows.append(row)
            if score < exp5_best_score:
                exp5_best_score = score
                exp5_best_name = name
                exp5_best_params = dict(distance_prune_percentile=float(prune),
                                        K_per_iteration=K)

    print(f"\n  Exp5 best: {exp5_best_name} (error={exp5_best_score:.4f})")
    best.update(exp5_best_params)

    # ═══════════════════════════════════════════════════════════════
    # Final: Run winner at 138 kV
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("FINAL: Best config at 138 kV")
    print(f"{'='*70}")
    print(f"  Best 345 kV config: {best}")

    final_cfg = make_config(base=best)
    final_cfg.w_dc = 0.0  # disable DC for 138 kV speed
    row, final_score = run_one("final_138kv", substations, 115, final_cfg, TARGETS_138)
    all_rows.append(row)

    # ═══════════════════════════════════════════════════════════════
    # Save results
    # ═══════════════════════════════════════════════════════════════
    csv_path = os.path.join(OUTPUT_DIR, "alignment_results.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n{'='*70}")
    print(f"All experiments complete. {len(all_rows)} rows saved to {csv_path}")
    print(f"{'='*70}")

    # Summary
    print(f"\nBaseline error (345 kV): {baseline_score:.4f}")
    print(f"Final best error (345 kV): {exp5_best_score:.4f}")
    print(f"Improvement: {(1 - exp5_best_score/baseline_score)*100:.1f}%")
    print(f"\nFinal config: {best}")
    print(f"\n138 kV error: {final_score:.4f}")

    # Gap table for best 345 kV
    print(f"\n{'='*70}")
    print("Gap table: Best 345 kV config vs Texas-7k reference")
    print(f"{'='*70}")
    best_345_rows = [r for r in all_rows if r["experiment"] == exp5_best_name]
    if not best_345_rows:
        # If exp5 didn't improve, use whatever the overall best was
        best_345_rows = sorted([r for r in all_rows if r["voltage_kv"] == 345],
                               key=lambda r: r["error_score"])
    if best_345_rows:
        b = best_345_rows[0]
        for metric, target_val in TARGETS_345.items():
            if metric == "intersection_rate":
                actual = b["intersection_rate_pct"] / 100
            elif metric == "mean_length_km":
                actual = b["mean_length_km"]
            elif metric == "mean_degree":
                actual = b["mean_degree"]
            else:
                actual = b.get(metric, 0)
            gap_pct = (actual - target_val) / target_val * 100 if target_val else 0
            print(f"  {metric:20s}  target={target_val:.4f}  actual={actual:.4f}  gap={gap_pct:+.1f}%")


if __name__ == "__main__":
    main()
