"""
Pipeline to build clustered load substations for Texas and New York.

This script:
  1. Loads Census load node data for each region
  2. Runs population-weighted geographic clustering
  3. Converts clusters to Bus objects
  4. Saves results to data/processed/
  5. Generates visualization plots

This implements Stage 1 (Substation Synthesis) of the Birchfield pipeline.
"""

import os
import sys
import yaml

# Add the project root to Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.graph_types import LoadNode, Bus
from core.load_nodes_clustering import cluster_load_nodes, Cluster
from ingest.census import load_load_nodes
from viz.cluster_visualization import (
    plot_clusters,
    plot_clusters_and_original_nodes,
    plot_bus_substations,
)


def load_config(config_path: str) -> dict:
    """Load YAML configuration file.

    Args:
        config_path: Path to YAML config file.

    Returns:
        Configuration dictionary.
    """
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def clusters_to_buses(clusters: list[Cluster], mw_per_capita: float = 2.0) -> list[Bus]:
    """Convert Cluster objects to Bus objects for pipeline integration.

    Assigns global bus IDs, substation numbers, and computes load from population.

    Args:
        clusters: List of Cluster instances from clustering algorithm.
        mw_per_capita: MW per person for load calculation (default 2.0).

    Returns:
        List of Bus instances with stage 1 fields populated:
          - bus_id, lat, lng, mw_load, sub_name, sub_num
    """
    buses = []

    for i, cluster in enumerate(clusters, start=1):
        # Compute load from population
        mw_load = cluster.total_population * mw_per_capita

        bus = Bus(
            bus_id=i,
            lat=cluster.cluster_lat,
            lng=cluster.cluster_lon,
            mw_load=mw_load,
            sub_name=f"Sub_{i}",
            sub_num=i,
        )
        buses.append(bus)

    return buses


def save_buses_csv(buses: list[Bus], csv_path: str) -> None:
    """Save Bus objects to CSV file.

    Args:
        buses: List of Bus instances.
        csv_path: Output CSV path.
    """
    import csv

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with open(csv_path, "w", newline="") as f:
        # Write stage 1 fields only
        fieldnames = ["bus_id", "lat", "lng", "mw_load", "sub_name", "sub_num"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for bus in buses:
            writer.writerow({
                "bus_id": bus.bus_id,
                "lat": bus.lat,
                "lng": bus.lng,
                "mw_load": bus.mw_load,
                "sub_name": bus.sub_name,
                "sub_num": bus.sub_num,
            })

    print(f"Saved {len(buses)} buses to {csv_path}")


def build_region(
    region_name: str,
    config_path: str,
    load_nodes_cache_path: str,
    output_dir: str = "data/processed",
) -> None:
    """Build clustered substations for a single region.

    Args:
        region_name: Name of the region (e.g., "Texas", "New York").
        config_path: Path to region's YAML config file.
        load_nodes_cache_path: Path to cached load nodes CSV.
        output_dir: Base directory for outputs.
    """
    print(f"\n{'='*60}")
    print(f"Building clustered substations for {region_name}")
    print(f"{'='*60}\n")

    # Load configuration
    config = load_config(config_path)
    n_target = config["substations"]["count"]
    bounds = config.get("bounds")

    print(f"Configuration:")
    print(f"  Target substations: {n_target}")
    print(f"  Bounds: {bounds}")

    # Load load nodes from cache
    if not os.path.exists(load_nodes_cache_path):
        raise FileNotFoundError(
            f"Load nodes cache not found: {load_nodes_cache_path}\n"
            f"Run ingest/census.py first to generate this file."
        )

    print(f"\nLoading load nodes from {load_nodes_cache_path}...")
    load_nodes = load_load_nodes(load_nodes_cache_path)
    print(f"Loaded {len(load_nodes)} load nodes")

    total_population = sum(n.population for n in load_nodes)
    total_load_mw = sum(n.load_mw for n in load_nodes)
    print(f"  Total population: {total_population:,}")
    print(f"  Total load: {total_load_mw:.1f} MW")

    # Run clustering
    print(f"\nRunning clustering to {n_target} clusters...")
    clusters = cluster_load_nodes(load_nodes, n_target, verbose=True)
    print(f"\nClustering complete: {len(clusters)} clusters created")

    # Verify cluster count
    assert len(clusters) == n_target, \
        f"Expected {n_target} clusters, got {len(clusters)}"

    # Convert clusters to buses
    print(f"\nConverting clusters to Bus objects...")
    mw_per_capita = config["census"]["load_factor_mw_per_person"]
    buses = clusters_to_buses(clusters, mw_per_capita)
    print(f"Created {len(buses)} bus objects")

    total_bus_load = sum(b.mw_load for b in buses)
    print(f"  Total bus load: {total_bus_load:.1f} MW")

    # Save results
    region_slug = region_name.lower().replace(" ", "_")
    buses_csv_path = os.path.join(output_dir, f"{region_slug}_substations.csv")
    save_buses_csv(buses, buses_csv_path)

    # Generate visualizations
    viz_dir = os.path.join(output_dir, "viz", region_slug)

    print(f"\nGenerating visualizations...")

    # Plot 1: Clusters with members
    plot1_path = os.path.join(viz_dir, f"{region_slug}_clusters.png")
    plot_clusters(
        clusters,
        title=f"{region_name} Load Node Clusters",
        out_path=plot1_path,
        bounds=bounds,
    )

    # Plot 2: Original nodes vs cluster centers
    plot2_path = os.path.join(viz_dir, f"{region_slug}_clustering_comparison.png")
    plot_clusters_and_original_nodes(
        load_nodes,
        clusters,
        title=f"{region_name} Clustering Result",
        out_path=plot2_path,
        bounds=bounds,
    )

    # Plot 3: Final bus substations
    plot3_path = os.path.join(viz_dir, f"{region_slug}_substations.png")
    plot_bus_substations(
        buses,
        title=f"{region_name} Load Substations",
        out_path=plot3_path,
        bounds=bounds,
    )

    print(f"\n{'='*60}")
    print(f"✓ {region_name} pipeline complete")
    print(f"{'='*60}\n")


def main():
    """Build clustered substations for Texas and New York."""
    # Texas
    build_region(
        region_name="Texas",
        config_path="config/texas.yaml",
        load_nodes_cache_path="data/processed/tx_load_nodes_filtered.csv",
        output_dir="data/processed",
    )

    # New York
    build_region(
        region_name="New York",
        config_path="config/new_york.yaml",
        load_nodes_cache_path="data/processed/ny_load_nodes.csv",
        output_dir="data/processed",
    )

    print("\n" + "="*60)
    print("✓ All regions complete!")
    print("="*60)
    print("\nOutputs:")
    print("  CSV Files:")
    print("    - data/processed/texas_substations.csv")
    print("    - data/processed/new_york_substations.csv")
    print("  Visualizations:")
    print("    - data/processed/viz/texas/")
    print("    - data/processed/viz/new_york/")
    print("    - data/processed/viz/tests/")


if __name__ == "__main__":
    main()
