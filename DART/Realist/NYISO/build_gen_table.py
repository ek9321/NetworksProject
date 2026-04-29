#!/usr/bin/env python3
"""
Step 3 (OSM-native) — Build gen.csv and init_state.csv from EIA-860.

Bus assignment (1 stage — EIA-860 has lat/lon for all NY generators):
  - EIA-860 plant lat/lon → nearest OSM substation node within 50 km

NYISO-specific notes:
  - Significant hydro (Niagara, St. Lawrence) — modeled as dispatchable
  - Oil peakers (NYC) — high marginal cost, quick start
  - No MORA equivalent — EIA-860 is the primary data source

Outputs:
  grid_data/sced_inputs/SourceData/gen.csv
  grid_data/sced_inputs/SourceData/init_state.csv
"""

import csv
import json
import math
import re
from pathlib import Path
from collections import defaultdict

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
NYISO_DIR = Path(__file__).resolve().parent
DATA      = NYISO_DIR / "grid_data"
SCED_DIR  = DATA / "sced_inputs"
SRC_DIR   = SCED_DIR / "SourceData"
SRC_DIR.mkdir(parents=True, exist_ok=True)

HTML_FILE = NYISO_DIR / "ny_grid_visualizer.html"
GEN_CSV   = DATA / "ny_generators_eia860.csv"

# ---------------------------------------------------------------------------
# Fuel and cost constants
# ---------------------------------------------------------------------------
# Fuel → (gen_fuel, unit_group_prefix, unit_type_label)
FUEL_MAP = {
    "Nuclear": ("Nuclear", "N", "Nuclear"),
    "Coal":    ("Coal",    "C", "Coal"),
    "Gas":     ("Gas",     "G", "Gas"),
    "Oil":     ("Oil",     "O", "Oil"),
    "Hydro":   ("Hydro",   "H", "Hydro"),
    "Wind":    ("Wind",    "W", "Wind"),
    "Solar":   ("Solar",   "S", "Solar"),
    "Biomass": ("Biomass", "B", "Biomass"),
    "Other":   ("Other",   "X", "Other"),
}

# PMin fraction of PMax (minimum stable output)
PMIN_FRAC = {
    "Nuclear": 0.90,
    "Coal":    0.40,
    "Gas":     0.30,
    "Oil":     0.20,
    "Hydro":   0.0,
    "Wind":    0.0,
    "Solar":   0.0,
    "Biomass": 0.30,
    "Other":   0.0,
}

# Flat marginal cost ($/MWh) — single-segment offer curve
FLAT_COST = {
    "Nuclear":  6.0,
    "Coal":    25.0,
    "Gas":     35.0,
    "Oil":     80.0,    # NYC peakers are expensive
    "Hydro":    5.0,
    "Wind":     0.0,
    "Solar":    0.0,
    "Biomass": 40.0,
    "Other":   50.0,
}

# Ramp rate (fraction of PMax per minute)
RAMP_FRAC = {
    "Nuclear": 0.002,
    "Coal":    0.01,
    "Gas":     0.05,
    "Oil":     0.10,
    "Hydro":   0.20,
    "Wind":    1.0,
    "Solar":   1.0,
    "Biomass": 0.02,
    "Other":   0.05,
}

# Minimum up/down time (hours)
MIN_TIME = {
    "Nuclear": (24, 24),
    "Coal":    (8, 8),
    "Gas":     (2, 2),
    "Oil":     (1, 1),
    "Hydro":   (0, 0),
    "Wind":    (0, 0),
    "Solar":   (0, 0),
    "Biomass": (4, 4),
    "Other":   (1, 1),
}

# Startup costs (cold/warm/hot hours and MBTU)
STARTUP = {
    "Nuclear": (48, 24, 12, 500, 250, 125),
    "Coal":    (12, 8,  4,  100, 60,  30),
    "Gas":     (4,  2,  1,  30,  15,  8),
    "Oil":     (2,  1,  0,  10,  5,   2),
    "Hydro":   (0,  0,  0,  0,   0,   0),
    "Wind":    (0,  0,  0,  0,   0,   0),
    "Solar":   (0,  0,  0,  0,   0,   0),
    "Biomass": (6,  3,  1,  40,  20,  10),
    "Other":   (2,  1,  0,  10,  5,   2),
}

# Fuel price $/MMBTU
FUEL_PRICE = {
    "Nuclear": 0.7,
    "Coal":    2.0,
    "Gas":     3.5,
    "Oil":     12.0,
    "Hydro":   0.0,
    "Wind":    0.0,
    "Solar":   0.0,
    "Biomass": 3.0,
    "Other":   5.0,
}

SNAP_RADIUS_KM = 50.0


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# 1. Parse NODES from ny_grid_visualizer.html for bus snapping
# ---------------------------------------------------------------------------
print("Loading NODES from ny_grid_visualizer.html...")
html = HTML_FILE.read_text(encoding="utf-8")
m = re.search(r"const NODES\s*=\s*(\[.*?\]);", html, re.DOTALL)
if not m:
    raise RuntimeError("Could not find NODES in ny_grid_visualizer.html")
nodes = json.loads(m.group(1))

# Build spatial grid for fast nearest-node lookup
GRID_CELL = 0.15  # ~17 km
node_grid = defaultdict(list)
for n in nodes:
    if n.get("split") or n.get("is_split"):
        continue  # skip split nodes — generators snap to real substations
    lat, lon = float(n["lat"]), float(n["lon"])
    ci = int(lat / GRID_CELL)
    cj = int(lon / GRID_CELL)
    node_grid[(ci, cj)].append(n)

print(f"  {len(nodes)} nodes loaded, {sum(len(v) for v in node_grid.values())} substations in grid")


def nearest_bus(lat, lon, max_km=SNAP_RADIUS_KM):
    """Find nearest OSM substation node within max_km. Returns (bus_id, dist_km) or (None, None)."""
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


# ---------------------------------------------------------------------------
# 2. Load EIA-860 generators
# ---------------------------------------------------------------------------
print(f"Loading NY generators from {GEN_CSV}...")
gen_df = pd.read_csv(GEN_CSV)
print(f"  {len(gen_df)} generators, {gen_df['pmax_mw'].sum():,.0f} MW total")

# ---------------------------------------------------------------------------
# 3. Assign generators to OSM buses
# ---------------------------------------------------------------------------
print("Assigning generators to OSM buses...")

gen_rows = []
init_rows = []
assigned = 0
unassigned = 0

for _, row in gen_df.iterrows():
    lat = row.get("lat")
    lon = row.get("lon")
    if pd.isna(lat) or pd.isna(lon):
        unassigned += 1
        continue

    bus_id, snap_dist = nearest_bus(lat, lon)
    if bus_id is None:
        unassigned += 1
        continue

    fuel = row["fuel"]
    fm = FUEL_MAP.get(fuel, FUEL_MAP["Other"])
    gen_fuel, grp_prefix, unit_type = fm

    pmax = float(row["pmax_mw"])
    pmin_frac = PMIN_FRAC.get(fuel, 0.0)
    pmin = round(pmax * pmin_frac, 2)
    flat_cost = FLAT_COST.get(fuel, 50.0)
    ramp_frac = RAMP_FRAC.get(fuel, 0.05)
    ramp_mw_min = round(pmax * ramp_frac, 2)
    min_up, min_down = MIN_TIME.get(fuel, (1, 1))
    cold_hr, warm_hr, hot_hr, cold_mbtu, warm_mbtu, hot_mbtu = STARTUP.get(fuel, (2, 1, 0, 10, 5, 2))
    fuel_price = FUEL_PRICE.get(fuel, 5.0)

    gen_uid = row["gen_uid"]

    gen_rows.append({
        "GEN UID":              gen_uid,
        "Bus ID":               bus_id,
        "Unit Group":           f"{grp_prefix}_{row['plant_code']}",
        "Unit Type":            unit_type,
        "Fuel":                 gen_fuel,
        "PMin MW":              pmin,
        "PMax MW":              pmax,
        "Min Down Time Hr":     min_down,
        "Min Up Time Hr":       min_up,
        "Ramp Rate MW/Min":     ramp_mw_min,
        "Start Time Cold Hr":   cold_hr,
        "Start Time Warm Hr":   warm_hr,
        "Start Time Hot Hr":    hot_hr,
        "Start Heat Cold MBTU": cold_mbtu,
        "Start Heat Warm MBTU": warm_mbtu,
        "Start Heat Hot MBTU":  hot_mbtu,
        "Fuel Price $/MMBTU":   fuel_price,
        "Fixed Cost($/hr)":     round(pmax * 0.5, 2),  # nominal fixed cost
        "Output_pct_0":         0.0,
        "Output_pct_1":         round(pmin / pmax, 4) if pmax > 0 else 0.0,
        "Output_pct_2":         1.0,
        "HR_avg_0":             0.0,
        "HR_incr_1":            flat_cost,
        "HR_incr_2":            flat_cost,
    })

    # Warm start: all units online for 1000 hours
    init_rows.append({
        "GEN":                gen_uid,
        "UnitOnT0State":      1000,
        "PowerGeneratedT0":   pmax,
    })

    assigned += 1

print(f"  Assigned: {assigned}, Unassigned: {unassigned}")

# ---------------------------------------------------------------------------
# 4. Write gen.csv and init_state.csv
# ---------------------------------------------------------------------------
gen_cols = [
    "GEN UID", "Bus ID", "Unit Group", "Unit Type", "Fuel",
    "PMin MW", "PMax MW", "Min Down Time Hr", "Min Up Time Hr",
    "Ramp Rate MW/Min",
    "Start Time Cold Hr", "Start Time Warm Hr", "Start Time Hot Hr",
    "Start Heat Cold MBTU", "Start Heat Warm MBTU", "Start Heat Hot MBTU",
    "Fuel Price $/MMBTU", "Fixed Cost($/hr)",
    "Output_pct_0", "Output_pct_1", "Output_pct_2",
    "HR_avg_0", "HR_incr_1", "HR_incr_2",
]

gen_out = pd.DataFrame(gen_rows, columns=gen_cols)
gen_out.to_csv(SRC_DIR / "gen.csv", index=False)
print(f"  Wrote {SRC_DIR / 'gen.csv'} ({len(gen_out):,} rows)")

init_out = pd.DataFrame(init_rows, columns=["GEN", "UnitOnT0State", "PowerGeneratedT0"])
init_out.to_csv(SRC_DIR / "init_state.csv", index=False)
print(f"  Wrote {SRC_DIR / 'init_state.csv'} ({len(init_out):,} rows)")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print()
print("Summary:")
fuel_stats = gen_out.groupby("Fuel").agg(
    count=("PMax MW", "size"),
    total_mw=("PMax MW", "sum")
).sort_values("total_mw", ascending=False)
for fuel, row in fuel_stats.iterrows():
    print(f"  {fuel:>10s}: {int(row['count']):4d} units, {row['total_mw']:8,.0f} MW")
print(f"  {'TOTAL':>10s}: {len(gen_out):4d} units, {gen_out['PMax MW'].sum():8,.0f} MW")
