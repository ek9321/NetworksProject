"""
Visualize matched ERCOT substations on the Texas HV lines map.

Generates multiple plots:
1. All matches color-coded by source
2. High-quality matches only (EIA-860 + OSM)
3. Confidence distribution
4. Match coverage by load zone

Usage:
    python plot_matched_nodes.py
"""

import json
import math
import os
from collections import defaultdict

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import numpy as np
from shapely.geometry import Point
from shapely.prepared import prep

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OIM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

SOURCE_STYLE = {
    "eia860":      {"color": "#2ca02c", "size": 18, "label": "EIA-860 plant match", "zorder": 5},
    "osm":         {"color": "#1f77b4", "size": 14, "label": "OSM substation match", "zorder": 4},
    "propagated":  {"color": "#ff7f0e", "size": 6,  "label": "Topology propagation", "zorder": 3},
    "lz_centroid": {"color": "#999999", "size": 4,  "label": "LZ centroid fallback", "zorder": 2},
}

CONF_COLORS = {
    "high":   "#2ca02c",
    "medium": "#ffdd57",
    "low":    "#ff7f0e",
    "none":   "#d62728",
}

LZ_COLORS = {
    "LZ_WEST":    "#e41a1c",
    "LZ_NORTH":   "#377eb8",
    "LZ_HOUSTON": "#4daf4a",
    "LZ_SOUTH":   "#984ea3",
}


def load_boundary():
    shp_path = os.path.join(PROJECT_ROOT, "vatic/data/grids/Texas-7k/Texas_State_Boundary-shp.zip")
    gdf = gpd.read_file(f"zip://{shp_path}")
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


def load_hv_lines():
    path = os.path.join(OIM_DIR, "data", "texas_hv_lines.geojson")
    with open(path) as f:
        return json.load(f)["features"]


def load_matched():
    path = os.path.join(OUTPUT_DIR, "texas_matched_substations.geojson")
    with open(path) as f:
        return json.load(f)["features"]


def clip_features(features, boundary_gdf):
    polygon = boundary_gdf.unary_union
    prepared = prep(polygon)
    return [f for f in features if prepared.contains(
        Point(f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1]))]


def draw_background(ax, boundary, hv_lines):
    """Draw state boundary and faint HV lines as background."""
    boundary.boundary.plot(ax=ax, color="black", linewidth=1.0, zorder=0)

    # Draw HV lines very faintly
    for f in hv_lines:
        coords = f["geometry"]["coordinates"]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        ax.plot(lons, lats, color="#cccccc", linewidth=0.3, alpha=0.4, zorder=1)

    bounds = boundary.total_bounds
    pad = 0.3
    ax.set_xlim(bounds[0] - pad, bounds[2] + pad)
    ax.set_ylim(bounds[1] - pad, bounds[3] + pad)

    center_lat = (bounds[1] + bounds[3]) / 2
    ax.set_aspect(1.0 / math.cos(math.radians(center_lat)))
    ax.grid(True, alpha=0.2)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")


def plot1_all_by_source(matched, boundary, hv_lines):
    """Plot all matches colored by source."""
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    draw_background(ax, boundary, hv_lines)

    # Plot in reverse zorder (centroids first, EIA last on top)
    for src in ["lz_centroid", "propagated", "osm", "eia860"]:
        style = SOURCE_STYLE[src]
        feats = [f for f in matched if f["properties"]["match_source"] == src]
        if not feats:
            continue
        lons = [f["geometry"]["coordinates"][0] for f in feats]
        lats = [f["geometry"]["coordinates"][1] for f in feats]
        ax.scatter(lons, lats, s=style["size"], color=style["color"],
                   alpha=0.6, zorder=style["zorder"], linewidths=0,
                   label=f"{style['label']} ({len(feats)})")

    ax.legend(loc="lower left", fontsize=8, framealpha=0.9)
    ax.set_title("ERCOT Settlement Node Matching — All Sources", fontsize=14)

    path = os.path.join(OUTPUT_DIR, "texas_all_matches_by_source.png")
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def plot2_hq_only(matched, boundary, hv_lines):
    """Plot only high-quality matches (EIA-860 + OSM, medium+ confidence)."""
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    draw_background(ax, boundary, hv_lines)

    hq = [f for f in matched
          if f["properties"]["match_source"] in ("eia860", "osm")
          and f["properties"]["confidence"] in ("high", "medium")]

    for src in ["osm", "eia860"]:
        style = SOURCE_STYLE[src]
        feats = [f for f in hq if f["properties"]["match_source"] == src]
        if not feats:
            continue

        for conf in ["medium", "high"]:
            conf_feats = [f for f in feats if f["properties"]["confidence"] == conf]
            if not conf_feats:
                continue
            lons = [f["geometry"]["coordinates"][0] for f in conf_feats]
            lats = [f["geometry"]["coordinates"][1] for f in conf_feats]
            edge = "black" if conf == "high" else "none"
            ew = 0.3 if conf == "high" else 0
            ax.scatter(lons, lats, s=style["size"] * (1.5 if conf == "high" else 1),
                       color=style["color"], alpha=0.7,
                       edgecolors=edge, linewidths=ew,
                       zorder=style["zorder"] + (1 if conf == "high" else 0))

    handles = [
        mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#2ca02c',
                      markeredgecolor='black', markeredgewidth=0.5, markersize=7,
                      label=f"EIA-860 high conf"),
        mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#2ca02c',
                      markersize=5, label=f"EIA-860 medium conf"),
        mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#1f77b4',
                      markeredgecolor='black', markeredgewidth=0.5, markersize=7,
                      label=f"OSM high conf"),
        mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#1f77b4',
                      markersize=5, label=f"OSM medium conf"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.9)
    ax.set_title(f"High-Quality Matches Only ({len(hq)} substations)", fontsize=14)

    path = os.path.join(OUTPUT_DIR, "texas_hq_matches.png")
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def plot3_confidence_histogram(matched):
    """Score distribution histogram."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: score histogram for EIA + OSM
    scored = [f["properties"]["score"] for f in matched
              if f["properties"]["match_source"] in ("eia860", "osm")
              and f["properties"]["score"] > 0]

    ax = axes[0]
    ax.hist(scored, bins=30, range=(70, 100), color="#1f77b4", edgecolor="white", alpha=0.8)
    ax.axvline(90, color="green", linestyle="--", linewidth=1.5, label="High threshold (90)")
    ax.axvline(75, color="orange", linestyle="--", linewidth=1.5, label="Medium threshold (75)")
    ax.set_xlabel("Ensemble Match Score")
    ax.set_ylabel("Count")
    ax.set_title("Score Distribution (EIA-860 + OSM matches)")
    ax.legend(fontsize=8)

    # Right: pie chart by source
    ax = axes[1]
    sources = defaultdict(int)
    for f in matched:
        sources[f["properties"]["match_source"]] += 1
    labels = []
    sizes = []
    colors = []
    for src in ["eia860", "osm", "propagated", "lz_centroid"]:
        if src in sources:
            labels.append(f"{SOURCE_STYLE[src]['label']}\n({sources[src]})")
            sizes.append(sources[src])
            colors.append(SOURCE_STYLE[src]["color"])
    ax.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%",
           startangle=90, textprops={"fontsize": 8})
    ax.set_title("Match Source Distribution")

    path = os.path.join(OUTPUT_DIR, "texas_match_statistics.png")
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def plot4_by_load_zone(matched, boundary, hv_lines):
    """Plot matches colored by ERCOT load zone."""
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    draw_background(ax, boundary, hv_lines)

    # Only plot EIA + OSM matches (the ones with real coordinates)
    hq = [f for f in matched
          if f["properties"]["match_source"] in ("eia860", "osm")]

    for lz, color in LZ_COLORS.items():
        feats = [f for f in hq if f["properties"]["load_zone"] == lz]
        if not feats:
            continue
        lons = [f["geometry"]["coordinates"][0] for f in feats]
        lats = [f["geometry"]["coordinates"][1] for f in feats]
        ax.scatter(lons, lats, s=10, color=color, alpha=0.6, zorder=3,
                   linewidths=0, label=f"{lz} ({len(feats)})")

    ax.legend(loc="lower left", fontsize=9, framealpha=0.9)
    ax.set_title("High-Quality Matches by ERCOT Load Zone", fontsize=14)

    path = os.path.join(OUTPUT_DIR, "texas_matches_by_lz.png")
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def main():
    print("Loading data...")
    boundary = load_boundary()
    hv_lines = load_hv_lines()
    matched = load_matched()

    # Clip lines to boundary for background
    polygon = boundary.unary_union
    prepared = prep(polygon)
    hv_lines = [f for f in hv_lines
                if any(prepared.contains(Point(c[0], c[1]))
                       for c in f["geometry"]["coordinates"])]

    print(f"Loaded {len(matched)} matched substations, {len(hv_lines)} HV lines")
    print()

    print("Generating plots...")
    plot1_all_by_source(matched, boundary, hv_lines)
    plot2_hq_only(matched, boundary, hv_lines)
    plot3_confidence_histogram(matched)
    plot4_by_load_zone(matched, boundary, hv_lines)
    print("\nDone!")


if __name__ == "__main__":
    main()
