"""
Visualization of clustered load nodes.

Displays both the original postal codes (small dots) and the resulting
cluster centers (large markers) on a geographic map.

All functions are read-only — they do not mutate data.
Output PNGs are saved to data/processed/viz/.
"""

import os
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

from core.load_nodes_clustering import Cluster, PostalCode
from core.graph_types import LoadNode, Bus


def plot_clusters(
    clusters: list[Cluster],
    title: str = "Load Node Clusters",
    out_path: str | None = None,
    bounds: dict | None = None,
) -> None:
    """Plot clustered load nodes showing both members and cluster centers.

    Individual postal codes are shown as small dots colored by their cluster.
    Cluster centers are shown as large stars sized by population.

    Args:
        clusters: List of Cluster instances from clustering algorithm.
        title: Plot title.
        out_path: If provided, save figure to this path.
        bounds: Optional dict with lat_min, lat_max, lon_min, lon_max.
    """
    fig, ax = plt.subplots(figsize=(14, 11))

    # Generate a distinct color for each cluster
    n_clusters = len(clusters)
    cmap = plt.cm.get_cmap("tab20" if n_clusters <= 20 else "hsv")
    colors = [cmap(i / n_clusters) for i in range(n_clusters)]

    total_members = 0
    total_population = 0

    # Plot postal code members (small dots)
    for i, cluster in enumerate(clusters):
        member_lats = [m.lat for m in cluster.members]
        member_lons = [m.lon for m in cluster.members]

        ax.scatter(
            member_lons, member_lats,
            c=[colors[i]] * len(cluster.members),
            s=3,
            alpha=0.5,
            edgecolors="none",
        )

        total_members += len(cluster.members)
        total_population += cluster.total_population

    # Plot cluster centers (large stars)
    center_lats = [c.cluster_lat for c in clusters]
    center_lons = [c.cluster_lon for c in clusters]
    center_pops = np.array([c.total_population for c in clusters])

    # Size cluster markers by population
    if center_pops.max() > 0:
        sizes = np.clip(center_pops / center_pops.max() * 300, 50, 300)
    else:
        sizes = np.full(len(clusters), 100)

    ax.scatter(
        center_lons, center_lats,
        c=colors,
        s=sizes,
        marker="*",
        alpha=0.9,
        edgecolors="black",
        linewidths=1.5,
        label="Cluster centers",
    )

    if bounds:
        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(
        f"{title}\n"
        f"{n_clusters} clusters, {total_members} postal codes, "
        f"{total_population:,} total population"
    )
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.legend(loc="lower left", fontsize=10)

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Saved: {out_path}")

    plt.close(fig)


def plot_clusters_and_original_nodes(
    original_nodes: list[LoadNode],
    clusters: list[Cluster],
    title: str = "Clustering Result",
    out_path: str | None = None,
    bounds: dict | None = None,
) -> None:
    """Plot original load nodes alongside cluster centers for comparison.

    Original nodes shown as gray dots sized by population.
    Cluster centers shown as colored stars sized by cluster population.

    Args:
        original_nodes: Original LoadNode instances before clustering.
        clusters: List of Cluster instances from clustering algorithm.
        title: Plot title.
        out_path: If provided, save figure to this path.
        bounds: Optional dict with lat_min, lat_max, lon_min, lon_max.
    """
    fig, ax = plt.subplots(figsize=(14, 11))

    # Plot original nodes as gray background
    orig_lats = [n.lat for n in original_nodes]
    orig_lons = [n.lon for n in original_nodes]
    orig_pops = np.array([n.population for n in original_nodes])

    if orig_pops.max() > 0:
        orig_sizes = np.clip(orig_pops / orig_pops.max() * 50, 2, 50)
    else:
        orig_sizes = np.full(len(original_nodes), 5)

    ax.scatter(
        orig_lons, orig_lats,
        c="#999999",
        s=orig_sizes,
        alpha=0.3,
        edgecolors="none",
        label=f"Original nodes (n={len(original_nodes)})",
    )

    # Plot cluster centers
    center_lats = [c.cluster_lat for c in clusters]
    center_lons = [c.cluster_lon for c in clusters]
    center_pops = np.array([c.total_population for c in clusters])

    if center_pops.max() > 0:
        sizes = np.clip(center_pops / center_pops.max() * 300, 50, 300)
    else:
        sizes = np.full(len(clusters), 100)

    ax.scatter(
        center_lons, center_lats,
        c="#e74c3c",
        s=sizes,
        marker="*",
        alpha=0.9,
        edgecolors="black",
        linewidths=1.5,
        label=f"Cluster centers (n={len(clusters)})",
    )

    if bounds:
        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    reduction_pct = (1 - len(clusters) / len(original_nodes)) * 100
    ax.set_title(
        f"{title}\n"
        f"{len(original_nodes)} nodes → {len(clusters)} clusters "
        f"({reduction_pct:.1f}% reduction)"
    )
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.legend(loc="lower left", fontsize=10)

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Saved: {out_path}")

    plt.close(fig)


def plot_bus_substations(
    buses: list[Bus],
    title: str = "Load Substations",
    out_path: str | None = None,
    bounds: dict | None = None,
) -> None:
    """Plot Bus objects (load substations) on a geographic map.

    Buses are colored by load (MW) and sized proportionally.

    Args:
        buses: List of Bus instances.
        title: Plot title.
        out_path: If provided, save figure to this path.
        bounds: Optional dict with lat_min, lat_max, lon_min, lon_max.
    """
    fig, ax = plt.subplots(figsize=(14, 11))

    lats = [b.lat for b in buses]
    lons = [b.lng for b in buses]
    loads = np.array([b.mw_load for b in buses])

    # Size markers by load
    if loads.max() > 0:
        sizes = np.clip(loads / loads.max() * 200, 20, 200)
    else:
        sizes = np.full(len(buses), 50)

    # Color by load using log scale
    if loads.max() > loads.min() > 0:
        norm = mcolors.LogNorm(vmin=max(loads.min(), 1), vmax=loads.max())
    else:
        norm = None

    sc = ax.scatter(
        lons, lats,
        c=loads,
        s=sizes,
        cmap="plasma",
        alpha=0.7,
        norm=norm,
        edgecolors="black",
        linewidths=0.5,
    )

    cbar = fig.colorbar(sc, ax=ax, shrink=0.7)
    cbar.set_label("Load (MW)")

    if bounds:
        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    total_load = loads.sum()
    ax.set_title(
        f"{title}\n"
        f"{len(buses)} substations, {total_load:.1f} MW total load"
    )
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.4)

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Saved: {out_path}")

    plt.close(fig)
