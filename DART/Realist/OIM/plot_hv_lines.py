"""
Plot high-voltage transmission lines from GeoJSON produced by fetch_hv_lines.py.

Color-codes lines by voltage tier with cosine aspect ratio correction.

Usage:
    python plot_hv_lines.py texas
"""

import argparse
import json
import math
import os
import zipfile

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import numpy as np
from shapely.geometry import Point, LineString
from shapely.prepared import prep

# Voltage tier styling: label -> (color, linewidth)
TIER_STYLE = {
    "115-229 kV": ("#2166ac", 0.6),    # blue
    "230-344 kV": ("#f4a582", 1.0),     # orange
    "345-499 kV": ("#d6604d", 1.4),     # red
    "500+ kV":    ("#7b3294", 2.0),     # purple
}

# Draw order (lower tiers behind higher)
TIER_ORDER = ["115-229 kV", "230-344 kV", "345-499 kV", "500+ kV"]

# Boundary shapefiles (relative to project root)
BOUNDARY_SHAPEFILES = {
    "texas": "vatic/data/grids/Texas-7k/Texas_State_Boundary-shp.zip",
}


def load_geojson(path):
    """Load GeoJSON FeatureCollection and return features list."""
    with open(path) as f:
        data = json.load(f)
    return data["features"]


def haversine_km(lat1, lon1, lat2, lon2):
    """Haversine distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def line_length_km(coords):
    """Total polyline length in km from (lon, lat) coords."""
    total = 0.0
    for i in range(len(coords) - 1):
        total += haversine_km(coords[i][1], coords[i][0], coords[i + 1][1], coords[i + 1][0])
    return total


def print_summary(features, region):
    """Print summary statistics to console."""
    tier_counts = {}
    tier_km = {}
    for tier in TIER_ORDER:
        tier_counts[tier] = 0
        tier_km[tier] = 0.0

    for f in features:
        tier = f["properties"]["voltage_tier"]
        if tier in tier_counts:
            tier_counts[tier] += 1
            tier_km[tier] += f["properties"].get("length_km", 0)

    print(f"\n{'=' * 50}")
    print(f"Region: {region}")
    print(f"Total HV lines: {len(features)}")
    print(f"{'=' * 50}")
    for tier in TIER_ORDER:
        print(f"  {tier:>12s}:  {tier_counts[tier]:5d} lines,  {tier_km[tier]:8.1f} km")
    total_km = sum(tier_km.values())
    print(f"  {'TOTAL':>12s}:  {len(features):5d} lines,  {total_km:8.1f} km")
    print()


def load_boundary(region):
    """Load state/region boundary shapefile. Returns GeoDataFrame or None."""
    if region not in BOUNDARY_SHAPEFILES:
        return None
    # Project root is one level up from OIM/
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shp_path = os.path.join(project_root, BOUNDARY_SHAPEFILES[region])
    if not os.path.exists(shp_path):
        print(f"Warning: boundary shapefile not found: {shp_path}")
        return None
    gdf = gpd.read_file(f"zip://{shp_path}")
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


def load_substations(region):
    """Load substation GeoJSON if available. Returns features list or None."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, "data", f"{region}_substations.geojson")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    return data["features"]


def clip_lines_to_boundary(features, boundary_gdf):
    """Keep only lines where at least one node falls inside the boundary polygon."""
    polygon = boundary_gdf.unary_union
    prepared = prep(polygon)
    clipped = []
    for f in features:
        coords = f["geometry"]["coordinates"]
        # Check if any vertex is inside the boundary
        for lon, lat in coords:
            if prepared.contains(Point(lon, lat)):
                clipped.append(f)
                break
    return clipped


def clip_substations_to_boundary(features, boundary_gdf):
    """Keep only substations inside the boundary polygon."""
    polygon = boundary_gdf.unary_union
    prepared = prep(polygon)
    clipped = []
    for f in features:
        lon, lat = f["geometry"]["coordinates"]
        if prepared.contains(Point(lon, lat)):
            clipped.append(f)
    return clipped


def plot_lines(features, region, output_path):
    """Create the voltage-tier-colored map with optional substation overlay."""
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))

    # Load boundary and clip features to it
    boundary = load_boundary(region)
    if boundary is not None:
        boundary.boundary.plot(ax=ax, color="black", linewidth=1.2, zorder=0)
        n_before = len(features)
        features = clip_lines_to_boundary(features, boundary)
        print(f"Clipped lines: {n_before} -> {len(features)} (inside boundary)")

    # Group features by tier for layered drawing
    tier_features = {tier: [] for tier in TIER_ORDER}
    for f in features:
        tier = f["properties"]["voltage_tier"]
        if tier in tier_features:
            tier_features[tier].append(f)

    # Draw in order (lower voltage behind)
    for tier in TIER_ORDER:
        color, lw = TIER_STYLE[tier]
        for f in tier_features[tier]:
            coords = f["geometry"]["coordinates"]
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            ax.plot(lons, lats, color=color, linewidth=lw, alpha=0.7, solid_capstyle="round")

    # Overlay substations if available
    sub_features = load_substations(region)
    n_transmission = 0
    n_other = 0
    if sub_features is not None:
        if boundary is not None:
            n_sub_before = len(sub_features)
            sub_features = clip_substations_to_boundary(sub_features, boundary)
            print(f"Clipped substations: {n_sub_before} -> {len(sub_features)} (inside boundary)")

        trans_lons, trans_lats = [], []
        other_lons, other_lats = [], []
        for sf in sub_features:
            props = sf["properties"]
            lon, lat = sf["geometry"]["coordinates"]
            voltage = props.get("voltage_kv")
            sub_type = props.get("substation_type", "")
            # Show transmission substations (or those with HV voltage) prominently
            if sub_type == "transmission" or (voltage is not None and voltage >= 115):
                trans_lons.append(lon)
                trans_lats.append(lat)
            else:
                other_lons.append(lon)
                other_lats.append(lat)

        if other_lons:
            ax.scatter(other_lons, other_lats, s=3, color="#888888", alpha=0.3,
                       zorder=3, linewidths=0)
            n_other = len(other_lons)
        if trans_lons:
            ax.scatter(trans_lons, trans_lats, s=12, color="#2ca02c", alpha=0.6,
                       zorder=4, linewidths=0.3, edgecolors="black")
            n_transmission = len(trans_lons)
        print(f"Plotted {n_transmission} transmission + {n_other} other substations")

    # Cosine aspect ratio correction at region center latitude
    all_lats = []
    for f in features:
        for c in f["geometry"]["coordinates"]:
            all_lats.append(c[1])
    if all_lats:
        center_lat = np.mean(all_lats)
        ax.set_aspect(1.0 / math.cos(math.radians(center_lat)))

    # Clip axes to boundary extent if available
    if boundary is not None:
        bounds = boundary.total_bounds  # [minx, miny, maxx, maxy]
        pad = 0.3
        ax.set_xlim(bounds[0] - pad, bounds[2] + pad)
        ax.set_ylim(bounds[1] - pad, bounds[3] + pad)

    # Legend
    handles = []
    if boundary is not None:
        handles.append(mlines.Line2D([], [], color="black", linewidth=1.2,
                                     label="State boundary"))
    for tier in TIER_ORDER:
        color, lw = TIER_STYLE[tier]
        count = len(tier_features[tier])
        handles.append(mlines.Line2D([], [], color=color, linewidth=lw,
                                     label=f"{tier} ({count} lines)"))
    if sub_features is not None:
        handles.append(plt.Line2D([], [], marker='o', color='w', markerfacecolor='#2ca02c',
                                  markeredgecolor='black', markeredgewidth=0.3, markersize=5,
                                  label=f"Transmission subs ({n_transmission})"))
        handles.append(plt.Line2D([], [], marker='o', color='w', markerfacecolor='#888888',
                                  markersize=3, label=f"Other subs ({n_other})"))
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.9)

    region_title = region.replace("_", " ").title()
    ax.set_title(f"OpenInfraMap HV Transmission Lines & Substations \u2014 {region_title}", fontsize=14)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"Saved plot to {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Plot HV lines from GeoJSON")
    parser.add_argument("region", help="Region name (must match fetched data filename)")
    args = parser.parse_args()

    region = args.region
    script_dir = os.path.dirname(os.path.abspath(__file__))
    geojson_path = os.path.join(script_dir, "data", f"{region}_hv_lines.geojson")
    output_dir = os.path.join(script_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{region}_hv_lines.png")

    if not os.path.exists(geojson_path):
        print(f"Error: {geojson_path} not found. Run fetch_hv_lines.py first.")
        sys.exit(1)

    features = load_geojson(geojson_path)
    print(f"Loaded {len(features)} features from {geojson_path}")

    print_summary(features, region)
    plot_lines(features, region, output_path)


if __name__ == "__main__":
    import sys
    main()
