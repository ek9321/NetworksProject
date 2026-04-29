#!/usr/bin/env python3
"""
analyze_network.py — Network science analysis of the ERCOT transmission grid.

Analyses:
  1. Basic topology: degree distribution, clustering, diameter
  2. Centrality: betweenness (capacity-weighted) identifies bottleneck corridors
  3. Community detection: spectral + Louvain, compared to ERCOT load zones
  4. Cascading failure simulation: targeted vs random edge removal
  5. Vulnerability comparison: random failure vs targeted attack

Produces figures in figures/ subdirectory.
"""

import os
import sys
import warnings
from collections import Counter

import numpy as np

try:
    import networkx as nx
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
except ImportError:
    print("pip install networkx matplotlib numpy")
    sys.exit(1)

warnings.filterwarnings("ignore", category=DeprecationWarning)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIG_DIR = os.path.join(SCRIPT_DIR, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

# ── Load graph ───────────────────────────────────────────────────────────────
graphml_path = os.path.join(SCRIPT_DIR, "ercot_network.graphml")
if not os.path.exists(graphml_path):
    print("Run build_network.py first.")
    sys.exit(1)

print("Loading graph...")
G = nx.read_graphml(graphml_path)
# graphml stores node IDs as strings — convert to int for consistency
G = nx.relabel_nodes(G, {n: int(n) for n in G.nodes()})
print(f"  {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

# Work with the giant connected component
gcc_nodes = max(nx.connected_components(G), key=len)
G_gcc = G.subgraph(gcc_nodes).copy()
print(f"  Giant component: {G_gcc.number_of_nodes()} nodes, {G_gcc.number_of_edges()} edges")


# ─────────────────────────────────────────────────────────────────────────────
# 1. BASIC TOPOLOGY
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 1. Basic Topology ═══")

degrees = [d for _, d in G_gcc.degree()]
print(f"Nodes: {G_gcc.number_of_nodes()}")
print(f"Edges: {G_gcc.number_of_edges()}")
print(f"Density: {nx.density(G_gcc):.6f}")
print(f"Degree — min: {min(degrees)}, max: {max(degrees)}, "
      f"mean: {np.mean(degrees):.2f}, median: {np.median(degrees):.0f}")
print(f"Avg clustering coefficient: {nx.average_clustering(G_gcc):.4f}")

# Degree distribution
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
deg_counts = Counter(degrees)
ks = sorted(deg_counts)
vals = [deg_counts[k] for k in ks]

axes[0].bar(ks, vals, color="steelblue", edgecolor="white", linewidth=0.3)
axes[0].set_xlabel("Degree")
axes[0].set_ylabel("Count")
axes[0].set_title("Degree Distribution")

# Log-log for power-law check
axes[1].scatter(ks, vals, s=15, color="steelblue")
axes[1].set_xscale("log")
axes[1].set_yscale("log")
axes[1].set_xlabel("Degree (log)")
axes[1].set_ylabel("Count (log)")
axes[1].set_title("Degree Distribution (log-log)")

plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "01_degree_distribution.png"), dpi=150)
plt.close()
print("  → figures/01_degree_distribution.png")


# ─────────────────────────────────────────────────────────────────────────────
# 2. CENTRALITY — betweenness weighted by inverse capacity
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 2. Betweenness Centrality ═══")

# Weight = 1/capacity so high-capacity lines are "shorter" paths
for u, v, d in G_gcc.edges(data=True):
    cap = d.get("capacity_mva", 400)
    d["weight"] = 1.0 / max(cap, 1)

bc = nx.betweenness_centrality(G_gcc, weight="weight", k=min(500, G_gcc.number_of_nodes()))
top_bc = sorted(bc.items(), key=lambda x: -x[1])[:20]
print("  Top 20 betweenness centrality nodes:")
for node, score in top_bc:
    d = G_gcc.nodes[node]
    print(f"    {str(d.get('name','?')):40s}  zone={str(d.get('zone','?')):8s}  "
          f"kV={str(d.get('base_kv','?')):>5s}  BC={score:.4f}")

# Edge betweenness
ebc = nx.edge_betweenness_centrality(G_gcc, weight="weight",
                                      k=min(300, G_gcc.number_of_nodes()))
top_ebc = sorted(ebc.items(), key=lambda x: -x[1])[:15]
print("\n  Top 15 edge betweenness:")
for (u, v), score in top_ebc:
    nu = str(G_gcc.nodes[u].get("name", "?"))
    nv = str(G_gcc.nodes[v].get("name", "?"))
    kv = G_gcc.edges[u, v].get("voltage_kv", "?")
    print(f"    {nu:35s} ↔ {nv:35s}  {kv}kV  EBC={score:.5f}")

# Geographic map colored by betweenness
fig, ax = plt.subplots(figsize=(12, 10))
lats = [G_gcc.nodes[n].get("lat", 0) for n in G_gcc.nodes()]
lngs = [G_gcc.nodes[n].get("lng", 0) for n in G_gcc.nodes()]
bc_vals = [bc.get(n, 0) for n in G_gcc.nodes()]

# draw edges first (light gray)
for u, v in G_gcc.edges():
    ax.plot([float(G_gcc.nodes[u]["lng"]), float(G_gcc.nodes[v]["lng"])],
            [float(G_gcc.nodes[u]["lat"]), float(G_gcc.nodes[v]["lat"])],
            color="#cccccc", linewidth=0.2, zorder=1)

sc = ax.scatter([float(x) for x in lngs], [float(x) for x in lats],
                c=bc_vals, cmap="hot_r", s=3, zorder=2)
plt.colorbar(sc, label="Betweenness Centrality", shrink=0.7)
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
ax.set_title("ERCOT Grid — Node Betweenness Centrality")
ax.set_aspect(1.2)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "02_betweenness_map.png"), dpi=150)
plt.close()
print("  → figures/02_betweenness_map.png")


# ─────────────────────────────────────────────────────────────────────────────
# 3. COMMUNITY DETECTION vs ERCOT ZONES
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 3. Community Detection ═══")

try:
    from networkx.algorithms.community import louvain_communities
    communities = louvain_communities(G_gcc, weight="capacity_mva", seed=42)
    print(f"  Louvain found {len(communities)} communities")
    for i, comm in enumerate(sorted(communities, key=len, reverse=True)[:8]):
        zone_dist = Counter(G_gcc.nodes[n].get("zone", "?") for n in comm)
        print(f"    Community {i}: {len(comm)} nodes — {dict(zone_dist)}")
except Exception as e:
    print(f"  Louvain failed: {e}")
    communities = None

# Plot: actual zones vs detected communities side by side
ZONE_COLORS = {"NORTH": "#2196F3", "SOUTH": "#4CAF50",
                "WEST": "#FF9800", "HOUSTON": "#E91E63"}

fig, axes = plt.subplots(1, 2, figsize=(20, 10))

# (a) actual ERCOT zones
for n in G_gcc.nodes():
    z = G_gcc.nodes[n].get("zone", "?")
    c = ZONE_COLORS.get(z, "#999999")
    axes[0].scatter(float(G_gcc.nodes[n]["lng"]), float(G_gcc.nodes[n]["lat"]),
                    c=c, s=2, zorder=2)
for u, v in G_gcc.edges():
    axes[0].plot([float(G_gcc.nodes[u]["lng"]), float(G_gcc.nodes[v]["lng"])],
                 [float(G_gcc.nodes[u]["lat"]), float(G_gcc.nodes[v]["lat"])],
                 color="#dddddd", linewidth=0.15, zorder=1)
legend_elements = [Line2D([0], [0], marker="o", color="w",
                          markerfacecolor=c, markersize=8, label=z)
                   for z, c in ZONE_COLORS.items()]
axes[0].legend(handles=legend_elements, loc="upper left")
axes[0].set_title("Actual ERCOT Load Zones")
axes[0].set_aspect(1.2)

# (b) detected communities
if communities:
    COMM_COLORS = plt.cm.Set2(np.linspace(0, 1, min(len(communities), 8)))
    node_to_comm = {}
    for i, comm in enumerate(sorted(communities, key=len, reverse=True)):
        for n in comm:
            node_to_comm[n] = i

    for n in G_gcc.nodes():
        ci = node_to_comm.get(n, 0)
        c = COMM_COLORS[ci % len(COMM_COLORS)]
        axes[1].scatter(float(G_gcc.nodes[n]["lng"]), float(G_gcc.nodes[n]["lat"]),
                        c=[c], s=2, zorder=2)
    for u, v in G_gcc.edges():
        axes[1].plot([float(G_gcc.nodes[u]["lng"]), float(G_gcc.nodes[v]["lng"])],
                     [float(G_gcc.nodes[u]["lat"]), float(G_gcc.nodes[v]["lat"])],
                     color="#dddddd", linewidth=0.15, zorder=1)
    axes[1].set_title(f"Louvain Communities ({len(communities)} detected)")
    axes[1].set_aspect(1.2)

plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "03_zones_vs_communities.png"), dpi=150)
plt.close()
print("  → figures/03_zones_vs_communities.png")


# ─────────────────────────────────────────────────────────────────────────────
# 4. CASCADING FAILURE SIMULATION
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 4. Cascading Failure Simulation ═══")


def simulate_cascade(graph, edges_to_remove, max_rounds=10):
    """
    Remove edges, then iteratively check for overloads using DC power flow
    approximation (betweenness as proxy for flow).

    Returns: (nodes_in_gcc_after, total_edges_tripped)
    """
    H = graph.copy()
    tripped = set()

    # initial removal
    for u, v in edges_to_remove:
        if H.has_edge(u, v):
            H.remove_edge(u, v)
            tripped.add((u, v))

    for _ in range(max_rounds):
        if H.number_of_edges() == 0:
            break
        # use edge betweenness as flow proxy
        ebc_h = nx.edge_betweenness_centrality(H, k=min(100, H.number_of_nodes()))
        # normalize: max flow ~ total generation
        max_ebc = max(ebc_h.values()) if ebc_h else 1
        new_trips = []
        for (u, v), score in ebc_h.items():
            cap = H.edges[u, v].get("capacity_mva", 400)
            # overload threshold: if relative betweenness exceeds capacity ratio
            if max_ebc > 0 and score / max_ebc > 1.5 * cap / 2400:
                new_trips.append((u, v))
        if not new_trips:
            break
        for u, v in new_trips:
            H.remove_edge(u, v)
            tripped.add((u, v))

    gcc_size = len(max(nx.connected_components(H), key=len)) if H.number_of_nodes() > 0 else 0
    return gcc_size, len(tripped)


# Targeted attack: remove edges by betweenness, one at a time
print("  Running targeted attack (by edge betweenness)...")
ebc_sorted = sorted(ebc.items(), key=lambda x: -x[1])
n_steps = 50
targeted_gcc = []
targeted_trips = []

for step in range(n_steps):
    edges_rm = [e for e, _ in ebc_sorted[:step + 1]]
    gcc_sz, n_trip = simulate_cascade(G_gcc, edges_rm)
    targeted_gcc.append(gcc_sz / G_gcc.number_of_nodes())
    targeted_trips.append(n_trip)
    if step % 10 == 0:
        print(f"    step {step+1}: GCC={gcc_sz} ({targeted_gcc[-1]:.1%}), tripped={n_trip}")

# Random failure: remove random edges
print("  Running random failure simulation (averaged over 5 trials)...")
rng = np.random.default_rng(42)
all_edges_list = list(G_gcc.edges())
random_gcc_avg = np.zeros(n_steps)

n_trials = 5
for trial in range(n_trials):
    perm = rng.permutation(len(all_edges_list))
    for step in range(n_steps):
        edges_rm = [all_edges_list[perm[i]] for i in range(step + 1)]
        gcc_sz, _ = simulate_cascade(G_gcc, edges_rm)
        random_gcc_avg[step] += gcc_sz / G_gcc.number_of_nodes()
random_gcc_avg /= n_trials

# Plot: targeted vs random
fig, ax = plt.subplots(figsize=(10, 6))
xs = range(1, n_steps + 1)
ax.plot(xs, targeted_gcc, "r-o", markersize=3, label="Targeted (highest betweenness first)")
ax.plot(xs, random_gcc_avg, "b-s", markersize=3, label="Random failure (avg 5 trials)")
ax.set_xlabel("Number of edges removed")
ax.set_ylabel("Giant component fraction")
ax.set_title("Network Resilience: Targeted Attack vs Random Failure")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "04_resilience_targeted_vs_random.png"), dpi=150)
plt.close()
print("  → figures/04_resilience_targeted_vs_random.png")


# ─────────────────────────────────────────────────────────────────────────────
# 5. GEOGRAPHIC VISUALIZATION — voltage layers + generation
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 5. Grid Map ═══")

fig, ax = plt.subplots(figsize=(14, 12))

KV_STYLE = {
    345: {"color": "#D32F2F", "lw": 1.0, "label": "345 kV"},
    230: {"color": "#1976D2", "lw": 0.6, "label": "230 kV"},
    138: {"color": "#777777", "lw": 0.2, "label": "138 kV"},
}

# draw edges by voltage
for u, v, d in G_gcc.edges(data=True):
    kv = float(d.get("voltage_kv", 138))
    if kv >= 345:
        style = KV_STYLE[345]
    elif kv >= 230:
        style = KV_STYLE[230]
    else:
        style = KV_STYLE[138]
    ax.plot([float(G_gcc.nodes[u]["lng"]), float(G_gcc.nodes[v]["lng"])],
            [float(G_gcc.nodes[u]["lat"]), float(G_gcc.nodes[v]["lat"])],
            color=style["color"], linewidth=style["lw"], alpha=0.6, zorder=1)

# draw generation nodes
FUEL_MARKERS = {"Nuclear": ("^", "#9C27B0", 80),
                "Coal": ("s", "#795548", 40),
                "Gas": ("o", "#FF5722", 20),
                "Wind": ("D", "#00BCD4", 15),
                "Solar": ("*", "#FFC107", 20)}

for fuel, (marker, color, size) in FUEL_MARKERS.items():
    xs, ys, ss = [], [], []
    for n, d in G_gcc.nodes(data=True):
        fuels = d.get("gen_fuels", "")
        if fuel in fuels:
            xs.append(float(d["lng"]))
            ys.append(float(d["lat"]))
            ss.append(max(size, float(d.get("gen_mw", 0)) / 50))
    if xs:
        ax.scatter(xs, ys, s=ss, c=color, marker=marker, label=fuel,
                   alpha=0.7, zorder=3, edgecolors="none")

# legend
line_handles = [Line2D([0], [0], color=s["color"], lw=s["lw"] * 2, label=s["label"])
                for s in KV_STYLE.values()]
gen_handles = [Line2D([0], [0], marker=m, color="w", markerfacecolor=c,
                      markersize=8, label=f)
               for f, (m, c, _) in FUEL_MARKERS.items()]
ax.legend(handles=line_handles + gen_handles, loc="upper left", fontsize=9)

ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
ax.set_title("ERCOT Transmission Grid — Voltage Levels & Generation")
ax.set_aspect(1.2)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "05_grid_map.png"), dpi=200)
plt.close()
print("  → figures/05_grid_map.png")


# ─────────────────────────────────────────────────────────────────────────────
# 6. COMPARISON WITH RANDOM GRAPH MODELS
# ─────────────────────────────────────────────────────────────────────────────
print("\n═══ 6. Comparison with Random Graph Models ═══")

n = G_gcc.number_of_nodes()
m = G_gcc.number_of_edges()
p_er = 2 * m / (n * (n - 1))

print(f"  ERCOT: n={n}, m={m}")
print(f"  Erdos-Renyi p={p_er:.6f}")

# generate comparison graphs
G_er = nx.erdos_renyi_graph(n, p_er, seed=42)
# Barabasi-Albert: m_ba edges per new node, choose to match edge count
m_ba = max(1, round(m / n))
G_ba = nx.barabasi_albert_graph(n, m_ba, seed=42)

models = {"ERCOT Grid": G_gcc, "Erdos-Renyi": G_er, "Barabasi-Albert": G_ba}

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
for ax, (name, graph) in zip(axes, models.items()):
    degs = [d for _, d in graph.degree()]
    dc = Counter(degs)
    ks = sorted(dc)
    ax.bar(ks, [dc[k] for k in ks], color="steelblue", edgecolor="white", linewidth=0.2)
    ax.set_xlabel("Degree")
    ax.set_ylabel("Count")
    ax.set_title(f"{name}\nn={graph.number_of_nodes()}, m={graph.number_of_edges()}")
    ax.set_xlim(-1, max(degs) + 1)

    # stats annotation
    cc = nx.average_clustering(graph)
    gcc_frac = len(max(nx.connected_components(graph), key=len)) / graph.number_of_nodes()
    ax.annotate(f"<k>={np.mean(degs):.1f}\nCC={cc:.3f}\nGCC={gcc_frac:.1%}",
                xy=(0.95, 0.95), xycoords="axes fraction",
                ha="right", va="top", fontsize=9,
                bbox=dict(boxstyle="round", fc="white", alpha=0.8))

plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "06_random_graph_comparison.png"), dpi=150)
plt.close()
print("  → figures/06_random_graph_comparison.png")

for name, graph in models.items():
    degs = [d for _, d in graph.degree()]
    cc = nx.average_clustering(graph)
    gcc_frac = len(max(nx.connected_components(graph), key=len)) / graph.number_of_nodes()
    print(f"  {name:20s}  <k>={np.mean(degs):5.1f}  CC={cc:.4f}  GCC={gcc_frac:.1%}")


print("\n═══ All analyses complete. See figures/ directory. ═══")
