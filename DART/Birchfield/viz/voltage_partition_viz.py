"""
Visualize voltage partition results.

Shows:
  - Substations colored by voltage level (115 kV only vs. 345 kV + 115 kV)
  - Generator substations vs. load-only substations
  - Substation type distribution
"""

import os
import csv
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def load_substations_with_buses(csv_path: str) -> list:
    """Load substations with voltage assignments."""
    substations = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sub = {
                'substation_id': int(row['substation_id']),
                'lat': float(row['lat']),
                'lng': float(row['lng']),
                'mw_load': float(row['mw_load']),
                'total_gen_mw': float(row['total_assigned_gen_mw']),
                'type': row['substation_type'],
                'voltages': []
            }

            # Extract voltage levels
            for key, val in row.items():
                if key.startswith('has_high_voltage_') and val.lower() == 'true':
                    kv = int(key.replace('has_high_voltage_', '').replace('kv', ''))
                    sub['voltages'].append(kv)

            sub['voltages'].sort(reverse=True)
            substations.append(sub)

    return substations


def plot_voltage_partition(region_name: str, output_dir: str = "data/processed"):
    """Create voltage partition visualization for a region."""

    region_slug = region_name.lower().replace(" ", "_")
    subs_path = os.path.join(output_dir, f"{region_slug}_substations_with_buses.csv")

    substations = load_substations_with_buses(subs_path)

    # Separate by voltage level and type
    single_voltage = []  # 115 kV only
    dual_voltage = []    # 345 kV + 115 kV

    for sub in substations:
        if len(sub['voltages']) == 1:
            single_voltage.append(sub)
        else:
            dual_voltage.append(sub)

    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8))

    # Left plot: Voltage levels
    ax1.set_title(f'{region_name} - Voltage Partition\n{len(dual_voltage)} substations with 345 kV ({len(dual_voltage)/len(substations)*100:.1f}%)',
                  fontsize=14, weight='bold')
    ax1.set_xlabel('Longitude', fontsize=12)
    ax1.set_ylabel('Latitude', fontsize=12)
    ax1.grid(True, alpha=0.3)

    # Plot single-voltage substations (115 kV only)
    if single_voltage:
        lngs = [s['lng'] for s in single_voltage]
        lats = [s['lat'] for s in single_voltage]
        ax1.scatter(lngs, lats, c='lightblue', s=10, alpha=0.6, label='115 kV only')

    # Plot dual-voltage substations (345 kV + 115 kV)
    if dual_voltage:
        lngs = [s['lng'] for s in dual_voltage]
        lats = [s['lat'] for s in dual_voltage]
        ax1.scatter(lngs, lats, c='red', s=30, alpha=0.8, marker='^', label='345 kV + 115 kV')

    ax1.legend(loc='upper right', fontsize=10)

    # Right plot: Substation types
    ax2.set_title(f'{region_name} - Substation Types', fontsize=14, weight='bold')
    ax2.set_xlabel('Longitude', fontsize=12)
    ax2.set_ylabel('Latitude', fontsize=12)
    ax2.grid(True, alpha=0.3)

    # Separate by type
    type_a = [s for s in substations if s['type'] == 'A']
    type_b = [s for s in substations if s['type'] == 'B']
    type_g = [s for s in substations if s['type'] == 'g']

    # Plot Type A (load-only)
    if type_a:
        lngs = [s['lng'] for s in type_a]
        lats = [s['lat'] for s in type_a]
        ax2.scatter(lngs, lats, c='lightblue', s=10, alpha=0.6, label=f'Type A (load-only): {len(type_a)}')

    # Plot Type B (load + gen)
    if type_b:
        lngs = [s['lng'] for s in type_b]
        lats = [s['lat'] for s in type_b]
        ax2.scatter(lngs, lats, c='orange', s=30, alpha=0.8, marker='s', label=f'Type B (load+gen): {len(type_b)}')

    # Plot Type g (gen-only)
    if type_g:
        lngs = [s['lng'] for s in type_g]
        lats = [s['lat'] for s in type_g]
        ax2.scatter(lngs, lats, c='green', s=30, alpha=0.8, marker='D', label=f'Type g (gen-only): {len(type_g)}')

    ax2.legend(loc='upper right', fontsize=10)

    plt.tight_layout()

    # Save
    viz_dir = f"viz/{region_slug}"
    os.makedirs(viz_dir, exist_ok=True)
    output_path = os.path.join(viz_dir, 'voltage_partition.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Saved voltage partition visualization to {output_path}")

    plt.close()

    # Print statistics
    print(f"\n{region_name} Statistics:")
    print(f"  Total substations: {len(substations)}")
    print(f"  115 kV only: {len(single_voltage)} ({len(single_voltage)/len(substations)*100:.1f}%)")
    print(f"  345 kV + 115 kV: {len(dual_voltage)} ({len(dual_voltage)/len(substations)*100:.1f}%)")
    print(f"  Type A (load-only): {len(type_a)} ({len(type_a)/len(substations)*100:.1f}%)")
    print(f"  Type B (load+gen): {len(type_b)} ({len(type_b)/len(substations)*100:.1f}%)")
    print(f"  Type g (gen-only): {len(type_g)} ({len(type_g)/len(substations)*100:.1f}%)")
    print()


def main():
    """Create voltage partition visualizations for all regions."""

    print("="*70)
    print("VOLTAGE PARTITION VISUALIZATION")
    print("="*70)
    print()

    # Texas
    plot_voltage_partition("Texas")

    # New York
    plot_voltage_partition("New York")

    print("="*70)
    print("✓ All visualizations complete")
    print("="*70)


if __name__ == "__main__":
    main()
