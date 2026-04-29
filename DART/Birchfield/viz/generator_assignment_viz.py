"""
Visualization of generator assignments to substations.

Shows Type A (load-only) and Type B (with generation) substations on a map.
"""

import os
import csv
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


def plot_generator_assignments(
    substations_csv: str,
    assignments_csv: str,
    title: str = "Substation Types",
    out_path: str | None = None,
    bounds: dict | None = None,
) -> None:
    """Plot substations colored by type (load-only vs with generation).

    Args:
        substations_csv: Path to all substations CSV
        assignments_csv: Path to generator assignments CSV
        title: Plot title
        out_path: Output path for PNG
        bounds: Optional geographic bounds
    """
    # Load all substations
    all_subs = {}
    with open(substations_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bus_id = int(row['bus_id'])
            all_subs[bus_id] = {
                'lat': float(row['lat']),
                'lng': float(row['lng']),
                'mw_load': float(row['mw_load']),
                'has_gen': False,
                'gen_mw': 0.0,
            }

    # Load generator assignments
    with open(assignments_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bus_id = int(row['bus_id'])
            if bus_id in all_subs:
                all_subs[bus_id]['has_gen'] = True
                all_subs[bus_id]['gen_mw'] = float(row['assigned_gen_mw'])

    # Separate Type A (load-only) and Type B (with generation)
    type_a = [(s['lng'], s['lat'], s['mw_load'])
              for s in all_subs.values() if not s['has_gen']]
    type_b = [(s['lng'], s['lat'], s['mw_load'], s['gen_mw'])
              for s in all_subs.values() if s['has_gen']]

    print(f"Plotting: {len(type_a)} Type A (load-only), {len(type_b)} Type B (with gen)")

    # Create plot
    fig, ax = plt.subplots(figsize=(16, 12))

    # Plot Type A substations (load-only) - gray circles
    if type_a:
        lons_a, lats_a, loads_a = zip(*type_a)
        sizes_a = np.array(loads_a)
        sizes_a = np.clip(sizes_a / sizes_a.max() * 80, 10, 80)

        ax.scatter(
            lons_a, lats_a,
            c='#95a5a6',
            s=sizes_a,
            alpha=0.5,
            edgecolors='none',
            label=f'Type A: Load-only ({len(type_a)})',
            zorder=1,
        )

    # Plot Type B substations (with generation) - colored by gen/load ratio
    if type_b:
        lons_b, lats_b, loads_b, gens_b = zip(*type_b)

        # Calculate gen/load ratios
        ratios = np.array([g / max(l, 0.1) for g, l in zip(gens_b, loads_b)])

        sizes_b = np.array(loads_b)
        sizes_b = np.clip(sizes_b / sizes_b.max() * 200, 30, 200)

        sc = ax.scatter(
            lons_b, lats_b,
            c=ratios,
            s=sizes_b,
            cmap='plasma',
            alpha=0.8,
            edgecolors='black',
            linewidths=0.8,
            vmin=0,
            vmax=4,
            label=f'Type B: With generation ({len(type_b)})',
            zorder=2,
        )

        # Colorbar
        cbar = fig.colorbar(sc, ax=ax, shrink=0.7)
        cbar.set_label("Gen/Load Ratio", fontsize=11)

    if bounds:
        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])

    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)

    total_load = sum(s['mw_load'] for s in all_subs.values())
    total_gen = sum(s['gen_mw'] for s in all_subs.values())

    ax.set_title(
        f"{title}\n"
        f"{len(all_subs)} substations: {len(type_a)} Type A (load-only), "
        f"{len(type_b)} Type B (with gen)\n"
        f"Total load: {total_load:.0f} MW, Total gen: {total_gen:.0f} MW",
        fontsize=13
    )
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.3)

    # Legend
    ax.legend(loc='lower left', fontsize=10, framealpha=0.9)

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=200, bbox_inches='tight')
        print(f"Saved: {out_path}")

    plt.close(fig)


def plot_generation_comparison(
    texas_subs_csv: str,
    texas_assign_csv: str,
    ny_subs_csv: str,
    ny_assign_csv: str,
    out_path: str | None = None,
) -> None:
    """Create side-by-side comparison of Texas and New York generation assignments.

    Args:
        texas_subs_csv: Texas substations CSV
        texas_assign_csv: Texas assignments CSV
        ny_subs_csv: New York substations CSV
        ny_assign_csv: New York assignments CSV
        out_path: Output path for PNG
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 9))

    for ax, subs_csv, assign_csv, title, bounds in [
        (ax1, texas_subs_csv, texas_assign_csv, "Texas",
         {"lon_min": -107, "lon_max": -93, "lat_min": 25.5, "lat_max": 37}),
        (ax2, ny_subs_csv, ny_assign_csv, "New York",
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
                    'mw_load': float(row['mw_load']),
                    'has_gen': False,
                    'gen_mw': 0.0,
                }

        with open(assign_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                bus_id = int(row['bus_id'])
                if bus_id in all_subs:
                    all_subs[bus_id]['has_gen'] = True
                    all_subs[bus_id]['gen_mw'] = float(row['assigned_gen_mw'])

        # Separate types
        type_a = [(s['lng'], s['lat'], s['mw_load'])
                  for s in all_subs.values() if not s['has_gen']]
        type_b = [(s['lng'], s['lat'], s['gen_mw'])
                  for s in all_subs.values() if s['has_gen']]

        # Plot Type A
        if type_a:
            lons_a, lats_a, loads_a = zip(*type_a)
            ax.scatter(lons_a, lats_a, c='#bdc3c7', s=15, alpha=0.4,
                      edgecolors='none', label=f'Type A ({len(type_a)})')

        # Plot Type B
        if type_b:
            lons_b, lats_b, gens_b = zip(*type_b)
            sizes_b = np.array(gens_b)
            sizes_b = np.clip(sizes_b / sizes_b.max() * 300, 30, 300)

            ax.scatter(lons_b, lats_b, c='#e74c3c', s=sizes_b, alpha=0.8,
                      edgecolors='black', linewidths=1,
                      label=f'Type B ({len(type_b)})')

        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")

        total_gen = sum(s['gen_mw'] for s in all_subs.values())
        ax.set_title(f"{title}\n{len(all_subs)} substations, {total_gen:.0f} MW gen")
        mean_lat = np.mean(ax.get_ylim())
        ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
        ax.grid(True, linestyle=":", alpha=0.3)
        ax.legend(loc='lower left', fontsize=9)

    plt.suptitle("Generator Assignment Comparison: Texas vs New York",
                 fontsize=14, fontweight='bold', y=0.98)
    plt.tight_layout()

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=200, bbox_inches='tight')
        print(f"Saved: {out_path}")

    plt.close(fig)


if __name__ == "__main__":
    # Texas
    plot_generator_assignments(
        substations_csv="data/processed/texas_substations.csv",
        assignments_csv="data/processed/texas_generator_assignments.csv",
        title="Texas Generator Assignment",
        out_path="data/processed/viz/texas/texas_generator_assignments.png",
        bounds={"lon_min": -107, "lon_max": -93, "lat_min": 25.5, "lat_max": 37},
    )

    # New York
    plot_generator_assignments(
        substations_csv="data/processed/new_york_substations.csv",
        assignments_csv="data/processed/new_york_generator_assignments.csv",
        title="New York Generator Assignment",
        out_path="data/processed/viz/new_york/new_york_generator_assignments.png",
        bounds={"lon_min": -80, "lon_max": -71, "lat_min": 40, "lat_max": 45.5},
    )

    # Comparison
    plot_generation_comparison(
        texas_subs_csv="data/processed/texas_substations.csv",
        texas_assign_csv="data/processed/texas_generator_assignments.csv",
        ny_subs_csv="data/processed/new_york_substations.csv",
        ny_assign_csv="data/processed/new_york_generator_assignments.csv",
        out_path="data/processed/viz/generator_assignment_comparison.png",
    )

    print("\n✓ Generator assignment visualizations complete!")
