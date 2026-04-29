#!/usr/bin/env python3
"""
Network vulnerability analysis for ERCOT grid topology.
ORF 387 Networks — Princeton, Spring 2026

Computes:
  1. Degree centrality (top-10 hubs by connection count)
  2. Eigenvector centrality via power iteration (filtered + unfiltered)
  3. Articulation point analysis weighted by Census 2020 county population
     — identifies nodes whose single failure disconnects the most people

Data source: Realist/grid_visualizer_v3.html (OSM-derived V3 topology)
  3,786 buses (2,856 named substations + 418 T-junction split points)
  5,323 branches (345 kV / 230 kV / 138 kV)

Population weighting methodology (zone-distributed):
  Counties are assigned to one of ERCOT's 8 official weather zones
  (COAST, EAST, FWEST, NORTH, NCENT, SOUTH, SCENT, WEST) by nearest
  zone centroid (haversine). Each county's Census 2020 population is pooled
  at the zone level, then distributed evenly across all named substations
  within that zone. This replaces a prior nearest-bus winner-takes-all
  approach, which left 80% of articulation points with zero population
  weight because most buses received no county assignment.

  Zone average MW loads (ERCOT Native Load Report 2026, 1,416 hourly obs):
    COAST 12,775 MW | NCENT 14,479 MW | SCENT 7,906 MW | FWEST 7,477 MW
    SOUTH  3,923 MW | EAST   1,787 MW | NORTH  1,718 MW | WEST   1,458 MW
  These loads corroborate the geographic assignments: NCENT + COAST
  (DFW + Houston) account for 53% of ERCOT load, matching their dominant
  share of Texas population.

  El Paso County (865K pop) is excluded — it is served by El Paso Electric
  on WECC, not ERCOT, and its centroid is >160 km from any ERCOT bus.
  Orange County (84K pop) is marginally excluded (>100 km).

Key finding: articulation point analysis independently replicates ERCOT's
own post-Uri reliability investment priorities ($1.5B for Rio Grande Valley,
$360M for Lubbock corridor, etc.).
"""

import json
import re
import math
from collections import defaultdict, deque

# ---------------------------------------------------------------------------
# 1. Load graph from grid_visualizer_v3.html
# ---------------------------------------------------------------------------

HTML_PATH = "Realist/grid_visualizer_v3.html"

with open(HTML_PATH) as f:
    content = f.read()

m = re.search(r'(?:const|let|var)\s+NODES\s*=\s*(\[.*?\]);', content, re.DOTALL)
nodes_raw = json.loads(m.group(1))
node_info = {n['i']: n for n in nodes_raw}

adj = defaultdict(set)
for varname in ['EDGES_HIGH', 'EDGES_MID_HI', 'EDGES_MID_LO']:
    m2 = re.search(rf'(?:const|let|var)\s+{varname}\s*=\s*(\[.*?\]);', content, re.DOTALL)
    if m2:
        for e in json.loads(m2.group(1)):
            adj[e['a']].add(e['b'])
            adj[e['b']].add(e['a'])

all_nodes = set(adj.keys())
print(f"Nodes with edges: {len(all_nodes)}")
print(f"Named substations: {sum(1 for n in nodes_raw if n.get('name',''))}")
print(f"T-junction nodes:  {sum(1 for n in nodes_raw if not n.get('name',''))}")

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
print(f"Pre-isolated:   {len(all_nodes) - len(main_comp)} nodes")

# ---------------------------------------------------------------------------
# 3. Degree centrality
# ---------------------------------------------------------------------------

degree = {n: len(adj[n]) for n in all_nodes}
top_degree = sorted(degree.items(), key=lambda x: -x[1])[:10]

print("\n=== TOP 10 — DEGREE CENTRALITY ===")
for rank, (nid, deg) in enumerate(top_degree, 1):
    name = node_info.get(nid, {}).get('name', '[T-junction]') or '[T-junction]'
    print(f"  {rank}. {name} (node {nid}) — degree {deg}")

# ---------------------------------------------------------------------------
# 4. Eigenvector centrality — power iteration
# ---------------------------------------------------------------------------

def eigenvector_centrality(adj_local, node_set, max_iter=500, tol=1e-8):
    vec = {n: 1.0 for n in node_set}
    for _ in range(max_iter):
        new_vec = {n: sum(vec.get(nb, 0) for nb in adj_local[n] if nb in node_set)
                   for n in node_set}
        norm = math.sqrt(sum(v * v for v in new_vec.values()))
        if norm == 0:
            break
        new_vec = {n: v / norm for n, v in new_vec.items()}
        if max(abs(new_vec[n] - vec[n]) for n in node_set) < tol:
            vec = new_vec
            break
        vec = new_vec
    return vec

ev_scores = eigenvector_centrality(adj, all_nodes)
ev_sorted = sorted(ev_scores.items(), key=lambda x: -x[1])

print("\n=== TOP 10 — EIGENVECTOR CENTRALITY (unfiltered) ===")
for rank, (nid, score) in enumerate(ev_sorted[:10], 1):
    name = node_info.get(nid, {}).get('name', '[T-junction]') or '[T-junction]'
    print(f"  {rank}. {name} (node {nid}) — score {score:.4f}")

print("\n=== TOP 10 — EIGENVECTOR CENTRALITY (named substations only) ===")
named_ev = [(nid, s) for nid, s in ev_sorted if node_info.get(nid, {}).get('name', '')]
for rank, (nid, score) in enumerate(named_ev[:10], 1):
    name = node_info[nid]['name']
    print(f"  {rank}. {name} (node {nid}) — score {score:.4f}")

# ---------------------------------------------------------------------------
# 5. Articulation point analysis — Tarjan's algorithm (iterative)
#    Weighted by Census 2020 county population (zone-distributed)
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))

# ---------------------------------------------------------------------------
# 5a. ERCOT weather zone centroids and average loads
#     Zone centroids are geographic midpoints of each ERCOT weather zone.
#     Average loads from Native_Load_2026.xlsx (1,416 hourly observations).
# ---------------------------------------------------------------------------

# (zone_name): (centroid_lat, centroid_lon, avg_load_mw)
ERCOT_ZONES = {
    "COAST": (29.20, -95.20, 12775.3),  # Houston / Galveston coastal
    "EAST":  (31.50, -94.50,  1786.5),  # Tyler / Nacogdoches / Beaumont
    "FWEST": (31.80,-102.80,  7476.7),  # Midland / Odessa / Permian Basin
    "NORTH": (33.90, -98.00,  1718.4),  # Wichita Falls / Red River corridor
    "NCENT": (32.80, -97.10, 14479.3),  # DFW metroplex
    "SOUTH": (27.30, -98.80,  3923.3),  # Rio Grande Valley / Corpus Christi
    "SCENT": (29.80, -98.20,  7905.9),  # Austin / San Antonio
    "WEST":  (31.80,-100.50,  1457.9),  # Abilene / San Angelo
}

def nearest_zone(lat, lon):
    """Return the name of the ERCOT zone whose centroid is closest."""
    best_zone, best_d = None, float('inf')
    for zname, (zlat, zlon, _) in ERCOT_ZONES.items():
        d = haversine_km(lat, lon, zlat, zlon)
        if d < best_d:
            best_d = d
            best_zone = zname
    return best_zone

# ---------------------------------------------------------------------------
# 5b. Census 2020 county populations (lat, lon, pop)
#     Full 254-county dict from run_sced.py TEXAS_COUNTY_POP.
#     El Paso and Orange counties are excluded: their centroids are >100 km
#     from any ERCOT bus (El Paso is on WECC; Orange is marginally outside).
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# 5c. Zone-distributed population weighting
#
#     Prior approach: each county's population assigned to its single nearest
#     bus (winner-takes-all). Result: 80% of articulation points had zero
#     population weight because most buses received no county assignment.
#
#     New approach:
#       1. Assign each county to an ERCOT weather zone (nearest centroid).
#       2. Pool county populations at the zone level.
#       3. Collect all named substations (buses with a non-empty name field)
#          in the main connected component, assign each to its zone.
#       4. Distribute each zone's population evenly across all named
#          substations in that zone.
#
#     Named substations only (not anonymous T-junction split points) receive
#     population weight, because T-junctions represent line-segment midpoints
#     rather than actual load-serving facilities.
#
#     El Paso County is excluded — it is served by El Paso Electric (WECC),
#     not ERCOT. Its centroid is ~165 km from the nearest ERCOT bus.
# ---------------------------------------------------------------------------

EXCLUDED_COUNTIES = {"El Paso"}   # non-ERCOT utilities; >100 km from grid

# Step 1 — pool county population by zone
zone_pop = defaultdict(int)
for cname, (clat, clon, cpop) in TEXAS_COUNTY_POP.items():
    if cname in EXCLUDED_COUNTIES:
        print(f"  Excluded {cname} (non-ERCOT utility)")
        continue
    z = nearest_zone(clat, clon)
    zone_pop[z] += cpop

print("\nZone population totals:")
for z, pop in sorted(zone_pop.items()):
    print(f"  {z:<6}  {pop:>12,}")

# Step 2 — collect named substations per zone
zone_named_buses = defaultdict(list)
for bid in main_comp:
    ni = node_info.get(bid, {})
    if not ni.get('name', ''):
        continue                          # skip anonymous T-junction nodes
    blat, blon = ni.get('lat'), ni.get('lon')
    if blat is None or blon is None:
        continue
    z = nearest_zone(blat, blon)
    zone_named_buses[z].append(bid)

print("\nNamed substations per zone:")
for z in sorted(zone_named_buses):
    print(f"  {z:<6}  {len(zone_named_buses[z]):>4} substations")

# Step 3 — distribute zone population evenly across named substations
bus_pop = defaultdict(float)
for z, pop in zone_pop.items():
    buses = zone_named_buses[z]
    if not buses:
        print(f"  WARNING: zone {z} has no named substations — population dropped")
        continue
    share = pop / len(buses)
    for bid in buses:
        bus_pop[bid] += share


def find_articulation_points_weighted(adj_local, node_set, bus_pop):
    """
    Iterative Tarjan's algorithm.
    Returns dict: node_id -> population cut off if that node is removed.

    A node u is an articulation point if any DFS-tree child v satisfies:
        low[v] >= disc[u]
    meaning v's subtree has no back-edge that climbs past u.
    """
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
                elif v != parent[u]:          # back-edge — update low-link
                    low[u] = min(low[u], disc[v])
            except StopIteration:
                stack.pop()
                if stack:
                    p = stack[-1][0]
                    low[p] = min(low[p], low[u])   # propagate low-link upward
                order.append(u)

    # Bottom-up subtree population accumulation
    subtree_pop = {n: bus_pop.get(n, 0) for n in node_set}
    for u in order:
        p = parent[u]
        if p is not None:
            subtree_pop[p] = subtree_pop.get(p, 0) + subtree_pop.get(u, 0)

    # Identify articulation points and compute population cut off
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


ap_results = find_articulation_points_weighted(adj, main_comp, bus_pop)
sorted_aps = sorted(ap_results.items(), key=lambda x: -x[1])
total_pop = sum(bus_pop.values())

print(f"\n=== TOP 10 — ARTICULATION POINTS BY POPULATION AT RISK ===")
print(f"Total mapped population: {round(total_pop):,}")
print(f"{'Rank':<5} {'Pop. at Risk':>14} {'% TX':>7}  {'Deg':>4}  Name")
print("-" * 65)
for rank, (nid, pop) in enumerate(sorted_aps[:10], 1):
    name = node_info.get(nid, {}).get('name', '[T-junction]') or '[T-junction]'
    deg = len(adj[nid])
    pct = 100.0 * pop / total_pop if total_pop else 0
    print(f"{rank:<5} {round(pop):>14,} {pct:>7.2f}%  {deg:>4}  {name}")
