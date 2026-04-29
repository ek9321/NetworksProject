#!/usr/bin/env python3
"""
Step 3b — Build storage.csv from EIA-860 NY storage units.

Bus assignment: EIA-860 lat/lon → nearest OSM substation within 50 km.

Outputs:
  grid_data/sced_inputs/SourceData/storage.csv
"""

import json
import math
import re
from pathlib import Path
from collections import defaultdict

import pandas as pd

NYISO_DIR = Path(__file__).resolve().parent
DATA      = NYISO_DIR / "grid_data"
SCED_DIR  = DATA / "sced_inputs"
SRC_DIR   = SCED_DIR / "SourceData"
SRC_DIR.mkdir(parents=True, exist_ok=True)

HTML_FILE   = NYISO_DIR / "ny_grid_visualizer.html"
STORAGE_CSV = DATA / "ny_storage_eia860.csv"

# Storage parameters
EFFICIENCY = 0.96       # one-way (Li-ion)
PS_EFFICIENCY = 0.80    # pumped storage round-trip ~ 0.80
DEFAULT_DURATION = {
    "BA": 4,   # batteries: 4-hour default
    "PS": 8,   # pumped storage: 8-hour default
}
SNAP_RADIUS_KM = 50.0
GRID_CELL = 0.15


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# Load nodes for bus snapping
print("Loading NODES from ny_grid_visualizer.html...")
html = Path(HTML_FILE).read_text(encoding="utf-8")
m = re.search(r"const NODES\s*=\s*(\[.*?\]);", html, re.DOTALL)
if not m:
    raise RuntimeError("Could not find NODES in ny_grid_visualizer.html")
nodes = json.loads(m.group(1))

node_grid = defaultdict(list)
for n in nodes:
    if n.get("split") or n.get("is_split"):
        continue
    lat, lon = float(n["lat"]), float(n["lon"])
    ci = int(lat / GRID_CELL)
    cj = int(lon / GRID_CELL)
    node_grid[(ci, cj)].append(n)


def nearest_bus(lat, lon, max_km=SNAP_RADIUS_KM):
    ci = int(lat / GRID_CELL)
    cj = int(lon / GRID_CELL)
    best_d, best_id = float("inf"), None
    for di in range(-2, 3):
        for dj in range(-2, 3):
            for n in node_grid.get((ci + di, cj + dj), []):
                d = haversine_km(lat, lon, float(n["lat"]), float(n["lon"]))
                if d < best_d:
                    best_d, best_id = d, n["i"]
    return (best_id, best_d) if best_d <= max_km else (None, None)


# Load storage units
print(f"Loading NY storage from {STORAGE_CSV}...")
if not STORAGE_CSV.exists():
    print(f"  File not found: {STORAGE_CSV}")
    print("  Run fetch_ny_generators.py first.")
    exit(1)

stor_df = pd.read_csv(STORAGE_CSV)
print(f"  {len(stor_df)} storage units, {stor_df['pmax_mw'].sum():,.0f} MW total")

# Assign to buses
print("Assigning storage units to OSM buses...")
stor_rows = []
assigned = 0

for _, row in stor_df.iterrows():
    lat = row.get("lat")
    lon = row.get("lon")
    if pd.isna(lat) or pd.isna(lon):
        continue

    bus_id, _ = nearest_bus(lat, lon)
    if bus_id is None:
        continue

    pmax = float(row["pmax_mw"])
    unit_type = row.get("unit_type", "BA")
    duration = DEFAULT_DURATION.get(unit_type, 4)
    energy_mwh = pmax * duration

    if unit_type == "PS":
        eff = math.sqrt(PS_EFFICIENCY)  # one-way efficiency
    else:
        eff = EFFICIENCY

    stor_rows.append({
        "STORAGE UID":        row["storage_uid"],
        "Bus ID":             bus_id,
        "Discharge Rate MW":  pmax,
        "Charge Rate MW":     pmax,
        "Energy Capacity MWh": energy_mwh,
        "Initial SOC MWh":    energy_mwh * 0.5,
        "Charge Efficiency":  round(eff, 4),
        "Discharge Efficiency": round(eff, 4),
        "_zone":              "",
        "_mwh_source":        "default_duration",
    })
    assigned += 1

print(f"  Assigned: {assigned}")

# Write output
stor_out = pd.DataFrame(stor_rows)
stor_out.to_csv(SRC_DIR / "storage.csv", index=False)
print(f"  Wrote {SRC_DIR / 'storage.csv'} ({len(stor_out):,} rows)")

# Summary
print()
print("Summary:")
print(f"  Total units:         {len(stor_out)}")
print(f"  Total discharge MW:  {stor_out['Discharge Rate MW'].sum():,.0f}")
print(f"  Total energy MWh:    {stor_out['Energy Capacity MWh'].sum():,.0f}")
