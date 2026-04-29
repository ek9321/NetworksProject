"""
Visualization of complete substation synthesis results.

Shows all three substation types:
  - Type A: Load-only substations (gray)
  - Type B: Substations with generation (blue/green)
  - Type g: Generator-only substations (red/orange)
"""

import os
import csv
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


def plot_all_substation_types(
    substations_csv: str,
    type_b_assignments_csv: str,
    type_g_substations_csv: str,
    title: str = "Complete Substation Synthesis",
    out_path: str | None = None,
    bounds: dict | None = None,
) -> None:
    """Plot all three substation types on a single map.

    Args:
        substations_csv: Path to all substations CSV (from clustering)
        type_b_assignments_csv: Path to Type B generator assignments
        type_g_substations_csv: Path to Type-g substations
        title: Plot title
        out_path: Output path for PNG
        bounds: Optional geographic bounds
    """
    # Load all substations (Type A + Type B)
    all_subs = {}
    with open(substations_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bus_id = int(row['bus_id'])
            all_subs[bus_id] = {
                'lat': float(row['lat']),
                'lng': float(row['lng']),
                'mw_load': float(row['mw_load']),
                'type': 'A',  # Default to Type A
                'gen_mw': 0.0,
            }

    # Mark Type B substations
    with open(type_b_assignments_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bus_id = int(row['bus_id'])
            if bus_id in all_subs:
                all_subs[bus_id]['type'] = 'B'
                all_subs[bus_id]['gen_mw'] = float(row['assigned_gen_mw'])

    # Load Type-g substations
    type_g_subs = []
    with open(type_g_substations_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            type_g_subs.append({
                'lat': float(row['lat']),
                'lng': float(row['lng']),
                'capacity_mw': float(row['total_capacity_mw']),
                'fuel': row['fuel_type'],
            })

    # Separate by type
    type_a = [(s['lng'], s['lat'], s['mw_load'])
              for s in all_subs.values() if s['type'] == 'A']
    type_b = [(s['lng'], s['lat'], s['mw_load'], s['gen_mw'])
              for s in all_subs.values() if s['type'] == 'B']
    type_g = [(s['lng'], s['lat'], s['capacity_mw'])
              for s in type_g_subs]

    print(f"Plotting: {len(type_a)} Type A, {len(type_b)} Type B, {len(type_g)} Type g")

    # Create plot
    fig, ax = plt.subplots(figsize=(18, 13))

    # Plot Type A (load-only) - small gray dots
    if type_a:
        lons_a, lats_a, loads_a = zip(*type_a)
        sizes_a = np.array(loads_a)
        if sizes_a.max() > 0:
            sizes_a = np.clip(sizes_a / sizes_a.max() * 40, 8, 40)
        else:
            sizes_a = np.full(len(type_a), 15)

        ax.scatter(
            lons_a, lats_a,
            c='#bdc3c7',
            s=sizes_a,
            alpha=0.4,
            edgecolors='none',
            label=f'Type A: Load-only ({len(type_a)})',
            zorder=1,
        )

    # Plot Type B (with generation) - blue/green, medium size
    if type_b:
        lons_b, lats_b, loads_b, gens_b = zip(*type_b)
        sizes_b = np.array(loads_b)
        if sizes_b.max() > 0:
            sizes_b = np.clip(sizes_b / sizes_b.max() * 120, 25, 120)
        else:
            sizes_b = np.full(len(type_b), 50)

        ax.scatter(
            lons_b, lats_b,
            c='#3498db',
            s=sizes_b,
            alpha=0.7,
            edgecolors='black',
            linewidths=0.6,
            label=f'Type B: Load + Gen ({len(type_b)})',
            zorder=2,
        )

    # Plot Type g (generator-only) - red/orange, sized by capacity
    if type_g:
        lons_g, lats_g, caps_g = zip(*type_g)
        sizes_g = np.array(caps_g)
        if sizes_g.max() > 0:
            sizes_g = np.clip(sizes_g / sizes_g.max() * 300, 40, 300)
        else:
            sizes_g = np.full(len(type_g), 80)

        ax.scatter(
            lons_g, lats_g,
            c='#e74c3c',
            s=sizes_g,
            alpha=0.8,
            edgecolors='black',
            linewidths=1.0,
            marker='s',  # Square markers for Type g
            label=f'Type g: Gen-only ({len(type_g)})',
            zorder=3,
        )

    if bounds:
        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])

    ax.set_xlabel("Longitude", fontsize=13)
    ax.set_ylabel("Latitude", fontsize=13)

    total_subs = len(all_subs)
    total_load = sum(s['mw_load'] for s in all_subs.values())
    total_gen_b = sum(s['gen_mw'] for s in all_subs.values())
    total_gen_g = sum(s['capacity_mw'] for s in type_g_subs)
    total_gen = total_gen_b + total_gen_g

    ax.set_title(
        f"{title}\n"
        f"{total_subs} load substations (A+B) + {len(type_g)} gen-only (g) = "
        f"{total_subs + len(type_g)} total\n"
        f"Load: {total_load:.0f} MW  |  Generation: {total_gen:.0f} MW  "
        f"(B: {total_gen_b:.0f} MW, g: {total_gen_g:.0f} MW)",
        fontsize=13,
        fontweight='bold'
    )
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.3)

    # Legend with better styling
    ax.legend(loc='lower left', fontsize=11, framealpha=0.95,
             edgecolor='black', fancybox=True)

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=200, bbox_inches='tight')
        print(f"Saved: {out_path}")

    plt.close(fig)


def plot_comparison_all_types(
    texas_subs_csv: str,
    texas_b_csv: str,
    texas_g_csv: str,
    ny_subs_csv: str,
    ny_b_csv: str,
    ny_g_csv: str,
    out_path: str | None = None,
) -> None:
    """Create side-by-side comparison of Texas and New York with all types.

    Args:
        texas_subs_csv: Texas substations
        texas_b_csv: Texas Type B assignments
        texas_g_csv: Texas Type g
        ny_subs_csv: New York substations
        ny_b_csv: New York Type B assignments
        ny_g_csv: New York Type g
        out_path: Output path
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(22, 10))

    for ax, subs_csv, b_csv, g_csv, title, bounds in [
        (ax1, texas_subs_csv, texas_b_csv, texas_g_csv, "Texas",
         {"lon_min": -107, "lon_max": -93, "lat_min": 25.5, "lat_max": 37}),
        (ax2, ny_subs_csv, ny_b_csv, ny_g_csv, "New York",
         {"lon_min": -80, "lon_max": -71, "lat_min": 40, "lat_max": 45.5}),
    ]:
        # Load data
        all_subs = {}
        with open(subs_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                bus_id = int(row['bus_id'])
                all_subs[bus_id] = {
                    'lat': float(row['lat']),
                    'lng': float(row['lng']),
                    'type': 'A',
                    'size': 10,
                }

        with open(b_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                bus_id = int(row['bus_id'])
                if bus_id in all_subs:
                    all_subs[bus_id]['type'] = 'B'
                    all_subs[bus_id]['size'] = 50

        type_g = []
        with open(g_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                type_g.append({
                    'lat': float(row['lat']),
                    'lng': float(row['lng']),
                    'size': 100,
                })

        # Plot
        type_a = [s for s in all_subs.values() if s['type'] == 'A']
        type_b = [s for s in all_subs.values() if s['type'] == 'B']

        if type_a:
            ax.scatter([s['lng'] for s in type_a], [s['lat'] for s in type_a],
                      c='#bdc3c7', s=[s['size'] for s in type_a], alpha=0.4,
                      edgecolors='none', label=f'Type A ({len(type_a)})')

        if type_b:
            ax.scatter([s['lng'] for s in type_b], [s['lat'] for s in type_b],
                      c='#3498db', s=[s['size'] for s in type_b], alpha=0.7,
                      edgecolors='black', linewidths=0.5,
                      label=f'Type B ({len(type_b)})')

        if type_g:
            ax.scatter([s['lng'] for s in type_g], [s['lat'] for s in type_g],
                      c='#e74c3c', s=[s['size'] for s in type_g], alpha=0.8,
                      marker='s', edgecolors='black', linewidths=0.8,
                      label=f'Type g ({len(type_g)})')

        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_title(f"{title}\n{len(all_subs)} load + {len(type_g)} gen-only")
        mean_lat = np.mean(ax.get_ylim())
        ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
        ax.grid(True, linestyle=":", alpha=0.3)
        ax.legend(loc='lower left', fontsize=9, framealpha=0.9)

    plt.suptitle("Complete Substation Synthesis: Texas vs New York",
                 fontsize=15, fontweight='bold', y=0.98)
    plt.tight_layout()

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=200, bbox_inches='tight')
        print(f"Saved: {out_path}")

    plt.close(fig)


if __name__ == "__main__":
    # Texas complete visualization
    plot_all_substation_types(
        substations_csv="data/processed/texas_substations.csv",
        type_b_assignments_csv="data/processed/texas_generator_assignments.csv",
        type_g_substations_csv="data/processed/texas_type_g_substations.csv",
        title="Texas Complete Substation Synthesis",
        out_path="data/processed/viz/texas/texas_all_substations.png",
        bounds={"lon_min": -107, "lon_max": -93, "lat_min": 25.5, "lat_max": 37},
    )

    # New York complete visualization
    plot_all_substation_types(
        substations_csv="data/processed/new_york_substations.csv",
        type_b_assignments_csv="data/processed/new_york_generator_assignments.csv",
        type_g_substations_csv="data/processed/new_york_type_g_substations.csv",
        title="New York Complete Substation Synthesis",
        out_path="data/processed/viz/new_york/new_york_all_substations.png",
        bounds={"lon_min": -80, "lon_max": -71, "lat_min": 40, "lat_max": 45.5},
    )

    # Side-by-side comparison
    plot_comparison_all_types(
        texas_subs_csv="data/processed/texas_substations.csv",
        texas_b_csv="data/processed/texas_generator_assignments.csv",
        texas_g_csv="data/processed/texas_type_g_substations.csv",
        ny_subs_csv="data/processed/new_york_substations.csv",
        ny_b_csv="data/processed/new_york_generator_assignments.csv",
        ny_g_csv="data/processed/new_york_type_g_substations.csv",
        out_path="data/processed/viz/complete_substation_synthesis_comparison.png",
    )

    print("\n✓ Complete substation synthesis visualizations complete!")
