#!/usr/bin/env python3
"""
Critical Articulation Point Map — ERCOT grid vulnerability analysis.
ORF 387 Networks — Princeton, Spring 2026

Produces a publication-quality map of the 7 most critical articulation points
in the ERCOT transmission network, identified by population-at-risk.

Population weighting: zone-distributed (see articulation_point_analysis.py).
Each county is assigned to the nearest ERCOT weather zone; zone population
is distributed evenly across all named substations in that zone.

Output: figures/critical_ap_map.png
"""

import json
import re
import math
from collections import defaultdict, deque

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import matplotlib.patheffects as pe
import numpy as np

# ---------------------------------------------------------------------------
# 1. Load graph from grid_visualizer_v3.html
# ---------------------------------------------------------------------------

HTML_PATH = "Realist/grid_visualizer_v3.html"

with open(HTML_PATH) as f:
    content = f.read()

m = re.search(r'(?:const|let|var)\s+NODES\s*=\s*(\[.*?\]);', content, re.DOTALL)
nodes_raw = json.loads(m.group(1))
node_info = {n['i']: n for n in nodes_raw}

# Build edge lists by voltage tier for differential rendering
edges_by_tier = {}
for varname in ['EDGES_HIGH', 'EDGES_MID_HI', 'EDGES_MID_LO']:
    m2 = re.search(rf'(?:const|let|var)\s+{varname}\s*=\s*(\[.*?\]);', content, re.DOTALL)
    if m2:
        edges_by_tier[varname] = json.loads(m2.group(1))

adj = defaultdict(set)
for tier_edges in edges_by_tier.values():
    for e in tier_edges:
        adj[e['a']].add(e['b'])
        adj[e['b']].add(e['a'])

all_nodes = set(adj.keys())

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

# ---------------------------------------------------------------------------
# 3. Zone centroids and population data
#    (duplicated from articulation_point_analysis.py for self-containment)
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

# ---------------------------------------------------------------------------
# 4. Zone-distributed population weighting
# ---------------------------------------------------------------------------

zone_pop = defaultdict(int)
for cname, (clat, clon, cpop) in TEXAS_COUNTY_POP.items():
    if cname in EXCLUDED_COUNTIES:
        continue
    z = nearest_zone(clat, clon)
    zone_pop[z] += cpop

zone_named_buses = defaultdict(list)
for bid in main_comp:
    ni = node_info.get(bid, {})
    if not ni.get('name', ''):
        continue
    blat, blon = ni.get('lat'), ni.get('lon')
    if blat is None or blon is None:
        continue
    z = nearest_zone(blat, blon)
    zone_named_buses[z].append(bid)

bus_pop = defaultdict(float)
for z, pop in zone_pop.items():
    buses = zone_named_buses[z]
    if not buses:
        continue
    share = pop / len(buses)
    for bid in buses:
        bus_pop[bid] += share

# ---------------------------------------------------------------------------
# 5. Articulation point analysis — iterative Tarjan's algorithm
# ---------------------------------------------------------------------------

def find_articulation_points_weighted(adj_local, node_set, bus_pop):
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

    subtree_pop = {n: bus_pop.get(n, 0) for n in node_set}
    for u in order:
        p = parent[u]
        if p is not None:
            subtree_pop[p] = subtree_pop.get(p, 0) + subtree_pop.get(u, 0)

    ap_cut = {}
    root_child_count = defaultdict(int)
    for u in node_set:
        if parent[u] is None:
            for c in children[u]:
                root_child_count[u] += 1

    for u in node_set:
        p = parent[u]
        if p is None:
            if root_child_count[u] > 1:
                child_pops = sorted(
                    [subtree_pop.get(c, 0) for c in children[u]], reverse=True)
                ap_cut[u] = sum(child_pops[1:]) + bus_pop.get(u, 0)
        else:
            for v in children[u]:
                if low[v] >= disc[u]:
                    ap_cut[u] = max(ap_cut.get(u, 0),
                                    subtree_pop.get(v, 0) + bus_pop.get(u, 0))
                    break

    return ap_cut


print("Running articulation point analysis...")
ap_results = find_articulation_points_weighted(adj, main_comp, bus_pop)
sorted_aps = sorted(ap_results.items(), key=lambda x: -x[1])
total_pop = sum(bus_pop.values())

print(f"Total mapped population: {round(total_pop):,}")
print(f"{'Rank':<5} {'Pop. at Risk':>14} {'% TX':>7}  Name")
print("-" * 55)
for rank, (nid, pop) in enumerate(sorted_aps[:15], 1):
    name = node_info.get(nid, {}).get('name', '[T-junction]') or '[T-junction]'
    pct = 100.0 * pop / total_pop if total_pop else 0
    print(f"{rank:<5} {round(pop):>14,} {pct:>7.2f}%  {name}")

# Keep only named substations for the visualization (T-junctions are
# line-segment midpoints, not load-serving facilities)
named_aps = [(nid, pop) for nid, pop in sorted_aps
             if node_info.get(nid, {}).get('name', '')]

# ---------------------------------------------------------------------------
# 6. Build coordinate lookup for all nodes
# ---------------------------------------------------------------------------

def node_coords(nid):
    ni = node_info.get(nid, {})
    return ni.get('lat'), ni.get('lon')

# ---------------------------------------------------------------------------
# 7. Plotting
# ---------------------------------------------------------------------------

TOP_N = 7
top_aps = named_aps[:TOP_N]

# ---------------------------------------------------------------------------
# Coordinates (confirmed from grid_visualizer_v3.html):
#   #1 Temple North:      lat=31.13, lon=-97.34  (SCENT)
#   #2 Waco Atco:         lat=31.49, lon=-97.25  (NCENT) ─┐
#   #3 Waco Woodway:      lat=31.51, lon=-97.22  (NCENT)  ├─ Waco cluster
#   #4 Waco Sanger Ave:   lat=31.52, lon=-97.20  (NCENT) ─┘
#   #5 Krugerville:       lat=33.28, lon=-96.99  (NCENT, north DFW)
#   #6 La Marque:         lat=29.37, lon=-94.97  (COAST, Galveston/Texas City)
#   #7 Tamina:            lat=30.19, lon=-95.35  (COAST, The Woodlands/Spring)
#
# The Waco cluster (ranks 2-4) spans only 0.04° lat × 0.05° lon — they
# overlap at full Texas scale. They are handled as a group annotation below.
# ---------------------------------------------------------------------------

fig, ax = plt.subplots(figsize=(14, 11), facecolor='white')
ax.set_facecolor('#f7f7f5')

# -- Draw background grid edges (all voltage tiers, faded)
print("Drawing background grid edges...")
tier_style = {
    'EDGES_HIGH':  dict(color='#aaaaab', lw=0.55, zorder=1),   # 345 kV
    'EDGES_MID_HI': dict(color='#c8c8c8', lw=0.35, zorder=1),  # 230 kV
    'EDGES_MID_LO': dict(color='#dedede', lw=0.22, zorder=1),  # 138 kV
}
for varname, style in tier_style.items():
    for e in edges_by_tier.get(varname, []):
        la, lo_a = node_coords(e['a'])
        lb, lo_b = node_coords(e['b'])
        if la and lb:
            ax.plot([lo_a, lo_b], [la, lb], **style)

# -- Other named articulation points as small gray dots (context)
print("Marking other articulation points...")
top_ids = {nid for nid, _ in top_aps}
for nid, pop in named_aps[TOP_N:]:
    if nid in top_ids:
        continue
    lat, lon = node_coords(nid)
    if lat:
        ax.scatter(lon, lat, s=10, color='#a0a0a0', zorder=3,
                   linewidths=0, alpha=0.55)

# -- Color palette: rank 1 darkest red → rank 7 light orange
CMAP = plt.cm.YlOrRd
colors = [CMAP(0.95 - i * 0.09) for i in range(TOP_N)]

# Marker sizes proportional to log(population)
max_pop = top_aps[0][1]
min_pop = top_aps[-1][1]
def marker_size(pop):
    if max_pop == min_pop:
        return 200
    return 90 + 320 * (math.log(pop) - math.log(min_pop)) / \
                       (math.log(max_pop) - math.log(min_pop))

# ---------------------------------------------------------------------------
# Plot dot markers for all 7 APs.
# The Waco cluster (ranks 1-2-3 in the sorted list, indices 1,2,3) will
# nearly overlap on the map — that is intentional and visually communicates
# the tight geographic concentration of the vulnerability.
# ---------------------------------------------------------------------------
print("Plotting top articulation points...")
for rank_i, (nid, pop) in enumerate(top_aps):
    lat, lon = node_coords(nid)
    if lat is None:
        print(f"  WARNING: no coords for node {nid}")
        continue
    color = colors[rank_i]
    ms = marker_size(pop)
    ax.scatter(lon, lat, s=ms + 55, color='white', zorder=5, linewidths=0)
    ax.scatter(lon, lat, s=ms, color=color, zorder=6, linewidths=1.1,
               edgecolors='#222222')
    ax.text(lon, lat, str(rank_i + 1), ha='center', va='center',
            fontsize=7.0, fontweight='bold', color='white', zorder=7)

# ---------------------------------------------------------------------------
# Individual label annotations.
#
# Waco cluster (ranks 2-4, indices 1-3): one shared callout box to the left,
# with three separate arrows — one to each substation.
# All other ranks get their own label box.
# ---------------------------------------------------------------------------

def pct(pop):
    return 100.0 * pop / total_pop

def short(name):
    return name.replace(" Substation","").replace(" Station","").strip()

def fmt_label(rank_i, nid, pop):
    name = node_info[nid].get('name', '')
    zone = nearest_zone(*node_coords(nid))
    return (f"#{rank_i+1} {short(name)}\n"
            f"Zone: {zone}\n"
            f"{round(pop):,} at risk  ({pct(pop):.2f}%)")

# Helper to draw a label with arrow
def draw_label(ax, text, xy, xytext, color, fontsize=6.9, rad=0.0):
    ax.annotate(
        text,
        xy=xy, xytext=xytext,
        fontsize=fontsize,
        ha='center', va='center',
        bbox=dict(boxstyle='round,pad=0.45', facecolor='white',
                  edgecolor=color, linewidth=1.5, alpha=0.94),
        arrowprops=dict(arrowstyle='->', color='#444444', lw=1.0,
                        connectionstyle=f'arc3,rad={rad}'),
        zorder=8,
    )

# Rank 1: Temple North — label to the right
nid1, pop1 = top_aps[0]
lat1, lon1 = node_coords(nid1)
draw_label(ax, fmt_label(0, nid1, pop1),
           xy=(lon1, lat1), xytext=(lon1 + 1.35, lat1 - 0.30),
           color=colors[0], rad=-0.15)

# Ranks 2-4: Waco cluster — shared callout to the left, three arrows
waco_label_lon, waco_label_lat = -100.5, 31.62
waco_text = (
    "Waco I-35 Cluster (NCENT)\n"
    "─────────────────────────\n"
    f"#2 Waco Atco         588,498 (2.09%)\n"
    f"#3 Waco Woodway    549,264 (1.95%)\n"
    f"#4 Waco Sanger Ave 510,031 (1.81%)"
)
# Draw the shared box first (no arrowprops — arrows drawn separately below)
ax.text(waco_label_lon, waco_label_lat, waco_text,
        fontsize=6.5, ha='center', va='center', family='monospace',
        bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                  edgecolor=colors[1], linewidth=1.5, alpha=0.95),
        zorder=8)

# Three arrows from the box to each Waco substation
for waco_rank_i in [1, 2, 3]:
    nid_w, _ = top_aps[waco_rank_i]
    lat_w, lon_w = node_coords(nid_w)
    ax.annotate(
        "", xy=(lon_w, lat_w),
        xytext=(waco_label_lon, waco_label_lat),
        arrowprops=dict(arrowstyle='->', color='#444444', lw=0.9,
                        connectionstyle='arc3,rad=0.0'),
        zorder=7,
    )

# Rank 5: Krugerville — label to the right
nid5, pop5 = top_aps[4]
lat5, lon5 = node_coords(nid5)
draw_label(ax, fmt_label(4, nid5, pop5),
           xy=(lon5, lat5), xytext=(lon5 + 1.30, lat5 + 0.10),
           color=colors[4], rad=0.10)

# Rank 6: La Marque — label below-left (Galveston/Texas City area)
nid6, pop6 = top_aps[5]
lat6, lon6 = node_coords(nid6)
draw_label(ax, fmt_label(5, nid6, pop6),
           xy=(lon6, lat6), xytext=(lon6 - 1.60, lat6 - 0.65),
           color=colors[5], rad=0.20)

# Rank 7: Tamina — label to the right (The Woodlands/Spring area)
nid7, pop7 = top_aps[6]
lat7, lon7 = node_coords(nid7)
draw_label(ax, fmt_label(6, nid7, pop7),
           xy=(lon7, lat7), xytext=(lon7 + 1.35, lat7 + 0.20),
           color=colors[6], rad=-0.10)

# ---------------------------------------------------------------------------
# Real-world ERCOT hardening project annotations (context boxes, blue)
# These mark post-Uri and post-Harvey investments near the critical zones.
# ---------------------------------------------------------------------------

def draw_project(ax, text, xy_target, xy_label, rad=0.15):
    ax.annotate(
        text,
        xy=xy_target, xytext=xy_label,
        fontsize=6.1,
        ha='center', va='center',
        color='#154360',
        bbox=dict(boxstyle='round,pad=0.4', facecolor='#d4e6f1',
                  edgecolor='#2874a6', linewidth=1.0, alpha=0.90),
        arrowprops=dict(arrowstyle='->', color='#2874a6', lw=0.85,
                        connectionstyle=f'arc3,rad={rad}'),
        zorder=9,
    )

# I-35 corridor reference (between Temple North and Waco cluster)
draw_project(ax,
    "I-35 Transmission Spine\n(Austin ↔ DFW, no bypass route)",
    xy_target=(-97.34, 31.33),  # midpoint between Temple and Waco
    xy_label=(-99.30, 30.60),
    rad=0.10,
)

# TNMP Galveston hardening post-Harvey
draw_project(ax,
    "TNMP Galveston Hardening\n(post-Harvey 2017, ~$200M)\nThin thread to Galveston Is.",
    xy_target=(lon6, lat6),
    xy_label=(-93.80, 29.10),
    rad=-0.20,
)

# RGV $1.5B context (not in top-7 but ERCOT's largest post-Uri investment)
draw_project(ax,
    "RGV $1.5B Upgrade\n(post-Uri 2021, SOUTH zone)\nNo top-7 AP — upgrade worked",
    xy_target=(-98.10, 26.40),
    xy_label=(-100.80, 26.00),
    rad=0.10,
)

# Lubbock $360M connectivity context
draw_project(ax,
    "Lubbock $360M\nConnectivity Project\n(FWEST zone)",
    xy_target=(-101.82, 33.61),
    xy_label=(-104.20, 34.20),
    rad=-0.15,
)

# ---------------------------------------------------------------------------
# I-35 corridor bracket: vertical arrow between Temple North and Waco cluster
# ---------------------------------------------------------------------------
ax.annotate(
    "", xy=(-97.28, 31.50), xytext=(-97.28, 31.16),
    arrowprops=dict(arrowstyle='<->', color='#922b21', lw=1.8,
                    mutation_scale=14),
    zorder=10,
)
ax.text(-97.12, 31.33, "I-35\nSpine", fontsize=7.0, color='#922b21',
        fontweight='bold', ha='left', va='center', zorder=10)

# ---------------------------------------------------------------------------
# Map bounds, labels, title
# ---------------------------------------------------------------------------
ax.set_xlim(-107.2, -93.0)
ax.set_ylim(25.5, 36.9)
ax.set_aspect('equal')

ax.set_xlabel("Longitude", fontsize=9)
ax.set_ylabel("Latitude", fontsize=9)
ax.set_title(
    "ERCOT Grid — 7 Most Critical Articulation Points by Population at Risk\n"
    "OSM V3 Topology · 3,786 buses · 5,323 branches  |  "
    "Census 2020, zone-distributed weighting  |  ORF 387 Networks, Princeton 2026",
    fontsize=10, pad=10,
)

# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------
legend_elements = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor=colors[0],
           markeredgecolor='#333', markersize=10,
           label='#1 Temple North (SCENT) — 677,816 at risk'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor=colors[2],
           markeredgecolor='#333', markersize=9,
           label='#2–4 Waco cluster (NCENT) — 510K–588K each'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor=colors[4],
           markeredgecolor='#333', markersize=7.5,
           label='#5 Krugerville (NCENT, N. DFW) — 156,933'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor=colors[5],
           markeredgecolor='#333', markersize=7,
           label='#6 La Marque (COAST, Galveston) — 147,490'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor=colors[6],
           markeredgecolor='#333', markersize=6.5,
           label='#7 Tamina (COAST, Woodlands) — 129,054'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#a0a0a0',
           markeredgecolor='#888', markersize=4.5,
           label='Other articulation points (ranks 8+)'),
    mpatches.Patch(facecolor='#aaaaab', label='345 kV backbone'),
    mpatches.Patch(facecolor='#c8c8c8', label='230 kV network'),
    mpatches.Patch(facecolor='#dedede', label='138 kV network'),
    mpatches.Patch(facecolor='#d4e6f1', edgecolor='#2874a6',
                   label='ERCOT hardening projects (context)'),
]
ax.legend(handles=legend_elements, loc='lower left', fontsize=6.6,
          framealpha=0.93, edgecolor='#bbbbbb',
          title="Articulation Points & Infrastructure", title_fontsize=7.2,
          handlelength=1.4)

plt.tight_layout()
out_path = "Realist/ERCOT_Calibration_Experiments/network_analysis/figures/critical_ap_map.png"
plt.savefig(out_path, dpi=180, bbox_inches='tight', facecolor='white')
print(f"\nSaved: {out_path}")
plt.close()
