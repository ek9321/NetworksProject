#!/usr/bin/env python3
"""
Step 2 — Build branch.csv using BFS graph contraction.

Algorithm (adapted from generate_visualizer.py _graph_pass):
  1. Load HV lines; cluster ALL line endpoints within 150 m into junction nodes.
  2. Build a junction adjacency graph: each OSM line adds one edge between its
     start-endpoint cluster and its end-endpoint cluster.
  3. Load bus.csv filtered to 138 kV+ AND geo_confidence in {high, medium}.
     Snap each junction cluster to the nearest PSSE bus within 1 km.
     Snapped clusters become stop nodes; all others are intermediate.
  4. BFS from every stop node outward through the junction graph, stopping only
     at other stop nodes. Each discovered path becomes a branch.
     (T-junctions are traversed through without creating synthetic buses.)
  5. Deduplicate parallel paths between the same bus pair, keep one per pair.
  6. Compute X_pu from haversine distance between bus lat/lon coordinates.
  7. Add synthetic transformer branches at multi-voltage substations.
  8. Write SourceData/branch.csv and filtered SourceData/bus.csv.

Outputs:
  sced_inputs/SourceData/branch.csv   — branches between PSSE bus IDs
  sced_inputs/SourceData/bus.csv      — filtered bus table (138kV+ high/med conf)
"""

import json
import math
import shutil
from pathlib import Path
from collections import defaultdict, deque

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO     = Path(__file__).resolve().parents[2]
DATA     = REPO / "Realist" / "grid_data"
SCED_DIR = DATA / "sced_inputs"
SRC_DIR  = SCED_DIR / "SourceData"
SRC_DIR.mkdir(parents=True, exist_ok=True)

HV_LINES = DATA / "texas_hv_lines.geojson"
BUS_CSV  = SCED_DIR / "bus.csv"

# ---------------------------------------------------------------------------
# Voltage tier parameters
# ---------------------------------------------------------------------------
VOLTAGE_TIERS = {
    138: (0.38, 300),   # (x_ohm_per_km, cont_rating_mva)
    230: (0.35, 600),
    345: (0.32, 1200),
    500: (0.28, 2000),
}

MIN_KV_FILTER  = 138    # only keep buses at this voltage or above
CONF_FILTER    = {"high", "medium"}
CLUSTER_RADIUS = 0.15   # km — endpoint clustering radius
GRID_CELL      = 0.002  # degrees (~222 m diagonal); 3×3 neighbourhood checked
SNAP_KM        = 1.0    # km — max distance to snap a cluster to a PSSE bus


def snap_voltage(kv):
    if kv <= 0:
        return 138
    return min(VOLTAGE_TIERS, key=lambda t: abs(t - kv))


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _grid_cell(lat, lon):
    return int(lat / GRID_CELL), int(lon / GRID_CELL)


# ---------------------------------------------------------------------------
# Step 1: Load HV lines
# ---------------------------------------------------------------------------

print("Loading HV lines...")
with open(HV_LINES, encoding="utf-8") as f:
    hv_data = json.load(f)

lines_meta = []   # (osm_id, voltage_kv)
endpoints  = []   # (lat, lon, line_idx, role)

for feat in hv_data["features"]:
    props  = feat["properties"]
    kv     = float(props.get("voltage_kv") or 0)
    osm_id = props.get("osm_id", 0)
    coords = feat["geometry"]["coordinates"]

    line_idx = len(lines_meta)
    lines_meta.append((osm_id, kv))

    start = (coords[0][1],  coords[0][0])
    end   = (coords[-1][1], coords[-1][0])
    endpoints.append((start[0], start[1], line_idx, "start"))
    endpoints.append((end[0],   end[1],   line_idx, "end"))

print(f"  Lines loaded: {len(lines_meta):,}")

# ---------------------------------------------------------------------------
# Step 2: Greedy 150 m grid-indexed endpoint clustering
# ---------------------------------------------------------------------------

print("Clustering endpoints (150 m radius)...")

clusters = []   # [lat, lon, count, max_kv]
grid     = {}   # (ci, cj) -> [cluster_idx, ...]


def _add_to_cluster(lat, lon, kv):
    ci, cj   = _grid_cell(lat, lon)
    best_idx = None
    best_d   = CLUSTER_RADIUS + 1.0

    for di in range(-1, 2):
        for dj in range(-1, 2):
            for c_idx in grid.get((ci + di, cj + dj), []):
                c = clusters[c_idx]
                d = haversine_km(lat, lon, c[0], c[1])
                if d <= CLUSTER_RADIUS and d < best_d:
                    best_idx = c_idx
                    best_d   = d

    if best_idx is not None:
        c = clusters[best_idx]
        n = c[2]
        c[0]  = (c[0] * n + lat) / (n + 1)
        c[1]  = (c[1] * n + lon) / (n + 1)
        c[2] += 1
        c[3]  = max(c[3], kv)
        return best_idx
    else:
        new_idx = len(clusters)
        clusters.append([lat, lon, 1, kv])
        grid.setdefault((ci, cj), []).append(new_idx)
        return new_idx


ep_to_cluster = {}   # (line_idx, role) -> cluster_idx

for ep_lat, ep_lon, line_idx, role in endpoints:
    kv = lines_meta[line_idx][1]
    c_idx = _add_to_cluster(ep_lat, ep_lon, kv)
    ep_to_cluster[(line_idx, role)] = c_idx

print(f"  Junction clusters formed: {len(clusters):,}")

# ---------------------------------------------------------------------------
# Step 3: Build junction adjacency graph
# ---------------------------------------------------------------------------

print("Building junction adjacency graph...")

jadj = defaultdict(set)   # cluster_idx -> set of neighbour cluster_idx
jkv  = {}                 # (min_c, max_c) -> max_kv along that edge

for line_idx, (osm_id, kv) in enumerate(lines_meta):
    c0 = ep_to_cluster.get((line_idx, "start"))
    c1 = ep_to_cluster.get((line_idx, "end"))
    if c0 is None or c1 is None or c0 == c1:
        continue
    jadj[c0].add(c1)
    jadj[c1].add(c0)
    key = (min(c0, c1), max(c0, c1))
    jkv[key] = max(jkv.get(key, 0), kv)

print(f"  Junction edges:           {sum(len(v) for v in jadj.values()) // 2:,}")

# ---------------------------------------------------------------------------
# Step 4: Load filtered bus.csv → snap clusters to PSSE buses
# ---------------------------------------------------------------------------

print(f"Loading bus.csv (filter: >= {MIN_KV_FILTER} kV, confidence: {CONF_FILTER})...")
bus_all = pd.read_csv(BUS_CSV, dtype=str)
bus_all["_kv"]   = pd.to_numeric(bus_all["BaseKV"], errors="coerce").fillna(0)
bus_all["_conf"] = bus_all["geo_confidence"].fillna("none").str.strip().str.lower()
bus_all["_lat"]  = pd.to_numeric(bus_all["lat"], errors="coerce")
bus_all["_lon"]  = pd.to_numeric(bus_all["lng"], errors="coerce")
bus_all["_bid"]  = pd.to_numeric(bus_all["Bus ID"], errors="coerce")

bus_filt = bus_all[
    (bus_all["_kv"] >= MIN_KV_FILTER) &
    (bus_all["_conf"].isin(CONF_FILTER)) &
    bus_all["_lat"].notna() &
    bus_all["_lon"].notna()
].copy().reset_index(drop=True)

print(f"  Buses after filter: {len(bus_filt):,} (of {len(bus_all):,} total)")

# Build grid index over PSSE buses for O(1) nearest-bus lookup
bus_grid = defaultdict(list)   # (ci, cj) -> list of bus row dicts

bus_records = []
for _, row in bus_filt.iterrows():
    rec = {
        "bid":  int(row["_bid"]),
        "lat":  float(row["_lat"]),
        "lon":  float(row["_lon"]),
        "kv":   float(row["_kv"]),
        "sub":  str(row.get("Sub Name", "")).strip(),
    }
    bus_records.append(rec)
    ci, cj = _grid_cell(rec["lat"], rec["lon"])
    for di in range(-3, 4):
        for dj in range(-3, 4):
            bus_grid[(ci + di, cj + dj)].append(rec)


def nearest_bus(lat, lon):
    ci, cj    = _grid_cell(lat, lon)
    best_rec  = None
    best_dist = SNAP_KM + 1.0
    for rec in bus_grid.get((ci, cj), []):
        d = haversine_km(lat, lon, rec["lat"], rec["lon"])
        if d <= SNAP_KM and d < best_dist:
            best_rec  = rec
            best_dist = d
    return best_rec


print("Snapping junction clusters to PSSE buses...")
cluster_to_bus = {}   # cluster_idx -> bus record

n_snapped = 0
for c_idx, c in enumerate(clusters):
    rec = nearest_bus(c[0], c[1])
    if rec is not None:
        cluster_to_bus[c_idx] = rec
        n_snapped += 1

print(f"  Clusters snapped to PSSE bus: {n_snapped:,}")

# ---------------------------------------------------------------------------
# Step 5: BFS contraction — find paths between PSSE bus stop nodes
# ---------------------------------------------------------------------------

print("BFS contraction to find substation-to-substation paths...")

stop_clusters = set(cluster_to_bus.keys())

branches_raw = set()   # (bus_id_a, bus_id_b, max_kv)

for start_c in stop_clusters:
    start_bid = cluster_to_bus[start_c]["bid"]
    visited   = {start_c}
    queue     = deque([(start_c, 0)])   # (cluster_idx, max_kv_so_far)

    while queue:
        curr_c, path_kv = queue.popleft()
        for next_c in jadj[curr_c]:
            if next_c in visited:
                continue
            visited.add(next_c)
            edge_kv  = jkv.get((min(curr_c, next_c), max(curr_c, next_c)), 0)
            new_kv   = max(path_kv, edge_kv)

            if next_c in stop_clusters:
                end_bid = cluster_to_bus[next_c]["bid"]
                if start_bid != end_bid:
                    a, b = min(start_bid, end_bid), max(start_bid, end_bid)
                    branches_raw.add((a, b, snap_voltage(new_kv)))
            else:
                queue.append((next_c, new_kv))

print(f"  Unique bus-to-bus paths found: {len(branches_raw):,}")

# ---------------------------------------------------------------------------
# Step 6: Build branch table with impedance
# ---------------------------------------------------------------------------

print("Computing branch impedances...")

bid_to_rec = {rec["bid"]: rec for rec in bus_records}

branches = []
for bus_a, bus_b, kv in branches_raw:
    rec_a = bid_to_rec.get(bus_a)
    rec_b = bid_to_rec.get(bus_b)
    if rec_a is None or rec_b is None:
        continue

    length_km    = haversine_km(rec_a["lat"], rec_a["lon"], rec_b["lat"], rec_b["lon"])
    if length_km < 0.1:
        length_km = 0.1    # floor: same-substation connections

    x_ohm_per_km, cont_rating = VOLTAGE_TIERS[kv]
    z_base = kv ** 2 / 100.0
    x_pu   = x_ohm_per_km * length_km / z_base

    branches.append({
        "UID":         f"L{bus_a}_{bus_b}",
        "From Bus":    bus_a,
        "To Bus":      bus_b,
        "R":           0.0,
        "X":           round(x_pu, 8),
        "B":           0.0,
        "Cont Rating": cont_rating,
    })

# ---------------------------------------------------------------------------
# Step 7: Synthetic transformer branches at multi-voltage substations
# ---------------------------------------------------------------------------

print("Adding synthetic transformer branches...")

# Map substation name → {kv: bus_id}
sub_voltage_buses = defaultdict(dict)
for rec in bus_records:
    sub = rec["sub"]
    if sub:
        kv_tier = snap_voltage(rec["kv"])
        # keep the bus closest to the exact tier
        if kv_tier not in sub_voltage_buses[sub]:
            sub_voltage_buses[sub][kv_tier] = rec["bid"]

n_transformers = 0
xfmr_pairs     = set()

for sub_name, tier_to_bus in sub_voltage_buses.items():
    tiers = sorted(tier_to_bus.keys())
    for i in range(len(tiers) - 1):
        lo_kv  = tiers[i]
        hi_kv  = tiers[i + 1]
        lo_bus = tier_to_bus[lo_kv]
        hi_bus = tier_to_bus[hi_kv]
        if lo_bus == hi_bus:
            continue
        pair = (min(lo_bus, hi_bus), max(lo_bus, hi_bus))
        if pair in xfmr_pairs:
            continue
        xfmr_pairs.add(pair)
        _, lo_rating = VOLTAGE_TIERS.get(lo_kv, VOLTAGE_TIERS[138])
        branches.append({
            "UID":         f"XFMR_{sub_name}_{hi_kv}_{lo_kv}",
            "From Bus":    hi_bus,
            "To Bus":      lo_bus,
            "R":           0.0,
            "X":           0.12,
            "B":           0.0,
            "Cont Rating": lo_rating,
        })
        n_transformers += 1

print(f"  Transformer branches added: {n_transformers:,}")
print(f"  Total branches:             {len(branches):,}")

# ---------------------------------------------------------------------------
# Step 8: Write outputs
# ---------------------------------------------------------------------------

print("Writing outputs...")

branch_df = pd.DataFrame(branches, columns=[
    "UID", "From Bus", "To Bus", "R", "X", "B", "Cont Rating"
])
branch_df.to_csv(SRC_DIR / "branch.csv", index=False)
print(f"  Wrote branch.csv ({len(branch_df):,} rows)")

# Bus table: only the filtered buses (138kV+ high/med conf)
# Keep original column order from bus_all
bus_out = bus_all[
    (bus_all["_kv"] >= MIN_KV_FILTER) &
    (bus_all["_conf"].isin(CONF_FILTER)) &
    bus_all["_lat"].notna()
].drop(columns=["_kv", "_conf", "_lat", "_lon", "_bid"]).copy()

bus_out.to_csv(SRC_DIR / "bus.csv", index=False)
print(f"  Wrote bus.csv ({len(bus_out):,} rows)")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("Summary:")
print(f"  OSM lines:                {len(lines_meta):,}")
print(f"  Junction clusters:        {len(clusters):,}")
print(f"  Clusters snapped to bus:  {n_snapped:,}")
print(f"  Buses (138kV+ high/med):  {len(bus_out):,}")
print(f"  Branches (OSM paths):     {len(branches_raw):,}")
print(f"  Branches (transformers):  {n_transformers:,}")
print(f"  Total branches:           {len(branch_df):,}")
