"""
Pipeline to cluster unassigned generators into Type-g substations.

This script:
  1. Loads all EIA generators and Type B assignments
  2. Identifies unassigned generators
  3. Clusters them into N_g = 5% of total substations
  4. Saves results with standardized column names

Implements Stage 1c of the Birchfield pipeline (Type-g substations).
"""

import os
import sys
import csv
import json

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.graph_types import GeneratorRecord
from core.remaining_generator_clustering import cluster_remaining_generators
from ingest.eia860 import load_generators_csv


def load_assigned_generator_ids(assignments_csv: str) -> set[str]:
    """Load set of generator IDs already assigned to Type B substations.

    Args:
        assignments_csv: Path to generator assignments CSV

    Returns:
        Set of assigned generator IDs
    """
    assigned_ids = set()

    with open(assignments_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Generator IDs are semicolon-delimited
            ids_str = row['generator_ids']
            if ids_str:
                ids = ids_str.split(';')
                assigned_ids.update(ids)

    return assigned_ids


def save_type_g_substations_csv(
    clusters,
    csv_path: str,
) -> None:
    """Save Type-g substations to CSV.

    Args:
        clusters: List of GeneratorCluster instances
        csv_path: Output CSV path
    """
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with open(csv_path, 'w', newline='') as f:
        fieldnames = [
            'substation_id',
            'generator_ids',
            'lat',
            'lng',
            'total_capacity_mw',
            'num_generators',
            'fuel_type',
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, cluster in enumerate(clusters, start=1):
            writer.writerow({
                'substation_id': i,
                'generator_ids': ';'.join(cluster.generator_ids),
                'lat': cluster.centroid_lat,
                'lng': cluster.centroid_lon,
                'total_capacity_mw': cluster.total_capacity_mw,
                'num_generators': len(cluster.generator_ids),
                'fuel_type': cluster.fuel_type,
            })

    print(f"Saved {len(clusters)} Type-g substations to {csv_path}")


def save_summary_csv(summary: dict, csv_path: str) -> None:
    """Save clustering summary to CSV.

    Args:
        summary: Summary dictionary
        csv_path: Output CSV path
    """
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'requested_n_g',
            'actual_n_g',
            'total_generators_clustered',
            'total_capacity_mw',
            'num_merges',
            'warnings',
        ])
        writer.writeheader()

        writer.writerow({
            'requested_n_g': summary['requested_n_g'],
            'actual_n_g': summary['actual_n_g'],
            'total_generators_clustered': summary['total_generators_clustered'],
            'total_capacity_mw': summary['total_capacity_mw'],
            'num_merges': summary['num_merges'],
            'warnings': ';'.join(summary['warnings']) if summary['warnings'] else '',
        })

    print(f"Saved summary to {csv_path}")


def cluster_remaining_for_region(
    region_name: str,
    state_code: str,
    total_substations: int,
    all_generators: list[GeneratorRecord],
    assignments_csv: str,
    output_dir: str = "data/processed",
    random_seed: int = 42,
) -> None:
    """Cluster unassigned generators for a single region.

    Args:
        region_name: Name of region (e.g., "Texas")
        state_code: State code for filtering generators (e.g., "TX")
        total_substations: Total number of substations (for calculating N_g)
        all_generators: Full list of EIA generators
        assignments_csv: Path to Type B generator assignments
        output_dir: Output directory
        random_seed: Random seed for reproducibility
    """
    print(f"\n{'='*60}")
    print(f"Clustering remaining generators for {region_name}")
    print(f"{'='*60}\n")

    # Filter generators to this state
    state_generators = [g for g in all_generators if g.state == state_code]
    print(f"Total generators in {state_code}: {len(state_generators)}")

    # Load assigned generator IDs
    assigned_ids = load_assigned_generator_ids(assignments_csv)
    print(f"Generators already assigned to Type B: {len(assigned_ids)}")

    # Filter to unassigned generators
    unassigned = [g for g in state_generators if g.generator_id not in assigned_ids]
    print(f"Unassigned generators: {len(unassigned)}")

    if not unassigned:
        print("WARNING: No unassigned generators! Skipping clustering.")
        return

    # Calculate N_g = 5% of total substations
    n_g = max(1, int(total_substations * 0.05))
    print(f"Target N_g (5% of {total_substations}): {n_g}")

    # Run clustering
    print(f"\nRunning clustering with fuel homogeneity constraints...")
    clusters, summary = cluster_remaining_generators(
        unassigned,
        n_g,
        enforce_fuel_homogeneity=True,
        exempt_fuel_types=["NUCLEAR", "HYDRO", "WIND", "SOLAR", "OTHER_RENEWABLE"],
        random_seed=random_seed,
        verbose=True,
    )

    # Save results
    region_slug = region_name.lower().replace(" ", "_")
    type_g_csv = os.path.join(output_dir, f"{region_slug}_type_g_substations.csv")
    summary_csv = os.path.join(output_dir, f"{region_slug}_type_g_summary.csv")

    save_type_g_substations_csv(clusters, type_g_csv)
    save_summary_csv(summary, summary_csv)

    # Also save full summary as JSON for easier inspection
    summary_json = os.path.join(output_dir, f"{region_slug}_type_g_summary.json")
    with open(summary_json, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"Saved detailed summary to {summary_json}")

    print(f"\n{'='*60}")
    print(f"✓ {region_name} Type-g clustering complete")
    print(f"{'='*60}\n")


def main():
    """Cluster remaining generators for Texas and New York."""

    # Load EIA generators once
    print("Loading EIA-860 generator data...")
    from ingest.eia860 import load_generators_csv
    all_generators = load_generators_csv("data/processed/eia860_generators.csv")
    print(f"Loaded {len(all_generators)} generators\n")

    # Texas
    cluster_remaining_for_region(
        region_name="Texas",
        state_code="TX",
        total_substations=1250,  # From config
        all_generators=all_generators,
        assignments_csv="data/processed/texas_generator_assignments.csv",
        output_dir="data/processed",
        random_seed=42,
    )

    # New York
    cluster_remaining_for_region(
        region_name="New York",
        state_code="NY",
        total_substations=600,  # From config
        all_generators=all_generators,
        assignments_csv="data/processed/new_york_generator_assignments.csv",
        output_dir="data/processed",
        random_seed=42,
    )

    print(f"\n{'='*60}")
    print("✓ All regions complete!")
    print(f"{'='*60}")
    print("\nOutputs:")
    print("  - data/processed/texas_type_g_substations.csv")
    print("  - data/processed/texas_type_g_summary.csv")
    print("  - data/processed/new_york_type_g_substations.csv")
    print("  - data/processed/new_york_type_g_summary.csv")


if __name__ == "__main__":
    main()
