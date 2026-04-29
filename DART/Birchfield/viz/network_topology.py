"""
Visualization of synthetic grid network topology.

Plots buses and transmission lines/transformers from SourceData CSVs.
Handles both the Texas-7k reference grid and our generated substations.
"""

import os
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import pandas as pd
import numpy as np


def plot_network_topology(
    bus_csv: str,
    branch_csv: str,
    title: str = "Network Topology",
    out_path: str | None = None,
    bounds: dict | None = None,
    max_branches: int | None = None,
    voltage_filter: float | None = None,
) -> None:
    """Plot network topology from bus and branch CSV files.

    Args:
        bus_csv: Path to bus.csv file with Bus ID, lat, lng columns.
        branch_csv: Path to branch.csv file with From Bus, To Bus columns.
        title: Plot title.
        out_path: If provided, save figure to this path.
        bounds: Optional dict with lat_min, lat_max, lon_min, lon_max.
        max_branches: If provided, only plot first N branches (for speed).
        voltage_filter: If provided, only show buses at this voltage level.
    """
    print(f"Loading network data from {os.path.dirname(bus_csv)}...")

    # Load buses
    buses = pd.read_csv(bus_csv)
    print(f"  Loaded {len(buses)} buses")

    # Filter by voltage if requested
    if voltage_filter is not None and 'BaseKV' in buses.columns:
        buses = buses[buses['BaseKV'] == voltage_filter]
        print(f"  Filtered to {len(buses)} buses at {voltage_filter} kV")

    # Create bus ID to coordinates mapping
    bus_coords = {}
    for _, row in buses.iterrows():
        bus_id = row['Bus ID']
        bus_coords[bus_id] = (row['lng'], row['lat'])

    # Load branches
    branches = pd.read_csv(branch_csv)
    print(f"  Loaded {len(branches)} branches")

    if max_branches is not None and len(branches) > max_branches:
        branches = branches.head(max_branches)
        print(f"  Limited to first {max_branches} branches for visualization")

    # Separate lines and transformers
    if 'Branch Device Type' in branches.columns:
        lines = branches[branches['Branch Device Type'] == 'Line']
        transformers = branches[branches['Branch Device Type'] == 'Transformer']
        print(f"  Lines: {len(lines)}, Transformers: {len(transformers)}")
    else:
        lines = branches
        transformers = pd.DataFrame()

    # Create plot
    fig, ax = plt.subplots(figsize=(16, 12))

    # Plot branches (transmission lines)
    line_count = 0
    for _, row in lines.iterrows():
        from_bus = row['From Bus']
        to_bus = row['To Bus']

        if from_bus in bus_coords and to_bus in bus_coords:
            from_lon, from_lat = bus_coords[from_bus]
            to_lon, to_lat = bus_coords[to_bus]

            ax.plot(
                [from_lon, to_lon],
                [from_lat, to_lat],
                color='#2c3e50',
                linewidth=0.3,
                alpha=0.4,
                zorder=1,
            )
            line_count += 1

    # Plot transformers (if separate)
    xfmr_count = 0
    if len(transformers) > 0:
        for _, row in transformers.iterrows():
            from_bus = row['From Bus']
            to_bus = row['To Bus']

            if from_bus in bus_coords and to_bus in bus_coords:
                from_lon, from_lat = bus_coords[from_bus]
                to_lon, to_lat = bus_coords[to_bus]

                ax.plot(
                    [from_lon, to_lon],
                    [from_lat, to_lat],
                    color='#e74c3c',
                    linewidth=0.2,
                    alpha=0.3,
                    zorder=1,
                )
                xfmr_count += 1

    print(f"  Drew {line_count} lines and {xfmr_count} transformers")

    # Plot buses by voltage level
    if 'BaseKV' in buses.columns:
        voltage_levels = sorted(buses['BaseKV'].unique())
        colors = plt.cm.viridis(np.linspace(0, 1, len(voltage_levels)))

        for voltage, color in zip(voltage_levels, colors):
            voltage_buses = buses[buses['BaseKV'] == voltage]
            ax.scatter(
                voltage_buses['lng'],
                voltage_buses['lat'],
                c=[color],
                s=2,
                alpha=0.7,
                edgecolors='none',
                label=f"{int(voltage)} kV",
                zorder=2,
            )
    else:
        # No voltage info, plot all buses the same
        ax.scatter(
            buses['lng'],
            buses['lat'],
            c='#3498db',
            s=2,
            alpha=0.7,
            edgecolors='none',
            zorder=2,
        )

    # Legend
    if 'BaseKV' in buses.columns:
        ax.legend(loc='lower left', fontsize=8, ncol=2, title="Voltage Level",
                  markerscale=3)

    # Add branch type legend if we have transformers
    if xfmr_count > 0:
        line_legend = mlines.Line2D([], [], color='#2c3e50', linewidth=1.5,
                                     label=f'Lines ({line_count})')
        xfmr_legend = mlines.Line2D([], [], color='#e74c3c', linewidth=1.5,
                                     label=f'Transformers ({xfmr_count})')
        ax.add_artist(ax.legend(handles=[line_legend, xfmr_legend],
                                loc='upper left', fontsize=8))

    if bounds:
        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])

    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    ax.set_title(
        f"{title}\n"
        f"{len(buses)} buses, {line_count} lines, {xfmr_count} transformers",
        fontsize=14
    )
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.3)

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=200, bbox_inches="tight")
        print(f"Saved: {out_path}")

    plt.close(fig)


def plot_combined_voltage_levels(
    bus_csv: str,
    branch_csv: str,
    voltage_levels: list[float],
    title: str = "Combined Network",
    out_path: str | None = None,
    bounds: dict | None = None,
) -> None:
    """Plot multiple voltage levels overlaid on the same map.

    Args:
        bus_csv: Path to bus.csv file with Bus ID, lat, lng columns.
        branch_csv: Path to branch.csv file with From Bus, To Bus columns.
        voltage_levels: List of voltage levels to overlay (e.g., [345.0, 138.0]).
        title: Plot title.
        out_path: If provided, save figure to this path.
        bounds: Optional dict with lat_min, lat_max, lon_min, lon_max.
    """
    print(f"Loading network data from {os.path.dirname(bus_csv)}...")

    # Load buses
    buses = pd.read_csv(bus_csv)
    print(f"  Loaded {len(buses)} buses")

    # Filter to requested voltage levels
    if 'BaseKV' in buses.columns:
        buses = buses[buses['BaseKV'].isin(voltage_levels)]
        print(f"  Filtered to {len(buses)} buses at {voltage_levels} kV")

    # Create bus ID to coordinates mapping
    bus_coords = {}
    bus_voltage = {}
    for _, row in buses.iterrows():
        bus_id = row['Bus ID']
        bus_coords[bus_id] = (row['lng'], row['lat'])
        if 'BaseKV' in row:
            bus_voltage[bus_id] = row['BaseKV']

    # Load branches
    branches = pd.read_csv(branch_csv)
    print(f"  Loaded {len(branches)} branches")

    # Filter to lines only (no transformers for clarity)
    if 'Branch Device Type' in branches.columns:
        lines = branches[branches['Branch Device Type'] == 'Line']
        print(f"  Lines: {len(lines)}")
    else:
        lines = branches

    # Create plot
    fig, ax = plt.subplots(figsize=(16, 12))

    # Define colors for voltage levels
    voltage_colors = {
        345.0: '#e74c3c',  # Red
        230.0: '#f39c12',  # Orange
        138.0: '#3498db',  # Blue
        69.0: '#2ecc71',   # Green
    }

    # Plot lines for each voltage level
    voltage_line_counts = {}
    for voltage in voltage_levels:
        line_count = 0
        color = voltage_colors.get(voltage, '#95a5a6')
        
        for _, row in lines.iterrows():
            from_bus = row['From Bus']
            to_bus = row['To Bus']

            # Only plot if both buses are at this voltage level
            if (from_bus in bus_coords and to_bus in bus_coords and
                bus_voltage.get(from_bus) == voltage and
                bus_voltage.get(to_bus) == voltage):
                
                from_lon, from_lat = bus_coords[from_bus]
                to_lon, to_lat = bus_coords[to_bus]

                ax.plot(
                    [from_lon, to_lon],
                    [from_lat, to_lat],
                    color=color,
                    linewidth=0.4 if voltage == 345.0 else 0.25,
                    alpha=0.6 if voltage == 345.0 else 0.4,
                    zorder=2 if voltage == 345.0 else 1,
                )
                line_count += 1
        
        voltage_line_counts[voltage] = line_count
        print(f"  {voltage} kV: {line_count} lines")

    # Plot buses
    for voltage in voltage_levels:
        voltage_buses = buses[buses['BaseKV'] == voltage]
        if len(voltage_buses) > 0:
            ax.scatter(
                voltage_buses['lng'],
                voltage_buses['lat'],
                s=15 if voltage == 345.0 else 8,
                color=voltage_colors.get(voltage, '#95a5a6'),
                alpha=0.7,
                label=f"{int(voltage)} kV ({len(voltage_buses)} buses)",
                edgecolors='none',
                zorder=3 if voltage == 345.0 else 2,
            )

    # Legend
    ax.legend(loc='lower left', fontsize=10, ncol=1, title="Voltage Levels")

    if bounds:
        ax.set_xlim(bounds["lon_min"], bounds["lon_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])

    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    
    total_lines = sum(voltage_line_counts.values())
    ax.set_title(
        f"{title}\n"
        f"{len(buses)} buses, {total_lines} lines",
        fontsize=14
    )
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=":", alpha=0.3)

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=200, bbox_inches="tight")
        print(f"Saved: {out_path}")

    plt.close(fig)


def plot_voltage_level_comparison(
    bus_csv: str,
    branch_csv: str,
    voltage_levels: list[float],
    title_prefix: str = "Network",
    out_dir: str = "data/processed/viz",
    bounds: dict | None = None,
) -> None:
    """Plot separate topology views for different voltage levels.

    Args:
        bus_csv: Path to bus.csv file.
        branch_csv: Path to branch.csv file.
        voltage_levels: List of voltage levels to plot separately.
        title_prefix: Prefix for plot titles.
        out_dir: Directory for output images.
        bounds: Optional geographic bounds.
    """
    for voltage in voltage_levels:
        out_path = os.path.join(
            out_dir,
            f"{title_prefix.lower().replace(' ', '_')}_{int(voltage)}kv.png"
        )
        plot_network_topology(
            bus_csv,
            branch_csv,
            title=f"{title_prefix} @ {int(voltage)} kV",
            out_path=out_path,
            bounds=bounds,
            voltage_filter=voltage,
        )


if __name__ == "__main__":
    # Plot the Texas-7k reference grid
    texas_7k_dir = "vatic/data/grids/Texas-7k/TX_Data/SourceData"

    # Full network - overlay of 345kV and 138kV (69kV too dense)
    plot_combined_voltage_levels(
        bus_csv=f"{texas_7k_dir}/bus.csv",
        branch_csv=f"{texas_7k_dir}/branch.csv",
        voltage_levels=[345.0, 138.0],
        title="Texas-7k: 345kV + 138kV Networks",
        out_path="data/processed/viz/texas/texas_7k_network_full.png",
    )

    # Individual voltage levels
    print("\nPlotting individual voltage levels...")
    plot_voltage_level_comparison(
        bus_csv=f"{texas_7k_dir}/bus.csv",
        branch_csv=f"{texas_7k_dir}/branch.csv",
        voltage_levels=[345.0, 230.0, 138.0, 69.0],
        title_prefix="Texas-7k",
        out_dir="data/processed/viz/texas",
    )

    print("\n✓ Network topology visualizations complete!")
