#!/usr/bin/env python3
"""
Step 2 (OSM-native) — Build branch.csv from generate_visualizer.py EDGES.

Reads NODES and EDGES_{HIGH,MID_HI,MID_LO} from ny_grid_visualizer.html.
Each edge {a, b, kv} connects two node indices (= Bus IDs from build_osm_bus_table.py).

Also adds synthetic transformer branches between substation node pairs
that are within 300 m of each other at different voltage tiers.

NYISO-specific notes:
  - 115 kV tier included (significant in NYISO, unlike ERCOT)
  - No blanket 345 kV upgrade — NYISO congestion is interface-based;
    branch ratings are calibrated individually in later experiments
  - 765 kV tier for the Massena-Marcy corridor

Impedance convention:
  X_pu = x_ohm_per_km * length_km / (kV^2 / 100)

Outputs:
  grid_data/sced_inputs/SourceData/branch.csv
"""

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
import os as _os

NYISO_DIR = Path(__file__).resolve().parent
DATA      = NYISO_DIR / "grid_data"
SCED_DIR  = DATA / "sced_inputs"
SRC_DIR   = SCED_DIR / "SourceData"
SRC_DIR.mkdir(parents=True, exist_ok=True)
OSM_BUS_CSV = SCED_DIR / "osm_bus.csv"

HTML_FILE        = NYISO_DIR / "ny_grid_visualizer.html"
HV_LINES_GEOJSON = DATA / "ny_hv_lines.geojson"

# ---------------------------------------------------------------------------
# Voltage tier parameters  (x_ohm_per_km, per_circuit_rating_mva)
# ---------------------------------------------------------------------------
VOLTAGE_TIERS = {
    115: (0.40, 200),
    138: (0.38, 400),
    230: (0.35, 600),
    345: (0.32, 1200),
    500: (0.28, 2000),
    765: (0.25, 2400),
}

XFMR_MAX_KM = 0.30


def snap_voltage(kv):
    if kv <= 0:
        return 115
    return min(VOLTAGE_TIERS, key=lambda t: abs(t - kv))


# ---------------------------------------------------------------------------
# Build cables lookup from ny_hv_lines.geojson
# ---------------------------------------------------------------------------
_TIER_STR_TO_KV = {
    "115-229 kV": 138,
    "230-344 kV": 230,
    "345-499 kV": 345,
    "500+ kV":    765,
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
        _circuits_str = str(_p.get("circuits", "") or "").strip()
        try:
            _circuits = max(1, int(_cables_str) // 3)
        except (ValueError, TypeError):
            try:
                _circuits = max(1, int(_circuits_str))
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

# NYISO defaults: most lines are single-circuit unless tagged otherwise
_DEFAULT_CIRCUITS = {115: 1, 138: 1, 230: 1, 345: 1, 500: 1, 765: 1}


def _lookup_circuits(mid_lat, mid_lon, tier_kv, max_km=8.0):
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
# 1. Parse HTML -> NODES and EDGES
# ---------------------------------------------------------------------------
print("Parsing NODES and EDGES from ny_grid_visualizer.html...")
html = HTML_FILE.read_text(encoding="utf-8")


def extract_json_array(html, varname):
    m = re.search(rf"const {varname}\s*=\s*(\[.*?\]);", html, re.DOTALL)
    if not m:
        raise RuntimeError(f"Could not find {varname} in ny_grid_visualizer.html")
    return json.loads(m.group(1))


nodes        = extract_json_array(html, "NODES")
edges_high   = extract_json_array(html, "EDGES_HIGH")
edges_mid_hi = extract_json_array(html, "EDGES_MID_HI")
edges_mid_lo = extract_json_array(html, "EDGES_MID_LO")

all_edges = edges_high + edges_mid_hi + edges_mid_lo

print(f"  Nodes:       {len(nodes):,}")
print(f"  Edges high:  {len(edges_high):,}  (>=345 kV)")
print(f"  Edges mid-hi:{len(edges_mid_hi):,}  (200-344 kV)")
print(f"  Edges mid-lo:{len(edges_mid_lo):,}  (115-199 kV)")
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
        bool(n.get("split", False) or n.get("is_split", False)),
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

    pair = (min(a, b), max(a, b))
    if pair in seen_pairs:
        continue
    seen_pairs.add(pair)

    lat_a, lon_a, kv_a, _ = node_info[a]
    lat_b, lon_b, kv_b, _ = node_info[b]

    length_km = haversine_km(lat_a, lon_a, lat_b, lon_b)
    if length_km < 0.1:
        length_km = 0.1

    effective_kv            = max(kv, kv_a, kv_b)
    tier                    = snap_voltage(effective_kv)
    x_ohm_per_km, per_circ = VOLTAGE_TIERS[tier]
    z_base                  = tier ** 2 / 100.0
    x_pu                    = x_ohm_per_km * length_km / z_base

    mid_lat = (lat_a + lat_b) / 2
    mid_lon = (lon_a + lon_b) / 2
    circuits    = _lookup_circuits(mid_lat, mid_lon, tier)
    cont_rating = per_circ * circuits

    branches.append({
        "UID":         f"L{a}_{b}",
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
# 4. Synthetic transformer branches
# ---------------------------------------------------------------------------
print("Finding synthetic transformer branches...")

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

                pair = (min(i, j), max(i, j))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                lo_kv   = min(tier_i, tier_j)
                hi_kv   = max(tier_i, tier_j)
                lo_bus  = i if tier_i == lo_kv else j
                hi_bus  = i if tier_i == hi_kv else j
                _, lo_rating = VOLTAGE_TIERS.get(lo_kv, VOLTAGE_TIERS[115])

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

print(f"  Transformer branches: {n_xfmr:,}")
print(f"  Total branches:       {len(branches):,}")

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
# 6. Post-processing: unconstrain SPL junctions and short stubs
# ---------------------------------------------------------------------------
print("Post-processing: unconstrain SPL junctions and short stubs...")

_spl_ids  = set(bus_df_filtered.loc[
    bus_df_filtered["is_split"].astype(str).str.lower().isin(["true", "1"]),
    "Bus ID"
].astype(int))
_bus_names = bus_df_filtered.set_index("Bus ID")["Bus Name"].to_dict()
_bus_lat   = bus_df_filtered.set_index("Bus ID")["lat"].to_dict()
_bus_lng   = bus_df_filtered.set_index("Bus ID")["lng"].to_dict()

_spl_mask = (
    branch_df["From Bus"].astype(int).isin(_spl_ids) |
    branch_df["To Bus"].astype(int).isin(_spl_ids)
)
branch_df.loc[_spl_mask, "Cont Rating"] = 999_999.0
print(f"  SPL branches unconstrained: {_spl_mask.sum():,}")

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
_outlet_mask = _stub_mask & (branch_df["Cont Rating"] < 999_000)
branch_df.loc[_outlet_mask, "Cont Rating"] = 999_999.0
print(f"  Stub branches unconstrained: {_outlet_mask.sum():,} (<1 km)")

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
print("Summary:")
print(f"  OSM line branches:    {len(branch_df) - n_xfmr:,}")
print(f"  Transformer branches: {n_xfmr:,}")
print(f"  Total branches:       {len(branch_df):,}")
print(f"  Unconstrained (>=999k):{_n_unconstrained:,}")
print(f"  Buses (main comp):    {len(bus_df_filtered):,}")
print(f"  Buses referenced:     "
      f"{len(set(branch_df['From Bus']) | set(branch_df['To Bus'])):,}")
