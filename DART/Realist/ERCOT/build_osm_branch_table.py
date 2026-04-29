#!/usr/bin/env python3
"""
Step 2 (OSM-native) — Build branch.csv from generate_visualizer.py EDGES.

Reads NODES and EDGES_{HIGH,MID_HI,MID_LO} from grid_visualizer.html.
Each edge {a, b, kv} connects two node indices (= Bus IDs from build_osm_bus_table.py).

Also adds synthetic transformer branches between substation node pairs
that are within 300 m of each other at different voltage tiers.

Impedance convention:
  X_pu = x_ohm_per_km * length_km / (kV^2 / 100)
  Stored as-is in CSV.  Vatic divides by 100 internally, preserving
  DC PTDF ratios (only relative reactances matter for DC power flow).

Outputs:
  sced_inputs/SourceData/branch.csv
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
    SCED_DIR = _SCRATCH / "sced_inputs"
    HTML_FILE         = _SCRATCH / "grid_data" / "grid_visualizer.html"
    HV_LINES_GEOJSON  = _SCRATCH / "grid_data" / "texas_hv_lines.geojson"
else:
    REPO     = Path(__file__).resolve().parents[2]
    REALIST  = REPO / "Realist"
    DATA     = REALIST / "grid_data"
    SCED_DIR = DATA / "sced_inputs"
    HTML_FILE         = REALIST / "grid_visualizer.html"
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
    # 138 kV: 250 MVA = single Drake ACSR (Texas-2k 161 kV median = 251 MVA).
    # 345/500 kV: realistic, validated against Texas-2k within 1%.
    # SPL branches near 345 kV substations get 1000 MVA (transformer proxy) — see step 6.
    138: (0.38, 250),
    230: (0.35, 600),
    345: (0.32, 1200),
    500: (0.28, 2000),
}

# Transformer proxy rating for SPL branches adjacent to 345+ kV substations.
# Real 345/138 kV transformers are typically 500–1500 MVA per unit.
# 1000 MVA is a conservative single-unit estimate.
TRANSFORMER_PROXY_MVA = 1000

# Max distance for synthetic transformer branch candidates
XFMR_MAX_KM = 0.30   # 300 m


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

    pair = (min(a, b), max(a, b))
    if pair in seen_pairs:
        continue
    seen_pairs.add(pair)

    lat_a, lon_a, kv_a, _ = node_info[a]
    lat_b, lon_b, kv_b, _ = node_info[b]

    length_km = haversine_km(lat_a, lon_a, lat_b, lon_b)
    if length_km < 0.1:
        length_km = 0.1     # floor: same-complex connections

    # Use the highest voltage available: edge tag > node kV > default 138 kV.
    # Edge kv=0 is common when the OSM way lacks a voltage tag; the connecting
    # bus voltages are more reliable in that case.
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
# Log circuits distribution
from collections import Counter as _Counter
circ_dist = _Counter(b["Cont Rating"] for b in branches)
for rating, cnt in sorted(circ_dist.items()):
    print(f"    {rating:>5} MVA: {cnt:4d} branches")

# ---------------------------------------------------------------------------
# 4. Synthetic transformer branches
#    Any two substation nodes within XFMR_MAX_KM at different voltage tiers.
#    Use a grid index so this is O(N) rather than O(N²).
# ---------------------------------------------------------------------------
print("Finding synthetic transformer branches...")

GRID_CELL = 0.003   # ~330 m diagonal — slightly larger than XFMR_MAX_KM

sub_nodes = [(i, lat, lon, kv)
             for i, (lat, lon, kv, is_spl) in node_info.items()
             if not is_spl]

# Build grid index
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

print(f"  Transformer branches: {n_xfmr:,}")
print(f"  Total branches:       {len(branches):,}")

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
# 6. Permanent post-processing: SPL segment ratings and outlet branches
#
# (a) SPL junction branches: segments created by T-junction line splitting.
#     Smart rating based on network context (session_2026-03-24 root cause analysis):
#
#     - Near 345+ kV: the branch is functioning as a transformer proxy between
#       the HV backbone and the 138 kV distribution network.  Real 345/138 kV
#       transformers are 500–1500 MVA.  Rate at TRANSFORMER_PROXY_MVA (1000).
#
#     - Pure 138 kV: the branch is a real T-junction segment on a 138 kV line.
#       Rate at the 138 kV voltage-tier rating (250 MVA).
#
#     The criterion: if EITHER endpoint of the SPL branch connects (via any
#     other branch) to a bus with a constrained rating >= 1200 MVA, it's
#     adjacent to the 345 kV network and gets the transformer proxy rating.
#
# (b) Plant outlet stubs and bus sections: branches where one endpoint has
#     "_Plant" in its name (generator outlet), or where haversine distance
#     < 1.0 km (bus sections / switching paths).  The generator's own MaxPower
#     in gen.csv is the binding constraint, not the outlet wire rating.
#     1.0 km threshold captures more stub segments than the old 0.5 km runtime
#     env-var version (see session_2026-03-19.md, best-so-far binding table).
# ---------------------------------------------------------------------------
print("Post-processing: smart SPL ratings and plant outlet stubs...")

# Build lookup sets from the bus table
_spl_ids  = set(bus_df_filtered.loc[bus_df_filtered["is_split"].astype(str).str.lower().isin(["true","1"]), "Bus ID"].astype(int))
_bus_names = bus_df_filtered.set_index("Bus ID")["Bus Name"].to_dict()
_bus_lat   = bus_df_filtered.set_index("Bus ID")["lat"].to_dict()
_bus_lng   = bus_df_filtered.set_index("Bus ID")["lng"].to_dict()

_spl_mask = (
    branch_df["From Bus"].astype(int).isin(_spl_ids) |
    branch_df["To Bus"].astype(int).isin(_spl_ids)
)

# Compute max constrained rating at each bus (ignoring 999k branches).
# Used to detect which buses are adjacent to the 345 kV backbone.
_bus_max_rating = {}
for _, _row in branch_df.iterrows():
    _r = _row["Cont Rating"]
    if _r >= 999_000:
        continue
    for _bid in (int(_row["From Bus"]), int(_row["To Bus"])):
        _bus_max_rating[_bid] = max(_bus_max_rating.get(_bid, 0), _r)

# (a-i) Transformer proxy: upgrade ANY branch (SPL or not) where one endpoint
#       is a 345+ kV bus.  This captures both SPL junctions and regular branches
#       at the 345→138 kV interface (e.g. L2649_3019 at P.H. Robinson).
_n_xfmr_proxy = 0
_xfmr_mask = pd.Series(False, index=branch_df.index)
for idx, row in branch_df.iterrows():
    if row["Cont Rating"] >= 999_000:
        continue  # skip already-unconstrained
    _fb = int(row["From Bus"])
    _tb = int(row["To Bus"])
    _max_fb = _bus_max_rating.get(_fb, 0)
    _max_tb = _bus_max_rating.get(_tb, 0)
    _cur = row["Cont Rating"]
    # One endpoint is 345+ kV, the other is lower → transformer interface
    if (_max_fb >= 1200 and _cur < 1200) or (_max_tb >= 1200 and _cur < 1200):
        if _cur < TRANSFORMER_PROXY_MVA:
            branch_df.at[idx, "Cont Rating"] = float(TRANSFORMER_PROXY_MVA)
            _xfmr_mask.at[idx] = True
            _n_xfmr_proxy += 1

print(f"  Transformer proxy ({TRANSFORMER_PROXY_MVA} MVA): {_n_xfmr_proxy:,} branches "
      f"(any branch at 345→138 kV interface)")

# (a-ii) SPL T-junction aggregation: SPL branches in pure 138 kV context get
#        2× voltage-tier rating (T-junction carries sum of downstream flows).
_n_line_seg = 0
for idx in branch_df.index[_spl_mask]:
    if _xfmr_mask.at[idx]:
        continue  # already upgraded to transformer proxy
    if branch_df.at[idx, "Cont Rating"] >= 999_000:
        continue  # already unconstrained (plant outlet / stub)
    _tier_rating = branch_df.at[idx, "Cont Rating"]
    branch_df.at[idx, "Cont Rating"] = _tier_rating * 2
    _n_line_seg += 1

print(f"  SPL T-junction aggregation (2× tier): {_n_line_seg:,} branches")
print(f"  SPL total: {_spl_mask.sum():,}")

# Plant outlets: one endpoint name contains "_Plant"
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
# 6b. 345 kV double-circuit upgrade
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
_WESTEX_KEEP = {"L1605_1612"}  # Morgan Creek→Tonkawa — intentionally 1200 MVA

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
print("Summary:")
print(f"  OSM line branches:    {len(branch_df) - n_xfmr:,}")
print(f"  Transformer branches: {n_xfmr:,}")
print(f"  Total branches:       {len(branch_df):,}")
print(f"  Unconstrained (≥999k):{_n_unconstrained:,}")
print(f"  Thermally limited:    {len(branch_df) - _n_unconstrained:,}")
print(f"  SPL-connected:        {_spl_mask.sum():,}")
print(f"  Xfmr proxy (all):    {_n_xfmr_proxy:,}")
print(f"  SPL T-junction (2×): {_n_line_seg:,}")
print(f"  Buses (main comp):    {len(bus_df_filtered):,}")
print(f"  Buses referenced:     "
      f"{len(set(branch_df['From Bus']) | set(branch_df['To Bus'])):,}")
