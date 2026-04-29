#!/usr/bin/env python3
"""
Step 1 (OSM-native) — Build bus table from generate_visualizer.py NODES.

Reads the NODES array already embedded in grid_visualizer.html (the live
website output).  Zone assignment is via point-in-polygon against
ercot_zones.geojson.  No PSSE bus numbers are used.

Outputs:
  sced_inputs/osm_bus.csv          — canonical OSM bus table
  sced_inputs/SourceData/bus.csv   — same file, where Vatic reads it
"""

import json
import math
import re
from pathlib import Path

import pandas as pd
from shapely.geometry import Point, shape

# ---------------------------------------------------------------------------
# Paths — override with env vars for v2 pipeline or cluster usage
# ---------------------------------------------------------------------------
import os as _os

if _os.environ.get("DARTBOARD_SCRATCH"):
    _SCRATCH    = Path(_os.environ["DARTBOARD_SCRATCH"])
    DATA        = _SCRATCH / "grid_data"
    SCED_DIR    = Path(_os.environ["SCED_DIR_OVERRIDE"]) if _os.environ.get("SCED_DIR_OVERRIDE") else _SCRATCH / "sced_inputs"
    HTML_FILE   = _SCRATCH / "grid_data" / "grid_visualizer.html"
else:
    REPO        = Path(__file__).resolve().parents[2]
    REALIST     = REPO / "Realist"
    DATA        = REALIST / "grid_data"
    SCED_DIR    = Path(_os.environ["SCED_DIR_OVERRIDE"]) if _os.environ.get("SCED_DIR_OVERRIDE") else DATA / "sced_inputs"
    HTML_FILE   = Path(_os.environ["VIZ_HTML"]) if _os.environ.get("VIZ_HTML") else REALIST / "grid_visualizer.html"

SRC_DIR   = SCED_DIR / "SourceData"
SRC_DIR.mkdir(parents=True, exist_ok=True)
ZONES_FILE  = DATA / "ercot_zones.geojson"

# ---------------------------------------------------------------------------
# Zone config
# ---------------------------------------------------------------------------
ZONE_UPPER = {"Houston": "HOUSTON", "North": "NORTH",
              "South": "SOUTH",   "West":  "WEST"}
ZONE_AREA  = {"NORTH": 1, "HOUSTON": 2, "SOUTH": 3, "WEST": 4}

# Reference bus: first substation node at or above this kV in NORTH zone.
REF_KV_MIN = 345


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# 1. Parse NODES from grid_visualizer.html
# ---------------------------------------------------------------------------
print("Parsing NODES from grid_visualizer.html...")
html = HTML_FILE.read_text(encoding="utf-8")
m = re.search(r"const NODES\s*=\s*(\[.*?\]);", html, re.DOTALL)
if not m:
    raise RuntimeError("Could not find NODES array in grid_visualizer.html")
nodes = json.loads(m.group(1))
print(f"  Total nodes: {len(nodes):,}")
subs   = [n for n in nodes if not n.get("split")]
splits = [n for n in nodes if n.get("split")]
print(f"  Substations: {len(subs):,}   Split points: {len(splits):,}")

# ---------------------------------------------------------------------------
# 2. Load ERCOT zone polygons
# ---------------------------------------------------------------------------
print("Loading ERCOT zone polygons...")
with open(ZONES_FILE, encoding="utf-8") as f:
    zones_data = json.load(f)

zone_shapes = []
zone_centroids = []
for feat in zones_data["features"]:
    raw_name = feat["properties"]["NAME"]       # e.g. "North"
    zone_name = ZONE_UPPER.get(raw_name, raw_name.upper())
    geom = shape(feat["geometry"])
    if not geom.is_valid:
        geom = geom.buffer(0)   # standard fix for topology conflicts
    zone_shapes.append((zone_name, geom))
    c = geom.centroid
    zone_centroids.append((zone_name, c.y, c.x))
print(f"  Zones loaded: {[z for z, _ in zone_shapes]}")


def get_zone(lat, lon):
    pt = Point(lon, lat)        # shapely uses (lon, lat)
    for zone_name, geom in zone_shapes:
        if geom.contains(pt):
            return zone_name
    # Fallback: nearest zone centroid
    best_zone = "NORTH"
    best_dist = float("inf")
    for zone_name, clat, clon in zone_centroids:
        d = haversine_km(lat, lon, clat, clon)
        if d < best_dist:
            best_dist = d
            best_zone = zone_name
    return best_zone


# ---------------------------------------------------------------------------
# 3. Build bus rows
# ---------------------------------------------------------------------------
print("Building bus rows (zone PIP)...")


def sanitize_name(raw, idx):
    """Make a clean, unique-ready bus name from OSM name + index."""
    if not raw:
        return f"OSM_{idx}"
    # Keep alphanumeric + underscore, replace spaces/hyphens
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", raw.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:48] or f"OSM_{idx}"


# Track used names to guarantee uniqueness
used_names = {}


def unique_name(raw, idx):
    base = sanitize_name(raw, idx)
    if base not in used_names:
        used_names[base] = idx
        return base
    return f"{base}_{idx}"


# Pick reference bus: first substation node at ≥ REF_KV_MIN kV in NORTH zone.
# We'll mark it during the main loop.
ref_bus_id = None

bus_rows = []
for node in nodes:
    i      = node["i"]
    lat    = float(node["lat"])
    lon    = float(node["lon"])
    kv     = float(node.get("kv") or 0)
    is_spl = bool(node.get("split", False))
    osm_id = str(node.get("id", ""))
    name   = str(node.get("name", "")).strip() if not is_spl else ""

    zone     = get_zone(lat, lon)
    area     = ZONE_AREA.get(zone, 1)
    bus_name = unique_name(name, i)
    sub_name = name.upper() if name else f"SPL_{i}"

    bus_rows.append({
        "Bus ID":   i,
        "Bus Name": bus_name,
        "Sub Name": sub_name,
        "BaseKV":   kv,
        "Bus Type": "PQ",      # filled in below for reference bus
        "MW Load":  0.0,
        "MVAR Load": 0.0,
        "Area":     area,
        "Sub Area": area,
        "Zone":     zone,
        "lat":      lat,
        "lng":      lon,
        "osm_id":   osm_id,
        "is_split": is_spl,
    })

    # Candidate for reference bus: highest-kV substation in NORTH zone
    if not is_spl and kv >= REF_KV_MIN and zone == "NORTH":
        if ref_bus_id is None:
            ref_bus_id = i

# Fallback: if no NORTH 345+ kV node, pick first 345+ kV node overall
if ref_bus_id is None:
    for row in bus_rows:
        if not row["is_split"] and row["BaseKV"] >= REF_KV_MIN:
            ref_bus_id = row["Bus ID"]
            break

# Fallback: just use first node
if ref_bus_id is None:
    ref_bus_id = bus_rows[0]["Bus ID"]

# Set reference bus type
for row in bus_rows:
    if row["Bus ID"] == ref_bus_id:
        row["Bus Type"] = "Slack"
        break

print(f"  Reference bus: Bus ID {ref_bus_id}")

# ---------------------------------------------------------------------------
# 4. Write output
# ---------------------------------------------------------------------------
COLS = [
    "Bus ID", "Bus Name", "Sub Name", "BaseKV", "Bus Type",
    "MW Load", "MVAR Load", "Area", "Sub Area", "Zone",
    "lat", "lng", "osm_id", "is_split",
]

bus_df = pd.DataFrame(bus_rows, columns=COLS)

osm_bus_path = SCED_DIR / "osm_bus.csv"
src_bus_path = SRC_DIR  / "bus.csv"

bus_df.to_csv(osm_bus_path, index=False)
bus_df.to_csv(src_bus_path, index=False)

print(f"  Wrote {osm_bus_path} ({len(bus_df):,} rows)")
print(f"  Wrote {src_bus_path} ({len(bus_df):,} rows)")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print()
print("Summary:")
print(f"  Total buses:     {len(bus_df):,}")
print(f"  Substation nodes:{len(subs):,}")
print(f"  Split-pt nodes:  {len(splits):,}")
print(f"  Reference bus:   ID {ref_bus_id} ({bus_df.loc[bus_df['Bus ID']==ref_bus_id,'Bus Name'].iloc[0]})")
zone_counts = bus_df.groupby("Zone").size()
print("  Zone distribution:")
for zone, cnt in zone_counts.items():
    print(f"    {zone:10s}: {cnt:5,}")
