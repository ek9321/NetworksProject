#!/usr/bin/env python3
"""
Step 2 (OSM-native) — Build branch.csv from generate_visualizer_v3.py EDGES.

V3: No compensating errors.
  - 138 kV base rating: 250 MVA (single-circuit Drake ACSR)
  - No SPL multiplier (T-junctions get same rating as their voltage tier)
  - No bridge-load compensation
  - Same 345 kV double-circuit policy (all 1200 → 2400 except WESTEX)
  - Same plant outlet stubs (999k for _Plant endpoints and < 1 km)
  - Same cables lookup from GeoJSON

Reads NODES and EDGES_{HIGH,MID_HI,MID_LO} from grid_visualizer_v3.html.
Each edge {a, b, kv} connects two node indices (= Bus IDs from build_osm_bus_table.py).

Impedance convention:
  X_pu = x_ohm_per_km * length_km / (kV^2 / 100)
  Stored as-is in CSV.  Vatic divides by 100 internally, preserving
  DC PTDF ratios (only relative reactances matter for DC power flow).

Outputs:
  sced_inputs_v3/SourceData/branch.csv
"""

import json
import math
import re
from collections import defaultdict, Counter
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths — cluster-aware (DARTBOARD_SCRATCH env var mirrors run_sced.py)
# ---------------------------------------------------------------------------
import os as _os

if _os.environ.get("DARTBOARD_SCRATCH"):
    _SCRATCH = Path(_os.environ["DARTBOARD_SCRATCH"])
    SCED_DIR = _SCRATCH / "sced_inputs_v3"
    HTML_FILE         = _SCRATCH / "grid_data" / "grid_visualizer_v3.html"
    HV_LINES_GEOJSON  = _SCRATCH / "grid_data" / "texas_hv_lines.geojson"
else:
    REPO     = Path(__file__).resolve().parents[2]
    REALIST  = REPO / "Realist"
    DATA     = REALIST / "grid_data"
    SCED_DIR = _os.environ.get("SCED_DIR_OVERRIDE")
    if SCED_DIR:
        SCED_DIR = Path(SCED_DIR)
    else:
        SCED_DIR = DATA / "sced_inputs_v3"
    HTML_FILE         = _os.environ.get("VIZ_HTML")
    if HTML_FILE:
        HTML_FILE = Path(HTML_FILE)
    else:
        HTML_FILE = REALIST / "grid_visualizer_v3.html"
    HV_LINES_GEOJSON  = DATA / "texas_hv_lines.geojson"

SRC_DIR  = SCED_DIR / "SourceData"
SRC_DIR.mkdir(parents=True, exist_ok=True)
OSM_BUS_CSV = SCED_DIR / "osm_bus.csv"

# ---------------------------------------------------------------------------
# Voltage tier parameters  (x_ohm_per_km, per_circuit_rating_mva)
#
# 138 kV: 250 MVA = single-circuit Drake ACSR (physically correct).
# V3 topology should be meshed enough to avoid the 600 MVA compensating
# error that v2 required.
# ---------------------------------------------------------------------------
VOLTAGE_TIERS = {
    138: (0.38, 250),
    230: (0.35, 400),
    345: (0.32, 1200),
    500: (0.28, 2000),
}

# Synthetic transformer: conservative single-unit estimate
TRANSFORMER_PROXY_MVA = 1000

# Synthetic transformer distance — co-located substations within 300 m
XFMR_MAX_KM = 0.30


def snap_voltage(kv):
    if kv <= 0:
        return 138
    return min(VOLTAGE_TIERS, key=lambda t: abs(t - kv))


# ---------------------------------------------------------------------------
# Build cables lookup from texas_hv_lines.geojson
# ---------------------------------------------------------------------------
_TIER_STR_TO_KV = {
    "115-229 kV": 138,
    "230-344 kV": 230,
    "345-499 kV": 345,
    "500+ kV":    500,
}

_CABLE_CELL = 0.10
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
            _circuits = 1
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

_DEFAULT_CIRCUITS = {138: 1, 230: 1, 345: 2, 500: 2}


def _lookup_circuits(mid_lat, mid_lon, tier_kv, max_km=8.0):
    """Return circuit count for nearest GeoJSON segment at given voltage tier."""
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
print(f"Parsing NODES and EDGES from {HTML_FILE}...")
html = HTML_FILE.read_text(encoding="utf-8")


def extract_json_array(html, varname):
    m = re.search(rf"const {varname}\s*=\s*(\[.*?\]);", html, re.DOTALL)
    if not m:
        raise RuntimeError(f"Could not find {varname} in HTML")
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

    # Use route distance from edge if available (v3 stores actual distance
    # along the OSM way geometry, not straight-line haversine).
    length_km = float(edge.get("km") or 0)
    if length_km < 0.1:
        # Fallback to haversine if no route distance stored
        length_km = haversine_km(lat_a, lon_a, lat_b, lon_b)
    if length_km < 0.1:
        length_km = 0.1

    effective_kv            = max(kv, kv_a, kv_b)
    tier                    = snap_voltage(effective_kv)
    x_ohm_per_km, per_circ = VOLTAGE_TIERS[tier]
    z_base                  = tier ** 2 / 100.0
    x_pu                    = x_ohm_per_km * length_km / z_base

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
circ_dist = Counter(b["Cont Rating"] for b in branches)
for rating, cnt in sorted(circ_dist.items()):
    print(f"    {rating:>5} MVA: {cnt:4d} branches")

# ---------------------------------------------------------------------------
# 4. Synthetic transformer branches (residual)
# ---------------------------------------------------------------------------
print("Finding residual synthetic transformer branches (300 m)...")

GRID_CELL = 0.003

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

                pair_key = (min(i, j), max(i, j), 'xfmr')
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

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
# ---------------------------------------------------------------------------
print("Filtering to largest connected component...")

import networkx as nx

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

branch_df = branch_df_full[
    branch_df_full["From Bus"].isin(main_comp) &
    branch_df_full["To Bus"].isin(main_comp)
].reset_index(drop=True)

bus_df_filtered = bus_df[bus_df["Bus ID"].isin(main_comp)].reset_index(drop=True)

osm_bus_path = SCED_DIR / "osm_bus.csv"
src_bus_path = SRC_DIR  / "bus.csv"
bus_df_filtered.to_csv(osm_bus_path, index=False)
bus_df_filtered.to_csv(src_bus_path, index=False)
print(f"  Updated {osm_bus_path} ({len(bus_df_filtered):,} rows)")
print(f"  Updated {src_bus_path} ({len(bus_df_filtered):,} rows)")

# ---------------------------------------------------------------------------
# 6. V3 post-processing: plant outlet stubs + 345 kV double-circuit
#
# NO SPL multiplier (topology handles it).
# NO bridge-load compensation (topology handles it).
# ---------------------------------------------------------------------------
print("Post-processing: V3 plant outlet stubs and 345 kV policy...")

_bus_names = bus_df_filtered.set_index("Bus ID")["Bus Name"].to_dict()
_bus_lat   = bus_df_filtered.set_index("Bus ID")["lat"].to_dict()
_bus_lng   = bus_df_filtered.set_index("Bus ID")["lng"].to_dict()

# (a) Plant outlets: one endpoint name contains "_Plant"
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
# 6b. 345 kV double-circuit upgrade (same policy as v2)
# ---------------------------------------------------------------------------
_WESTEX_KEEP = set()

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
    if rating == 1200.0 and uid not in _WESTEX_KEEP:
        branch_df.at[idx, "Cont Rating"] = 2400.0
        _n_345_upgraded += 1

print(f"  345 kV single→double-circuit: {_n_345_upgraded} branches upgraded to 2400 MVA")
print(f"  WESTEX preserved: {', '.join(_WESTEX_KEEP) or 'not found'} kept at 1200 MVA")

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
print("Summary (V3 — no compensating errors):")
print(f"  OSM line branches:    {len(branch_df) - n_xfmr:,}")
print(f"  Explicit XFMR (300m): {n_xfmr:,}")
print(f"  Total branches:       {len(branch_df):,}")
print(f"  Unconstrained (≥999k):{_n_unconstrained:,}")
print(f"  Thermally limited:    {len(branch_df) - _n_unconstrained:,}")
print(f"  138 kV base rating:   250 MVA (single-circuit)")
print(f"  SPL multiplier:       None (1×)")
print(f"  Bridge compensation:  None")
print(f"  Buses (main comp):    {len(bus_df_filtered):,}")
print(f"  Buses referenced:     "
      f"{len(set(branch_df['From Bus']) | set(branch_df['To Bus'])):,}")
