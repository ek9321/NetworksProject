"""Side-by-side visualizations: Texas-7k vs Dartboard-on-7k-buses vs Dartboard-orig.

Produces PNGs under Calibration/outputs:
  - comparison_345kv.png   (3 panels: Texas-7k | Dartboard-on-7k | Dartboard-orig)
  - comparison_138kv.png   (3 panels: Texas-7k 138 kV | Dartboard-on-7k 115 kV | Dartboard-orig 115 kV)
  - degree_histograms.png  (degree distributions for each network pair)
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np

from .network_io import (
    load_texas7k_network,
    load_dartboard_texas_network,
    load_calibration_network,
    Network,
)
from .network_stats import compute_degree_stats


REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "Calibration", "outputs")


def _compute_bounds_from_texas7k() -> dict:
    """Compute geographic bounds from the Texas-7k bus.csv file."""
    import pandas as pd
    bus_path = os.path.join(
        REPO_ROOT, "vatic", "data", "grids", "Texas-7k",
        "TX_Data", "SourceData", "bus.csv",
    )
    buses = pd.read_csv(bus_path)
    lat_min, lat_max = float(buses["lat"].min()), float(buses["lat"].max())
    lon_min, lon_max = float(buses["lng"].min()), float(buses["lng"].max())
    dlat = (lat_max - lat_min) * 0.02
    dlon = (lon_max - lon_min) * 0.02
    return {
        "lat_min": lat_min - dlat, "lat_max": lat_max + dlat,
        "lon_min": lon_min - dlon, "lon_max": lon_max + dlon,
    }


def _plot_network(ax, network: Network, title: str, color: str = "#2c3e50",
                  node_color: str = "#3498db", lw: float = 0.3) -> None:
    for edge in network.edges:
        (lat1, lng1) = network.nodes[edge.from_id]
        (lat2, lng2) = network.nodes[edge.to_id]
        ax.plot([lng1, lng2], [lat1, lat2], color=color, linewidth=lw, alpha=0.4, zorder=1)
    if network.nodes:
        lats = [lat for (lat, _) in network.nodes.values()]
        lngs = [lng for (_, lng) in network.nodes.values()]
        ax.scatter(lngs, lats, c=node_color, s=2, alpha=0.7, edgecolors="none", zorder=2)
    n = len(network.nodes)
    m = len(network.edges)
    mn = m / n if n else 0
    ax.set_title(f"{title}\n{n} nodes, {m} edges, m/n={mn:.3f}", fontsize=10)


def _apply_bounds_and_aspect(ax, bounds: dict) -> None:
    ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
    ax.set_ylim(bounds["lat_min"], bounds["lat_max"])
    ax.set_xlabel("Longitude", fontsize=9)
    ax.set_ylabel("Latitude", fontsize=9)
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.3)


def _plot_three_panels(networks: List[Network], titles: List[str],
                       suptitle: str, out_path: str, bounds: dict) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(22, 7), sharex=True, sharey=True)
    for ax, net, title in zip(axes, networks, titles):
        _plot_network(ax, net, title)
        _apply_bounds_and_aspect(ax, bounds)
    fig.suptitle(suptitle, fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _plot_degree_histograms(networks: List[Network], labels: List[str],
                            suptitle: str, out_path: str) -> None:
    """Plot degree distributions for multiple networks on a single figure."""
    fig, axes = plt.subplots(1, len(networks), figsize=(6 * len(networks), 5),
                             sharey=False)
    if len(networks) == 1:
        axes = [axes]
    for ax, net, label in zip(axes, networks, labels):
        ds = compute_degree_stats(net)
        deg_vals = list(ds.degree_counts.values())
        deg_hist = Counter(deg_vals)
        degrees = sorted(deg_hist.keys())
        counts = [deg_hist[d] for d in degrees]
        ax.bar(degrees, counts, color="#3498db", edgecolor="white")
        ax.set_xlabel("Degree", fontsize=11)
        ax.set_ylabel("# Nodes", fontsize=11)
        ax.set_title(f"{label}\nmean={ds.mean_degree:.2f}, max={ds.max_degree}", fontsize=10)
    fig.suptitle(suptitle, fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    bounds = _compute_bounds_from_texas7k()

    # Load all networks
    t7k_345 = load_texas7k_network(voltage_filter=[345.0])
    t7k_138 = load_texas7k_network(voltage_filter=[138.0])
    cal_345 = load_calibration_network(voltage_kv=345)
    cal_115 = load_calibration_network(voltage_kv=115)
    dart_345 = load_dartboard_texas_network(voltage_kv=345)
    dart_115 = load_dartboard_texas_network(voltage_kv=115)

    # --- 345 kV: 3-panel comparison ---
    _plot_three_panels(
        networks=[t7k_345, cal_345, dart_345],
        titles=["Texas-7k 345 kV", "Dartboard-on-7k 345 kV", "Dartboard-orig 345 kV"],
        suptitle="345 kV Topology Comparison",
        out_path=os.path.join(OUTPUT_DIR, "comparison_345kv.png"),
        bounds=bounds,
    )

    # --- 138/115 kV: 3-panel comparison ---
    _plot_three_panels(
        networks=[t7k_138, cal_115, dart_115],
        titles=["Texas-7k 138 kV", "Dartboard-on-7k 115 kV", "Dartboard-orig 115 kV"],
        suptitle="138/115 kV Topology Comparison",
        out_path=os.path.join(OUTPUT_DIR, "comparison_138kv.png"),
        bounds=bounds,
    )

    # --- Degree histograms ---
    _plot_degree_histograms(
        networks=[t7k_345, cal_345, dart_345],
        labels=["Texas-7k 345 kV", "Dartboard-on-7k 345 kV", "Dartboard-orig 345 kV"],
        suptitle="Degree Distribution — 345 kV",
        out_path=os.path.join(OUTPUT_DIR, "degree_histograms_345kv.png"),
    )
    _plot_degree_histograms(
        networks=[t7k_138, cal_115, dart_115],
        labels=["Texas-7k 138 kV", "Dartboard-on-7k 115 kV", "Dartboard-orig 115 kV"],
        suptitle="Degree Distribution — 138/115 kV",
        out_path=os.path.join(OUTPUT_DIR, "degree_histograms_138kv.png"),
    )

    print("✓ Visualizations saved to Calibration/outputs/")


if __name__ == "__main__":
    main()
