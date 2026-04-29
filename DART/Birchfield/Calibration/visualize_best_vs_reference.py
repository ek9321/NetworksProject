"""Side-by-side: Texas-7k reference vs best calibrated Dartboard topology.

Produces 2-panel PNGs at each voltage level showing the reference network
next to our best-fit parameter sweep result, with key metrics annotated.

Outputs:
  Calibration/outputs/best_vs_ref_345kv.png
  Calibration/outputs/best_vs_ref_115kv.png
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .network_io import load_texas7k_network, Network, NetworkEdge
from .network_stats import compute_network_stats

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "Calibration", "outputs")

# Best configs from parameter sweep
BEST_345 = "mn1.55_wint25_wd1.242_pr95.0_345kv.csv"
BEST_115 = "mn1.28_wint0_wd1.242_115kv.csv"


def _load_sweep_network(csv_name: str) -> Network:
    """Load a network from a sweep_lines CSV + Texas-7k bus positions."""
    lines_path = os.path.join(OUTPUT_DIR, "sweep_lines", csv_name)
    bus_path = os.path.join(
        REPO_ROOT, "vatic", "data", "grids", "Texas-7k",
        "TX_Data", "SourceData", "bus.csv",
    )

    bus_df = pd.read_csv(bus_path).rename(columns={"Bus ID": "bus_id"}).set_index("bus_id")
    all_coords: Dict[int, Tuple[float, float]] = {}
    for bus_id, row in bus_df.iterrows():
        all_coords[int(bus_id)] = (float(row["lat"]), float(row["lng"]))

    lines_df = pd.read_csv(lines_path)
    nodes: Dict[int, Tuple[float, float]] = {}
    edges: List[NetworkEdge] = []
    for _, row in lines_df.iterrows():
        from_id = int(row["from_sub"])
        to_id = int(row["to_sub"])
        if from_id in all_coords:
            nodes[from_id] = all_coords[from_id]
        if to_id in all_coords:
            nodes[to_id] = all_coords[to_id]
        edges.append(NetworkEdge(from_id=from_id, to_id=to_id,
                                 length_km=float(row["length_km"])))
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
    """Draw edges then nodes."""
    for e in net.edges:
        lat1, lng1 = net.nodes[e.from_id]
        lat2, lng2 = net.nodes[e.to_id]
        ax.plot([lng1, lng2], [lat1, lat2],
                color=edge_color, linewidth=lw, alpha=0.45, zorder=1)

    lats = [c[0] for c in net.nodes.values()]
    lngs = [c[1] for c in net.nodes.values()]
    ax.scatter(lngs, lats, c=node_color, s=node_size,
               alpha=0.75, edgecolors="none", zorder=2)


def _annotate_stats(ax, stats, is_ref: bool) -> None:
    """Add a text box with key metrics."""
    lines = [
        f"Nodes: {stats.num_nodes}",
        f"Edges: {stats.num_edges}",
        f"m/n:   {stats.mn_ratio:.3f}",
        f"⟨deg⟩: {stats.degree_stats.mean_degree:.2f}",
        f"Intersect: {stats.intersection_rate * 100:.1f}%",
        f"⟨len⟩: {stats.length_stats.mean_km:.1f} km",
    ]
    text = "\n".join(lines)
    ax.text(0.02, 0.98, text, transform=ax.transAxes,
            fontsize=9, fontfamily="monospace",
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor="#999", alpha=0.85))


def _apply_geo(ax, bounds: dict) -> None:
    ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
    ax.set_ylim(bounds["lat_min"], bounds["lat_max"])
    ax.set_xlabel("Longitude", fontsize=9)
    ax.set_ylabel("Latitude", fontsize=9)
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.25)
    ax.tick_params(labelsize=8)


def _make_comparison(ref: Network, best: Network,
                     ref_label: str, best_label: str,
                     suptitle: str, out_path: str,
                     bounds: dict, node_size: float = 3.0,
                     lw: float = 0.4) -> None:
    """Two-panel figure: reference on left, best calibrated on right."""
    fig, (ax_ref, ax_best) = plt.subplots(
        1, 2, figsize=(18, 8), sharex=True, sharey=True)

    # Reference (blue tones)
    _draw_network(ax_ref, ref, edge_color="#1a5276", node_color="#2980b9",
                  lw=lw, node_size=node_size)
    ref_stats = compute_network_stats(ref)
    ax_ref.set_title(ref_label, fontsize=12, fontweight="bold", color="#1a5276")
    _annotate_stats(ax_ref, ref_stats, is_ref=True)
    _apply_geo(ax_ref, bounds)

    # Best calibrated (red/orange tones)
    _draw_network(ax_best, best, edge_color="#922b21", node_color="#e74c3c",
                  lw=lw, node_size=node_size)
    best_stats = compute_network_stats(best)
    ax_best.set_title(best_label, fontsize=12, fontweight="bold", color="#922b21")
    _annotate_stats(ax_best, best_stats, is_ref=False)
    _apply_geo(ax_best, bounds)

    fig.suptitle(suptitle, fontsize=15, fontweight="bold", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {out_path}")


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    bounds = _compute_bounds()

    print("Loading networks...")

    # 345 kV
    ref_345 = load_texas7k_network(voltage_filter=[345.0])
    best_345 = _load_sweep_network(BEST_345)

    _make_comparison(
        ref=ref_345, best=best_345,
        ref_label="Texas-7k Reference (345 kV)",
        best_label="Dartboard Best (345 kV)\nmn=1.55  w_int=25  w_d=1.242",
        suptitle="345 kV — Reference vs Best Calibrated Topology",
        out_path=os.path.join(OUTPUT_DIR, "best_vs_ref_345kv.png"),
        bounds=bounds,
        node_size=5.0, lw=0.5,
    )

    # 115/138 kV
    ref_138 = load_texas7k_network(voltage_filter=[138.0])
    best_115 = _load_sweep_network(BEST_115)

    _make_comparison(
        ref=ref_138, best=best_115,
        ref_label="Texas-7k Reference (138 kV)",
        best_label="Dartboard Best (115 kV)\nmn=1.28  w_int=0  w_d=1.242",
        suptitle="138/115 kV — Reference vs Best Calibrated Topology",
        out_path=os.path.join(OUTPUT_DIR, "best_vs_ref_115kv.png"),
        bounds=bounds,
        node_size=1.5, lw=0.25,
    )

    print("Done.")


if __name__ == "__main__":
    main()
