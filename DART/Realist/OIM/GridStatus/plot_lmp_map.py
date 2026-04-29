"""
Plot ERCOT real-time LMPs on the Texas transmission network.

Joins LMP data → ERCOT settlement points → geolocated substations → map.

Usage (from project root, using the 3.12 venv for gridstatus pull,
       then system python for plotting):

    # Pull fresh LMPs (requires 3.12 venv)
    OIM/.venv312/bin/python3.12 OIM/GridStatus/pull_lmp.py

    # Plot (system python is fine)
    python3 OIM/GridStatus/plot_lmp_map.py
"""

import csv
import json
import math
import os
from collections import defaultdict
from datetime import datetime

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import matplotlib.lines as mlines
import numpy as np
from shapely.geometry import Point
from shapely.prepared import prep

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OIM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRIDSTATUS_DIR = os.path.dirname(os.path.abspath(__file__))
SP_DIR = os.path.join(PROJECT_ROOT, "SP_List_EB_Mapping")


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


def clip_lines(features, boundary_gdf):
    polygon = boundary_gdf.unary_union
    prepared = prep(polygon)
    return [f for f in features if any(
        prepared.contains(Point(c[0], c[1])) for c in f["geometry"]["coordinates"])]


def load_matched_substations():
    """Load geolocated substations from FirstPass."""
    path = os.path.join(OIM_DIR, "FirstPass", "texas_matched_substations.csv")
    subs = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            subs[row["ercot_substation"]] = {
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "source": row["match_source"],
                "confidence": row["confidence"],
                "load_zone": row["load_zone"],
            }
    return subs


def build_lmp_location_to_substation():
    """Map LMP location names (resource nodes) to ERCOT substations."""
    mapping = {}

    # From Resource_Node_to_Unit
    path = os.path.join(SP_DIR, "Resource_Node_to_Unit_01292026_104938.csv")
    with open(path) as f:
        for row in csv.DictReader(f):
            mapping[row["RESOURCE_NODE"]] = row["UNIT_SUBSTATION"]

    # From Settlement_Points RESOURCE_NODE column
    path = os.path.join(SP_DIR, "Settlement_Points_01292026_104938.csv")
    with open(path) as f:
        for row in csv.DictReader(f):
            rn = row.get("RESOURCE_NODE", "").strip()
            if rn and rn not in mapping:
                mapping[rn] = row["SUBSTATION"]

    return mapping


def load_lmp_snapshot():
    """Load most recent LMP data and return per-substation aggregated LMPs."""
    lmp_path = os.path.join(OIM_DIR, "data", "lmp_test.csv")
    if not os.path.exists(lmp_path):
        print(f"Error: {lmp_path} not found. Run pull_lmp.py first.")
        return None, None, None

    rows = []
    with open(lmp_path) as f:
        for row in csv.DictReader(f):
            rows.append(row)

    # Find latest SCED timestamp
    timestamps = sorted(set(r["SCED Timestamp"] for r in rows))
    latest = timestamps[-1]

    # Get resource node LMPs at latest timestamp
    latest_rn = {r["Location"]: float(r["LMP"])
                 for r in rows
                 if r["SCED Timestamp"] == latest and r["Location Type"] == "Resource Node"}

    # Get hub/LZ prices
    hub_lz = {r["Location"]: float(r["LMP"])
              for r in rows
              if r["SCED Timestamp"] == latest and r["Location Type"] != "Resource Node"}

    return latest_rn, hub_lz, latest


def aggregate_to_substations(lmp_by_rn, rn_to_sub, matched_subs):
    """
    Map LMP resource nodes → substations → coordinates.
    Returns list of dicts: {lat, lon, lmp, substation, source, load_zone}
    """
    # Group LMPs by substation
    sub_lmps = defaultdict(list)
    for rn, lmp in lmp_by_rn.items():
        sub = rn_to_sub.get(rn)
        if sub:
            sub_lmps[sub].append(lmp)

    # Average LMP per substation, attach coordinates
    points = []
    for sub, lmps in sub_lmps.items():
        if sub not in matched_subs:
            continue
        m = matched_subs[sub]
        points.append({
            "lat": m["lat"],
            "lon": m["lon"],
            "lmp": sum(lmps) / len(lmps),
            "substation": sub,
            "source": m["source"],
            "load_zone": m["load_zone"],
            "n_nodes": len(lmps),
        })
    return points


def draw_background(ax, boundary, hv_lines):
    boundary.boundary.plot(ax=ax, color="black", linewidth=1.0, zorder=0)
    for f in hv_lines:
        coords = f["geometry"]["coordinates"]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        ax.plot(lons, lats, color="#d0d0d0", linewidth=0.3, alpha=0.5, zorder=1)
    bounds = boundary.total_bounds
    pad = 0.3
    ax.set_xlim(bounds[0] - pad, bounds[2] + pad)
    ax.set_ylim(bounds[1] - pad, bounds[3] + pad)
    center_lat = (bounds[1] + bounds[3]) / 2
    ax.set_aspect(1.0 / math.cos(math.radians(center_lat)))
    ax.grid(True, alpha=0.15)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")


def plot_lmp_map(points, hub_lz, timestamp, boundary, hv_lines, output_dir, tag="all"):
    """Main LMP heatmap on the transmission network."""
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    draw_background(ax, boundary, hv_lines)

    lmps = [p["lmp"] for p in points]
    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]

    # Diverging colormap centered on 0
    vmax = max(abs(min(lmps)), abs(max(lmps)), 1.0)
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    cmap = cm.RdYlBu_r  # Red = expensive, Blue = cheap/negative

    sc = ax.scatter(lons, lats, c=lmps, cmap=cmap, norm=norm,
                    s=20, alpha=0.8, zorder=4, linewidths=0.2, edgecolors="black")

    cbar = plt.colorbar(sc, ax=ax, shrink=0.7, pad=0.02)
    cbar.set_label("LMP ($/MWh)", fontsize=10)

    # Annotate hub/LZ prices
    lz_positions = {
        "LZ_WEST": (-102.0, 31.5),
        "LZ_NORTH": (-97.5, 34.0),
        "LZ_HOUSTON": (-95.0, 29.8),
        "LZ_SOUTH": (-98.5, 28.0),
        "HB_HOUSTON": (-94.5, 30.5),
        "HB_NORTH": (-96.0, 35.5),
        "HB_SOUTH": (-97.0, 26.5),
        "HB_WEST": (-104.5, 32.5),
    }
    for loc, (lon, lat) in lz_positions.items():
        if loc in hub_lz:
            price = hub_lz[loc]
            color = "#d62728" if price > 0 else "#1f77b4"
            ax.annotate(f"{loc}\n${price:.2f}",
                        xy=(lon, lat), fontsize=7, fontweight="bold",
                        color=color, ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                                  edgecolor=color, alpha=0.85),
                        zorder=10)

    # Stats box
    stats_text = (
        f"Nodes plotted: {len(points)}\n"
        f"LMP range: ${min(lmps):.2f} to ${max(lmps):.2f}\n"
        f"Mean: ${sum(lmps)/len(lmps):.2f}"
    )
    ax.text(0.98, 0.98, stats_text, transform=ax.transAxes, fontsize=8,
            verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.9), zorder=10)

    ts_clean = timestamp.replace("-06:00", " CST") if timestamp else ""
    ax.set_title(f"ERCOT Real-Time LMPs — {ts_clean}", fontsize=13)

    path = os.path.join(output_dir, f"texas_lmp_map_{tag}.png")
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def plot_lmp_hq_only(points, hub_lz, timestamp, boundary, hv_lines, output_dir):
    """LMP map with only high-quality (EIA/OSM) matches."""
    hq = [p for p in points if p["source"] in ("eia860", "osm")]
    print(f"HQ points for LMP map: {len(hq)}")
    plot_lmp_map(hq, hub_lz, timestamp, boundary, hv_lines, output_dir, tag="hq")


def plot_congestion(points, hub_lz, timestamp, boundary, hv_lines, output_dir):
    """
    Highlight congestion by showing deviation from the system average.
    Large deviations = transmission constraints.
    """
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    draw_background(ax, boundary, hv_lines)

    lmps = [p["lmp"] for p in points]
    mean_lmp = sum(lmps) / len(lmps)
    deviations = [p["lmp"] - mean_lmp for p in points]
    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]

    vmax = max(abs(min(deviations)), abs(max(deviations)), 0.5)
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    cmap = cm.PiYG_r  # Pink = above avg (congested import), Green = below avg

    sc = ax.scatter(lons, lats, c=deviations, cmap=cmap, norm=norm,
                    s=25, alpha=0.8, zorder=4, linewidths=0.2, edgecolors="black")

    cbar = plt.colorbar(sc, ax=ax, shrink=0.7, pad=0.02)
    cbar.set_label("LMP Deviation from Mean ($/MWh)", fontsize=10)

    stats_text = (
        f"System mean LMP: ${mean_lmp:.2f}\n"
        f"Max deviation: ${max(deviations):.2f}\n"
        f"Min deviation: ${min(deviations):.2f}"
    )
    ax.text(0.98, 0.98, stats_text, transform=ax.transAxes, fontsize=8,
            verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.9), zorder=10)

    ts_clean = timestamp.replace("-06:00", " CST") if timestamp else ""
    ax.set_title(f"ERCOT Congestion Map (LMP Deviation from Mean) — {ts_clean}", fontsize=13)

    path = os.path.join(output_dir, "texas_congestion_map.png")
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def main():
    print("Loading data...")
    boundary = load_boundary()
    hv_lines = clip_lines(load_hv_lines(), boundary)
    matched_subs = load_matched_substations()
    rn_to_sub = build_lmp_location_to_substation()

    lmp_by_rn, hub_lz, timestamp = load_lmp_snapshot()
    if lmp_by_rn is None:
        return

    print(f"SCED timestamp: {timestamp}")
    print(f"Resource node LMPs: {len(lmp_by_rn)}")
    print(f"Hub/LZ prices: {len(hub_lz)}")

    points = aggregate_to_substations(lmp_by_rn, rn_to_sub, matched_subs)
    print(f"Substations with LMP + coordinates: {len(points)}")

    os.makedirs(GRIDSTATUS_DIR, exist_ok=True)

    print("\nGenerating plots...")
    plot_lmp_map(points, hub_lz, timestamp, boundary, hv_lines, GRIDSTATUS_DIR, tag="all")
    plot_lmp_hq_only(points, hub_lz, timestamp, boundary, hv_lines, GRIDSTATUS_DIR)
    plot_congestion(points, hub_lz, timestamp, boundary, hv_lines, GRIDSTATUS_DIR)

    print("\nDone!")


if __name__ == "__main__":
    main()
