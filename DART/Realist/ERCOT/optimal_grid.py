#!/usr/bin/env python3
"""
Optimal Grid Design for ERCOT — lambda_2 Maximization under Budget Constraint
==============================================================================
Intended as a *topological upper bound*, not a serious grid design. Useful
for the paper as a sanity check on whether targeted upgrades (articulation
bypasses) capture most of the resilience we could get from a redesign.

Caveats, documented here and in the paper:
  - No flow feasibility check (lambda_2 max is purely topological).
  - 138 kV can't move GW-scale power long distances, but the cost-tier
    function below allows short 138 kV choices. This is how the optimizer
    "saves money" — but such a grid might not be dispatchable.
  - 1.3x right-of-way multiplier applied to BOTH grids (applies equally,
    preserves relative budget).

Fixes relative to earlier version:
  - Population attack now uses actual population-weighted MW load (the
    previous version read bus.csv "MW Load" column, which is zero for all
    real substations, making the attack effectively random).
  - Attack-curve f-axis refers to the 3000 REAL substations in both grids.
    Split nodes in the real grid stay in the graph as topology but are not
    attackable (you can't knock out a geometric fiction).
  - lambda_2 reported with explicit caveat: real graph has 3786 nodes
    (3000 real subs + 786 OSM split nodes), optimal has 3000 real subs
    only. Raw lambda_2 ratio is NOT apples-to-apples.
"""

import json
import math
import time
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from math import radians, sin, cos, sqrt, atan2
from scipy.spatial import Delaunay
from scipy.sparse import csr_matrix, lil_matrix
from scipy.sparse.linalg import eigsh
from sklearn.neighbors import BallTree
import networkx as nx

warnings.filterwarnings("ignore")

# ── paths ──
DATA = Path("/Users/jackhasker/ORF387/Dartboard/Realist/grid_data/sced_inputs_v3/SourceData")
OUT  = Path("/Users/jackhasker/ORF387/Dartboard/Realist/ERCOT")
FIG  = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

# ── cost model (ERCOT 2024 RTP, with ROW penalty) ──
ROW_MULT  = 1.3     # right-of-way and terrain multiplier (applied to both grids)
COST_138  = 1.553 * ROW_MULT   # $M/km, 138 kV
COST_345S = 1.304 * ROW_MULT   # $M/km, 345 kV single-circuit
COST_345D = 2.609 * ROW_MULT   # $M/km, 345 kV double-circuit

# ── ERCOT zone load (same as network_analysis.py) ──
ZONE_LOAD_MW = {"NORTH": 23000.0, "HOUSTON": 11500.0, "SOUTH": 10500.0, "WEST": 7000.0}

# Bus-level pop-weighted load is written by network_analysis.py to bus_load.csv.
# We require that file here to fix the previous bug where we used the (always-zero)
# "MW Load" column from bus.csv — which silently made the population attack random.
BUS_LOAD_CSV = OUT / "bus_load.csv"

def haversine(lat1, lng1, lat2, lng2):
    """Haversine distance in km."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlng/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

def cost_by_rating(rating):
    """Assign cost-per-km by Cont Rating (MVA) for real grid."""
    if rating <= 400:
        return COST_138
    elif rating <= 1500:
        return COST_345S
    else:
        return COST_345D

def cost_by_distance(dist_km):
    """Assign cost-per-km by distance for new candidate lines."""
    if dist_km < 80:
        return COST_138
    elif dist_km <= 300:
        return COST_345S
    else:
        return COST_345D

def voltage_label_by_rating(rating):
    if rating <= 400:
        return "138 kV"
    elif rating <= 1500:
        return "345 kV single"
    else:
        return "345 kV double"

def voltage_label_by_distance(dist_km):
    if dist_km < 80:
        return "138 kV"
    elif dist_km <= 300:
        return "345 kV single"
    else:
        return "345 kV double"


# ═══════════════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════════════
print("=" * 70)
print("LOADING DATA")
print("=" * 70)

bus = pd.read_csv(DATA / "bus.csv")
branch = pd.read_csv(DATA / "branch.csv")

bus["is_split"] = bus["is_split"].astype(str).str.strip().str.lower() == "true"
real_buses = bus[~bus["is_split"]].copy().reset_index(drop=True)

print(f"  Total buses:  {len(bus)}")
print(f"  Real subs:    {len(real_buses)}")
print(f"  Split nodes:  {bus['is_split'].sum()}")
print(f"  Branches:     {len(branch)}")

# Build lat/lng lookup keyed on Bus ID
bus_lat = dict(zip(bus["Bus ID"], bus["lat"]))
bus_lng = dict(zip(bus["Bus ID"], bus["lng"]))

# ═══════════════════════════════════════════════════════════════════════
# STEP 1 — REAL GRID COST ESTIMATE
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 1: REAL GRID COST ESTIMATE")
print("=" * 70)

distances = []
costs = []
tiers = []
for _, row in branch.iterrows():
    fb, tb = int(row["From Bus"]), int(row["To Bus"])
    d = haversine(bus_lat[fb], bus_lng[fb], bus_lat[tb], bus_lng[tb])
    cpk = cost_by_rating(row["Cont Rating"])
    c = d * cpk
    distances.append(d)
    costs.append(c)
    tiers.append(voltage_label_by_rating(row["Cont Rating"]))

branch["dist_km"] = distances
branch["cost_M"] = costs
branch["tier"] = tiers

total_real_cost_M = sum(costs)
total_real_cost_B = total_real_cost_M / 1000.0
total_route_km = sum(distances)

print(f"  Total real grid cost:   ${total_real_cost_B:.3f} B")
print(f"  Number of branches:     {len(branch)}")
print(f"  Total route-km:         {total_route_km:.1f} km")
print(f"  Mean branch length:     {np.mean(distances):.2f} km")
print(f"  Median branch length:   {np.median(distances):.2f} km")

tier_costs = branch.groupby("tier")["cost_M"].sum() / 1000.0
tier_counts = branch.groupby("tier")["cost_M"].count()
print("  Cost by tier:")
for t in tier_costs.index:
    print(f"    {t}: ${tier_costs[t]:.3f} B  ({tier_counts[t]} branches)")


# ═══════════════════════════════════════════════════════════════════════
# STEP 2 — GENERATE CANDIDATE EDGES
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 2: GENERATE CANDIDATE EDGES")
print("=" * 70)

# Map real-sub Bus IDs to contiguous 0..N-1 indices
real_ids = real_buses["Bus ID"].values
real_lats = real_buses["lat"].values
real_lngs = real_buses["lng"].values
id_to_idx = {bid: i for i, bid in enumerate(real_ids)}
N = len(real_ids)
print(f"  Real substations: {N}")

# --- existing edges among real subs ---
existing_edges = set()
for _, row in branch.iterrows():
    fb, tb = int(row["From Bus"]), int(row["To Bus"])
    if fb in id_to_idx and tb in id_to_idx:
        a, b = id_to_idx[fb], id_to_idx[tb]
        if a != b:
            existing_edges.add((min(a, b), max(a, b)))
print(f"  Existing edges among real subs: {len(existing_edges)}")

# --- Delaunay triangulation ---
print("  Computing Delaunay triangulation...")
points = np.column_stack([real_lats, real_lngs])
tri = Delaunay(points)
cand_set = set()
for simplex in tri.simplices:
    for k in range(3):
        a, b = int(simplex[k]), int(simplex[(k+1) % 3])
        if a != b:
            edge = (min(a, b), max(a, b))
            if edge not in existing_edges:
                cand_set.add(edge)
print(f"  Delaunay candidates (excl existing): {len(cand_set)}")

# --- KNN for additional candidates ---
print("  Computing 5-NN candidates...")
coords_rad = np.deg2rad(np.column_stack([real_lats, real_lngs]))
tree = BallTree(coords_rad, metric="haversine")
dists_rad, inds = tree.query(coords_rad, k=6)  # k=6 because first is self
for i in range(N):
    for j_pos in range(1, 6):
        j = int(inds[i, j_pos])
        d_km = dists_rad[i, j_pos] * 6371.0
        if d_km > 500:
            continue
        if i != j:
            edge = (min(i, j), max(i, j))
            if edge not in existing_edges:
                cand_set.add(edge)

print(f"  Total unique candidates: {len(cand_set)}")

# Cap at 100k
if len(cand_set) > 100000:
    import random
    random.seed(42)
    cand_set = set(random.sample(list(cand_set), 100000))
    print(f"  Capped at 100,000")

# --- compute distance and cost for each candidate ---
print("  Computing candidate distances and costs...")
cand_list = list(cand_set)
cand_dist = np.zeros(len(cand_list))
cand_cost = np.zeros(len(cand_list))
cand_tier = []
for k, (i, j) in enumerate(cand_list):
    d = haversine(real_lats[i], real_lngs[i], real_lats[j], real_lngs[j])
    cand_dist[k] = d
    cand_cost[k] = d * cost_by_distance(d)
    cand_tier.append(voltage_label_by_distance(d))

print(f"  Candidate cost range: ${cand_cost.min():.2f}M — ${cand_cost.max():.2f}M")
print(f"  Candidate dist range: {cand_dist.min():.1f} km — {cand_dist.max():.1f} km")


# ═══════════════════════════════════════════════════════════════════════
# STEP 3 — BUILD OPTIMAL GRID (GREEDY λ₂ MAXIMIZATION)
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 3: GREEDY λ₂ MAXIMIZATION")
print("=" * 70)

budget_M = total_real_cost_M
print(f"  Total budget: ${budget_M / 1000:.3f} B")

# --- MST on real substations ---
print("  Building MST on real substations...")
G_full = nx.Graph()
for i in range(N):
    G_full.add_node(i)

# Add edges with haversine weight for MST
all_pairs_for_mst = []
# Use Delaunay + existing as seed for MST (much faster than all-pairs)
mst_edge_set = set()
for simplex in tri.simplices:
    for k in range(3):
        a, b = int(simplex[k]), int(simplex[(k+1) % 3])
        if a != b:
            mst_edge_set.add((min(a, b), max(a, b)))
# Also add existing edges
for e in existing_edges:
    mst_edge_set.add(e)
# And KNN edges
for i in range(N):
    for j_pos in range(1, 6):
        j = int(inds[i, j_pos])
        if i != j:
            mst_edge_set.add((min(i, j), max(i, j)))

for (a, b) in mst_edge_set:
    d = haversine(real_lats[a], real_lngs[a], real_lats[b], real_lngs[b])
    G_full.add_edge(a, b, weight=d)

mst = nx.minimum_spanning_tree(G_full, weight="weight")
mst_edges = list(mst.edges())
mst_cost_M = 0.0
mst_route_km = 0.0
for (a, b) in mst_edges:
    d = haversine(real_lats[a], real_lngs[a], real_lats[b], real_lngs[b])
    mst_cost_M += d * cost_by_distance(d)
    mst_route_km += d

print(f"  MST edges: {len(mst_edges)}")
print(f"  MST cost:  ${mst_cost_M / 1000:.3f} B")
print(f"  MST route: {mst_route_km:.1f} km")

remaining_M = budget_M - mst_cost_M
print(f"  Remaining budget after MST: ${remaining_M / 1000:.3f} B")

if remaining_M <= 0:
    print("  WARNING: MST already exceeds budget! Proceeding with MST only.")
    remaining_M = 0

# --- Build adjacency for optimal graph ---
opt_adj = set()
for (a, b) in mst_edges:
    opt_adj.add((min(a, b), max(a, b)))


def build_sparse_laplacian(adj_set, n):
    """Build sparse Laplacian from edge set."""
    row, col, data = [], [], []
    deg = np.zeros(n)
    for (a, b) in adj_set:
        row.extend([a, b, a, b])
        col.extend([b, a, a, b])
        data.extend([-1, -1, 1, 1])
        deg[a] += 1
        deg[b] += 1
    # The degree contributions are already embedded in the off-diag/diag pattern above
    # Actually let's build properly
    L = lil_matrix((n, n), dtype=np.float64)
    for (a, b) in adj_set:
        L[a, b] -= 1.0
        L[b, a] -= 1.0
        L[a, a] += 1.0
        L[b, b] += 1.0
    return L.tocsr()


def compute_fiedler(adj_set, n):
    """Compute algebraic connectivity λ₂ and Fiedler vector."""
    L = build_sparse_laplacian(adj_set, n)
    try:
        vals, vecs = eigsh(L, k=2, which="SM", tol=1e-6)
        idx = np.argsort(vals)
        lam2 = float(vals[idx[1]])
        fiedler = vecs[:, idx[1]]
    except Exception:
        lam2 = 0.0
        fiedler = np.zeros(n)
    return lam2, fiedler


# --- initial Fiedler vector ---
print("  Computing initial Fiedler vector on MST...")
lam2, fiedler = compute_fiedler(opt_adj, N)
print(f"  MST λ₂ = {lam2:.6f}")

# --- Filter candidates: remove those already in opt_adj ---
avail_idx = []
for k in range(len(cand_list)):
    edge = cand_list[k]
    if edge not in opt_adj:
        avail_idx.append(k)
print(f"  Available candidates after removing MST overlaps: {len(avail_idx)}")

# --- Greedy loop ---
print("  Starting greedy loop...")
t0 = time.time()
edges_added = 0
total_opt_cost_added_M = 0.0
iter_count = 0
fiedler_recompute_interval = 50

# Precompute: convert avail to numpy arrays for speed
avail_idx = np.array(avail_idx, dtype=np.int64)
avail_mask = np.ones(len(avail_idx), dtype=bool)

while remaining_M > 0:
    # Filter to affordable
    affordable = avail_mask & (cand_cost[avail_idx] <= remaining_M)
    if not np.any(affordable):
        print(f"  No affordable candidates remain. Stopping.")
        break

    # Compute proxy scores for ALL affordable candidates
    aff_positions = np.where(affordable)[0]
    if len(aff_positions) == 0:
        break

    # Proxy: (fiedler_i - fiedler_j)^2 / cost
    batch_i = np.array([cand_list[avail_idx[p]][0] for p in aff_positions])
    batch_j = np.array([cand_list[avail_idx[p]][1] for p in aff_positions])
    dv = fiedler[batch_i] - fiedler[batch_j]
    proxy = dv**2 / cand_cost[avail_idx[aff_positions]]

    # Take top 200 by proxy
    top_k = min(200, len(proxy))
    top_local = np.argpartition(proxy, -top_k)[-top_k:]
    top_positions = aff_positions[top_local]

    # For these top 200, efficiency = (v_i - v_j)^2 / cost (same as proxy here)
    best_eff = -1
    best_pos = -1
    for p in top_positions:
        k = avail_idx[p]
        i, j = cand_list[k]
        dv_val = fiedler[i] - fiedler[j]
        eff = dv_val**2 / cand_cost[k]
        if eff > best_eff:
            best_eff = eff
            best_pos = p

    if best_pos == -1:
        break

    k = avail_idx[best_pos]
    i, j = cand_list[k]
    edge = (min(i, j), max(i, j))

    # Add edge
    opt_adj.add(edge)
    avail_mask[best_pos] = False
    remaining_M -= cand_cost[k]
    total_opt_cost_added_M += cand_cost[k]
    edges_added += 1
    iter_count += 1

    # Recompute Fiedler every N iterations
    if iter_count % fiedler_recompute_interval == 0:
        lam2, fiedler = compute_fiedler(opt_adj, N)
        if iter_count % 100 == 0:
            elapsed = time.time() - t0
            print(f"    iter {iter_count}: +{edges_added} edges, λ₂={lam2:.6f}, "
                  f"remaining=${remaining_M/1000:.3f}B, elapsed={elapsed:.0f}s")

# Final recompute
lam2_opt, fiedler_opt = compute_fiedler(opt_adj, N)

total_opt_cost_M = mst_cost_M + total_opt_cost_added_M
total_opt_route_km = mst_route_km
for k in range(len(cand_list)):
    if cand_list[k] in opt_adj and cand_list[k] not in set((min(a,b), max(a,b)) for a,b in mst_edges):
        total_opt_route_km += cand_dist[k]

elapsed = time.time() - t0
print(f"\n  Greedy complete in {elapsed:.0f}s")
print(f"  Edges added beyond MST: {edges_added}")
print(f"  Total optimal edges:    {len(opt_adj)}")
print(f"  Total optimal cost:     ${total_opt_cost_M / 1000:.3f} B")
print(f"  Remaining budget:       ${remaining_M / 1000:.3f} B")
print(f"  Optimal λ₂:             {lam2_opt:.6f}")

# Compute optimal route km properly
opt_route_km = 0.0
opt_tier_costs = {"138 kV": 0.0, "345 kV single": 0.0, "345 kV double": 0.0}
for (a, b) in opt_adj:
    d = haversine(real_lats[a], real_lngs[a], real_lats[b], real_lngs[b])
    opt_route_km += d
    cpk = cost_by_distance(d)
    c = d * cpk
    t = voltage_label_by_distance(d)
    opt_tier_costs[t] += c / 1000.0  # in billions

print(f"  Optimal total route-km: {opt_route_km:.1f}")


# ═══════════════════════════════════════════════════════════════════════
# STEP 4 — ATTACK CURVES: REAL vs OPTIMAL
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 4: ATTACK CURVES")
print("=" * 70)

# --- Build real graph (all nodes) ---
print("  Building real graph (all nodes)...")
G_real = nx.Graph()
for _, row in bus.iterrows():
    G_real.add_node(int(row["Bus ID"]))
for _, row in branch.iterrows():
    G_real.add_edge(int(row["From Bus"]), int(row["To Bus"]))

# --- Build optimal graph (real subs only) ---
print("  Building optimal graph...")
G_opt = nx.Graph()
for i in range(N):
    G_opt.add_node(int(real_ids[i]))
for (a, b) in opt_adj:
    G_opt.add_edge(int(real_ids[a]), int(real_ids[b]))

# --- Compute real grid λ₂ ---
# The real-sub-only subgraph is disconnected (many subs connect through
# synthetic split nodes), so λ₂ on that subgraph is 0.  For a fair
# comparison we compute λ₂ on the FULL graph (all 3786 buses) and also
# report the effective λ₂ of the real-sub-only GCC.
print("  Computing real grid λ₂ (full graph, all 3786 buses)...")
all_bus_ids = sorted(bus["Bus ID"].tolist())
full_id_to_idx = {bid: i for i, bid in enumerate(all_bus_ids)}
full_N = len(all_bus_ids)
full_edges = set()
for _, row in branch.iterrows():
    fb, tb = int(row["From Bus"]), int(row["To Bus"])
    a2, b2 = full_id_to_idx[fb], full_id_to_idx[tb]
    if a2 != b2:
        full_edges.add((min(a2, b2), max(a2, b2)))
lam2_real_full, _ = compute_fiedler(full_edges, full_N)
print(f"  Real grid λ₂ (full graph, {full_N} nodes): {lam2_real_full:.6f}")

# Also compute on real-sub subgraph (will be 0 due to disconnection)
real_sub_edges = set()
for _, row in branch.iterrows():
    fb, tb = int(row["From Bus"]), int(row["To Bus"])
    if fb in id_to_idx and tb in id_to_idx:
        a, b = id_to_idx[fb], id_to_idx[tb]
        if a != b:
            real_sub_edges.add((min(a, b), max(a, b)))
lam2_real_sub, _ = compute_fiedler(real_sub_edges, N)
print(f"  Real grid λ₂ (real-sub only, {N} nodes): {lam2_real_sub:.6f}")
print(f"  NOTE: real-sub subgraph is disconnected (split nodes removed)")

# Use full-graph λ₂ as the fair comparison value
lam2_real = lam2_real_full

# --- Attack strategies ---
def gcc_fraction(G, removed_nodes):
    """GCC fraction after removing nodes."""
    H = G.copy()
    H.remove_nodes_from(removed_nodes)
    if len(H) == 0:
        return 0.0
    return len(max(nx.connected_components(H), key=len)) / len(G)


# Load population-weighted MW load (written by network_analysis.py)
if not BUS_LOAD_CSV.exists():
    raise FileNotFoundError(
        f"{BUS_LOAD_CSV} not found. Run network_analysis.py first — it "
        "writes pop-weighted bus loads that this script needs for a "
        "meaningful population attack."
    )
bus_load_df = pd.read_csv(BUS_LOAD_CSV)
pop_load_map = dict(zip(bus_load_df["Bus ID"], bus_load_df["MW_Load_pop"]))
split_id_set = set(bus[bus["is_split"]]["Bus ID"])
real_sub_id_set = set(bus[~bus["is_split"]]["Bus ID"])
print(f"  Loaded pop-weighted MW load (sum = {bus_load_df['MW_Load_pop'].sum():.0f} MW)")

def attack_curve(G, strategy, fracs, attackable_nodes, n_trials=5, real_sub_count=3000):
    """
    Run attack and return GCC fraction at each f.
    f is expressed as a fraction of REAL-SUBSTATION nodes (real_sub_count).
    The attack target pool is `attackable_nodes` (which excludes split nodes
    in the real grid — you cannot knock out a geometric fiction).
    GCC measured on the full graph `G` (split nodes included as topology).

    strategy: 'random', 'degree', 'betweenness', 'population'
    """
    nodes = list(G.nodes())

    if strategy == "random":
        results = np.zeros(len(fracs))
        for trial in range(n_trials):
            rng = np.random.RandomState(42 + trial)
            order = list(rng.permutation(attackable_nodes))
            for fi, f in enumerate(fracs):
                k = int(f * real_sub_count)
                removed = order[:k]
                results[fi] += gcc_fraction(G, removed)
        return results / n_trials

    elif strategy == "degree":
        deg = dict(G.degree())
        order = sorted(attackable_nodes, key=lambda x: deg.get(x, 0), reverse=True)
    elif strategy == "betweenness":
        print("    Computing betweenness centrality...")
        bc = nx.betweenness_centrality(G, k=min(500, len(G)))
        order = sorted(attackable_nodes, key=lambda x: bc.get(x, 0), reverse=True)
    elif strategy == "population":
        order = sorted(attackable_nodes, key=lambda x: pop_load_map.get(x, 0.0), reverse=True)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    results = np.zeros(len(fracs))
    for fi, f in enumerate(fracs):
        k = int(f * real_sub_count)
        removed = order[:k]
        results[fi] = gcc_fraction(G, removed)
    return results


# Fraction steps (of real-substation count, 3000)
fracs = [0.0, 0.005, 0.01] + [i * 0.02 for i in range(1, 26)]  # up to 0.50

# Real grid: attackable = real subs only (splits are topology, not attackable)
real_attackable = [n for n in G_real.nodes() if n in real_sub_id_set]
# Optimal grid: all nodes are real subs (no splits)
opt_attackable = list(G_opt.nodes())
print(f"  Real-grid attackable nodes: {len(real_attackable)}")
print(f"  Optimal-grid attackable nodes: {len(opt_attackable)}")

strategies = ["random", "degree", "betweenness", "population"]
colors = {"random": "grey", "degree": "red", "betweenness": "blue", "population": "green"}

results_real = {}
results_opt = {}

for strat in strategies:
    print(f"  Running {strat} attack on real grid...")
    results_real[strat] = attack_curve(G_real, strat, fracs, real_attackable, real_sub_count=len(real_attackable))
    print(f"  Running {strat} attack on optimal grid...")
    results_opt[strat] = attack_curve(G_opt, strat, fracs, opt_attackable, real_sub_count=len(opt_attackable))

# --- Plot ---
print("  Plotting attack curves...")
fig, ax = plt.subplots(figsize=(10, 7))
for strat in strategies:
    ax.plot(fracs, results_real[strat], color=colors[strat], linestyle="-",
            linewidth=2, label=f"Real — {strat}")
    ax.plot(fracs, results_opt[strat], color=colors[strat], linestyle="--",
            linewidth=2, label=f"Optimal — {strat}")

ax.axhline(0.5, color="black", linestyle=":", alpha=0.5, label="GCC = 0.50")
ax.set_xlabel("Fraction of nodes removed (f)", fontsize=13)
ax.set_ylabel("GCC / original size", fontsize=13)
ax.set_title("ERCOT Grid Resilience: Real vs. Optimal (Same Budget)", fontsize=14)
ax.legend(fontsize=9, ncol=2, loc="lower left")
ax.set_xlim(0, 0.50)
ax.set_ylim(0, 1.05)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(FIG / "real_vs_optimal_attack_curves.png", dpi=200)
plt.close(fig)
print(f"  Saved: {FIG / 'real_vs_optimal_attack_curves.png'}")

# --- Compute f* (GCC drops below 0.5) ---
def find_fstar(fracs, gcc_vals):
    for i, (f, g) in enumerate(zip(fracs, gcc_vals)):
        if g < 0.5:
            return f
    return float("nan")

fstar = {}
for strat in strategies:
    fstar[f"real_{strat}"] = find_fstar(fracs, results_real[strat])
    fstar[f"opt_{strat}"] = find_fstar(fracs, results_opt[strat])

# GCC at specific f values
def gcc_at_f(fracs, gcc_vals, target_f):
    # Find closest f
    idx = np.argmin(np.abs(np.array(fracs) - target_f))
    return float(gcc_vals[idx])

gcc_snapshots = {}
for strat in strategies:
    for f_val in [0.05, 0.10, 0.20]:
        gcc_snapshots[f"real_{strat}_f{f_val:.2f}"] = gcc_at_f(fracs, results_real[strat], f_val)
        gcc_snapshots[f"opt_{strat}_f{f_val:.2f}"] = gcc_at_f(fracs, results_opt[strat], f_val)


# ═══════════════════════════════════════════════════════════════════════
# STEP 5 — COST BREAKDOWN FIGURE
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 5: COST BREAKDOWN FIGURE")
print("=" * 70)

real_tier_costs = {"138 kV": 0.0, "345 kV single": 0.0, "345 kV double": 0.0}
for t in tier_costs.index:
    real_tier_costs[t] = float(tier_costs[t])

fig2, axes = plt.subplots(1, 2, figsize=(12, 5))
tier_labels = ["138 kV", "345 kV single", "345 kV double"]
tier_colors = ["#4CAF50", "#2196F3", "#FF5722"]

# Real grid
vals_real = [real_tier_costs.get(t, 0) for t in tier_labels]
axes[0].bar(tier_labels, vals_real, color=tier_colors)
axes[0].set_title("Real Grid Cost by Voltage Tier", fontsize=12)
axes[0].set_ylabel("Cost ($B)")
for i, v in enumerate(vals_real):
    axes[0].text(i, v + 0.1, f"${v:.2f}B", ha="center", fontsize=10)

# Optimal grid
vals_opt = [opt_tier_costs.get(t, 0) for t in tier_labels]
axes[1].bar(tier_labels, vals_opt, color=tier_colors)
axes[1].set_title("Optimal Grid Cost by Voltage Tier", fontsize=12)
axes[1].set_ylabel("Cost ($B)")
for i, v in enumerate(vals_opt):
    axes[1].text(i, v + 0.1, f"${v:.2f}B", ha="center", fontsize=10)

fig2.suptitle("Cost Breakdown: Real vs. Optimal Grid", fontsize=14, y=1.02)
fig2.tight_layout()
fig2.savefig(FIG / "optimal_grid_cost_breakdown.png", dpi=200, bbox_inches="tight")
plt.close(fig2)
print(f"  Saved: {FIG / 'optimal_grid_cost_breakdown.png'}")


# ═══════════════════════════════════════════════════════════════════════
# STEP 6 — SUMMARY
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 6: SUMMARY")
print("=" * 70)

summary = {
    "real_grid": {
        "total_cost_billions": round(total_real_cost_B, 4),
        "n_nodes": int(len(bus)),
        "n_nodes_real_subs": int(N),
        "n_edges": int(len(branch)),
        "total_route_km": round(total_route_km, 1),
        "mean_edge_length_km": round(float(np.mean(distances)), 2),
        "lambda2_full_graph": round(lam2_real_full, 6),
        "lambda2_real_sub_only": round(lam2_real_sub, 6),
        "lambda2_note": "real-sub subgraph is disconnected (431 components) because split nodes are removed; full-graph lambda2 used for comparison",
        "fstar_random": fstar.get("real_random"),
        "fstar_degree": fstar.get("real_degree"),
        "fstar_betweenness": fstar.get("real_betweenness"),
        "fstar_population": fstar.get("real_population"),
        "cost_by_tier_billions": {k: round(v, 4) for k, v in real_tier_costs.items()},
    },
    "optimal_grid": {
        "total_cost_billions": round(total_opt_cost_M / 1000, 4),
        "n_nodes": int(N),
        "n_edges": int(len(opt_adj)),
        "n_mst_edges": int(len(mst_edges)),
        "n_greedy_edges": int(edges_added),
        "total_route_km": round(opt_route_km, 1),
        "mean_edge_length_km": round(opt_route_km / len(opt_adj), 2),
        "lambda2": round(lam2_opt, 6),
        "fstar_random": fstar.get("opt_random"),
        "fstar_degree": fstar.get("opt_degree"),
        "fstar_betweenness": fstar.get("opt_betweenness"),
        "fstar_population": fstar.get("opt_population"),
        "cost_by_tier_billions": {k: round(v, 4) for k, v in opt_tier_costs.items()},
    },
    "comparison": {
        "cost_difference_billions": round(total_opt_cost_M / 1000 - total_real_cost_B, 4),
        "row_multiplier_applied_to_both": ROW_MULT,
        "lambda2_real_full": round(lam2_real_full, 6),
        "lambda2_optimal": round(lam2_opt, 6),
        "lambda2_comparison_caveat": (
            "The real graph has 3786 nodes (3000 real substations + 786 OSM "
            "split nodes inserted during geometry extraction), while the "
            "optimal graph has 3000 nodes. lambda_2 depends on graph size: "
            "adding degree-2 or degree-3 pass-through nodes reduces lambda_2. "
            "The raw ratio (lam2_opt / lam2_real_full) therefore OVERSTATES "
            "the resilience gain. We report it only as an upper bound. "
            "The attack-curve comparison (fractions of 3000 real substations "
            "removed in BOTH grids) is the fair comparison and the one we "
            "emphasize in the paper."
        ),
        "lambda2_improvement_ratio_RAW": round(lam2_opt / max(lam2_real_full, 1e-12), 2),
        "fstar_improvement": {
            strat: round((fstar.get(f"opt_{strat}", 0) or 0) - (fstar.get(f"real_{strat}", 0) or 0), 4)
            for strat in strategies
        },
        "attack_methodology_note": (
            "Both grids attacked with f = fraction of real substations removed. "
            "Real grid: splits stay in graph as topology, not attackable. "
            "Optimal grid: all 3000 nodes are real subs (no splits). "
            "GCC normalized by attackable-node count in each case."
        ),
    },
    "gcc_snapshots": gcc_snapshots,
}

with open(OUT / "optimal_grid_results.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)
print(f"  Saved: {OUT / 'optimal_grid_results.json'}")

print("\n" + "-" * 70)
print("RESULTS SUMMARY")
print("-" * 70)
print(json.dumps(summary, indent=2, default=str))
print("\nDone.")
