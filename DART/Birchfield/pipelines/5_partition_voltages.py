"""
Pipeline to partition substations by voltage level and create buses.

This script:
  1. Loads all substations (Type A, B, g)
  2. Assigns voltage levels to substations via weighted sampling
  3. Creates buses at appropriate voltages
  4. Creates internal transformers
  5. Saves detailed CSV outputs for topology generation

Implements Stage 2 of the Birchfield pipeline (Voltage Partitioning).
"""

import os
import sys
import csv
import json
import yaml

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.voltage_partition import voltage_partition


def load_config(config_path: str) -> dict:
    """Load YAML configuration."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def save_substations_with_buses_csv(substations, csv_path: str) -> None:
    """Save substation metadata with voltage assignments."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    # Get all voltage levels from substations
    all_voltages = set()
    for sub in substations:
        all_voltages.update(sub.has_high_voltage.keys())
    voltage_levels = sorted(all_voltages, reverse=True)

    # Build field names
    fieldnames = [
        'substation_id',
        'lat',
        'lng',
        'mw_load',
        'assigned_generators',
        'total_assigned_gen_mw',
        'substation_type',
    ]

    # Add has_high_voltage_<V> columns
    for v in voltage_levels:
        fieldnames.append(f'has_high_voltage_{v}kv')

    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for sub in substations:
            row = {
                'substation_id': sub.substation_id,
                'lat': sub.lat,
                'lng': sub.lng,
                'mw_load': sub.mw_load,
                'assigned_generators': ';'.join(sub.assigned_generator_ids),
                'total_assigned_gen_mw': sub.total_gen_mw,
                'substation_type': sub.substation_type,
            }

            for v in voltage_levels:
                row[f'has_high_voltage_{v}kv'] = sub.has_high_voltage.get(v, False)

            writer.writerow(row)

    print(f"Saved {len(substations)} substations to {csv_path}")


def save_buses_csv(buses, csv_path: str) -> None:
    """Save bus definitions."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with open(csv_path, 'w', newline='') as f:
        fieldnames = [
            'bus_id',
            'substation_id',
            'voltage_kv',
            'role',
            'connected_load_mw',
            'connected_generator_ids',
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for bus in buses:
            writer.writerow({
                'bus_id': bus.bus_id,
                'substation_id': bus.substation_id,
                'voltage_kv': bus.voltage_kv,
                'role': bus.role,
                'connected_load_mw': bus.connected_load_mw,
                'connected_generator_ids': ';'.join(bus.connected_generator_ids),
            })

    print(f"Saved {len(buses)} buses to {csv_path}")


def save_transformers_csv(transformers, csv_path: str) -> None:
    """Save internal transformer definitions."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with open(csv_path, 'w', newline='') as f:
        fieldnames = [
            'transformer_id',
            'substation_id',
            'from_bus_id',
            'to_bus_id',
            'from_kv',
            'to_kv',
            'rating_mva',
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for xfmr in transformers:
            writer.writerow({
                'transformer_id': xfmr.transformer_id,
                'substation_id': xfmr.substation_id,
                'from_bus_id': xfmr.from_bus_id,
                'to_bus_id': xfmr.to_bus_id,
                'from_kv': xfmr.from_kv,
                'to_kv': xfmr.to_kv,
                'rating_mva': xfmr.rating_mva,
            })

    print(f"Saved {len(transformers)} transformers to {csv_path}")


def save_summary_csv(summary: dict, csv_path: str) -> None:
    """Save voltage partition summary."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=summary.keys())
        writer.writeheader()
        writer.writerow(summary)

    print(f"Saved summary to {csv_path}")


def partition_region(
    region_name: str,
    config_path: str,
    output_dir: str = "data/processed",
) -> None:
    """Execute voltage partition for a single region."""

    print(f"\n{'='*70}")
    print(f"Voltage Partition: {region_name}")
    print(f"{'='*70}\n")

    # Load config
    config = load_config(config_path)
    voltage_config = config['voltage']
    topology_config = config['topology']

    voltage_levels = voltage_config['levels']
    pct_with_high = voltage_config['pct_substations_with_high_voltage']
    random_seed = topology_config.get('random_seed', 42)

    print(f"Configuration:")
    print(f"  Voltage levels: {voltage_levels}")
    print(f"  High-voltage percentages: {pct_with_high}")
    print(f"  Random seed: {random_seed}")

    # Build input paths
    region_slug = region_name.lower().replace(" ", "_")
    substations_csv = os.path.join(output_dir, f"{region_slug}_substations.csv")
    type_b_csv = os.path.join(output_dir, f"{region_slug}_generator_assignments.csv")
    type_g_csv = os.path.join(output_dir, f"{region_slug}_type_g_substations.csv")

    # Run voltage partition
    substations, buses, transformers, summary = voltage_partition(
        substations_csv=substations_csv,
        type_b_assignments_csv=type_b_csv,
        type_g_substations_csv=type_g_csv,
        voltage_levels=voltage_levels,
        pct_with_high_voltage=pct_with_high,
        random_seed=random_seed,
        verbose=True,
    )

    # Save outputs
    print("\nSaving outputs...")

    # Substations with voltage assignments
    subs_out = os.path.join(output_dir, f"{region_slug}_substations_with_buses.csv")
    save_substations_with_buses_csv(substations, subs_out)

    # Buses
    buses_out = os.path.join(output_dir, f"{region_slug}_buses.csv")
    save_buses_csv(buses, buses_out)

    # Transformers
    xfmr_out = os.path.join(output_dir, f"{region_slug}_transformers.csv")
    save_transformers_csv(transformers, xfmr_out)

    # Summary
    summary_csv = os.path.join(output_dir, f"{region_slug}_voltage_partition_summary.csv")
    save_summary_csv(summary, summary_csv)

    # Also save as JSON for inspection
    summary_json = os.path.join(output_dir, f"{region_slug}_voltage_partition_summary.json")
    with open(summary_json, 'w') as f:
        # Convert voltage_levels list to JSON-serializable format
        json_summary = {k: (list(v) if isinstance(v, list) else v) for k, v in summary.items()}
        json.dump(json_summary, f, indent=2)
    print(f"Saved summary to {summary_json}")

    print(f"\n{'='*70}")
    print(f"✓ {region_name} voltage partition complete")
    print(f"{'='*70}\n")


def main():
    """Execute voltage partition for Texas and New York."""

    print("="*70)
    print("STAGE 2: VOLTAGE PARTITION")
    print("="*70)

    # Texas
    partition_region(
        region_name="Texas",
        config_path="config/texas.yaml",
        output_dir="data/processed",
    )

    # New York
    partition_region(
        region_name="New York",
        config_path="config/new_york.yaml",
        output_dir="data/processed",
    )

    print(f"\n{'='*70}")
    print("✓ All regions complete!")
    print(f"{'='*70}")
    print("\nOutputs:")
    print("  Substations with voltages:")
    print("    - data/processed/texas_substations_with_buses.csv")
    print("    - data/processed/new_york_substations_with_buses.csv")
    print("  Buses:")
    print("    - data/processed/texas_buses.csv")
    print("    - data/processed/new_york_buses.csv")
    print("  Transformers:")
    print("    - data/processed/texas_transformers.csv")
    print("    - data/processed/new_york_transformers.csv")


if __name__ == "__main__":
    main()
