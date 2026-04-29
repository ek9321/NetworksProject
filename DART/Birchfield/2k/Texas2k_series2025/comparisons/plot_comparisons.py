"""Side-by-side visualizations: Texas2k reference vs Dartboard biconnectivity topology.

Produces in Texas2k_series2025/comparisons/:
  - map_500kv.png          2-panel map: Texas2k ref (left, blue) vs Dartboard biconn (right, red)
  - map_115kv.png          same for 115 kV
  - degree_dist_500kv.png  overlaid bar chart of degree distribution
  - degree_dist_115kv.png  same for 115 kV
  - length_dist_500kv.png  overlaid histogram of line lengths with mean lines
  - length_dist_115kv.png  same for 115 kV
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from typing import Dict, List, Tuple

# Ensure repo root is on sys.path so we can import core and Calibration
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import matplotlib.pyplot as plt
import numpy as np

from core.topology_generation import TopologyConfig, TopologyGenerator, SubstationNode
from Calibration.texas2k_io import load_texas2k_substations, load_texas2k_reference_network
from Calibration.network_io import Network, NetworkEdge
from Calibration.network_stats import (
    compute_network_stats,
    compute_degree_distribution,
    NetworkStats,
)

OUTPUT_DIR = os.path.join(REPO_ROOT, "Texas2k_series2025", "comparisons")


# ── Biconnectivity-fix configs (Experiment 3) ────────────────────────────

def _make_500kv_config() -> TopologyConfig:
    cfg = TopologyConfig()
    cfg.target_mn_ratio = 1.544
    cfg.use_biconnectivity_bonus = True
    cfg.w_dc = 0.5
    cfg.max_intersection_rate = 1.0
    return cfg


def _make_115kv_config() -> TopologyConfig:
    cfg = TopologyConfig()
    cfg.target_mn_ratio = 1.657
    cfg.use_biconnectivity_bonus = True
    cfg.w_dc = 0.5
    cfg.max_intersection_rate = 1.0
    return cfg


# ── Helpers ──────────────────────────────────────────────────────────────

def _network_from_lines(lines, substations) -> Network:
    """Build a Network object from TopologyGenerator output lines."""
    sub_map = {s.sub_id: (s.lat, s.lng) for s in substations}
    nodes: Dict[int, Tuple[float, float]] = {}
    edges: List[NetworkEdge] = []
    for line in lines:
        nodes[line.from_sub] = sub_map[line.from_sub]
        nodes[line.to_sub] = sub_map[line.to_sub]
        edges.append(NetworkEdge(from_id=line.from_sub, to_id=line.to_sub,
                                 length_km=line.length_km))
    return Network(nodes=nodes, edges=edges)


def _compute_bounds(substations: List[SubstationNode]) -> dict:
    """Compute geographic bounds from all Texas2k substations with 3% padding."""
    lats = [s.lat for s in substations]
    lngs = [s.lng for s in substations]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lngs), max(lngs)
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

def _make_map_comparison(ref: Network, gen: Network,
                         ref_stats: NetworkStats, gen_stats: NetworkStats,
                         ref_label: str, gen_label: str,
                         suptitle: str, out_path: str,
                         bounds: dict, node_size: float = 3.0,
                         lw: float = 0.4) -> None:
    fig, (ax_ref, ax_gen) = plt.subplots(
        1, 2, figsize=(18, 8), sharex=True, sharey=True)

    _draw_network(ax_ref, ref, edge_color="#1a5276", node_color="#2980b9",
                  lw=lw, node_size=node_size)
    ax_ref.set_title(ref_label, fontsize=12, fontweight="bold", color="#1a5276")
    _annotate_stats(ax_ref, ref_stats)
    _apply_geo(ax_ref, bounds)

    _draw_network(ax_gen, gen, edge_color="#922b21", node_color="#e74c3c",
                  lw=lw, node_size=node_size)
    ax_gen.set_title(gen_label, fontsize=12, fontweight="bold", color="#922b21")
    _annotate_stats(ax_gen, gen_stats)
    _apply_geo(ax_gen, bounds)

    fig.suptitle(suptitle, fontsize=15, fontweight="bold", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out_path}")


# ── Degree distribution overlay ──────────────────────────────────────────

def _make_degree_comparison(ref: Network, gen: Network,
                            ref_label: str, gen_label: str,
                            suptitle: str, out_path: str) -> None:
    ref_dist = compute_degree_distribution(ref)
    gen_dist = compute_degree_distribution(gen)

    all_degrees = sorted(set(ref_dist.keys()) | set(gen_dist.keys()))
    ref_fracs = [ref_dist.get(d, 0) for d in all_degrees]
    gen_fracs = [gen_dist.get(d, 0) for d in all_degrees]

    x = np.arange(len(all_degrees))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width/2, ref_fracs, width, label=ref_label,
           color="#2980b9", alpha=0.8, edgecolor="white")
    ax.bar(x + width/2, gen_fracs, width, label=gen_label,
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

def _make_length_comparison(ref: Network, gen: Network,
                            ref_label: str, gen_label: str,
                            suptitle: str, out_path: str) -> None:
    ref_lengths = [e.length_km for e in ref.edges]
    gen_lengths = [e.length_km for e in gen.edges]

    bins = np.linspace(0, max(max(ref_lengths), max(gen_lengths)) * 1.05, 30)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(ref_lengths, bins=bins, density=True, alpha=0.6,
            color="#2980b9", label=ref_label, edgecolor="white")
    ax.hist(gen_lengths, bins=bins, density=True, alpha=0.6,
            color="#e74c3c", label=gen_label, edgecolor="white")

    ref_mean = np.mean(ref_lengths)
    gen_mean = np.mean(gen_lengths)
    ax.axvline(ref_mean, color="#1a5276", linestyle="--", linewidth=1.5,
               label=f"{ref_label} mean={ref_mean:.1f} km")
    ax.axvline(gen_mean, color="#922b21", linestyle="--", linewidth=1.5,
               label=f"{gen_label} mean={gen_mean:.1f} km")

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

    print("Loading Texas2k substations...")
    all_subs = load_texas2k_substations(hv_class="500kv")
    bounds = _compute_bounds(all_subs)

    # Filter substations by voltage class for topology generation
    subs_500 = [s for s in all_subs if s.has_345kv]
    subs_115 = [s for s in all_subs if s.has_115kv]

    print(f"  {len(subs_500)} substations with 500 kV buses")
    print(f"  {len(subs_115)} substations with 115 kV buses")

    # ── 500 kV ──
    print("\nGenerating 500 kV topology (biconnectivity fix)...")
    cfg_500 = _make_500kv_config()
    gen_500 = TopologyGenerator(substations=subs_500, voltage_kv=345,
                                config=cfg_500, verbose=False)
    lines_500 = gen_500.run()
    net_gen_500 = _network_from_lines(lines_500, subs_500)
    stats_gen_500 = compute_network_stats(net_gen_500)

    print("Loading Texas2k 500 kV reference network...")
    ref_500 = load_texas2k_reference_network("500kv")
    stats_ref_500 = compute_network_stats(ref_500)

    _make_map_comparison(
        ref=ref_500, gen=net_gen_500,
        ref_stats=stats_ref_500, gen_stats=stats_gen_500,
        ref_label="Texas2k Reference (500 kV)",
        gen_label="Dartboard Biconn (500 kV)\nmn=1.544",
        suptitle="500 kV -- Texas2k Reference vs Dartboard Biconnectivity",
        out_path=os.path.join(OUTPUT_DIR, "map_500kv.png"),
        bounds=bounds, node_size=5.0, lw=0.5,
    )

    _make_degree_comparison(
        ref=ref_500, gen=net_gen_500,
        ref_label="Texas2k 500 kV",
        gen_label="Dartboard Biconn 500 kV",
        suptitle="Degree Distribution -- 500 kV",
        out_path=os.path.join(OUTPUT_DIR, "degree_dist_500kv.png"),
    )

    _make_length_comparison(
        ref=ref_500, gen=net_gen_500,
        ref_label="Texas2k 500 kV",
        gen_label="Dartboard Biconn 500 kV",
        suptitle="Line Length Distribution -- 500 kV",
        out_path=os.path.join(OUTPUT_DIR, "length_dist_500kv.png"),
    )

    # ── 115 kV ──
    print("\nGenerating 115 kV topology (biconnectivity fix)...")
    cfg_115 = _make_115kv_config()
    gen_115 = TopologyGenerator(substations=subs_115, voltage_kv=115,
                                config=cfg_115, verbose=False)
    lines_115 = gen_115.run()
    net_gen_115 = _network_from_lines(lines_115, subs_115)
    stats_gen_115 = compute_network_stats(net_gen_115)

    print("Loading Texas2k 115 kV reference network...")
    ref_115 = load_texas2k_reference_network("115kv")
    stats_ref_115 = compute_network_stats(ref_115)

    _make_map_comparison(
        ref=ref_115, gen=net_gen_115,
        ref_stats=stats_ref_115, gen_stats=stats_gen_115,
        ref_label="Texas2k Reference (115 kV)",
        gen_label="Dartboard Biconn (115 kV)\nmn=1.657",
        suptitle="115 kV -- Texas2k Reference vs Dartboard Biconnectivity",
        out_path=os.path.join(OUTPUT_DIR, "map_115kv.png"),
        bounds=bounds, node_size=1.5, lw=0.25,
    )

    _make_degree_comparison(
        ref=ref_115, gen=net_gen_115,
        ref_label="Texas2k 115 kV",
        gen_label="Dartboard Biconn 115 kV",
        suptitle="Degree Distribution -- 115 kV",
        out_path=os.path.join(OUTPUT_DIR, "degree_dist_115kv.png"),
    )

    _make_length_comparison(
        ref=ref_115, gen=net_gen_115,
        ref_label="Texas2k 115 kV",
        gen_label="Dartboard Biconn 115 kV",
        suptitle="Line Length Distribution -- 115 kV",
        out_path=os.path.join(OUTPUT_DIR, "length_dist_115kv.png"),
    )

    # ── Print gap tables ──
    for label, rs, gs in [("500 kV", stats_ref_500, stats_gen_500),
                          ("115 kV", stats_ref_115, stats_gen_115)]:
        print(f"\n{'='*60}")
        print(f"Gap table: {label}")
        print(f"{'='*60}")
        metrics = [
            ("m/n", rs.mn_ratio, gs.mn_ratio),
            ("mean_deg", rs.degree_stats.mean_degree, gs.degree_stats.mean_degree),
            ("mean_len_km", rs.length_stats.mean_km, gs.length_stats.mean_km),
            ("median_len_km", rs.length_stats.median_km, gs.length_stats.median_km),
            ("intersect%", rs.intersection_rate, gs.intersection_rate),
            ("meshedness", rs.meshedness, gs.meshedness),
            ("deg1_frac", rs.deg1_frac, gs.deg1_frac),
            ("deg2_frac", rs.deg2_frac, gs.deg2_frac),
            ("deg3+_frac", rs.deg3plus_frac, gs.deg3plus_frac),
        ]
        print(f"  {'Metric':16s}  {'Ref':>8s}  {'Biconn':>8s}  {'Gap':>8s}")
        print(f"  {'-'*16}  {'-'*8}  {'-'*8}  {'-'*8}")
        for name, ref_val, gen_val in metrics:
            gap = (gen_val - ref_val) / ref_val * 100 if ref_val else 0
            print(f"  {name:16s}  {ref_val:8.4f}  {gen_val:8.4f}  {gap:+7.1f}%")

    print(f"\nDone. All visualizations saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
