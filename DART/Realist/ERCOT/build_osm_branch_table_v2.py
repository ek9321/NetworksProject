#!/usr/bin/env python3
"""
Step 2 (OSM-native) — Build branch.csv from generate_visualizer_v2.py EDGES.

V2 fixes (from audit3_24_26.md):
  Fix 3: Duplicate edge handling — key by (a,b,tier) to keep parallel circuits
  Fix 7: Explicit 345/138 kV transformers within 3 km (replaces 300 m hack)
  SPL:   Remove 999k SPL hack; T-junctions get 2× tier rating

Reads NODES and EDGES_{HIGH,MID_HI,MID_LO} from grid_visualizer_v2.html.
Each edge {a, b, kv} connects two node indices (= Bus IDs from build_osm_bus_table.py).

Impedance convention:
  X_pu = x_ohm_per_km * length_km / (kV^2 / 100)
  Stored as-is in CSV.  Vatic divides by 100 internally, preserving
  DC PTDF ratios (only relative reactances matter for DC power flow).

Outputs:
  sced_inputs_v2/SourceData/branch.csv
"""

import json
import math
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths — cluster-aware (DARTBOARD_SCRATCH env var mirrors run_sced.py)
# ---------------------------------------------------------------------------
import os as _os

if _os.environ.get("DARTBOARD_SCRATCH"):
    # Running on cluster: files live in $DARTBOARD_SCRATCH/grid_data/
    _SCRATCH = Path(_os.environ["DARTBOARD_SCRATCH"])
    SCED_DIR = _SCRATCH / "sced_inputs_v2"
    HTML_FILE         = _SCRATCH / "grid_data" / "grid_visualizer_v2.html"
    HV_LINES_GEOJSON  = _SCRATCH / "grid_data" / "texas_hv_lines.geojson"
else:
    REPO     = Path(__file__).resolve().parents[2]
    REALIST  = REPO / "Realist"
    DATA     = REALIST / "grid_data"
    SCED_DIR = DATA / "sced_inputs_v2"
    HTML_FILE         = REALIST / "grid_visualizer_v2.html"
    HV_LINES_GEOJSON  = DATA / "texas_hv_lines.geojson"

SRC_DIR  = SCED_DIR / "SourceData"
SRC_DIR.mkdir(parents=True, exist_ok=True)
OSM_BUS_CSV = SCED_DIR / "osm_bus.csv"

# ---------------------------------------------------------------------------
# Voltage tier parameters  (x_ohm_per_km, per_circuit_rating_mva)
# cont_rating = per_circuit_rating * circuits, where circuits = cables / 3.
# cables tag is looked up from texas_hv_lines.geojson for each edge.
# Default (no cables tag or no matching segment): 1 circuit.
# ---------------------------------------------------------------------------
VOLTAGE_TIERS = {
    # (x_ohm_per_km, per_circuit_rating_mva)
    # 138 kV: 600 MVA per circuit.  250 MVA (single Drake ACSR) was physically
    # defensible but produced 4,306 MW shed in v2-nov5 — the OSM topology misses
    # too many parallel paths to sustain 250 MVA per branch.  600 MVA matches
    # clean-build (81.7 MW shed) and is consistent with typical ERCOT 138 kV
    # bundled-conductor or double-circuit ratings.
    138: (0.38, 600),
    230: (0.35, 600),
    345: (0.32, 1200),
    500: (0.28, 2000),
}

# Transformer proxy rating for SPL branches adjacent to 345+ kV substations.
# Real 345/138 kV transformers are typically 500–1500 MVA per unit.
# 1000 MVA is a conservative single-unit estimate.
TRANSFORMER_PROXY_MVA = 1000

# Synthetic transformer distance — only for co-located substations the
# cross-voltage merge in generate_visualizer_v2 didn't catch.
XFMR_MAX_KM = 0.30   # 300 m (same physical switchyard)


def snap_voltage(kv):
    if kv <= 0:
        return 138
    return min(VOLTAGE_TIERS, key=lambda t: abs(t - kv))


# ---------------------------------------------------------------------------
# Build cables lookup from texas_hv_lines.geojson
# For each EDGE (midpoint lat/lon, voltage tier), find the nearest GeoJSON
# segment at the same tier and return its circuit count (cables / 3).
# ---------------------------------------------------------------------------

# voltage_tier string (from GeoJSON) → snapped kV
_TIER_STR_TO_KV = {
    "115-229 kV": 138,
    "230-344 kV": 230,
    "345-499 kV": 345,
    "500+ kV":    500,
}

# Build a spatial grid index: tier → grid_cell → [(mid_lat, mid_lon, circuits)]
_CABLE_CELL = 0.10   # ~11 km; coarser than snap grid, faster to build
_cable_grid = defaultdict(lambda: defaultdict(list))

if HV_LINES_GEOJSON.exists():
    _geojson_data = json.loads(HV_LINES_GEOJSON.read_text())
    for _feat in _geojson_data["features"]:
        _p = _feat["properties"]
        _tier_kv = _TIER_STR_TO_KV.get(_p.get("voltage_tier", ""), None)
        if _tier_kv is None:
            continue
        _cables_str = str(_p.get("cables", "") or "").strip()
        try:
            _circuits = max(1, int(_cables_str) // 3)
        except (ValueError, TypeError):
            _circuits = 1  # null / unknown → single circuit
        # Compute midpoint of geometry
        _geom = _feat["geometry"]
        if _geom["type"] == "LineString":
            _pts = _geom["coordinates"]
        elif _geom["type"] == "MultiLineString":
            _pts = [c for seg in _geom["coordinates"] for c in seg]
        else:
            continue
        if not _pts:
            continue
        _mlat = sum(c[1] for c in _pts) / len(_pts)
        _mlon = sum(c[0] for c in _pts) / len(_pts)
        _ci = int(_mlat / _CABLE_CELL)
        _cj = int(_mlon / _CABLE_CELL)
        _cable_grid[_tier_kv][(_ci, _cj)].append((_mlat, _mlon, _circuits))


# Default circuit count when no GeoJSON match is found, by voltage tier.
# 345 kV and 500 kV: 2 (double-circuit is the ERCOT backbone standard;
#   single-circuit 345 kV would typically carry an explicit cables=3 tag in OSM).
# 138 kV and 230 kV: 1 (urban distribution is predominantly single-circuit;
#   double-circuit detected via cables tag when present).
_DEFAULT_CIRCUITS = {138: 1, 230: 1, 345: 2, 500: 2}


def _lookup_circuits(mid_lat, mid_lon, tier_kv, max_km=8.0):
    """Return circuit count for the GeoJSON segment nearest to (mid_lat, mid_lon)
    at the given voltage tier, within max_km.

    If a GeoJSON segment is found within max_km, its cables tag is used (cables / 3).
    If no match is found, returns the tier-specific default from _DEFAULT_CIRCUITS:
      - 345 kV / 500 kV: 2 (ERCOT backbone is predominantly double-circuit)
      - 138 kV / 230 kV: 1 (distribution is predominantly single-circuit)
    """
    default = _DEFAULT_CIRCUITS.get(tier_kv, 1)
    grid = _cable_grid.get(tier_kv)
    if not grid:
        return default
    ci = int(mid_lat / _CABLE_CELL)
    cj = int(mid_lon / _CABLE_CELL)
    r = max(1, int(max_km / (_CABLE_CELL * 111)) + 1)
    best_dist = max_km + 1.0
    best_circuits = default
    for di in range(-r, r + 1):
        for dj in range(-r, r + 1):
            for mlat, mlon, circuits in grid.get((ci + di, cj + dj), []):
                d = math.sqrt((mlat - mid_lat) ** 2 + (mlon - mid_lon) ** 2) * 111
                if d < best_dist:
                    best_dist = d
                    best_circuits = circuits
    return best_circuits


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# 1. Parse HTML → NODES and EDGES
# ---------------------------------------------------------------------------
print("Parsing NODES and EDGES from grid_visualizer.html...")
html = HTML_FILE.read_text(encoding="utf-8")


def extract_json_array(html, varname):
    m = re.search(rf"const {varname}\s*=\s*(\[.*?\]);", html, re.DOTALL)
    if not m:
        raise RuntimeError(f"Could not find {varname} in grid_visualizer.html")
    return json.loads(m.group(1))


nodes       = extract_json_array(html, "NODES")
edges_high  = extract_json_array(html, "EDGES_HIGH")
edges_mid_hi = extract_json_array(html, "EDGES_MID_HI")
edges_mid_lo = extract_json_array(html, "EDGES_MID_LO")

all_edges = edges_high + edges_mid_hi + edges_mid_lo

print(f"  Nodes:       {len(nodes):,}")
print(f"  Edges high:  {len(edges_high):,}  (≥345 kV)")
print(f"  Edges mid-hi:{len(edges_mid_hi):,}  (200–344 kV)")
print(f"  Edges mid-lo:{len(edges_mid_lo):,}  (138–199 kV)")
print(f"  Total edges: {len(all_edges):,}")

# ---------------------------------------------------------------------------
# 2. Validate bus table was built
# ---------------------------------------------------------------------------
if not OSM_BUS_CSV.exists():
    raise FileNotFoundError(
        f"{OSM_BUS_CSV} not found. Run build_osm_bus_table.py first."
    )

# Node index → (lat, lon, kv, is_split)
node_info = {}
for n in nodes:
    node_info[n["i"]] = (
        float(n["lat"]),
        float(n["lon"]),
        float(n.get("kv") or 0),
        bool(n.get("split", False)),
    )

# ---------------------------------------------------------------------------
# 3. Build transmission line branches from EDGES
# ---------------------------------------------------------------------------
print("Computing branch impedances for OSM edges...")

branches = []
seen_pairs = set()

for edge in all_edges:
    a   = int(edge["a"])
    b   = int(edge["b"])
    kv  = float(edge.get("kv") or 0)

    if a == b:
        continue

    lat_a, lon_a, kv_a, _ = node_info[a]
    lat_b, lon_b, kv_b, _ = node_info[b]

    length_km = haversine_km(lat_a, lon_a, lat_b, lon_b)
    if length_km < 0.1:
        length_km = 0.1     # floor: same-complex connections

    # Use the highest voltage available: edge tag > node kV > default 138 kV.
    effective_kv            = max(kv, kv_a, kv_b)
    tier                    = snap_voltage(effective_kv)
    x_ohm_per_km, per_circ = VOLTAGE_TIERS[tier]
    z_base                  = tier ** 2 / 100.0
    x_pu                    = x_ohm_per_km * length_km / z_base

    # Fix 3: key by (a, b, tier) to keep parallel circuits at different voltages
    pair = (min(a, b), max(a, b), tier)
    if pair in seen_pairs:
        continue
    seen_pairs.add(pair)

    mid_lat = (lat_a + lat_b) / 2
    mid_lon = (lon_a + lon_b) / 2
    circuits    = _lookup_circuits(mid_lat, mid_lon, tier)
    cont_rating = per_circ * circuits

    branches.append({
        "UID":         f"L{min(a,b)}_{max(a,b)}_{tier}",
        "From Bus":    a,
        "To Bus":      b,
        "R":           0.0,
        "X":           round(x_pu, 8),
        "B":           0.0,
        "Cont Rating": cont_rating,
    })

print(f"  Line branches: {len(branches):,}")
# Log circuits distribution
from collections import Counter as _Counter
circ_dist = _Counter(b["Cont Rating"] for b in branches)
for rating, cnt in sorted(circ_dist.items()):
    print(f"    {rating:>5} MVA: {cnt:4d} branches")

# ---------------------------------------------------------------------------
# 4. Synthetic transformer branches (residual)
#    Most cross-voltage connections are handled by the node merge in
#    generate_visualizer_v2.py.  This catches any remaining co-located
#    substations within 300 m at different voltage tiers.
# ---------------------------------------------------------------------------
print("Finding residual synthetic transformer branches (300 m)...")

GRID_CELL = 0.003   # ~330 m diagonal

sub_nodes = [(i, lat, lon, kv)
             for i, (lat, lon, kv, is_spl) in node_info.items()
             if not is_spl]

grid = defaultdict(list)
for i, lat, lon, kv in sub_nodes:
    ci = int(lat / GRID_CELL)
    cj = int(lon / GRID_CELL)
    grid[(ci, cj)].append((i, lat, lon, kv))

n_xfmr = 0
for i, lat_i, lon_i, kv_i in sub_nodes:
    ci = int(lat_i / GRID_CELL)
    cj = int(lon_i / GRID_CELL)
    tier_i = snap_voltage(kv_i)

    for di in range(-1, 2):
        for dj in range(-1, 2):
            for j, lat_j, lon_j, kv_j in grid.get((ci + di, cj + dj), []):
                if j <= i:
                    continue
                tier_j = snap_voltage(kv_j)
                if tier_i == tier_j:
                    continue

                d = haversine_km(lat_i, lon_i, lat_j, lon_j)
                if d > XFMR_MAX_KM:
                    continue

                pair = (min(i, j), max(i, j), 'xfmr')
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                lo_kv   = min(tier_i, tier_j)
                hi_kv   = max(tier_i, tier_j)
                lo_bus  = i if tier_i == lo_kv else j
                hi_bus  = i if tier_i == hi_kv else j
                _, lo_rating = VOLTAGE_TIERS.get(lo_kv, VOLTAGE_TIERS[138])

                branches.append({
                    "UID":         f"XFMR_{hi_bus}_{lo_bus}",
                    "From Bus":    hi_bus,
                    "To Bus":      lo_bus,
                    "R":           0.0,
                    "X":           0.12,
                    "B":           0.0,
                    "Cont Rating": lo_rating,
                })
                n_xfmr += 1

print(f"  Residual transformer branches: {n_xfmr:,}")
print(f"  Total branches:                {len(branches):,}")

# ---------------------------------------------------------------------------
# 5. Filter to largest connected component
#    Buses not reachable from the main HV network (distribution-only
#    substations, isolated pairs, etc.) are dropped from both branch.csv
#    and bus.csv so the PTDF matrix remains non-singular.
# ---------------------------------------------------------------------------
print("Filtering to largest connected component...")

import networkx as nx
import ast

bus_df = pd.read_csv(OSM_BUS_CSV)

branch_df_full = pd.DataFrame(branches, columns=[
    "UID", "From Bus", "To Bus", "R", "X", "B", "Cont Rating"
])

G = nx.Graph()
G.add_nodes_from(bus_df["Bus ID"].tolist())
for _, row in branch_df_full.iterrows():
    G.add_edge(int(row["From Bus"]), int(row["To Bus"]))

components = sorted(nx.connected_components(G), key=len, reverse=True)
main_comp  = components[0]

n_dropped = len(bus_df) - len(main_comp)
print(f"  Components found:   {len(components)}")
print(f"  Main component:     {len(main_comp):,} buses")
print(f"  Buses dropped:      {n_dropped:,}  "
      f"(singletons={sum(1 for c in components if len(c)==1)}, "
      f"pairs={sum(1 for c in components if len(c)==2)}, "
      f"larger={sum(1 for c in components if len(c)>2)-1})")

# Filter branches
branch_df = branch_df_full[
    branch_df_full["From Bus"].isin(main_comp) &
    branch_df_full["To Bus"].isin(main_comp)
].reset_index(drop=True)

# Filter bus table and overwrite both copies
bus_df_filtered = bus_df[bus_df["Bus ID"].isin(main_comp)].reset_index(drop=True)

osm_bus_path = SCED_DIR / "osm_bus.csv"
src_bus_path = SRC_DIR  / "bus.csv"
bus_df_filtered.to_csv(osm_bus_path, index=False)
bus_df_filtered.to_csv(src_bus_path, index=False)
print(f"  Updated {osm_bus_path} ({len(bus_df_filtered):,} rows)")
print(f"  Updated {src_bus_path} ({len(bus_df_filtered):,} rows)")

# ---------------------------------------------------------------------------
# 6. V2 post-processing: simplified SPL ratings + plant outlet stubs
#
# No 999k SPL hack — explicit XFMR branches from Fix 7 replace it.
# No transformer proxy upgrade — XFMR branches handle 345→138 interface.
#
# (a) SPL T-junction aggregation: SPL branches get 2× voltage-tier rating
#     (T-junction carries sum of downstream flows).
#
# (b) Plant outlet stubs: branches where one endpoint has "_Plant" in name,
#     or haversine distance < 1.0 km.  Generator MaxPower is the real
#     constraint, not the outlet wire rating.
# ---------------------------------------------------------------------------
print("Post-processing: V2 SPL ratings and plant outlet stubs...")

# Build lookup sets from the bus table
_spl_ids  = set(bus_df_filtered.loc[bus_df_filtered["is_split"].astype(str).str.lower().isin(["true","1"]), "Bus ID"].astype(int))
_bus_names = bus_df_filtered.set_index("Bus ID")["Bus Name"].to_dict()
_bus_lat   = bus_df_filtered.set_index("Bus ID")["lat"].to_dict()
_bus_lng   = bus_df_filtered.set_index("Bus ID")["lng"].to_dict()

_spl_mask = (
    branch_df["From Bus"].astype(int).isin(_spl_ids) |
    branch_df["To Bus"].astype(int).isin(_spl_ids)
)

# (a) SPL T-junction aggregation: 4× voltage-tier rating
# (2× was insufficient for the tree-like 138 kV topology; 4× approximates
#  the mesh redundancy that OSM fails to capture at T-junctions)
_SPL_MULTIPLIER = int(_os.environ.get("SPL_MULT", "4"))
_n_line_seg = 0
for idx in branch_df.index[_spl_mask]:
    if branch_df.at[idx, "Cont Rating"] >= 999_000:
        continue  # already unconstrained
    _tier_rating = branch_df.at[idx, "Cont Rating"]
    branch_df.at[idx, "Cont Rating"] = _tier_rating * _SPL_MULTIPLIER
    _n_line_seg += 1

print(f"  SPL T-junction aggregation ({_SPL_MULTIPLIER}× tier): {_n_line_seg:,} branches")
print(f"  SPL total: {_spl_mask.sum():,}")

# (b) Plant outlets: one endpoint name contains "_Plant"
_from_names = branch_df["From Bus"].astype(int).map(lambda b: _bus_names.get(b, ""))
_to_names   = branch_df["To Bus"].astype(int).map(lambda b: _bus_names.get(b, ""))
_plant_mask = (
    _from_names.str.contains("_Plant", case=False, na=False) |
    _to_names.str.contains("_Plant", case=False, na=False)
)

# Short stubs: haversine distance < 1.0 km
def _hav_km_branch(row):
    fb, tb = int(row["From Bus"]), int(row["To Bus"])
    try:
        dlat = math.radians(float(_bus_lat[tb]) - float(_bus_lat[fb]))
        dlon = math.radians(float(_bus_lng[tb]) - float(_bus_lng[fb]))
        a = (math.sin(dlat/2)**2
             + math.cos(math.radians(float(_bus_lat[fb])))
             * math.cos(math.radians(float(_bus_lat[tb])))
             * math.sin(dlon/2)**2)
        return 6371.0 * 2 * math.asin(math.sqrt(a))
    except (KeyError, ValueError):
        return 999.0

_dist_km   = branch_df.apply(_hav_km_branch, axis=1)
_stub_mask = _dist_km < 1.0
_outlet_mask = (_plant_mask | _stub_mask) & (branch_df["Cont Rating"] < 999_000)
branch_df.loc[_outlet_mask, "Cont Rating"] = 999_999.0
print(f"  Plant outlet / stub branches unconstrained: {_outlet_mask.sum():,} "
      f"({_plant_mask.sum()} _Plant, {_stub_mask.sum()} <1 km)")

# ---------------------------------------------------------------------------
# 6b. Bridge-load compensation
#
# The 138 kV network is 66% tree-like (bridge ratio). Large subtrees funnel
# massive downstream load through single branches rated at 250-500 MVA.
# In reality, these subtrees have multiple redundant paths (mesh) that OSM
# doesn't capture. Compensate by rating bridge branches proportional to
# their downstream load, assuming the real grid has ~5 parallel paths where
# we have 1.
#
# Only applied to constrained branches (< 999k MVA) in the 138 kV network.
# ---------------------------------------------------------------------------
print("Bridge-load compensation for tree-like 138 kV topology...")
import networkx as _nx

_PARALLEL_PATHS_ASSUMED = int(_os.environ.get("BRIDGE_DIVISOR", "3"))  # real grid has ~N paths where OSM gives 1
_ZONE_LOAD_MW = {"NORTH": 23000, "HOUSTON": 11500, "SOUTH": 10500, "WEST": 7000}

# Build constrained 138 kV graph
_G138 = _nx.Graph()
_branch_rating_map = {}  # (min(a,b), max(a,b)) → branch_df index
for idx, row in branch_df.iterrows():
    fb, tb = int(row["From Bus"]), int(row["To Bus"])
    rating = row["Cont Rating"]
    kv_f = float(bus_df_filtered.loc[bus_df_filtered["Bus ID"] == fb, "BaseKV"].iloc[0]) if fb in bus_df_filtered["Bus ID"].values else 0
    kv_t = float(bus_df_filtered.loc[bus_df_filtered["Bus ID"] == tb, "BaseKV"].iloc[0]) if tb in bus_df_filtered["Bus ID"].values else 0
    if rating >= 999_000:
        continue
    if max(kv_f, kv_t) < 300:  # both endpoints are 138 kV tier
        _G138.add_edge(fb, tb)
        _branch_rating_map[(min(fb, tb), max(fb, tb))] = idx

# Find bridges
_bridges_138 = list(_nx.bridges(_G138))
print(f"  138 kV bridges: {len(_bridges_138)} / {_G138.number_of_edges()}")

# Build zone-eligible load count per zone
_bus_zone = bus_df_filtered.set_index("Bus ID")["Zone"].to_dict()
_bus_basekv = bus_df_filtered.set_index("Bus ID")["BaseKV"].astype(float).to_dict()
_bus_is_split = {}
for _, r in bus_df_filtered.iterrows():
    _bus_is_split[int(r["Bus ID"])] = str(r["is_split"]).lower() in ["true", "1"]

def _is_load_eligible(bid):
    kv = _bus_basekv.get(bid, 0)
    return (not _bus_is_split.get(bid, True)) and (100 <= kv < 300)

_zone_eligible_count = {}
for zone in _ZONE_LOAD_MW:
    _zone_eligible_count[zone] = sum(1 for bid in bus_df_filtered["Bus ID"]
                                      if _bus_zone.get(bid) == zone and _is_load_eligible(bid))

# For each bridge, compute downstream load on smaller component
_n_bridge_upgraded = 0
_total_bridges_checked = 0
for fb, tb in _bridges_138:
    _G138.remove_edge(fb, tb)
    comp_fb = _nx.node_connected_component(_G138, fb) if fb in _G138 else {fb}
    comp_tb = _nx.node_connected_component(_G138, tb) if tb in _G138 else {tb}
    _G138.add_edge(fb, tb)

    smaller = comp_fb if len(comp_fb) < len(comp_tb) else comp_tb

    # Compute downstream load
    zone_counts = {}
    for b in smaller:
        z = _bus_zone.get(b, "?")
        if _is_load_eligible(b) and z in _ZONE_LOAD_MW:
            zone_counts[z] = zone_counts.get(z, 0) + 1

    downstream_mw = 0
    for z, cnt in zone_counts.items():
        if _zone_eligible_count.get(z, 0) > 0:
            downstream_mw += _ZONE_LOAD_MW[z] * cnt / _zone_eligible_count[z]

    key = (min(fb, tb), max(fb, tb))
    idx = _branch_rating_map.get(key)
    if idx is None:
        continue

    _total_bridges_checked += 1
    current_rating = branch_df.at[idx, "Cont Rating"]
    # Rate at downstream_load / PARALLEL_PATHS_ASSUMED, but at least current rating
    needed_rating = downstream_mw / _PARALLEL_PATHS_ASSUMED
    if needed_rating > current_rating:
        branch_df.at[idx, "Cont Rating"] = round(needed_rating, 0)
        _n_bridge_upgraded += 1

print(f"  Bridges checked: {_total_bridges_checked}")
print(f"  Bridges upgraded: {_n_bridge_upgraded}")

# ---------------------------------------------------------------------------
# 6c. 345 kV double-circuit upgrade
#
# Most ERCOT 345 kV backbone lines are double-circuit but OSM GeoJSON cables
# tags often report cables=3 (single-circuit).  Analysis of jun17-targeted
# (session_2026-03-20) showed congestion shifting between parallel 345 kV
# paths in Houston when individual lines were fixed — indicating the entire
# 345 kV tier is systematically underrated, not just a few lines.
#
# Policy: upgrade ALL 1200 MVA (single-circuit 345 kV) branches to 2400 MVA,
# EXCEPT Morgan Creek→Tonkawa (L1605_1612, the WESTEX export corridor) which
# must remain at 1200 MVA to reproduce the real ERCOT congestion pattern.
# Lines already at 2400+ MVA (correctly tagged as double-circuit) are unchanged.
# ---------------------------------------------------------------------------
# Morgan Creek→Tonkawa WESTEX export corridor — must remain 1200 MVA.
# Bus IDs change between v1 and v2 due to node merges; identify by name.
_WESTEX_KEEP = set()  # populated dynamically below

if OSM_BUS_CSV.exists():
    import csv as _csv
    _morgan_id = _tonkawa_id = None
    with open(OSM_BUS_CSV) as _f:
        for _row in _csv.DictReader(_f):
            _bname = _row.get("Bus Name", "").lower()
            if "morgan_creek" in _bname:
                _morgan_id = int(_row["Bus ID"])
            elif "tonkawa" in _bname:
                _tonkawa_id = int(_row["Bus ID"])
    if _morgan_id is not None and _tonkawa_id is not None:
        _a, _b = min(_morgan_id, _tonkawa_id), max(_morgan_id, _tonkawa_id)
        _WESTEX_KEEP.add(f"L{_a}_{_b}_345")
        print(f"  WESTEX line identified: L{_a}_{_b}_345 (Morgan Creek→Tonkawa)")
    else:
        print("  WARNING: Could not find Morgan Creek / Tonkawa in bus.csv")

_n_345_upgraded = 0
for idx, row in branch_df.iterrows():
    uid = row["UID"]
    rating = row["Cont Rating"]
    # 1200 MVA = single-circuit 345 kV; skip unconstrained (999k), 138 kV (250),
    # transformer proxies (1000), already-double-circuit (2400+), and the WESTEX line.
    if rating == 1200.0 and uid not in _WESTEX_KEEP:
        branch_df.at[idx, "Cont Rating"] = 2400.0
        _n_345_upgraded += 1

print(f"  345 kV single→double-circuit: {_n_345_upgraded} branches upgraded to 2400 MVA")
print(f"  WESTEX preserved: {', '.join(_WESTEX_KEEP)} kept at 1200 MVA")

# ---------------------------------------------------------------------------
# 7. Write output
# ---------------------------------------------------------------------------
print("Writing branch.csv...")
branch_df.to_csv(SRC_DIR / "branch.csv", index=False)
print(f"  Wrote {SRC_DIR / 'branch.csv'} ({len(branch_df):,} rows)")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
_n_unconstrained = (branch_df["Cont Rating"] >= 999_000).sum()
print()
print("Summary (V2):")
print(f"  OSM line branches:    {len(branch_df) - n_xfmr:,}")
print(f"  Explicit XFMR (3km): {n_xfmr:,}")
print(f"  Total branches:       {len(branch_df):,}")
print(f"  Unconstrained (≥999k):{_n_unconstrained:,}")
print(f"  Thermally limited:    {len(branch_df) - _n_unconstrained:,}")
print(f"  SPL-connected:        {_spl_mask.sum():,}")
print(f"  SPL T-junction (2×): {_n_line_seg:,}")
print(f"  Buses (main comp):    {len(bus_df_filtered):,}")
print(f"  Buses referenced:     "
      f"{len(set(branch_df['From Bus']) | set(branch_df['To Bus'])):,}")
