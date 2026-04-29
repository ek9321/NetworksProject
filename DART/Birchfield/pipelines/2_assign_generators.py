"""
Pipeline to assign generators to substations for Texas and New York.

This script:
  1. Loads clustered substations from Stage 1
  2. Loads EIA-860 generator data
  3. Assigns generators to Nb = 5.5% of substations
  4. Saves results and generates visualizations

Implements Stage 1b of the Birchfield pipeline (generator assignment).
"""

import os
import sys
import json
import csv

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.graph_types import Bus, GeneratorRecord
from core.generator_assignment import assign_generators_to_substations


def load_substations_csv(csv_path: str) -> list[Bus]:
    """Load substations from CSV file.

    Args:
        csv_path: Path to substations CSV (from clustering stage)

    Returns:
        List of Bus instances
    """
    buses = []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bus = Bus(
                bus_id=int(row['bus_id']),
                lat=float(row['lat']),
                lng=float(row['lng']),
                mw_load=float(row['mw_load']),
                sub_name=row['sub_name'],
                sub_num=int(row['sub_num']),
            )
            buses.append(bus)

    return buses


def save_assignments_csv(
    assignments,
    csv_path: str,
) -> None:
    """Save generator assignments to CSV.

    Args:
        assignments: List of GeneratorAssignment instances
        csv_path: Output CSV path
    """
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with open(csv_path, 'w', newline='') as f:
        fieldnames = [
            'bus_id', 'sub_name', 'lat', 'lng', 'mw_load',
            'target_gen_mw', 'assigned_gen_mw', 'shortfall_mw',
            'num_generators', 'generator_ids', 'generator_capacities'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for assignment in assignments:
            bus = assignment.substation
            gen_ids = [g.generator_id for g in assignment.assigned_generators]
            gen_caps = [g.nameplate_capacity_mw for g in assignment.assigned_generators]

            writer.writerow({
                'bus_id': bus.bus_id,
                'sub_name': bus.sub_name,
                'lat': bus.lat,
                'lng': bus.lng,
                'mw_load': bus.mw_load,
                'target_gen_mw': assignment.target_gen_mw,
                'assigned_gen_mw': assignment.assigned_gen_mw,
                'shortfall_mw': assignment.shortfall_mw,
                'num_generators': len(assignment.assigned_generators),
                'generator_ids': ';'.join(gen_ids),
                'generator_capacities': ';'.join(f"{c:.1f}" for c in gen_caps),
            })

    print(f"Saved {len(assignments)} assignments to {csv_path}")


def save_summary_json(summary: dict, json_path: str) -> None:
    """Save assignment summary to JSON.

    Args:
        summary: Summary dictionary
        json_path: Output JSON path
    """
    os.makedirs(os.path.dirname(json_path), exist_ok=True)

    with open(json_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"Saved summary to {json_path}")


def assign_generators_for_region(
    region_name: str,
    substations_csv: str,
    state_code: str,
    eia_generators: list[GeneratorRecord],
    output_dir: str = "data/processed",
    random_seed: int = 42,
) -> None:
    """Assign generators for a single region.

    Args:
        region_name: Name of region (e.g., "Texas")
        substations_csv: Path to clustered substations CSV
        state_code: State code for filtering generators (e.g., "TX")
        eia_generators: Full list of EIA generators
        output_dir: Output directory
        random_seed: Random seed for reproducibility
    """
    print(f"\n{'='*60}")
    print(f"Assigning generators for {region_name}")
    print(f"{'='*60}\n")

    # Load substations
    print(f"Loading substations from {substations_csv}...")
    substations = load_substations_csv(substations_csv)
    print(f"  Loaded {len(substations)} substations")

    # Filter generators to this state
    state_generators = [g for g in eia_generators if g.state == state_code]
    print(f"  Filtered to {len(state_generators)} generators in {state_code}")

    # Run assignment
    print(f"\nRunning generator assignment...")
    assignments, summary = assign_generators_to_substations(
        substations,
        state_generators,
        fraction_with_generation=0.055,  # 5.5% per Birchfield
        random_seed=random_seed,
        max_distance_km=None,  # Unlimited per plan
        verbose=True,
    )

    # Save results
    region_slug = region_name.lower().replace(" ", "_")
    assignments_csv = os.path.join(output_dir, f"{region_slug}_generator_assignments.csv")
    summary_json = os.path.join(output_dir, f"{region_slug}_generator_summary.json")

    save_assignments_csv(assignments, assignments_csv)
    save_summary_json(summary, summary_json)

    print(f"\n{'='*60}")
    print(f"✓ {region_name} generator assignment complete")
    print(f"{'='*60}\n")


def main():
    """Assign generators for Texas and New York."""

    # Load EIA generators once
    print("Loading EIA-860 generator data...")
    from ingest.eia860 import load_generators_csv
    eia_generators = load_generators_csv("data/processed/eia860_generators.csv")
    print(f"Loaded {len(eia_generators)} generators\n")

    # Texas
    assign_generators_for_region(
        region_name="Texas",
        substations_csv="data/processed/texas_substations.csv",
        state_code="TX",
        eia_generators=eia_generators,
        output_dir="data/processed",
        random_seed=42,
    )

    # New York
    assign_generators_for_region(
        region_name="New York",
        substations_csv="data/processed/new_york_substations.csv",
        state_code="NY",
        eia_generators=eia_generators,
        output_dir="data/processed",
        random_seed=42,
    )

    print(f"\n{'='*60}")
    print("✓ All regions complete!")
    print(f"{'='*60}")
    print("\nOutputs:")
    print("  - data/processed/texas_generator_assignments.csv")
    print("  - data/processed/texas_generator_summary.json")
    print("  - data/processed/new_york_generator_assignments.csv")
    print("  - data/processed/new_york_generator_summary.json")


if __name__ == "__main__":
    main()
