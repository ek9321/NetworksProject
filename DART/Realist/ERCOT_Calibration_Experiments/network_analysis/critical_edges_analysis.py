#!/usr/bin/env python3
"""
Critical edges analysis for the ERCOT transmission network.
ORF 387 Networks — Princeton, Spring 2026

Companion to articulation_point_analysis.py: this script asks the edge-level
version of the same question. Which transmission lines, when cut, disconnect
the most people — and which lines carry the most population-weighted flow?

Three metrics computed:

  (1) Bridges — Tarjan's iterative algorithm.
      An edge is a bridge iff its removal disconnects the graph.
      Weight each bridge by min(pop on side A, pop on side B) to rank bridges
      by the magnitude of the disconnection they would cause.

  (2) Edge betweenness centrality (unweighted) — Brandes' algorithm.
      Counts how often each edge lies on a shortest path between any pair
      of nodes. High-betweenness edges carry the most "topological traffic."

  (3) Population-weighted edge betweenness.
      Same as (2) but each source-target pair (s,t) is weighted by
      pop(s) * pop(t). This directly measures how much population-to-population
      flow each edge carries.

Cross-reference: the script flags edges corresponding to known SCED-binding
corridors (Morgan Creek <-> Tonkawa: WESTEX export) so we can compare the
topological critical-edge ranking against the physics-based ranking from
the DC-SCED model.

Output:
  - printed top-10 rankings for each metric
  - figures/critical_edges_map.png (companion to critical_ap_map.png)
  - results/critical_edges_ranking.csv (raw data for the report)

Data source: Realist/grid_visualizer_v3.html (OSM V3 topology)
Population weighting: zone-distributed, Census 2020
  (see articulation_point_analysis.py for methodology)
"""

import json
import re
import math
import csv
import os
from collections import defaultdict, deque

# ---------------------------------------------------------------------------
# 1. Graph loading
# ---------------------------------------------------------------------------

HTML_PATH = "Realist/grid_visualizer_v3.html"

with open(HTML_PATH) as f:
    content = f.read()

m = re.search(r'(?:const|let|var)\s+NODES\s*=\s*(\[.*?\]);', content, re.DOTALL)
nodes_raw = json.loads(m.group(1))
node_info = {n['i']: n for n in nodes_raw}

# Keep edges as first-class objects so we can tag each with voltage tier
# for the visualization. An edge is stored as a frozenset({a,b}) for
# undirected-lookup. We also keep adj for BFS/DFS.
edges_by_tier = {}
for varname in ['EDGES_HIGH', 'EDGES_MID_HI', 'EDGES_MID_LO']:
    m2 = re.search(rf'(?:const|let|var)\s+{varname}\s*=\s*(\[.*?\]);', content, re.DOTALL)
    if m2:
        edges_by_tier[varname] = json.loads(m2.group(1))

# Build adjacency + edge tier map
adj = defaultdict(set)
edge_tier = {}      # frozenset({a,b}) -> 'EDGES_HIGH' | 'EDGES_MID_HI' | 'EDGES_MID_LO'
edge_list = []      # list of (a, b, tier) for iteration
for varname, tier_edges in edges_by_tier.items():
    for e in tier_edges:
        a, b = e['a'], e['b']
        adj[a].add(b)
        adj[b].add(a)
        key = frozenset((a, b))
        if key not in edge_tier:      # first-seen tier wins (rare: parallel edges)
            edge_tier[key] = varname
            edge_list.append((a, b, varname))

all_nodes = set(adj.keys())
print(f"Nodes: {len(all_nodes)}  |  Unique edges: {len(edge_tier)}")

# ---------------------------------------------------------------------------
# 2. Main connected component
# ---------------------------------------------------------------------------

def bfs_from(start, blocked=None):
    blocked = blocked or set()
    visited = set()
    q = deque([start])
    visited.add(start)
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in visited and v not in blocked:
                visited.add(v)
                q.append(v)
    return visited

main_comp = bfs_from(next(iter(all_nodes)))
print(f"Main component: {len(main_comp)} nodes")

# ---------------------------------------------------------------------------
# 3. Population weighting (zone-distributed; replicated from AP analysis)
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))

ERCOT_ZONES = {
    "COAST": (29.20, -95.20, 12775.3),
    "EAST":  (31.50, -94.50,  1786.5),
    "FWEST": (31.80,-102.80,  7476.7),
    "NORTH": (33.90, -98.00,  1718.4),
    "NCENT": (32.80, -97.10, 14479.3),
    "SOUTH": (27.30, -98.80,  3923.3),
    "SCENT": (29.80, -98.20,  7905.9),
    "WEST":  (31.80,-100.50,  1457.9),
}

def nearest_zone(lat, lon):
    best_zone, best_d = None, float('inf')
    for zname, (zlat, zlon, _) in ERCOT_ZONES.items():
        d = haversine_km(lat, lon, zlat, zlon)
        if d < best_d:
            best_d = d
            best_zone = zname
    return best_zone

# Full Census 2020 county dict (same as articulation_point_analysis.py)
TEXAS_COUNTY_POP = {
    "Anderson":(31.82,-95.65,57863),"Andrews":(32.31,-102.64,18705),
    "Angelina":(31.37,-94.62,86771),"Aransas":(28.12,-97.05,23510),
    "Archer":(33.62,-98.69,8474),"Armstrong":(34.97,-101.36,1848),
    "Atascosa":(28.89,-98.53,48781),"Austin":(29.89,-96.28,30167),
    "Bailey":(34.07,-102.83,6985),"Bandera":(29.75,-99.25,21941),
    "Bastrop":(30.10,-97.31,97216),"Baylor":(33.62,-99.22,3530),
    "Bee":(28.42,-97.74,32691),"Bell":(31.05,-97.48,362924),
    "Bexar":(29.45,-98.52,2009324),"Blanco":(30.26,-98.41,11279),
    "Borden":(32.74,-101.43,641),"Bosque":(31.90,-97.64,18685),
    "Bowie":(33.44,-94.16,94090),"Brazoria":(29.17,-95.49,372031),
    "Brazos":(30.66,-96.30,229211),"Brewster":(29.79,-103.25,9203),
    "Briscoe":(34.53,-101.20,1546),"Brooks":(27.03,-98.22,7076),
    "Brown":(31.77,-99.00,37864),"Burleson":(30.49,-96.61,18443),
    "Burnet":(30.79,-98.23,47597),"Caldwell":(29.83,-97.62,45883),
    "Calhoun":(28.44,-96.61,21290),"Callahan":(32.30,-99.37,13943),
    "Cameron":(26.15,-97.58,423163),"Camp":(33.00,-94.98,13094),
    "Carson":(35.40,-101.35,5926),"Cass":(33.07,-94.34,30016),
    "Castro":(34.53,-102.26,7530),"Chambers":(29.71,-94.63,45689),
    "Cherokee":(31.83,-95.17,52646),"Childress":(34.53,-100.21,7306),
    "Clay":(33.78,-98.20,10303),"Cochran":(33.60,-102.84,2547),
    "Coke":(31.89,-100.52,3009),"Coleman":(31.77,-99.43,8547),
    "Collin":(33.19,-96.57,1064465),"Collingsworth":(34.96,-100.27,2920),
    "Colorado":(29.62,-96.53,21493),"Comal":(29.82,-98.27,156209),
    "Comanche":(31.95,-98.56,13635),"Concho":(31.32,-99.74,2726),
    "Cooke":(33.64,-97.21,41071),"Coryell":(31.39,-97.79,80766),
    "Cottle":(34.08,-100.28,1398),"Crane":(31.43,-102.35,4797),
    "Crockett":(30.72,-101.42,3405),"Crosby":(33.61,-101.30,5737),
    "Culberson":(31.44,-104.52,2163),"Dallam":(36.28,-102.60,6703),
    "Dallas":(32.77,-96.80,2613539),"Dawson":(32.74,-101.95,12547),
    "Deaf Smith":(34.96,-102.60,18546),"Delta":(33.39,-95.68,5331),
    "Denton":(33.21,-97.13,906422),"DeWitt":(29.09,-97.35,20097),
    "Dickens":(33.62,-100.79,2211),"Dimmit":(28.43,-99.75,10124),
    "Donley":(34.96,-100.81,3278),"Duval":(27.68,-98.49,11157),
    "Eastland":(32.31,-98.82,18583),"Ector":(31.87,-102.53,166223),
    "Edwards":(29.98,-100.30,1932),"Ellis":(32.35,-96.76,185141),
    "Erath":(32.23,-98.20,43564),"Falls":(31.27,-96.93,17297),
    "Fannin":(33.59,-96.11,36496),"Fayette":(29.88,-96.92,25066),
    "Fisher":(32.74,-100.40,3848),"Floyd":(33.97,-101.30,5728),
    "Foard":(33.98,-99.78,1186),"Fort Bend":(29.53,-95.77,811688),
    "Franklin":(33.17,-95.22,10720),"Freestone":(31.70,-96.15,19717),
    "Frio":(28.87,-99.11,20306),"Gaines":(32.74,-102.63,22010),
    "Galveston":(29.37,-94.85,342139),"Garza":(33.18,-101.30,6229),
    "Gillespie":(30.32,-98.94,26208),"Glasscock":(31.87,-101.52,1408),
    "Goliad":(28.66,-97.45,7658),"Gonzales":(29.46,-97.49,20837),
    "Gray":(35.40,-100.81,21886),"Grayson":(33.62,-96.68,136212),
    "Gregg":(32.47,-94.82,123945),"Grimes":(30.54,-95.93,28880),
    "Guadalupe":(29.61,-97.96,166847),"Hale":(34.07,-101.82,33406),
    "Hall":(34.53,-100.68,2964),"Hamilton":(31.69,-98.11,8461),
    "Hansford":(36.28,-101.35,5399),"Hardeman":(34.29,-99.75,3801),
    "Hardin":(30.27,-94.36,57602),"Harris":(29.85,-95.40,4731145),
    "Harrison":(32.55,-94.38,66553),"Hartley":(35.84,-102.60,5576),
    "Haskell":(33.18,-99.73,5336),"Hays":(30.06,-98.03,246521),
    "Hemphill":(35.84,-100.27,3819),"Henderson":(32.22,-95.85,82737),
    "Hidalgo":(26.40,-98.10,870781),"Hill":(31.99,-97.13,35399),
    "Hockley":(33.61,-102.35,23006),"Hood":(32.44,-97.82,64099),
    "Hopkins":(33.15,-95.56,37084),"Houston":(31.32,-95.42,22968),
    "Howard":(32.31,-101.44,36664),"Hudspeth":(31.46,-105.38,4886),
    "Hunt":(33.13,-96.09,99630),"Hutchinson":(35.84,-101.35,21061),
    "Irion":(31.32,-100.98,1536),"Jack":(33.23,-98.17,9003),
    "Jackson":(28.96,-96.58,14591),"Jasper":(30.72,-93.99,35710),
    "Jeff Davis":(30.72,-104.12,2274),"Jefferson":(30.04,-94.17,252358),
    "Jim Hogg":(27.06,-99.08,5300),"Jim Wells":(27.73,-98.08,40128),
    "Johnson":(32.38,-97.37,179685),"Jones":(32.74,-99.87,19891),
    "Karnes":(28.89,-97.86,15505),"Kaufman":(32.60,-96.28,136154),
    "Kendall":(29.95,-98.70,46687),"Kenedy":(26.93,-97.65,404),
    "Kent":(33.18,-100.77,762),"Kerr":(30.06,-99.34,53635),
    "Kimble":(30.50,-99.74,4472),"King":(33.62,-100.26,272),
    "Kinney":(29.35,-100.42,3667),"Kleberg":(27.43,-97.81,31549),
    "Knox":(33.60,-99.76,3664),"La Salle":(28.34,-99.10,7430),
    "Lamar":(33.67,-95.54,49532),"Lamb":(34.07,-102.35,13262),
    "Lampasas":(31.19,-98.24,21281),"Lavaca":(29.38,-96.92,20154),
    "Lee":(30.32,-97.04,17239),"Leon":(31.29,-95.97,17151),
    "Liberty":(30.17,-94.82,90697),"Limestone":(31.54,-96.59,23437),
    "Lipscomb":(36.28,-100.27,3233),"Live Oak":(28.35,-98.12,12207),
    "Llano":(30.71,-98.69,20860),"Loving":(31.85,-103.59,64),
    "Lubbock":(33.61,-101.82,310569),"Lynn":(33.18,-101.82,5808),
    "Madison":(30.97,-95.92,14218),"Marion":(33.00,-94.36,10083),
    "Martin":(32.31,-101.95,5771),"Mason":(30.73,-99.23,4274),
    "Matagorda":(28.79,-96.01,36702),"Maverick":(28.74,-100.31,57887),
    "McCulloch":(31.20,-99.34,7984),"McLennan":(31.55,-97.17,262065),
    "McMullen":(28.35,-98.57,707),"Medina":(29.35,-99.11,50607),
    "Menard":(30.88,-99.82,2148),"Midland":(32.00,-102.08,169895),
    "Milam":(30.79,-96.97,24823),"Mills":(31.49,-98.60,4873),
    "Mitchell":(32.31,-100.92,8545),"Montague":(33.67,-97.73,19546),
    "Montgomery":(30.30,-95.50,620443),"Moore":(35.84,-101.89,21904),
    "Morris":(33.11,-94.71,12388),"Motley":(34.07,-100.79,1156),
    "Nacogdoches":(31.62,-94.65,64785),"Navarro":(32.05,-96.47,50125),
    "Newton":(30.77,-93.73,13488),"Nolan":(32.31,-100.40,14669),
    "Nueces":(27.73,-97.59,342510),"Ochiltree":(36.28,-100.81,9836),
    "Oldham":(35.40,-102.60,1911),"Palo Pinto":(32.74,-98.30,28409),
    "Panola":(32.15,-94.31,23440),"Parker":(32.77,-97.81,148222),
    "Parmer":(34.53,-102.78,9605),"Pecos":(30.79,-102.72,15823),
    "Polk":(30.82,-94.83,51353),"Potter":(35.40,-101.88,117415),
    "Presidio":(29.79,-104.35,6131),"Rains":(32.87,-95.79,12514),
    "Randall":(34.96,-101.89,140977),"Reagan":(31.37,-101.52,3367),
    "Real":(29.83,-99.83,3389),"Red River":(33.63,-94.99,12023),
    "Reeves":(31.32,-103.69,15976),"Refugio":(28.33,-97.16,7236),
    "Roberts":(35.84,-100.81,885),"Robertson":(31.02,-96.51,16953),
    "Rockwall":(32.92,-96.41,107741),"Runnels":(31.83,-99.97,10264),
    "Rusk":(32.11,-94.77,53595),"Sabine":(31.35,-93.87,10542),
    "San Augustine":(31.39,-94.17,8490),"San Jacinto":(30.57,-95.10,29773),
    "San Patricio":(27.97,-97.52,67138),"San Saba":(31.17,-98.72,6055),
    "Schleicher":(30.90,-100.54,2793),"Scurry":(32.74,-100.91,16703),
    "Shackelford":(32.74,-99.35,3282),"Shelby":(31.79,-94.14,25048),
    "Sherman":(36.28,-101.89,3034),"Smith":(32.38,-95.27,232751),
    "Somervell":(32.22,-97.77,9128),"Starr":(26.56,-98.77,64633),
    "Stephens":(32.73,-98.82,9366),"Sterling":(31.83,-101.05,1291),
    "Stonewall":(33.18,-100.25,1285),"Sutton":(30.51,-100.53,3786),
    "Swisher":(34.53,-101.74,7236),"Tarrant":(32.77,-97.29,2110640),
    "Taylor":(32.31,-99.89,138034),"Terrell":(30.22,-102.08,775),
    "Terry":(33.18,-102.35,12004),"Throckmorton":(33.18,-99.21,1517),
    "Titus":(33.21,-94.96,32750),"Tom Green":(31.40,-100.45,119664),
    "Travis":(30.33,-97.77,1290188),"Trinity":(31.09,-95.37,14585),
    "Tyler":(30.77,-94.35,21672),"Upshur":(32.73,-94.96,41782),
    "Upton":(31.37,-102.05,3657),"Uvalde":(29.36,-99.78,25926),
    "Val Verde":(29.89,-101.15,48879),"Van Zandt":(32.56,-95.83,56590),
    "Victoria":(28.80,-96.98,92084),"Walker":(30.74,-95.57,72791),
    "Waller":(30.00,-95.99,55246),"Ward":(31.51,-103.10,11998),
    "Washington":(30.21,-96.39,34796),"Webb":(27.74,-99.51,276652),
    "Wharton":(29.31,-96.21,41551),"Wheeler":(35.40,-100.27,5056),
    "Wichita":(33.99,-98.71,131818),"Wilbarger":(34.09,-99.25,12769),
    "Willacy":(26.47,-97.82,20880),"Williamson":(30.65,-97.60,609017),
    "Wilson":(29.18,-98.07,51584),"Winkler":(31.85,-103.06,7802),
    "Wise":(33.21,-97.65,77028),"Wood":(32.78,-95.38,45539),
    "Yoakum":(33.18,-102.82,8713),"Young":(33.17,-98.68,17806),
    "Zapata":(27.07,-99.17,14179),"Zavala":(28.86,-99.76,12166),
}
EXCLUDED_COUNTIES = {"El Paso"}

# Pool county population by zone
zone_pop = defaultdict(int)
for cname, (clat, clon, cpop) in TEXAS_COUNTY_POP.items():
    if cname in EXCLUDED_COUNTIES:
        continue
    zone_pop[nearest_zone(clat, clon)] += cpop

# Collect named substations per zone (T-junctions get no population weight)
zone_named_buses = defaultdict(list)
for bid in main_comp:
    ni = node_info.get(bid, {})
    if not ni.get('name', ''):
        continue
    blat, blon = ni.get('lat'), ni.get('lon')
    if blat is None or blon is None:
        continue
    zone_named_buses[nearest_zone(blat, blon)].append(bid)

# Distribute zone population evenly across named substations
bus_pop = defaultdict(float)
for z, pop in zone_pop.items():
    buses = zone_named_buses[z]
    if not buses:
        continue
    share = pop / len(buses)
    for bid in buses:
        bus_pop[bid] += share

total_pop = sum(bus_pop.values())
print(f"Total mapped population: {round(total_pop):,}")

# ---------------------------------------------------------------------------
# 4. Bridge detection via iterative Tarjan
# ---------------------------------------------------------------------------
#
# An edge (u, v) where v is a DFS-tree child of u is a bridge iff
#     low[v] > disc[u]
# meaning no back-edge climbs from v's subtree past u.
#
# After the DFS we also compute subtree_pop[v] so that the population cut
# by removing a bridge is min(subtree_pop[v], total_pop - subtree_pop[v]).
# ---------------------------------------------------------------------------

def find_bridges_weighted(adj_local, node_set, bus_pop):
    disc = {}
    low = {}
    parent = {}
    children = defaultdict(list)
    order = []
    timer = [0]

    for root in node_set:
        if root in disc:
            continue
        parent[root] = None
        stack = [(root, iter(n for n in adj_local[root] if n in node_set))]
        disc[root] = low[root] = timer[0]
        timer[0] += 1

        while stack:
            u, nbrs = stack[-1]
            try:
                v = next(nbrs)
                if v not in disc:
                    parent[v] = u
                    children[u].append(v)
                    disc[v] = low[v] = timer[0]
                    timer[0] += 1
                    stack.append((v, iter(n for n in adj_local[v] if n in node_set)))
                elif v != parent[u]:
                    low[u] = min(low[u], disc[v])
            except StopIteration:
                stack.pop()
                if stack:
                    p = stack[-1][0]
                    low[p] = min(low[p], low[u])
                order.append(u)

    # Bottom-up subtree population accumulation
    subtree_pop = {n: bus_pop.get(n, 0.0) for n in node_set}
    for u in order:
        p = parent[u]
        if p is not None:
            subtree_pop[p] += subtree_pop[u]

    total = sum(bus_pop.get(n, 0.0) for n in node_set)

    # A tree edge (parent[v], v) is a bridge iff low[v] > disc[parent[v]]
    bridges = {}   # frozenset({u,v}) -> population cut
    for v in node_set:
        p = parent.get(v)
        if p is None:
            continue
        if low[v] > disc[p]:
            cut = min(subtree_pop[v], total - subtree_pop[v])
            bridges[frozenset((p, v))] = cut
    return bridges


print("\nFinding bridges...")
bridges = find_bridges_weighted(adj, main_comp, bus_pop)
print(f"  Found {len(bridges)} bridges "
      f"({100.0*len(bridges)/len(edge_tier):.1f}% of all edges)")

# ---------------------------------------------------------------------------
# 5. Brandes' edge betweenness centrality (unweighted + population-weighted)
# ---------------------------------------------------------------------------
#
# Standard Brandes, extended to weighted endpoint pairs.
# For unweighted: every (s, t) pair counts equally (w(s,t) = 1).
# For population-weighted: w(s, t) = pop(s) * pop(t).
# We factor: outer loop sums pop(s) * delta_s_reduced(v), where delta_s_reduced
# uses pop(w) as the endpoint weight of w in the dependency recursion.
#
# Edge betweenness on an undirected graph with unit weights:
#     C_B(e) = sum_{s,t, s<t} (#shortest s-t paths through e) / (#shortest s-t paths)
# ---------------------------------------------------------------------------

def brandes_edge_betweenness(adj_local, node_set, endpoint_weight=None,
                              source_filter=None):
    """
    If endpoint_weight is None: standard unweighted edge betweenness.
    If endpoint_weight is a dict: each (s, t) pair is weighted by
        endpoint_weight[s] * endpoint_weight[t].
    source_filter (optional): only iterate outer sources in this set.
    """
    C_B = defaultdict(float)
    sources = source_filter if source_filter is not None else node_set
    n_sources = len(sources)
    progress_step = max(1, n_sources // 20)

    for i, s in enumerate(sources):
        if endpoint_weight is not None and endpoint_weight.get(s, 0) == 0:
            continue

        # Single-source BFS
        S = []                         # stack of nodes in BFS order
        P = defaultdict(list)          # predecessors
        sigma = defaultdict(float)
        sigma[s] = 1.0
        d = {s: 0}
        Q = deque([s])
        while Q:
            v = Q.popleft()
            S.append(v)
            dv = d[v]
            for w in adj_local[v]:
                if w not in node_set:
                    continue
                if w not in d:
                    d[w] = dv + 1
                    Q.append(w)
                if d[w] == dv + 1:
                    sigma[w] += sigma[v]
                    P[w].append(v)

        # Accumulation (dependency, pop-weighted or unweighted)
        delta = defaultdict(float)
        if endpoint_weight is None:
            while S:
                w = S.pop()
                coeff = (1.0 + delta[w]) / sigma[w] if sigma[w] else 0.0
                for v in P[w]:
                    contrib = sigma[v] * coeff
                    C_B[frozenset((v, w))] += contrib
                    delta[v] += contrib
        else:
            pop_s = endpoint_weight.get(s, 0.0)
            while S:
                w = S.pop()
                pop_w = endpoint_weight.get(w, 0.0)
                coeff = (pop_w + delta[w]) / sigma[w] if sigma[w] else 0.0
                for v in P[w]:
                    contrib = sigma[v] * coeff
                    # edge (v, w) receives pop(s) * contrib
                    C_B[frozenset((v, w))] += pop_s * contrib
                    delta[v] += contrib

        if (i + 1) % progress_step == 0:
            print(f"    progress: {i+1}/{n_sources} sources")

    # Undirected graph: each pair counted twice
    for e in C_B:
        C_B[e] /= 2.0
    return dict(C_B)


print("\nComputing edge betweenness (unweighted)...")
eb_unweighted = brandes_edge_betweenness(adj, main_comp)

# For population-weighted: skip sources with zero population (T-junctions).
# This is both correct (they contribute 0) and ~25% faster.
pop_sources = {n for n in main_comp if bus_pop.get(n, 0) > 0}
print(f"\nComputing edge betweenness (population-weighted)"
      f" over {len(pop_sources)} populated sources...")
eb_popweighted = brandes_edge_betweenness(
    adj, main_comp,
    endpoint_weight=bus_pop,
    source_filter=pop_sources,
)

# ---------------------------------------------------------------------------
# 6. Known SCED-binding edges (cross-reference set)
# ---------------------------------------------------------------------------

SCED_BINDING_NAMES = [
    ("Morgan Creek Substation", "Tonkawa Substation",
     "WESTEX export corridor (L1605_1612). Real ERCOT constraint."),
]

def resolve_named_edge(name_a, name_b):
    """Return the node-ID edge frozenset for a named substation pair, or None."""
    name_to_id = {}
    for nid, ni in node_info.items():
        n = ni.get('name', '')
        if n:
            name_to_id.setdefault(n, nid)
    a = name_to_id.get(name_a)
    b = name_to_id.get(name_b)
    if a is None or b is None:
        return None
    # Direct edge?
    if b in adj[a]:
        return frozenset((a, b))
    # If not directly connected, try one hop through a T-junction
    for mid in adj[a]:
        if b in adj[mid] and not node_info.get(mid, {}).get('name', ''):
            return (frozenset((a, mid)), frozenset((mid, b)))
    return None

sced_ref = {}
print("\nResolving known SCED-binding edges...")
for a_name, b_name, note in SCED_BINDING_NAMES:
    res = resolve_named_edge(a_name, b_name)
    if res is None:
        print(f"  [MISS] {a_name} <-> {b_name}")
    elif isinstance(res, frozenset):
        sced_ref[res] = (a_name, b_name, note)
        print(f"  direct edge: {a_name} <-> {b_name}")
    else:
        # Two-edge path through a T-junction
        sced_ref[res[0]] = (a_name, "[T-jxn]", note)
        sced_ref[res[1]] = ("[T-jxn]", b_name, note)
        print(f"  two-hop via T-jxn: {a_name} <-> ... <-> {b_name}")

# ---------------------------------------------------------------------------
# 7. Reporting
# ---------------------------------------------------------------------------

def edge_label(e):
    a, b = tuple(e)
    na = node_info.get(a, {}).get('name', '') or '[T-jxn]'
    nb = node_info.get(b, {}).get('name', '') or '[T-jxn]'
    tier = edge_tier.get(e, '?')
    kv = {'EDGES_HIGH': '345', 'EDGES_MID_HI': '230', 'EDGES_MID_LO': '138'}.get(tier, '?')
    return f"{na} <-> {nb} ({kv} kV)"

print("\n" + "=" * 80)
print("TOP BRIDGES BY POPULATION CUT  (edge removal disconnects the grid)")
print("=" * 80)
sorted_bridges = sorted(bridges.items(), key=lambda x: -x[1])
print(f"{'Rank':<5} {'Pop. cut':>12} {'% TX':>7}   Edge")
print("-" * 80)
for rank, (e, cut) in enumerate(sorted_bridges[:15], 1):
    pct = 100.0 * cut / total_pop
    star = "  *" if e in sced_ref else ""
    print(f"{rank:<5} {round(cut):>12,} {pct:>7.2f}%   {edge_label(e)}{star}")

print("\n" + "=" * 80)
print("TOP EDGE BETWEENNESS — UNWEIGHTED")
print("=" * 80)
sorted_eb_u = sorted(eb_unweighted.items(), key=lambda x: -x[1])
print(f"{'Rank':<5} {'Score':>14}  Edge")
print("-" * 80)
for rank, (e, s) in enumerate(sorted_eb_u[:15], 1):
    star = "  *" if e in sced_ref else ""
    print(f"{rank:<5} {s:>14,.0f}  {edge_label(e)}{star}")

print("\n" + "=" * 80)
print("TOP EDGE BETWEENNESS — POPULATION-WEIGHTED")
print("  (each (s, t) pair weighted by pop(s) * pop(t))")
print("=" * 80)
sorted_eb_p = sorted(eb_popweighted.items(), key=lambda x: -x[1])
print(f"{'Rank':<5} {'Score (pop^2)':>18}   Edge")
print("-" * 80)
for rank, (e, s) in enumerate(sorted_eb_p[:15], 1):
    star = "  *" if e in sced_ref else ""
    print(f"{rank:<5} {s:>18,.3e}   {edge_label(e)}{star}")

# ---------------------------------------------------------------------------
# 8. Rank correlation — do unweighted and pop-weighted agree?
# ---------------------------------------------------------------------------

def rank_overlap(list_a, list_b, k):
    sa = {e for e, _ in list_a[:k]}
    sb = {e for e, _ in list_b[:k]}
    return len(sa & sb) / k if k else 0

print("\n" + "=" * 80)
print("RANK OVERLAP between unweighted and pop-weighted betweenness")
print("=" * 80)
for k in (10, 25, 50, 100):
    ov = rank_overlap(sorted_eb_u, sorted_eb_p, k)
    print(f"  top-{k:<3d}  overlap = {ov:.2f}")

# ---------------------------------------------------------------------------
# 9. Export full ranking as CSV for the map and for the report
# ---------------------------------------------------------------------------

results_dir = "Realist/ERCOT_Calibration_Experiments/network_analysis/results"
os.makedirs(results_dir, exist_ok=True)
csv_path = os.path.join(results_dir, "critical_edges_ranking.csv")

all_edges = set(edge_tier.keys())
rows = []
for e in all_edges:
    a, b = tuple(e)
    lat_a, lon_a = node_info.get(a, {}).get('lat'), node_info.get(a, {}).get('lon')
    lat_b, lon_b = node_info.get(b, {}).get('lat'), node_info.get(b, {}).get('lon')
    rows.append({
        'a_id': a, 'b_id': b,
        'a_name': node_info.get(a, {}).get('name', '') or '',
        'b_name': node_info.get(b, {}).get('name', '') or '',
        'a_lat': lat_a, 'a_lon': lon_a, 'b_lat': lat_b, 'b_lon': lon_b,
        'voltage_tier': edge_tier[e],
        'is_bridge': int(e in bridges),
        'bridge_pop_cut': bridges.get(e, 0),
        'eb_unweighted': eb_unweighted.get(e, 0.0),
        'eb_popweighted': eb_popweighted.get(e, 0.0),
        'sced_binding': int(e in sced_ref),
    })

rows.sort(key=lambda r: -r['bridge_pop_cut'] - r['eb_popweighted'])
with open(csv_path, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"\nWrote {len(rows)} edges to {csv_path}")
