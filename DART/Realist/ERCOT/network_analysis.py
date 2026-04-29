"""
ERCOT Power Grid Network Science Analysis
==========================================
Performs 5 analyses on the ERCOT grid topology:
  1. Attack-curve resilience (Albert-Barabasi-Jeong plot)
  2. Simplified DC power flow cascade simulation
  3. Null-model benchmark (configuration model)
  4. Spectral / community analysis
  5. Link prediction -> upgrade ranking

All figures saved to figures/ directory, results to network_analysis_results.json.
"""

import json
import math
import os
import sys
import time
import warnings
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import eigsh

warnings.filterwarnings("ignore")

# Try seaborn-style
try:
    plt.style.use("seaborn-v0_8-whitegrid")
except Exception:
    try:
        plt.style.use("seaborn-whitegrid")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path("/Users/jackhasker/ORF387/Dartboard/Realist/ERCOT")
FIG_DIR = BASE_DIR / "figures"
FIG_DIR.mkdir(exist_ok=True)

BUS_CSV = Path("/Users/jackhasker/ORF387/Dartboard/Realist/grid_data/sced_inputs_v3/SourceData/bus.csv")
BRANCH_CSV = Path("/Users/jackhasker/ORF387/Dartboard/Realist/grid_data/sced_inputs_v3/SourceData/branch.csv")

RESULTS = {}  # accumulate all numerical results

# ---------------------------------------------------------------------------
# Texas county population data (Census 2020) for load allocation
# ---------------------------------------------------------------------------
TEXAS_COUNTY_POP = {
    "Anderson": (31.82, -95.65, 57863), "Andrews": (32.31, -102.64, 18705),
    "Angelina": (31.37, -94.62, 86771), "Aransas": (28.12, -97.05, 23510),
    "Archer": (33.62, -98.69, 8474), "Armstrong": (34.97, -101.36, 1848),
    "Atascosa": (28.89, -98.53, 48781), "Austin": (29.89, -96.28, 30167),
    "Bailey": (34.07, -102.83, 6985), "Bandera": (29.75, -99.25, 21941),
    "Bastrop": (30.10, -97.31, 97216), "Baylor": (33.62, -99.22, 3530),
    "Bee": (28.42, -97.74, 32691), "Bell": (31.05, -97.48, 362924),
    "Bexar": (29.45, -98.52, 2009324), "Blanco": (30.26, -98.41, 11279),
    "Borden": (32.74, -101.43, 641), "Bosque": (31.90, -97.64, 18685),
    "Bowie": (33.44, -94.16, 94090), "Brazoria": (29.17, -95.49, 372031),
    "Brazos": (30.66, -96.30, 229211), "Brewster": (29.79, -103.25, 9203),
    "Briscoe": (34.53, -101.20, 1546), "Brooks": (27.03, -98.22, 7076),
    "Brown": (31.77, -99.00, 37864), "Burleson": (30.49, -96.61, 18443),
    "Burnet": (30.79, -98.23, 47597), "Caldwell": (29.83, -97.62, 45883),
    "Calhoun": (28.44, -96.61, 21290), "Callahan": (32.30, -99.37, 13943),
    "Cameron": (26.15, -97.58, 423163), "Camp": (33.00, -94.98, 13094),
    "Carson": (35.40, -101.35, 5926), "Cass": (33.07, -94.34, 30016),
    "Castro": (34.53, -102.26, 7530), "Chambers": (29.71, -94.63, 45689),
    "Cherokee": (31.83, -95.17, 52646), "Childress": (34.53, -100.21, 7306),
    "Clay": (33.78, -98.20, 10303), "Cochran": (33.60, -102.84, 2547),
    "Coke": (31.89, -100.52, 3009), "Coleman": (31.77, -99.43, 8547),
    "Collin": (33.19, -96.57, 1064465), "Collingsworth": (34.96, -100.27, 2920),
    "Colorado": (29.62, -96.53, 21493), "Comal": (29.82, -98.27, 156209),
    "Comanche": (31.95, -98.56, 13635), "Concho": (31.32, -99.74, 2726),
    "Cooke": (33.64, -97.21, 41071), "Coryell": (31.39, -97.79, 80766),
    "Cottle": (34.08, -100.28, 1398), "Crane": (31.43, -102.35, 4797),
    "Crockett": (30.72, -101.42, 3405), "Crosby": (33.61, -101.30, 5737),
    "Culberson": (31.44, -104.52, 2163), "Dallam": (36.28, -102.60, 6703),
    "Dallas": (32.77, -96.80, 2613539), "Dawson": (32.74, -101.95, 12547),
    "Deaf Smith": (34.96, -102.60, 18546), "Delta": (33.39, -95.68, 5331),
    "Denton": (33.21, -97.13, 906422), "DeWitt": (29.09, -97.35, 20097),
    "Dickens": (33.62, -100.79, 2211), "Dimmit": (28.43, -99.75, 10124),
    "Donley": (34.96, -100.81, 3278), "Duval": (27.68, -98.49, 11157),
    "Eastland": (32.31, -98.82, 18583), "Ector": (31.87, -102.53, 166223),
    "Edwards": (29.98, -100.30, 1932), "El Paso": (31.77, -106.49, 865657),
    "Ellis": (32.35, -96.76, 185141), "Erath": (32.23, -98.20, 43564),
    "Falls": (31.27, -96.93, 17297), "Fannin": (33.59, -96.11, 36496),
    "Fayette": (29.88, -96.92, 25066), "Fisher": (32.74, -100.40, 3848),
    "Floyd": (33.97, -101.30, 5728), "Foard": (33.98, -99.78, 1186),
    "Fort Bend": (29.53, -95.77, 811688), "Franklin": (33.17, -95.22, 10720),
    "Freestone": (31.70, -96.15, 19717), "Frio": (28.87, -99.11, 20306),
    "Gaines": (32.74, -102.63, 22010), "Galveston": (29.37, -94.85, 342139),
    "Garza": (33.18, -101.30, 6229), "Gillespie": (30.32, -98.94, 26208),
    "Glasscock": (31.87, -101.52, 1408), "Goliad": (28.66, -97.45, 7658),
    "Gonzales": (29.46, -97.49, 20837), "Gray": (35.40, -100.81, 21886),
    "Grayson": (33.62, -96.68, 136212), "Gregg": (32.47, -94.82, 123945),
    "Grimes": (30.54, -95.93, 28880), "Guadalupe": (29.61, -97.96, 166847),
    "Hale": (34.07, -101.82, 33406), "Hall": (34.53, -100.68, 2964),
    "Hamilton": (31.69, -98.11, 8461), "Hansford": (36.28, -101.35, 5399),
    "Hardeman": (34.29, -99.75, 3801), "Hardin": (30.27, -94.36, 57602),
    "Harris": (29.85, -95.40, 4731145), "Harrison": (32.55, -94.38, 66553),
    "Hartley": (35.84, -102.60, 5576), "Haskell": (33.18, -99.73, 5336),
    "Hays": (30.06, -98.03, 246521), "Hemphill": (35.84, -100.27, 3819),
    "Henderson": (32.22, -95.85, 82737), "Hidalgo": (26.40, -98.10, 870781),
    "Hill": (31.99, -97.13, 35399), "Hockley": (33.61, -102.35, 23006),
    "Hood": (32.44, -97.82, 64099), "Hopkins": (33.15, -95.56, 37084),
    "Houston": (31.32, -95.42, 22968), "Howard": (32.31, -101.44, 36664),
    "Hudspeth": (31.46, -105.38, 4886), "Hunt": (33.13, -96.09, 99630),
    "Hutchinson": (35.84, -101.35, 21061), "Irion": (31.32, -100.98, 1536),
    "Jack": (33.23, -98.17, 9003), "Jackson": (28.96, -96.58, 14591),
    "Jasper": (30.72, -93.99, 35710), "Jeff Davis": (30.72, -104.12, 2274),
    "Jefferson": (30.04, -94.17, 252358), "Jim Hogg": (27.06, -99.08, 5300),
    "Jim Wells": (27.73, -98.08, 40128), "Johnson": (32.38, -97.37, 179685),
    "Jones": (32.74, -99.87, 19891), "Karnes": (28.89, -97.86, 15505),
    "Kaufman": (32.60, -96.28, 136154), "Kendall": (29.95, -98.70, 46687),
    "Kenedy": (26.93, -97.65, 404), "Kent": (33.18, -100.77, 762),
    "Kerr": (30.06, -99.34, 53635), "Kimble": (30.50, -99.74, 4472),
    "King": (33.62, -100.26, 272), "Kinney": (29.35, -100.42, 3667),
    "Kleberg": (27.43, -97.81, 31549), "Knox": (33.60, -99.76, 3664),
    "La Salle": (28.34, -99.10, 7430), "Lamar": (33.67, -95.54, 49532),
    "Lamb": (34.07, -102.35, 13262), "Lampasas": (31.19, -98.24, 21281),
    "Lavaca": (29.38, -96.92, 20154), "Lee": (30.32, -97.04, 17239),
    "Leon": (31.29, -95.97, 17151), "Liberty": (30.17, -94.82, 90697),
    "Limestone": (31.54, -96.59, 23437), "Lipscomb": (36.28, -100.27, 3233),
    "Live Oak": (28.35, -98.12, 12207), "Llano": (30.71, -98.69, 20860),
    "Loving": (31.85, -103.59, 64), "Lubbock": (33.61, -101.82, 310569),
    "Lynn": (33.18, -101.82, 5808), "Madison": (30.97, -95.92, 14218),
    "Marion": (33.00, -94.36, 10083), "Martin": (32.31, -101.95, 5771),
    "Mason": (30.73, -99.23, 4274), "Matagorda": (28.79, -96.01, 36702),
    "Maverick": (28.74, -100.31, 57887), "McCulloch": (31.20, -99.34, 7984),
    "McLennan": (31.55, -97.17, 262065), "McMullen": (28.35, -98.57, 707),
    "Medina": (29.35, -99.11, 50607), "Menard": (30.88, -99.82, 2148),
    "Midland": (32.00, -102.08, 169895), "Milam": (30.79, -96.97, 24823),
    "Mills": (31.49, -98.60, 4873), "Mitchell": (32.31, -100.92, 8545),
    "Montague": (33.67, -97.73, 19546), "Montgomery": (30.30, -95.50, 620443),
    "Moore": (35.84, -101.89, 21904), "Morris": (33.11, -94.71, 12388),
    "Motley": (34.07, -100.79, 1156), "Nacogdoches": (31.62, -94.65, 64785),
    "Navarro": (32.05, -96.47, 50125), "Newton": (30.77, -93.73, 13488),
    "Nolan": (32.31, -100.40, 14669), "Nueces": (27.73, -97.59, 342510),
    "Ochiltree": (36.28, -100.81, 9836), "Oldham": (35.40, -102.60, 1911),
    "Orange": (30.13, -93.86, 84047), "Palo Pinto": (32.74, -98.30, 28409),
    "Panola": (32.15, -94.31, 23440), "Parker": (32.77, -97.81, 148222),
    "Parmer": (34.53, -102.78, 9605), "Pecos": (30.79, -102.72, 15823),
    "Polk": (30.82, -94.83, 51353), "Potter": (35.40, -101.88, 117415),
    "Presidio": (29.79, -104.35, 6131), "Rains": (32.87, -95.79, 12514),
    "Randall": (34.96, -101.89, 140977), "Reagan": (31.37, -101.52, 3367),
    "Real": (29.83, -99.83, 3389), "Red River": (33.63, -94.99, 12023),
    "Reeves": (31.32, -103.69, 15976), "Refugio": (28.33, -97.16, 7236),
    "Roberts": (35.84, -100.81, 885), "Robertson": (31.02, -96.51, 16953),
    "Rockwall": (32.92, -96.41, 107741), "Runnels": (31.83, -99.97, 10264),
    "Rusk": (32.11, -94.77, 53595), "Sabine": (31.35, -93.87, 10542),
    "San Augustine": (31.39, -94.17, 8490), "San Jacinto": (30.57, -95.10, 29773),
    "San Patricio": (27.97, -97.52, 67138), "San Saba": (31.17, -98.72, 6055),
    "Schleicher": (30.90, -100.54, 2793), "Scurry": (32.74, -100.91, 16703),
    "Shackelford": (32.74, -99.35, 3282), "Shelby": (31.79, -94.14, 25048),
    "Sherman": (36.28, -101.89, 3034), "Smith": (32.38, -95.27, 232751),
    "Somervell": (32.22, -97.77, 9128), "Starr": (26.56, -98.77, 64633),
    "Stephens": (32.73, -98.82, 9366), "Sterling": (31.83, -101.05, 1291),
    "Stonewall": (33.18, -100.25, 1285), "Sutton": (30.51, -100.53, 3786),
    "Swisher": (34.53, -101.74, 7236), "Tarrant": (32.77, -97.29, 2110640),
    "Taylor": (32.31, -99.89, 138034), "Terrell": (30.22, -102.08, 775),
    "Terry": (33.18, -102.35, 12004), "Throckmorton": (33.18, -99.21, 1517),
    "Titus": (33.21, -94.96, 32750), "Tom Green": (31.40, -100.45, 119664),
    "Travis": (30.33, -97.77, 1290188), "Trinity": (31.09, -95.37, 14585),
    "Tyler": (30.77, -94.35, 21672), "Upshur": (32.73, -94.96, 41782),
    "Upton": (31.37, -102.05, 3657), "Uvalde": (29.36, -99.78, 25926),
    "Val Verde": (29.89, -101.15, 48879), "Van Zandt": (32.56, -95.83, 56590),
    "Victoria": (28.80, -96.98, 92084), "Walker": (30.74, -95.57, 72791),
    "Waller": (30.00, -95.99, 55246), "Ward": (31.51, -103.10, 11998),
    "Washington": (30.21, -96.39, 34796), "Webb": (27.74, -99.51, 276652),
    "Wharton": (29.31, -96.21, 41551), "Wheeler": (35.40, -100.27, 5056),
    "Wichita": (33.99, -98.71, 131818), "Wilbarger": (34.09, -99.25, 12769),
    "Willacy": (26.47, -97.82, 20880), "Williamson": (30.65, -97.60, 609017),
    "Wilson": (29.18, -98.07, 51584), "Winkler": (31.85, -103.06, 7802),
    "Wise": (33.21, -97.65, 77028), "Wood": (32.78, -95.38, 45539),
    "Yoakum": (33.18, -102.82, 8713), "Young": (33.17, -98.68, 17806),
    "Zapata": (27.07, -99.17, 14179), "Zavala": (28.86, -99.76, 12166),
}
_COUNTY_LIST = list(TEXAS_COUNTY_POP.values())

ZONE_LOAD_MW = {"NORTH": 23000.0, "HOUSTON": 11500.0, "SOUTH": 10500.0, "WEST": 7000.0}

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(min(a, 1.0)))

def nearest_county_pop(lat, lon):
    best_dist = float("inf")
    best_pop = 1
    for clat, clon, pop in _COUNTY_LIST:
        d = haversine_km(lat, lon, clat, clon)
        if d < best_dist:
            best_dist = d
            best_pop = pop
    return best_pop

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
print("=" * 70)
print("ERCOT NETWORK SCIENCE ANALYSIS")
print("=" * 70)

bus_df = pd.read_csv(BUS_CSV)
branch_df = pd.read_csv(BRANCH_CSV)

print(f"Buses: {len(bus_df)}, Branches: {len(branch_df)}")

# Compute population-weighted load for each bus
bus_df["is_split_bool"] = bus_df["is_split"].astype(str).str.lower().isin(["true", "1"])
base_kv = pd.to_numeric(bus_df["BaseKV"], errors="coerce").fillna(0.0)
is_load_bus = (~bus_df["is_split_bool"]) & (base_kv >= 100) & (base_kv < 300)

# Assign county population weight
bus_df["pop_weight"] = bus_df.apply(
    lambda r: nearest_county_pop(r["lat"], r["lng"]) if pd.notna(r["lat"]) and pd.notna(r["lng"]) else 1.0, axis=1
)

# Distribute zone MW load proportional to population (same as run_sced.py "pop" method)
bus_df["MW_Load_computed"] = 0.0
for zone, zone_mw in ZONE_LOAD_MW.items():
    zmask = (bus_df["Zone"] == zone) & is_load_bus
    ztotal = bus_df.loc[zmask, "pop_weight"].sum()
    if ztotal > 0:
        bus_df.loc[zmask, "MW_Load_computed"] = zone_mw * bus_df.loc[zmask, "pop_weight"] / ztotal

total_load = bus_df["MW_Load_computed"].sum()
print(f"Total computed load: {total_load:.1f} MW")

# Write bus_load.csv so optimal_grid.py (and anything else downstream)
# can use pop-weighted MW load without re-executing this script.
_out_load = bus_df[["Bus ID", "Zone", "lat", "lng", "is_split_bool", "MW_Load_computed"]].rename(
    columns={"is_split_bool": "is_split", "MW_Load_computed": "MW_Load_pop"}
)
_out_load.to_csv(BASE_DIR / "bus_load.csv", index=False)
print(f"Wrote bus_load.csv ({len(_out_load)} rows)")

# Build graph
G = nx.Graph()
for _, row in bus_df.iterrows():
    bid = int(row["Bus ID"])
    G.add_node(bid, zone=row["Zone"], lat=row["lat"], lng=row["lng"],
               mw_load=row["MW_Load_computed"], is_split=row["is_split_bool"],
               base_kv=base_kv[row.name], pop_weight=row["pop_weight"])

for _, row in branch_df.iterrows():
    fb = int(row["From Bus"])
    tb = int(row["To Bus"])
    if fb in G.nodes and tb in G.nodes:
        G.add_edge(fb, tb, uid=row["UID"], r=row["R"], x=row["X"],
                   b_shunt=row["B"], cont_rating=row["Cont Rating"])

print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

# Check connectivity
components = list(nx.connected_components(G))
print(f"Connected components: {len(components)}")
gcc_nodes = max(components, key=len)
print(f"Giant component: {len(gcc_nodes)} nodes ({100*len(gcc_nodes)/G.number_of_nodes():.1f}%)")

# Use only the giant connected component for all analyses
G_full = G.copy()
G = G.subgraph(gcc_nodes).copy()
n_orig = G.number_of_nodes()
print(f"Working with giant component: {n_orig} nodes, {G.number_of_edges()} edges")

# =========================================================================
# ANALYSIS 1: Attack-curve resilience
# =========================================================================
print("\n" + "=" * 70)
print("ANALYSIS 1: Attack-curve resilience (Albert-Barabasi-Jeong)")
print("=" * 70)

fracs = np.arange(0, 0.51, 0.01)
strategies = ["random", "degree", "eigenvector", "population", "betweenness"]

# Pre-compute centralities on the working graph
t0 = time.time()
print("Computing centralities...")
degree_dict = dict(G.degree())
print(f"  Degree: done ({time.time()-t0:.1f}s)")

t0 = time.time()
try:
    eigen_dict = nx.eigenvector_centrality(G, max_iter=1000, tol=1e-4)
except nx.PowerIterationFailedConvergence:
    print("  Eigenvector centrality did not converge, using degree centrality as fallback")
    eigen_dict = nx.degree_centrality(G)
print(f"  Eigenvector: done ({time.time()-t0:.1f}s)")

t0 = time.time()
# Use approximate betweenness for speed (k=500 sample)
between_dict = nx.betweenness_centrality(G, k=min(500, n_orig))
print(f"  Betweenness (approx k=500): done ({time.time()-t0:.1f}s)")

# Population weight ordering: sort by MW_Load_computed descending, skip is_split for ordering
pop_order = []
for n in G.nodes():
    mw = G.nodes[n].get("mw_load", 0.0)
    is_sp = G.nodes[n].get("is_split", False)
    pop_order.append((n, mw, is_sp))
# Sort: non-split nodes by MW load desc, then split nodes
pop_order_nonsplit = sorted([(n, mw) for n, mw, isp in pop_order if not isp], key=lambda x: -x[1])
pop_order_split = [(n, mw) for n, mw, isp in pop_order if isp]
pop_ordered_nodes = [n for n, _ in pop_order_nonsplit] + [n for n, _ in pop_order_split]

# Build ordering for each strategy
orderings = {}
orderings["degree"] = sorted(G.nodes(), key=lambda n: -degree_dict[n])
orderings["eigenvector"] = sorted(G.nodes(), key=lambda n: -eigen_dict[n])
orderings["betweenness"] = sorted(G.nodes(), key=lambda n: -between_dict[n])
orderings["population"] = pop_ordered_nodes

def compute_gcc_frac(graph, remove_order, frac):
    """Remove frac of nodes, return gcc size / original size."""
    n_remove = int(frac * n_orig)
    H = graph.copy()
    nodes_to_remove = remove_order[:n_remove]
    nodes_to_remove = [n for n in nodes_to_remove if n in H]
    H.remove_nodes_from(nodes_to_remove)
    if H.number_of_nodes() == 0:
        return 0.0
    return max(len(c) for c in nx.connected_components(H)) / n_orig

attack_curves = {}

# Random: average over 10 trials
print("Computing attack curves...")
random_curves = []
rng = np.random.default_rng(42)
all_nodes = list(G.nodes())
for trial in range(10):
    perm = rng.permutation(all_nodes).tolist()
    curve = []
    for f in fracs:
        curve.append(compute_gcc_frac(G, perm, f))
    random_curves.append(curve)
attack_curves["random"] = np.mean(random_curves, axis=0).tolist()
print("  Random (10 trials): done")

for strat in ["degree", "eigenvector", "population", "betweenness"]:
    curve = []
    for f in fracs:
        curve.append(compute_gcc_frac(G, orderings[strat], f))
    attack_curves[strat] = curve
    print(f"  {strat}: done")

# Plot
fig, ax = plt.subplots(figsize=(10, 7))
colors = {"random": "gray", "degree": "red", "eigenvector": "blue",
          "betweenness": "green", "population": "orange"}
labels = {"random": "Random", "degree": "Degree (highest first)",
          "eigenvector": "Eigenvector centrality", "betweenness": "Betweenness centrality",
          "population": "Population-weighted load"}

for strat in strategies:
    ax.plot(fracs, attack_curves[strat], label=labels[strat], color=colors[strat], linewidth=2)

ax.axhline(y=0.5, color="black", linestyle="--", alpha=0.5, label="50% threshold")
ax.set_xlabel("Fraction of nodes removed (f)", fontsize=13)
ax.set_ylabel("Giant component fraction (S/N)", fontsize=13)
ax.set_title("ERCOT Grid Resilience: Attack Curves", fontsize=15)
ax.legend(fontsize=11)
ax.set_xlim(0, 0.5)
ax.set_ylim(0, 1.05)
fig.tight_layout()
fig.savefig(FIG_DIR / "attack_curves.png", dpi=200)
plt.close(fig)
print("  Saved figures/attack_curves.png")

# Compute f* (fraction where GCC < 50%)
f_star = {}
for strat in strategies:
    curve = attack_curves[strat]
    fs = None
    for i, f in enumerate(fracs):
        if curve[i] < 0.5:
            fs = float(f)
            break
    f_star[strat] = fs if fs is not None else ">0.50"
    print(f"  f*({strat}) = {f_star[strat]}")

# GCC fraction at f=0.10 and f=0.20
gcc_at_f = {}
for strat in strategies:
    idx10 = int(0.10 / 0.01)
    idx20 = int(0.20 / 0.01)
    gcc_at_f[strat] = {
        "f=0.10": round(attack_curves[strat][idx10], 4),
        "f=0.20": round(attack_curves[strat][idx20], 4),
    }
    print(f"  {strat}: S(f=0.10)={gcc_at_f[strat]['f=0.10']:.4f}, S(f=0.20)={gcc_at_f[strat]['f=0.20']:.4f}")

RESULTS["analysis_1_attack_curves"] = {
    "f_star": {k: (v if isinstance(v, str) else round(v, 2)) for k, v in f_star.items()},
    "gcc_fraction_at_f": gcc_at_f,
}

# =========================================================================
# ANALYSIS 2: N-1 contingency stress analysis (replaces iterative cascade)
# =========================================================================
#
# We abandon the iterative cascade model because our toy base case is
# unrealistically stressed (proportional-to-PMax dispatch, pop-weighted
# load) — every first-iteration trip cascaded 200+ lines, which is a
# numerical artifact, not grid physics. Instead we do a single-step N-1:
# trip one line, solve DC flow once, measure how much stress that single
# outage places on the rest of the grid.
#
# Per-line metrics:
#   n_overloaded   = # of remaining lines whose post-trip |flow| > rating
#   max_overload   = max |flow|/rating across remaining lines
#   total_mw_over  = sum of (|flow| - rating) for overloaded lines [MW]
#   creates_island = did the trip disconnect the graph?
#
# Caveat: this is still toy physics. Dispatch is proportional-to-PMax,
# not economic. Real ERCOT SCED would give different base flows. We
# report relative rankings, not absolute MW.
# =========================================================================
print("\n" + "=" * 70)
print("ANALYSIS 2: N-1 contingency stress analysis")
print("=" * 70)

try:
    nodes_list = sorted(G.nodes())
    node_idx = {n: i for i, n in enumerate(nodes_list)}
    N = len(nodes_list)

    # Find slack bus
    slack_bus = None
    for n in nodes_list:
        if bus_df.loc[bus_df["Bus ID"] == n, "Bus Type"].values[0] == "Slack":
            slack_bus = n
            break
    if slack_bus is None:
        slack_bus = max(nodes_list, key=lambda n: G.degree(n))
    slack_idx = node_idx[slack_bus]
    print(f"Slack bus: {slack_bus} (index {slack_idx})")

    gen_df = pd.read_csv(Path("/Users/jackhasker/ORF387/Dartboard/Realist/grid_data/sced_inputs_v3/SourceData/gen.csv"))
    gen_by_bus = gen_df.groupby("Bus ID")["PMax MW"].sum().to_dict()
    total_gen_capacity = sum(v for k, v in gen_by_bus.items() if k in set(nodes_list))
    print(f"Gen capacity on GCC: {total_gen_capacity:.1f} MW across {len(gen_by_bus)} gen buses")

    # Build branch list with susceptances
    branches = []
    for u, v, data in G.edges(data=True):
        x_val = data.get("x", 0.01)
        if x_val <= 0 or pd.isna(x_val):
            x_val = 0.001
        b_val = 1.0 / x_val
        rating = float(data.get("cont_rating", 999999))
        uid = data.get("uid", f"{u}_{v}")
        branches.append((u, v, b_val, rating, uid))
    n_branches = len(branches)
    print(f"Branches for DC flow: {n_branches}")

    # Edge betweenness for reference metric
    t0 = time.time()
    edge_between = nx.edge_betweenness_centrality(G, k=min(500, N))
    print(f"Edge betweenness computed ({time.time()-t0:.1f}s)")
    # Map to UIDs via (u,v) lookup — build once, then fast lookup
    uv_to_uid = {(min(u,v), max(u,v)): uid for u,v,_,_,uid in branches}
    branch_eb = {}
    for (u, v), eb_val in edge_between.items():
        key = (min(u,v), max(u,v))
        if key in uv_to_uid:
            branch_eb[uv_to_uid[key]] = eb_val

    # Base injection vector
    P_inj = np.zeros(N)
    for n in nodes_list:
        P_inj[node_idx[n]] = -G.nodes[n].get("mw_load", 0.0)
    total_load_dc = -P_inj.sum()
    for bus_id, pmax in gen_by_bus.items():
        if bus_id in node_idx and total_gen_capacity > 0:
            P_inj[node_idx[bus_id]] += total_load_dc * (pmax / total_gen_capacity)
    residual = P_inj.sum()
    P_inj[slack_idx] -= residual
    print(f"DC base case: total load = {total_load_dc:.1f} MW, residual = {residual:.4f} MW")

    def solve_dc_flow(active_branches, P_injection, slack_i):
        n = len(P_injection)
        B = np.zeros((n, n))
        for u, v, b_val, rating, uid in active_branches:
            i = node_idx.get(u); j = node_idx.get(v)
            if i is None or j is None: continue
            B[i, i] += b_val; B[j, j] += b_val
            B[i, j] -= b_val; B[j, i] -= b_val
        idx_keep = list(range(n)); idx_keep.remove(slack_i)
        B_red = B[np.ix_(idx_keep, idx_keep)]
        P_red = P_injection[idx_keep]
        try:
            theta_red = np.linalg.solve(B_red, P_red)
        except np.linalg.LinAlgError:
            return None
        theta = np.zeros(n)
        for k, idx in enumerate(idx_keep):
            theta[idx] = theta_red[k]
        flows = {}
        for u, v, b_val, rating, uid in active_branches:
            i = node_idx.get(u); j = node_idx.get(v)
            if i is None or j is None: continue
            flows[uid] = b_val * (theta[i] - theta[j])
        return flows

    # Base-case flows (reference)
    print("Solving base-case DC flow...")
    t0 = time.time()
    base_flows = solve_dc_flow(branches, P_inj, slack_idx)
    print(f"Base case solved ({time.time()-t0:.1f}s)")
    if base_flows is None:
        raise RuntimeError("Base case DC flow singular")

    # Base-case overload count (a sanity check; should be modest for
    # a well-calibrated grid — if high, documents the toy-dispatch caveat)
    base_overloads = sum(1 for b in branches if abs(base_flows.get(b[4], 0)) > b[3] and b[3] < 999999)
    base_max_ratio = max((abs(base_flows.get(b[4], 0))/b[3]) for b in branches if b[3] < 999999 and b[3] > 0)
    print(f"Base case: {base_overloads}/{n_branches} lines over rating, max ratio = {base_max_ratio:.2f}")
    print("  (high base-case overload counts documents the toy-dispatch limitation)")

    bridges_set = set()
    for u, v in nx.bridges(G):
        key = (min(u,v), max(u,v))
        if key in uv_to_uid:
            bridges_set.add(uv_to_uid[key])

    # Sample: top-100 by edge betweenness + 100 random for comparison
    sorted_by_eb = sorted(branches, key=lambda b: branch_eb.get(b[4], 0), reverse=True)
    top_eb = sorted_by_eb[:100]
    rng_ct = np.random.default_rng(123)
    random_sample_idx = rng_ct.choice(n_branches, size=100, replace=False)
    random_sample = [branches[i] for i in random_sample_idx if branches[i][4] not in {b[4] for b in top_eb}]
    test_branches = top_eb + random_sample
    print(f"Running N-1 on {len(test_branches)} lines ({len(top_eb)} top-EB + {len(random_sample)} random)...")

    n1_results = []
    t0 = time.time()
    for idx_b, (bu, bv, bb, br, buid) in enumerate(test_branches):
        active = [b for b in branches if b[4] != buid]
        # Check if the trip islands the graph (would make DC singular)
        H = nx.Graph()
        H.add_nodes_from(nodes_list)
        for b in active:
            H.add_edge(b[0], b[1])
        creates_island = (nx.number_connected_components(H) > 1)
        if creates_island:
            n1_results.append({
                "line": buid,
                "edge_betweenness": round(branch_eb.get(buid, 0), 6),
                "is_bridge": buid in bridges_set,
                "n_overloaded": None,
                "max_overload_ratio": None,
                "total_mw_over_rating": None,
                "creates_island": True,
                "category": "top_eb" if idx_b < len(top_eb) else "random",
            })
            continue

        flows = solve_dc_flow(active, P_inj, slack_idx)
        if flows is None:
            n1_results.append({"line": buid, "edge_betweenness": round(branch_eb.get(buid, 0), 6),
                "is_bridge": buid in bridges_set, "n_overloaded": None,
                "max_overload_ratio": None, "total_mw_over_rating": None,
                "creates_island": True,
                "category": "top_eb" if idx_b < len(top_eb) else "random"})
            continue

        n_over = 0; max_ratio = 0.0; total_over = 0.0
        for b in active:
            if b[3] < 999999 and b[3] > 0 and b[4] in flows:
                f_abs = abs(flows[b[4]])
                ratio = f_abs / b[3]
                if ratio > max_ratio:
                    max_ratio = ratio
                if f_abs > b[3]:
                    n_over += 1
                    total_over += (f_abs - b[3])
        n1_results.append({
            "line": buid,
            "edge_betweenness": round(branch_eb.get(buid, 0), 6),
            "is_bridge": buid in bridges_set,
            "n_overloaded": int(n_over),
            "max_overload_ratio": round(max_ratio, 4),
            "total_mw_over_rating": round(total_over, 2),
            "creates_island": False,
            "category": "top_eb" if idx_b < len(top_eb) else "random",
        })
        if (idx_b + 1) % 50 == 0:
            print(f"  {idx_b+1}/{len(test_branches)} done ({time.time()-t0:.1f}s)")

    n1_df = pd.DataFrame(n1_results)
    n1_df.to_csv(BASE_DIR / "n1_stress_results.csv", index=False)
    print(f"Saved n1_stress_results.csv ({len(n1_df)} entries)")

    # Summary: top 10 by total MW over rating (among non-islanding, non-top lines)
    ok_df = n1_df[~n1_df["creates_island"]].copy()
    top10_stress = ok_df.nlargest(10, "total_mw_over_rating")
    print("\nTop 10 lines by N-1 stress (non-islanding):")
    for _, row in top10_stress.iterrows():
        print(f"  {row['line']}: max_overload={row['max_overload_ratio']:.2f}x, "
              f"{row['n_overloaded']} lines over, total={row['total_mw_over_rating']:.0f} MW over")

    # Correlations among non-islanding contingencies
    if len(ok_df) > 10:
        corr_eb = ok_df["total_mw_over_rating"].corr(ok_df["edge_betweenness"])
    else:
        corr_eb = float("nan")
    n_islanders = int(n1_df["creates_island"].sum())
    n_bridges = int(n1_df["is_bridge"].sum())
    print(f"\nCorrelation(total_mw_over, edge_betweenness) = {corr_eb:.4f}  (n={len(ok_df)} non-islanding)")
    print(f"Contingencies that island the grid: {n_islanders}/{len(n1_df)}")
    print(f"Bridges in test set: {n_bridges}/{len(n1_df)}")

    # Plot: histogram of post-trip max overload ratio, split by category
    fig, ax = plt.subplots(figsize=(10, 6))
    for cat, color in [("top_eb","steelblue"), ("random","gray")]:
        vals = ok_df[ok_df["category"]==cat]["max_overload_ratio"].values
        if len(vals) > 0:
            ax.hist(vals, bins=25, color=color, edgecolor="white", alpha=0.7, label=f"{cat} (n={len(vals)})")
    ax.axvline(x=1.0, color="red", linestyle="--", alpha=0.7, label="Rating (1.0×)")
    ax.set_xlabel("Post-trip max overload ratio (max |flow|/rating)", fontsize=13)
    ax.set_ylabel("Count of contingencies", fontsize=13)
    ax.set_title("N-1 Contingency Stress: Top-Betweenness vs Random Lines", fontsize=14)
    ax.legend(fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "n1_stress.png", dpi=200)
    plt.close(fig)
    print("Saved figures/n1_stress.png")

    RESULTS["analysis_2_n1_stress"] = {
        "base_case_overloads": int(base_overloads),
        "base_case_max_ratio": round(float(base_max_ratio), 4),
        "base_case_toy_dispatch_note": "Base case uses generation distributed proportional to PMax, not economic dispatch. High base overload counts reflect this simplification; N-1 results should be read as relative rankings, not absolute MW.",
        "n_tested": len(n1_df),
        "n_non_islanding": int(len(ok_df)),
        "n_islanding_contingencies": n_islanders,
        "n_bridges_in_sample": n_bridges,
        "corr_total_mw_over_vs_edge_betweenness": round(float(corr_eb), 4) if not np.isnan(corr_eb) else None,
        "top_10_stress_lines": top10_stress[["line","max_overload_ratio","n_overloaded","total_mw_over_rating","is_bridge"]].to_dict("records"),
    }

except Exception as e:
    print(f"N-1 ANALYSIS FAILED: {e}")
    import traceback; traceback.print_exc()
    RESULTS["analysis_2_n1_stress"] = {"error": str(e)}

# =========================================================================
# ANALYSIS 3: Null-model benchmark
# =========================================================================
print("\n" + "=" * 70)
print("ANALYSIS 3: Null-model benchmark (configuration model)")
print("=" * 70)

try:
    # Real ERCOT metrics
    # Algebraic connectivity (lambda_2)
    t0 = time.time()
    L = nx.laplacian_matrix(G).astype(float)
    eigvals_real = eigsh(L, k=2, which="SM", return_eigenvectors=False)
    lambda2_real = float(sorted(eigvals_real)[1])
    print(f"ERCOT algebraic connectivity (lambda_2): {lambda2_real:.6f} ({time.time()-t0:.1f}s)")

    # Fraction of articulation points
    aps_real = set(nx.articulation_points(G))
    ap_frac_real = len(aps_real) / G.number_of_nodes()
    print(f"ERCOT articulation point fraction: {ap_frac_real:.4f} ({len(aps_real)}/{G.number_of_nodes()})")

    # GCC after removing top 5% degree nodes
    top5pct_n = int(0.05 * G.number_of_nodes())
    top5pct_nodes = sorted(G.nodes(), key=lambda n: -G.degree(n))[:top5pct_n]
    H_test = G.copy()
    H_test.remove_nodes_from(top5pct_nodes)
    if H_test.number_of_nodes() > 0:
        gcc_after_top5_real = max(len(c) for c in nx.connected_components(H_test)) / G.number_of_nodes()
    else:
        gcc_after_top5_real = 0.0
    print(f"ERCOT GCC after removing top-5% degree: {gcc_after_top5_real:.4f}")

    # Null model realizations
    degree_seq = [d for _, d in G.degree()]
    null_lambda2 = []
    null_ap_frac = []
    null_gcc_top5 = []

    print("Generating 20 configuration model realizations...")
    for trial in range(20):
        # Generate configuration model
        G_null = nx.configuration_model(degree_seq, seed=42 + trial)
        G_null = nx.Graph(G_null)  # remove parallel edges
        G_null.remove_edges_from(nx.selfloop_edges(G_null))  # remove self-loops

        # Use only giant component
        if G_null.number_of_nodes() == 0:
            continue
        gcc_null = max(nx.connected_components(G_null), key=len)
        G_null_gcc = G_null.subgraph(gcc_null).copy()

        if G_null_gcc.number_of_nodes() < 10:
            continue

        # Lambda_2
        try:
            L_null = nx.laplacian_matrix(G_null_gcc).astype(float)
            ev_null = eigsh(L_null, k=2, which="SM", return_eigenvectors=False)
            null_lambda2.append(float(sorted(ev_null)[1]))
        except Exception:
            pass

        # AP fraction
        aps_null = set(nx.articulation_points(G_null_gcc))
        null_ap_frac.append(len(aps_null) / G_null_gcc.number_of_nodes())

        # GCC after top-5% removal
        top5_null_n = int(0.05 * G_null_gcc.number_of_nodes())
        top5_null_nodes = sorted(G_null_gcc.nodes(), key=lambda n: -G_null_gcc.degree(n))[:top5_null_n]
        H_null = G_null_gcc.copy()
        H_null.remove_nodes_from(top5_null_nodes)
        if H_null.number_of_nodes() > 0:
            null_gcc_top5.append(max(len(c) for c in nx.connected_components(H_null)) / G_null_gcc.number_of_nodes())
        else:
            null_gcc_top5.append(0.0)

        if (trial + 1) % 5 == 0:
            print(f"  Completed {trial + 1}/20 realizations")

    # Z-scores
    def zscore(real_val, null_vals):
        if len(null_vals) < 2:
            return float("nan")
        mu = np.mean(null_vals)
        sigma = np.std(null_vals, ddof=1)
        if sigma < 1e-12:
            return float("nan")
        return (real_val - mu) / sigma

    z_lambda2 = zscore(lambda2_real, null_lambda2)
    z_ap_frac = zscore(ap_frac_real, null_ap_frac)
    z_gcc_top5 = zscore(gcc_after_top5_real, null_gcc_top5)

    print(f"\nZ-scores (ERCOT vs null):")
    print(f"  Algebraic connectivity: z = {z_lambda2:.3f} (ERCOT={lambda2_real:.6f}, null mean={np.mean(null_lambda2):.6f})")
    print(f"  AP fraction:            z = {z_ap_frac:.3f} (ERCOT={ap_frac_real:.4f}, null mean={np.mean(null_ap_frac):.4f})")
    print(f"  GCC after top-5% removal: z = {z_gcc_top5:.3f} (ERCOT={gcc_after_top5_real:.4f}, null mean={np.mean(null_gcc_top5):.4f})")

    # Plot
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    metrics = [
        (null_lambda2, lambda2_real, "Algebraic connectivity ($\\lambda_2$)", z_lambda2),
        (null_ap_frac, ap_frac_real, "Articulation point fraction", z_ap_frac),
        (null_gcc_top5, gcc_after_top5_real, "GCC after top-5% degree removal", z_gcc_top5),
    ]

    for ax, (null_vals, real_val, title, z) in zip(axes, metrics):
        ax.hist(null_vals, bins=10, color="lightblue", edgecolor="gray", alpha=0.8, label="Null model")
        ax.axvline(x=real_val, color="red", linewidth=2, linestyle="--", label=f"ERCOT (z={z:.2f})")
        ax.set_title(title, fontsize=12)
        ax.set_ylabel("Count")
        ax.legend(fontsize=9)

    fig.suptitle("ERCOT vs Configuration Model Null", fontsize=14, y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "null_model_comparison.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("Saved figures/null_model_comparison.png")

    RESULTS["analysis_3_null_model"] = {
        "ercot_lambda2": round(lambda2_real, 6),
        "ercot_ap_fraction": round(ap_frac_real, 4),
        "ercot_gcc_after_top5_removal": round(gcc_after_top5_real, 4),
        "null_mean_lambda2": round(float(np.mean(null_lambda2)), 6),
        "null_mean_ap_fraction": round(float(np.mean(null_ap_frac)), 4),
        "null_mean_gcc_after_top5_removal": round(float(np.mean(null_gcc_top5)), 4),
        "z_score_lambda2": round(z_lambda2, 3),
        "z_score_ap_fraction": round(z_ap_frac, 3),
        "z_score_gcc_after_top5_removal": round(z_gcc_top5, 3),
        "interpretation_note": (
            "The configuration model rewires edges randomly while preserving the "
            "degree sequence. It contains NO spatial constraint: it will freely "
            "connect Lubbock to Houston. Any geographically embedded network will "
            "therefore look 'fragile' versus this null, because the null cannot "
            "exhibit the long-range weak coupling that makes real grids hard to "
            "route across. Our large negative z-scores (e.g. z = -79 on hub-removal) "
            "quantify ERCOT's spatial embedding cost, NOT an unusual pathology. "
            "They should be read as 'ERCOT is geographic' rather than 'ERCOT is broken.'"
        ),
    }

except Exception as e:
    print(f"NULL MODEL ANALYSIS FAILED: {e}")
    import traceback; traceback.print_exc()
    RESULTS["analysis_3_null_model"] = {"error": str(e)}

# =========================================================================
# ANALYSIS 4: Spectral bottleneck analysis
# =========================================================================
#
# NOTE ON INTERPRETATION: The Fiedler vector defines a single bipartition
# of the graph. It cannot "recover 4 zones" — only one cut. Previous
# versions of this analysis reported "95% zone purity" as a validation of
# ERCOT's zonal structure; that framing was mathematically incoherent
# because any graph bisection over 4 geographically contiguous regions
# will lump 2 zones on each side. What the Fiedler cut actually reveals
# is the *tightest bottleneck* in the network: the partition that minimizes
# the ratio (edges crossing) / (min partition size). We report that
# bottleneck here, including:
#   - which zones fall on each side
#   - number of edges crossing the cut
#   - total MVA rating of those edges = bottleneck transfer capacity
#   - the Cheeger lower bound on conductance: h(G) >= lambda_2 / 2
#
# We drop the Louvain-vs-zone modularity comparison: Louvain found 37
# communities while zones are 4, and modularity is monotonically
# biased toward finer partitions, so Q=0.92 vs Q=0.71 compared nothing.
# =========================================================================
print("\n" + "=" * 70)
print("ANALYSIS 4: Spectral bottleneck analysis")
print("=" * 70)

try:
    lambda2 = lambda2_real
    print(f"Algebraic connectivity (lambda_2): {lambda2:.6f}")

    # Fiedler vector via combinatorial Laplacian (matches lambda2_real)
    t0 = time.time()
    L = nx.laplacian_matrix(G).astype(float)
    eigvals_L, eigvecs_L = eigsh(L, k=2, which="SM")
    sort_idx = np.argsort(eigvals_L)
    fiedler_vec = eigvecs_L[:, sort_idx[1]]
    print(f"Fiedler vector computed ({time.time()-t0:.1f}s)")

    nodes_sorted = sorted(G.nodes())
    fiedler_map = {n: float(fiedler_vec[i]) for i, n in enumerate(nodes_sorted)}

    # Describe the bipartition (not "purity" — just where each zone falls)
    pos_side = [n for n in nodes_sorted if fiedler_map[n] > 0]
    neg_side = [n for n in nodes_sorted if fiedler_map[n] <= 0]
    print(f"\nFiedler bipartition: {len(pos_side)} nodes (+) vs {len(neg_side)} nodes (-)")

    zone_split = {}
    for zone in ["NORTH", "HOUSTON", "SOUTH", "WEST"]:
        zn = [n for n in G.nodes() if G.nodes[n].get("zone") == zone]
        pos = sum(1 for n in zn if fiedler_map[n] > 0)
        zone_split[zone] = {"total": len(zn), "positive_side": pos, "negative_side": len(zn)-pos}
        print(f"  {zone}: {pos}/{len(zn)} on (+) side, {len(zn)-pos} on (-) side")
    pos_dominant_zones = [z for z, d in zone_split.items() if d["positive_side"] > d["negative_side"]]
    neg_dominant_zones = [z for z, d in zone_split.items() if d["positive_side"] <= d["negative_side"]]
    print(f"  Bipartition groups {pos_dominant_zones} vs {neg_dominant_zones}")

    # Bottleneck edges: edges with endpoints on opposite sides of the Fiedler cut
    bottleneck_edges = []
    for u, v, data in G.edges(data=True):
        if fiedler_map[u] * fiedler_map[v] < 0:
            rating = data.get("cont_rating", 0.0)
            if pd.isna(rating):
                rating = 0.0
            bottleneck_edges.append((u, v, float(rating), data.get("uid", f"{u}_{v}")))

    n_cut_edges = len(bottleneck_edges)
    bottleneck_mva = sum(e[2] for e in bottleneck_edges)
    total_mva = sum(float(d.get("cont_rating", 0.0) or 0.0) for _,_,d in G.edges(data=True))
    print(f"\nBottleneck edges (crossing Fiedler cut): {n_cut_edges}")
    print(f"Total MVA rating across bottleneck: {bottleneck_mva:.0f} MVA")
    print(f"Fraction of grid MVA at the bottleneck: {100*bottleneck_mva/total_mva:.2f}%")

    # Conductance of the Fiedler cut (actual, not just the bound)
    # phi = cut_size / min(vol(S), vol(S_c)) where vol = sum of degrees
    deg = dict(G.degree())
    vol_pos = sum(deg[n] for n in pos_side)
    vol_neg = sum(deg[n] for n in neg_side)
    phi_fiedler = n_cut_edges / min(vol_pos, vol_neg)
    cheeger_lower = lambda2 / 2
    # Upper bound: h(G) <= sqrt(2 * d_max * lambda_2)
    d_max = max(deg.values())
    cheeger_upper = math.sqrt(2 * d_max * lambda2)
    print(f"Conductance of Fiedler cut: phi = {phi_fiedler:.6f}")
    print(f"Cheeger bounds: {cheeger_lower:.6f} <= h(G) <= {cheeger_upper:.6f}")

    # Spectral figure: spatial map + Fiedler value histogram
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    # Left: histogram of Fiedler values by zone (kept for descriptive value)
    ax = axes[0]
    zone_colors = {"NORTH": "#1f77b4", "HOUSTON": "#d62728", "SOUTH": "#2ca02c", "WEST": "#ff7f0e"}
    for zone in ["NORTH", "HOUSTON", "SOUTH", "WEST"]:
        zn = [n for n in nodes_sorted if G.nodes[n].get("zone") == zone]
        vals = [fiedler_map[n] for n in zn]
        ax.hist(vals, bins=40, alpha=0.55, label=zone, color=zone_colors[zone])
    ax.axvline(x=0, color="black", linestyle="--", alpha=0.7, label="Fiedler cut")
    ax.set_xlabel("Fiedler vector value", fontsize=12)
    ax.set_ylabel("Node count", fontsize=12)
    ax.set_title("Fiedler Value Distribution by Zone\n(descriptive; cut is 2-way, not 4-way)", fontsize=12)
    ax.legend(fontsize=10)
    # Right: spatial map with bottleneck edges highlighted
    ax = axes[1]
    xs = [G.nodes[n].get("lng", 0) for n in nodes_sorted]
    ys = [G.nodes[n].get("lat", 0) for n in nodes_sorted]
    side_color = ["#d62728" if fiedler_map[n] > 0 else "#1f77b4" for n in nodes_sorted]
    ax.scatter(xs, ys, c=side_color, s=4, alpha=0.5, zorder=2)
    # Overlay bottleneck edges
    for u, v, rating, uid in bottleneck_edges:
        ax.plot([G.nodes[u]["lng"], G.nodes[v]["lng"]],
                [G.nodes[u]["lat"], G.nodes[v]["lat"]],
                color="black", linewidth=0.8, alpha=0.9, zorder=3)
    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    ax.set_title(f"Fiedler Bipartition + Bottleneck Edges\n({n_cut_edges} edges, {bottleneck_mva:.0f} MVA)", fontsize=12)
    fig.suptitle(f"Spectral Bottleneck (lambda_2 = {lambda2:.5f}, conductance = {phi_fiedler:.4f})",
                 fontsize=14, y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "spectral_analysis.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("Saved figures/spectral_analysis.png")

    RESULTS["analysis_4_spectral"] = {
        "algebraic_connectivity_lambda2": round(lambda2, 6),
        "bipartition_sizes": {"positive_side": len(pos_side), "negative_side": len(neg_side)},
        "fiedler_bipartition_zone_split": zone_split,
        "fiedler_bipartition_groups": {
            "positive_side_dominant_zones": pos_dominant_zones,
            "negative_side_dominant_zones": neg_dominant_zones,
        },
        "bottleneck_n_edges": n_cut_edges,
        "bottleneck_total_mva": round(bottleneck_mva, 1),
        "bottleneck_fraction_of_grid_mva": round(bottleneck_mva/total_mva, 4),
        "fiedler_cut_conductance": round(phi_fiedler, 6),
        "cheeger_lower_bound": round(cheeger_lower, 6),
        "cheeger_upper_bound": round(cheeger_upper, 6),
        "interpretation_note": "The Fiedler vector produces one bipartition, not a 4-way clustering. We report which zones fall on each side of that single cut and the MVA capacity crossing it. We dropped the Louvain-vs-zone modularity comparison because Louvain's 37 communities vs the zones' 4 made Q comparison apples-to-oranges.",
    }

except Exception as e:
    print(f"SPECTRAL ANALYSIS FAILED: {e}")
    import traceback; traceback.print_exc()
    RESULTS["analysis_4_spectral"] = {"error": str(e)}

# =========================================================================
# ANALYSIS 5: Link prediction -> upgrade ranking
# =========================================================================
print("\n" + "=" * 70)
print("ANALYSIS 5: Link prediction / upgrade ranking")
print("=" * 70)

try:
    # Find articulation points with MW Load > 0 (real load, not split)
    aps = set(nx.articulation_points(G))
    ap_load_nodes = [n for n in aps if G.nodes[n].get("mw_load", 0) > 0
                     and not G.nodes[n].get("is_split", False)]
    print(f"Articulation points with load: {len(ap_load_nodes)}")

    # For each AP, compute MW at risk (load in the smaller component if removed)
    ap_risk = []
    for ap_node in ap_load_nodes:
        H = G.copy()
        H.remove_node(ap_node)
        comps = list(nx.connected_components(H))
        if len(comps) <= 1:
            # Still connected somehow (multi-edges?)
            continue
        # Find which component has slack (or largest component as "surviving")
        largest_comp = max(comps, key=len)
        # MW at risk = load in all non-largest components + load on the AP itself
        mw_at_risk = G.nodes[ap_node].get("mw_load", 0)
        for comp in comps:
            if comp is not largest_comp:
                mw_at_risk += sum(G.nodes[n].get("mw_load", 0) for n in comp)
        ap_risk.append((ap_node, mw_at_risk))

    # Sort by MW at risk, take top 20
    ap_risk.sort(key=lambda x: -x[1])
    top20_aps = ap_risk[:20]
    print(f"Top 20 APs by MW at risk (max = {top20_aps[0][1]:.1f} MW)")

    # For each AP, find the nearest non-adjacent substation that would demote
    # it from AP status. Strategy: find nodes in *different* biconnected components
    # incident to this AP, then connect the two sides to create a bypass.
    upgrade_candidates = []

    # Pre-compute biconnected components
    bcc_list = list(nx.biconnected_components(G))
    # Map each AP to the biconnected components it belongs to
    ap_to_bccs = defaultdict(list)
    for i, bcc in enumerate(bcc_list):
        for n in bcc:
            if n in aps:
                ap_to_bccs[n].append(i)

    for ap_node, mw_at_risk in top20_aps:
        ap_lat = G.nodes[ap_node].get("lat")
        ap_lng = G.nodes[ap_node].get("lng")
        if pd.isna(ap_lat) or pd.isna(ap_lng):
            continue

        neighbors = set(G.neighbors(ap_node))
        my_bccs = ap_to_bccs.get(ap_node, [])

        if len(my_bccs) < 2:
            continue

        # Get nodes in the smaller biconnected components (the "at risk" sides)
        # and nodes in the larger side. A new edge bridging two different BCCs
        # of this AP removes AP status.
        bcc_sizes = [(idx, len(bcc_list[idx])) for idx in my_bccs]
        bcc_sizes.sort(key=lambda x: -x[1])

        # Nodes in the largest BCC (the "safe" side)
        large_bcc_nodes = bcc_list[bcc_sizes[0][0]] - {ap_node}
        # Nodes in all other BCCs (the "at risk" sides)
        small_bcc_nodes = set()
        for idx, sz in bcc_sizes[1:]:
            small_bcc_nodes |= (bcc_list[idx] - {ap_node})

        # Find the nearest pair (one from each side) to build a bypass line
        best_candidate_from = None
        best_candidate_to = None
        best_dist = float("inf")

        # Build sorted candidate list from small side
        small_with_coords = []
        for n in small_bcc_nodes:
            nlat = G.nodes[n].get("lat")
            nlng = G.nodes[n].get("lng")
            if pd.notna(nlat) and pd.notna(nlng):
                small_with_coords.append((n, nlat, nlng))

        large_with_coords = []
        for n in large_bcc_nodes:
            nlat = G.nodes[n].get("lat")
            nlng = G.nodes[n].get("lng")
            if pd.notna(nlat) and pd.notna(nlng):
                large_with_coords.append((n, nlat, nlng))

        # Find closest pair between the two sides
        for sn, slat, slng in small_with_coords:
            for ln, llat, llng in large_with_coords:
                if G.has_edge(sn, ln):
                    continue
                d = haversine_km(slat, slng, llat, llng)
                if d < best_dist:
                    best_dist = d
                    best_candidate_from = sn
                    best_candidate_to = ln

        if best_candidate_from is not None and best_dist < 500:
            efficiency = mw_at_risk / best_dist if best_dist > 0 else 0
            def _bus_name(bid):
                rows = bus_df.loc[bus_df["Bus ID"] == bid, "Bus Name"]
                return rows.values[0] if len(rows) > 0 else str(bid)

            upgrade_candidates.append({
                "ap_bus": int(ap_node),
                "ap_name": _bus_name(ap_node),
                "from_bus": int(best_candidate_from),
                "from_name": _bus_name(best_candidate_from),
                "to_bus": int(best_candidate_to),
                "to_name": _bus_name(best_candidate_to),
                "distance_km": round(best_dist, 2),
                "mw_saved": round(mw_at_risk, 2),
                "efficiency_mw_per_km": round(efficiency, 2),
            })

    # Sort by efficiency
    upgrade_candidates.sort(key=lambda x: -x["efficiency_mw_per_km"])
    top10_upgrades = upgrade_candidates[:10]

    print(f"\nFound {len(upgrade_candidates)} upgrade candidates")
    print("\nTop 10 upgrade candidates by efficiency (MW/km):")
    for i, uc in enumerate(top10_upgrades):
        print(f"  {i+1}. AP={uc['ap_name'][:30]}, line: {uc['from_name'][:20]} -> {uc['to_name'][:20]}: "
              f"{uc['efficiency_mw_per_km']:.1f} MW/km "
              f"({uc['mw_saved']:.0f} MW saved, {uc['distance_km']:.1f} km)")

    # Plot
    fig, ax = plt.subplots(figsize=(12, 6))
    if top10_upgrades:
        names = [f"{uc['ap_name'][:25]}" for uc in top10_upgrades]
        efficiencies = [uc["efficiency_mw_per_km"] for uc in top10_upgrades]
        bars = ax.barh(range(len(names)), efficiencies, color="steelblue", edgecolor="white")
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=10)
        ax.invert_yaxis()
        ax.set_xlabel("Efficiency (MW saved / km new line)", fontsize=13)
        ax.set_title("Top 10 Grid Upgrade Candidates by Efficiency", fontsize=14)

        for i, uc in enumerate(top10_upgrades):
            ax.text(efficiencies[i] + max(efficiencies) * 0.02, i,
                    f"{uc['mw_saved']:.0f} MW, {uc['distance_km']:.1f} km",
                    va="center", fontsize=9)
    else:
        ax.text(0.5, 0.5, "No upgrade candidates found\n(all APs require long bypass lines)",
                ha="center", va="center", fontsize=14, transform=ax.transAxes)
        ax.set_title("Top 10 Grid Upgrade Candidates by Efficiency", fontsize=14)

    fig.tight_layout()
    fig.savefig(FIG_DIR / "upgrade_ranking.png", dpi=200)
    plt.close(fig)
    print("Saved figures/upgrade_ranking.png")

    RESULTS["analysis_5_upgrade_ranking"] = {
        "total_articulation_points_with_load": len(ap_load_nodes),
        "top_10_upgrades": top10_upgrades,
    }

except Exception as e:
    print(f"UPGRADE ANALYSIS FAILED: {e}")
    import traceback; traceback.print_exc()
    RESULTS["analysis_5_upgrade_ranking"] = {"error": str(e)}

# =========================================================================
# Save all results
# =========================================================================
print("\n" + "=" * 70)
print("Saving results to network_analysis_results.json")
print("=" * 70)

# Add graph summary
RESULTS["graph_summary"] = {
    "n_buses": int(bus_df.shape[0]),
    "n_branches": int(branch_df.shape[0]),
    "n_nodes_gcc": int(n_orig),
    "n_edges_gcc": int(G.number_of_edges()),
    "n_connected_components": len(components),
    "total_computed_load_mw": round(total_load, 1),
    "zones": list(ZONE_LOAD_MW.keys()),
    "zone_load_mw": ZONE_LOAD_MW,
}

# JSON serialization helper
def json_safe(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

with open(BASE_DIR / "network_analysis_results.json", "w") as f:
    json.dump(RESULTS, f, indent=2, default=json_safe)

print("Done! All results saved.")
print(f"\nFiles created:")
print(f"  {BASE_DIR / 'network_analysis_results.json'}")
print(f"  {BASE_DIR / 'cascade_results.csv'}")
for fig_file in sorted(FIG_DIR.glob("*.png")):
    print(f"  {fig_file}")
