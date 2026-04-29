"""Compare Texas-7k network structure against Dartboard-generated topology on 7k buses.

Computes side-by-side metrics for:
  - Texas-7k reference (345 kV and 138 kV subsets)
  - Dartboard topology generated on Texas-7k buses (345 kV and 115≈138 kV)
  - Dartboard original Texas (1.3k-node Stage 3 output)

Prints metrics and writes a CSV summary to Calibration/outputs/.
"""

from __future__ import annotations

import csv
import os
from collections import Counter

from .network_io import (
    load_texas7k_network,
    load_dartboard_texas_network,
    load_calibration_network,
)
from .network_stats import compute_network_stats, NetworkStats


REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "Calibration", "outputs")


def _print_stats(label: str, stats: NetworkStats) -> None:
    print(f"\n=== {label} ===")
    print(f"Nodes: {stats.num_nodes}")
    print(f"Edges: {stats.num_edges}")
    print(f"m/n ratio: {stats.mn_ratio:.3f}")
    print(f"Mean degree: {stats.degree_stats.mean_degree:.2f}")
    print(f"Max degree: {stats.degree_stats.max_degree}")

    # Degree histogram (compact)
    deg_vals = list(stats.degree_stats.degree_counts.values())
    deg_hist = Counter(deg_vals)
    hist_str = ", ".join(f"d={d}: {c}" for d, c in sorted(deg_hist.items()))
    print(f"Degree histogram: {hist_str}")

    print(
        f"Line length (km): mean={stats.length_stats.mean_km:.2f}, "
        f"median={stats.length_stats.median_km:.2f}, max={stats.length_stats.max_km:.2f}"
    )
    print(f"Intersection rate: {stats.intersection_rate * 100:.2f}%")


def _stats_row(label: str, stats: NetworkStats) -> dict:
    return {
        "network": label,
        "nodes": stats.num_nodes,
        "edges": stats.num_edges,
        "mn_ratio": round(stats.mn_ratio, 4),
        "mean_degree": round(stats.degree_stats.mean_degree, 2),
        "max_degree": stats.degree_stats.max_degree,
        "mean_length_km": round(stats.length_stats.mean_km, 2),
        "median_length_km": round(stats.length_stats.median_km, 2),
        "max_length_km": round(stats.length_stats.max_km, 2),
        "intersection_rate_pct": round(stats.intersection_rate * 100, 2),
    }


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rows = []

    # --- Texas-7k reference ---
    print("Loading Texas-7k reference networks...")
    texas7k_all = load_texas7k_network(voltage_filter=None)
    texas7k_all_stats = compute_network_stats(texas7k_all)
    _print_stats("Texas-7k ALL transmission lines", texas7k_all_stats)
    rows.append(_stats_row("Texas-7k ALL lines", texas7k_all_stats))

    texas7k_345 = load_texas7k_network(voltage_filter=[345.0])
    texas7k_345_stats = compute_network_stats(texas7k_345)
    _print_stats("Texas-7k 345 kV", texas7k_345_stats)
    rows.append(_stats_row("Texas-7k 345 kV", texas7k_345_stats))

    texas7k_138 = load_texas7k_network(voltage_filter=[138.0])
    texas7k_138_stats = compute_network_stats(texas7k_138)
    _print_stats("Texas-7k 138 kV", texas7k_138_stats)
    rows.append(_stats_row("Texas-7k 138 kV", texas7k_138_stats))

    # --- Dartboard on Texas-7k buses (calibration run) ---
    print("\nLoading Dartboard-on-Texas-7k calibration networks...")
    cal_345 = load_calibration_network(voltage_kv=345)
    cal_345_stats = compute_network_stats(cal_345)
    _print_stats("Dartboard-on-7k 345 kV", cal_345_stats)
    rows.append(_stats_row("Dartboard-on-7k 345 kV", cal_345_stats))

    cal_115 = load_calibration_network(voltage_kv=115)
    cal_115_stats = compute_network_stats(cal_115)
    _print_stats("Dartboard-on-7k 138≈115 kV", cal_115_stats)
    rows.append(_stats_row("Dartboard-on-7k 138≈115 kV", cal_115_stats))

    # --- Dartboard original (small-scale Stage 3) ---
    print("\nLoading Dartboard original Texas networks...")
    dart_345 = load_dartboard_texas_network(voltage_kv=345)
    dart_345_stats = compute_network_stats(dart_345)
    _print_stats("Dartboard-orig 345 kV (197 nodes)", dart_345_stats)
    rows.append(_stats_row("Dartboard-orig 345 kV", dart_345_stats))

    dart_115 = load_dartboard_texas_network(voltage_kv=115)
    dart_115_stats = compute_network_stats(dart_115)
    _print_stats("Dartboard-orig 115 kV (1312 nodes)", dart_115_stats)
    rows.append(_stats_row("Dartboard-orig 115 kV", dart_115_stats))

    # --- Write CSV summary ---
    csv_path = os.path.join(OUTPUT_DIR, "comparison_summary.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved comparison CSV: {csv_path}")


if __name__ == "__main__":
    main()
