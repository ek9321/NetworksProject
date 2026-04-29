"""Visualize best alignment experiment result vs Texas-7k reference.

Produces under Calibration/outputs/alignment/:
  - best_vs_ref_345kv.png   (2-panel map: Texas-7k left, best Dartboard right)
  - best_vs_ref_138kv.png   (same for 138/115 kV)
  - degree_dist_345kv.png   (overlaid degree distribution histograms)
  - degree_dist_138kv.png
  - length_dist_345kv.png   (overlaid line length histograms)
  - length_dist_138kv.png

Regenerates topologies using the best configs from the alignment sweep.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.topology_generation import TopologyConfig, TopologyGenerator, SubstationNode
from .network_io import (
    load_texas7k_network,
    build_texas7k_substation_nodes_for_topology,
    Network,
    NetworkEdge,
)
from .network_stats import (
    compute_network_stats,
    compute_degree_distribution,
    NetworkStats,
)

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "Calibration", "outputs", "alignment")


# ── Best configs from alignment sweep ────────────────────────────────────

def _make_best_345_config() -> TopologyConfig:
    cfg = TopologyConfig()
    cfg.target_mn_ratio = 1.55
    cfg.w_intersect = 25
    cfg.w_dist = 0.6
    cfg.distance_prune_percentile = 95.0
    cfg.max_intersection_rate = 1.0
    return cfg


def _make_best_138_config() -> TopologyConfig:
    cfg = TopologyConfig()
    cfg.target_mn_ratio = 1.28
    cfg.w_intersect = 25
    cfg.w_dist = 0.6
    cfg.distance_prune_percentile = 95.0
    cfg.max_intersection_rate = 1.0
    cfg.w_dc = 0.0  # disable DC for 138 kV speed
    return cfg


# ── Helpers ──────────────────────────────────────────────────────────────

def _network_from_lines(lines, substations) -> Network:
    sub_map = {s.sub_id: (s.lat, s.lng) for s in substations}
    nodes: Dict[int, Tuple[float, float]] = {}
    edges: List[NetworkEdge] = []
    for line in lines:
        nodes[line.from_sub] = sub_map[line.from_sub]
        nodes[line.to_sub] = sub_map[line.to_sub]
        edges.append(NetworkEdge(from_id=line.from_sub, to_id=line.to_sub,
                                 length_km=line.length_km))
    return Network(nodes=nodes, edges=edges)


def _compute_bounds() -> dict:
    bus_path = os.path.join(
        REPO_ROOT, "vatic", "data", "grids", "Texas-7k",
        "TX_Data", "SourceData", "bus.csv",
    )
    buses = pd.read_csv(bus_path)
    lat_min, lat_max = float(buses["lat"].min()), float(buses["lat"].max())
    lon_min, lon_max = float(buses["lng"].min()), float(buses["lng"].max())
    dlat = (lat_max - lat_min) * 0.03
    dlon = (lon_max - lon_min) * 0.03
    return {
        "lat_min": lat_min - dlat, "lat_max": lat_max + dlat,
        "lon_min": lon_min - dlon, "lon_max": lon_max + dlon,
    }


def _draw_network(ax, net: Network, edge_color: str, node_color: str,
                  lw: float = 0.4, node_size: float = 3.0) -> None:
    for e in net.edges:
        lat1, lng1 = net.nodes[e.from_id]
        lat2, lng2 = net.nodes[e.to_id]
        ax.plot([lng1, lng2], [lat1, lat2],
                color=edge_color, linewidth=lw, alpha=0.45, zorder=1)

    lats = [c[0] for c in net.nodes.values()]
    lngs = [c[1] for c in net.nodes.values()]
    ax.scatter(lngs, lats, c=node_color, s=node_size,
               alpha=0.75, edgecolors="none", zorder=2)


def _apply_geo(ax, bounds: dict) -> None:
    ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
    ax.set_ylim(bounds["lat_min"], bounds["lat_max"])
    ax.set_xlabel("Longitude", fontsize=9)
    ax.set_ylabel("Latitude", fontsize=9)
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.25)
    ax.tick_params(labelsize=8)


def _annotate_stats(ax, stats: NetworkStats) -> None:
    lines = [
        f"Nodes: {stats.num_nodes}",
        f"Edges: {stats.num_edges}",
        f"m/n:   {stats.mn_ratio:.3f}",
        f"<deg>: {stats.degree_stats.mean_degree:.2f}",
        f"mesh:  {stats.meshedness:.3f}",
        f"d1%:   {stats.deg1_frac*100:.1f}%",
        f"d3+%:  {stats.deg3plus_frac*100:.1f}%",
        f"<len>: {stats.length_stats.mean_km:.1f} km",
        f"int%:  {stats.intersection_rate*100:.1f}%",
    ]
    text = "\n".join(lines)
    ax.text(0.02, 0.98, text, transform=ax.transAxes,
            fontsize=8.5, fontfamily="monospace",
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor="#999", alpha=0.85))


# ── Map comparison ───────────────────────────────────────────────────────

def _make_map_comparison(ref: Network, best: Network,
                         ref_stats: NetworkStats, best_stats: NetworkStats,
                         ref_label: str, best_label: str,
                         suptitle: str, out_path: str,
                         bounds: dict, node_size: float = 3.0,
                         lw: float = 0.4) -> None:
    fig, (ax_ref, ax_best) = plt.subplots(
        1, 2, figsize=(18, 8), sharex=True, sharey=True)

    _draw_network(ax_ref, ref, edge_color="#1a5276", node_color="#2980b9",
                  lw=lw, node_size=node_size)
    ax_ref.set_title(ref_label, fontsize=12, fontweight="bold", color="#1a5276")
    _annotate_stats(ax_ref, ref_stats)
    _apply_geo(ax_ref, bounds)

    _draw_network(ax_best, best, edge_color="#922b21", node_color="#e74c3c",
                  lw=lw, node_size=node_size)
    ax_best.set_title(best_label, fontsize=12, fontweight="bold", color="#922b21")
    _annotate_stats(ax_best, best_stats)
    _apply_geo(ax_best, bounds)

    fig.suptitle(suptitle, fontsize=15, fontweight="bold", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out_path}")


# ── Degree distribution overlay ──────────────────────────────────────────

def _make_degree_comparison(ref: Network, best: Network,
                            ref_label: str, best_label: str,
                            suptitle: str, out_path: str) -> None:
    ref_dist = compute_degree_distribution(ref)
    best_dist = compute_degree_distribution(best)

    all_degrees = sorted(set(ref_dist.keys()) | set(best_dist.keys()))
    ref_fracs = [ref_dist.get(d, 0) for d in all_degrees]
    best_fracs = [best_dist.get(d, 0) for d in all_degrees]

    x = np.arange(len(all_degrees))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width/2, ref_fracs, width, label=ref_label,
           color="#2980b9", alpha=0.8, edgecolor="white")
    ax.bar(x + width/2, best_fracs, width, label=best_label,
           color="#e74c3c", alpha=0.8, edgecolor="white")

    ax.set_xlabel("Node Degree", fontsize=11)
    ax.set_ylabel("Fraction of Nodes", fontsize=11)
    ax.set_title(suptitle, fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(all_degrees)
    ax.legend(fontsize=10)
    ax.grid(axis="y", linestyle=":", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out_path}")


# ── Length distribution overlay ──────────────────────────────────────────

def _make_length_comparison(ref: Network, best: Network,
                            ref_label: str, best_label: str,
                            suptitle: str, out_path: str) -> None:
    ref_lengths = [e.length_km for e in ref.edges]
    best_lengths = [e.length_km for e in best.edges]

    bins = np.linspace(0, max(max(ref_lengths), max(best_lengths)) * 1.05, 30)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(ref_lengths, bins=bins, density=True, alpha=0.6,
            color="#2980b9", label=ref_label, edgecolor="white")
    ax.hist(best_lengths, bins=bins, density=True, alpha=0.6,
            color="#e74c3c", label=best_label, edgecolor="white")

    ref_mean = np.mean(ref_lengths)
    best_mean = np.mean(best_lengths)
    ax.axvline(ref_mean, color="#1a5276", linestyle="--", linewidth=1.5,
               label=f"{ref_label} mean={ref_mean:.1f} km")
    ax.axvline(best_mean, color="#922b21", linestyle="--", linewidth=1.5,
               label=f"{best_label} mean={best_mean:.1f} km")

    ax.set_xlabel("Line Length (km)", fontsize=11)
    ax.set_ylabel("Density", fontsize=11)
    ax.set_title(suptitle, fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out_path}")


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    bounds = _compute_bounds()

    print("Loading Texas-7k substations...")
    substations = build_texas7k_substation_nodes_for_topology()

    # ── 345 kV ──
    print("\nGenerating best 345 kV topology...")
    cfg_345 = _make_best_345_config()
    gen_345 = TopologyGenerator(substations=substations, voltage_kv=345,
                                config=cfg_345, verbose=False)
    lines_345 = gen_345.run()
    best_345 = _network_from_lines(lines_345, substations)
    best_345_stats = compute_network_stats(best_345)

    print("Loading Texas-7k 345 kV reference...")
    ref_345 = load_texas7k_network(voltage_filter=[345.0])
    ref_345_stats = compute_network_stats(ref_345)

    _make_map_comparison(
        ref=ref_345, best=best_345,
        ref_stats=ref_345_stats, best_stats=best_345_stats,
        ref_label="Texas-7k Reference (345 kV)",
        best_label="Dartboard Best (345 kV)\nw_dist=0.6",
        suptitle="345 kV — Reference vs Best Alignment",
        out_path=os.path.join(OUTPUT_DIR, "best_vs_ref_345kv.png"),
        bounds=bounds, node_size=5.0, lw=0.5,
    )

    _make_degree_comparison(
        ref=ref_345, best=best_345,
        ref_label="Texas-7k 345 kV",
        best_label="Dartboard Best 345 kV",
        suptitle="Degree Distribution — 345 kV",
        out_path=os.path.join(OUTPUT_DIR, "degree_dist_345kv.png"),
    )

    _make_length_comparison(
        ref=ref_345, best=best_345,
        ref_label="Texas-7k 345 kV",
        best_label="Dartboard Best 345 kV",
        suptitle="Line Length Distribution — 345 kV",
        out_path=os.path.join(OUTPUT_DIR, "length_dist_345kv.png"),
    )

    # ── 138 kV ──
    print("\nGenerating best 138 kV topology...")
    cfg_138 = _make_best_138_config()
    gen_138 = TopologyGenerator(substations=substations, voltage_kv=115,
                                config=cfg_138, verbose=False)
    lines_138 = gen_138.run()
    best_138 = _network_from_lines(lines_138, substations)
    best_138_stats = compute_network_stats(best_138)

    print("Loading Texas-7k 138 kV reference...")
    ref_138 = load_texas7k_network(voltage_filter=[138.0])
    ref_138_stats = compute_network_stats(ref_138)

    _make_map_comparison(
        ref=ref_138, best=best_138,
        ref_stats=ref_138_stats, best_stats=best_138_stats,
        ref_label="Texas-7k Reference (138 kV)",
        best_label="Dartboard Best (138 kV)\nmn=1.28 w_dist=0.6",
        suptitle="138 kV — Reference vs Best Alignment",
        out_path=os.path.join(OUTPUT_DIR, "best_vs_ref_138kv.png"),
        bounds=bounds, node_size=1.5, lw=0.25,
    )

    _make_degree_comparison(
        ref=ref_138, best=best_138,
        ref_label="Texas-7k 138 kV",
        best_label="Dartboard Best 138 kV",
        suptitle="Degree Distribution — 138 kV",
        out_path=os.path.join(OUTPUT_DIR, "degree_dist_138kv.png"),
    )

    _make_length_comparison(
        ref=ref_138, best=best_138,
        ref_label="Texas-7k 138 kV",
        best_label="Dartboard Best 138 kV",
        suptitle="Line Length Distribution — 138 kV",
        out_path=os.path.join(OUTPUT_DIR, "length_dist_138kv.png"),
    )

    # ── Print gap tables ──
    for label, rs, bs in [("345 kV", ref_345_stats, best_345_stats),
                          ("138 kV", ref_138_stats, best_138_stats)]:
        print(f"\n{'='*60}")
        print(f"Gap table: {label}")
        print(f"{'='*60}")
        metrics = [
            ("m/n", rs.mn_ratio, bs.mn_ratio),
            ("mean_deg", rs.degree_stats.mean_degree, bs.degree_stats.mean_degree),
            ("mean_len_km", rs.length_stats.mean_km, bs.length_stats.mean_km),
            ("median_len_km", rs.length_stats.median_km, bs.length_stats.median_km),
            ("intersect%", rs.intersection_rate, bs.intersection_rate),
            ("meshedness", rs.meshedness, bs.meshedness),
            ("deg1_frac", rs.deg1_frac, bs.deg1_frac),
            ("deg2_frac", rs.deg2_frac, bs.deg2_frac),
            ("deg3+_frac", rs.deg3plus_frac, bs.deg3plus_frac),
        ]
        print(f"  {'Metric':16s}  {'Ref':>8s}  {'Best':>8s}  {'Gap':>8s}")
        print(f"  {'-'*16}  {'-'*8}  {'-'*8}  {'-'*8}")
        for name, ref_val, best_val in metrics:
            gap = (best_val - ref_val) / ref_val * 100 if ref_val else 0
            print(f"  {name:16s}  {ref_val:8.4f}  {best_val:8.4f}  {gap:+7.1f}%")

    print(f"\nDone. All visualizations saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
