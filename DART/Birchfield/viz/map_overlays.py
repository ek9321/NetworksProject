"""
Visualization of load and generation nodes on geographic maps.

All functions are read-only — they do not mutate data.
Output PNGs are saved to data/processed/viz/.
"""

import os
import sys

# Add the project root to Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

from core.graph_types import LoadNode, GeneratorRecord


def plot_load_nodes(
    nodes: list[LoadNode],
    title: str = "Load Nodes",
    out_path: str | None = None,
    bounds: dict | None = None,
) -> None:
    """Plot load nodes colored by population, sized by load.

    Args:
        nodes: List of LoadNode instances.
        title: Plot title.
        out_path: If provided, save figure to this path.
        bounds: Optional dict with lat_min, lat_max, lon_min, lon_max.
    """
    lats = [n.lat for n in nodes]
    lons = [n.lon for n in nodes]
    pops = np.array([n.population for n in nodes])
    loads = np.array([n.load_mw for n in nodes])

    fig, ax = plt.subplots(figsize=(12, 10))

    sizes = np.clip(loads / loads.max() * 60, 3, 60)
    norm = mcolors.LogNorm(vmin=max(pops.min(), 1), vmax=pops.max())

    sc = ax.scatter(
        lons, lats, c=pops, s=sizes, cmap="viridis",
        alpha=0.6, norm=norm, edgecolors="none",
    )

    cbar = fig.colorbar(sc, ax=ax, shrink=0.7)
    cbar.set_label("Population (log scale)")

    if bounds:
        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"{title}  (n={len(nodes)})")
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.4)

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Saved: {out_path}")

    plt.close(fig)


def plot_generation_nodes(
    generators: list[GeneratorRecord],
    title: str = "Generation Nodes",
    out_path: str | None = None,
    bounds: dict | None = None,
) -> None:
    """Plot generator locations colored by fuel type, sized by capacity.

    Args:
        generators: List of GeneratorRecord instances.
        title: Plot title.
        out_path: If provided, save figure to this path.
        bounds: Optional dict with lat_min, lat_max, lon_min, lon_max.
    """
    fuel_colors = {
        "NG": "#e74c3c",       # red — natural gas
        "BIT": "#4a4a4a",      # dark gray — bituminous coal
        "SUB": "#6a6a6a",      # gray — subbituminous coal
        "LIG": "#8a8a8a",      # light gray — lignite
        "NUC": "#9b59b6",      # purple — nuclear
        "SUN": "#f1c40f",      # yellow — solar
        "WND": "#3498db",      # blue — wind
        "WAT": "#1abc9c",      # teal — hydro
        "DFO": "#e67e22",      # orange — distillate fuel oil
        "WDS": "#27ae60",      # green — wood/biomass
        "OTH": "#95a5a6",      # muted gray — other
    }

    lats = [g.lat for g in generators]
    lons = [g.lon for g in generators]
    caps = np.array([g.nameplate_capacity_mw for g in generators])
    fuels = [g.energy_source_1 or "OTH" for g in generators]

    colors = [fuel_colors.get(f, fuel_colors["OTH"]) for f in fuels]
    sizes = np.clip(caps / caps.max() * 80, 3, 80)

    fig, ax = plt.subplots(figsize=(12, 10))

    ax.scatter(
        lons, lats, c=colors, s=sizes, alpha=0.5, edgecolors="none",
    )

    # Legend: one entry per fuel type actually present
    seen = []
    for fuel in fuel_colors:
        if fuel in fuels:
            ax.scatter([], [], c=fuel_colors[fuel], s=30, label=fuel)
            seen.append(fuel)
    remaining = set(fuels) - set(seen)
    if remaining:
        ax.scatter([], [], c=fuel_colors["OTH"], s=30, label="Other")

    ax.legend(loc="lower left", fontsize=8, ncol=2, title="Fuel")

    if bounds:
        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"{title}  (n={len(generators)}, total={caps.sum():.0f} MW)")
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.4)

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Saved: {out_path}")

    plt.close(fig)


def plot_load_and_generation(
    nodes: list[LoadNode],
    generators: list[GeneratorRecord],
    title: str = "Load & Generation Overlay",
    out_path: str | None = None,
    bounds: dict | None = None,
) -> None:
    """Overlay load nodes and generation nodes on a single map.

    Load nodes shown as gray dots sized by load.
    Generators shown as colored dots by fuel type, sized by capacity.
    """
    fuel_colors = {
        "NG": "#e74c3c",
        "BIT": "#4a4a4a",
        "SUB": "#6a6a6a",
        "LIG": "#8a8a8a",
        "NUC": "#9b59b6",
        "SUN": "#f1c40f",
        "WND": "#3498db",
        "WAT": "#1abc9c",
        "DFO": "#e67e22",
        "WDS": "#27ae60",
        "OTH": "#95a5a6",
    }

    fig, ax = plt.subplots(figsize=(14, 11))

    # Load nodes — background layer
    load_lats = [n.lat for n in nodes]
    load_lons = [n.lon for n in nodes]
    load_mws = np.array([n.load_mw for n in nodes])
    load_sizes = np.clip(load_mws / load_mws.max() * 40, 2, 40)

    ax.scatter(
        load_lons, load_lats, c="#cccccc", s=load_sizes,
        alpha=0.4, edgecolors="none", label=f"Load ({len(nodes)} nodes)",
    )

    # Generation nodes — foreground layer
    gen_lats = [g.lat for g in generators]
    gen_lons = [g.lon for g in generators]
    gen_caps = np.array([g.nameplate_capacity_mw for g in generators])
    gen_fuels = [g.energy_source_1 or "OTH" for g in generators]
    gen_colors = [fuel_colors.get(f, fuel_colors["OTH"]) for f in gen_fuels]
    gen_sizes = np.clip(gen_caps / gen_caps.max() * 80, 4, 80)

    ax.scatter(
        gen_lons, gen_lats, c=gen_colors, s=gen_sizes,
        alpha=0.6, edgecolors="none",
    )

    # Legend
    ax.scatter([], [], c="#cccccc", s=20, label=f"Load ({len(nodes)})")
    for fuel in fuel_colors:
        if fuel in gen_fuels:
            ax.scatter([], [], c=fuel_colors[fuel], s=20, label=fuel)

    ax.legend(loc="lower left", fontsize=8, ncol=2, title="Node Type / Fuel")

    if bounds:
        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    total_load = load_mws.sum()
    total_gen = gen_caps.sum()
    ax.set_title(
        f"{title}\n"
        f"Load: {len(nodes)} nodes, {total_load:.0f} MW  |  "
        f"Gen: {len(generators)} units, {total_gen:.0f} MW"
    )
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.4)

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Saved: {out_path}")

    plt.close(fig)


if __name__ == "__main__":
    # Simple test to verify the module works    
    # Create some dummy data for testing
    test_load_nodes = [
        LoadNode(zcta="12345", lat=40.7128, lon=-74.0060, population=10000, load_mw=50.0),
        LoadNode(zcta="67890", lat=40.7580, lon=-73.9855, population=8000, load_mw=40.0),
    ]
    
    test_generators = [
        GeneratorRecord(
            plant_code=1001, generator_id="G1", lat=40.7489, lon=-73.9857,
            state="NY", nameplate_capacity_mw=100.0, energy_source_1="NG"
        ),
        GeneratorRecord(
            plant_code=1002, generator_id="G2", lat=40.7282, lon=-74.0776,
            state="NY", nameplate_capacity_mw=75.0, energy_source_1="SUN"
        ),
    ]
    
    # Test if we can create plots without saving them
    print("Testing load nodes plot...")
    plot_load_nodes(test_load_nodes, title="Test Load Nodes")
    
    print("Testing generation nodes plot...")
    plot_generation_nodes(test_generators, title="Test Generation Nodes")
    
    print("Testing combined plot...")
    plot_load_and_generation(
        test_load_nodes, test_generators, title="Test Combined Plot"
    )
    
    # Test saving plots to the expected output directory
    print("\nTesting file output...")
    viz_dir = "data/processed/viz"
    plot_load_nodes(
        test_load_nodes, 
        title="Test Load Nodes", 
        out_path=f"{viz_dir}/test_load_nodes.png"
    )
    plot_generation_nodes(
        test_generators, 
        title="Test Generation Nodes",
        out_path=f"{viz_dir}/test_generation_nodes.png"
    )
    plot_load_and_generation(
        test_load_nodes, test_generators, 
        title="Test Combined Plot",
        out_path=f"{viz_dir}/test_combined.png"
    )
    
    print("All visualization functions working correctly!")
