"""
Dartboard Code - Converted from Colab Notebook
Original: dartboard_code_v1.ipynb

This script performs synthetic grid topology generation following the Birchfield methodology.
"""

import os
import pandas as pd
import numpy as np
import requests
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import pdfplumber
import geopandas as gpd
from shapely.geometry import Point
from sklearn.cluster import AgglomerativeClustering
from scipy.spatial import Delaunay, cKDTree
import networkx as nx

# ======================================================================
# Configuration - Local File Paths
# ======================================================================

# Input data paths (relative to script location)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_PATH = os.path.join(SCRIPT_DIR, "GoldBook.pdf")
GAZ_PATH = os.path.join(SCRIPT_DIR, "2020_Gaz_zcta_national 2 (1).txt")
EIA_DIR = os.path.join(SCRIPT_DIR, "eia8602023")

# Output directory
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ======================================================================
# Utility Functions
# ======================================================================

def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great-circle distance between two points on Earth (in miles).
    """
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    r = 3956  # Earth radius in miles
    return c * r


# ======================================================================
# Gold Book Extraction Functions
# ======================================================================

def extract_gold_book_generators(pdf_path):
    """Extract generator data from NY Gold Book PDF."""
    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(83, 103):
            page = pdf.pages[i]
            table = page.extract_table()
            if table:
                start_row = 1 if i == 83 else 2
                all_rows.extend(table[start_row:])
    
    columns = ["Owner", "Station_Unit", "Zone", "PTID", "Town", "County", "State",
               "In_Service", "Nameplate_MW", "CRIS_MW", "Summer_MW", "Winter_MW",
               "Dual_Fuel", "Unit_Type", "Fuel_1", "Fuel_2", "2023_Net_Energy", "Notes"]
    df = pd.DataFrame(all_rows, columns=columns)
    return df


def extract_gold_book_full(pdf_path, output_path):
    """Full Gold Book extraction with dynamic column handling."""
    if not os.path.exists(pdf_path):
        print(f"ERROR: The file was not found at: {pdf_path}")
        return None
    
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 4,
    }

    all_data = []
    valid_zones = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"]

    print("Starting Gold Book extraction...")

    with pdfplumber.open(pdf_path) as pdf:
        for i in range(83, 105):
            page = pdf.pages[i]
            table = page.extract_table(table_settings)
            if table:
                for row in table:
                    if len(row) > 3 and row[2] in valid_zones:
                        clean_row = [str(cell).replace("\n", " ") if cell else "" for cell in row]
                        all_data.append(clean_row)
            if i % 5 == 0:
                print(f"Processed page index {i}...")

    if not all_data:
        print("Error: No data found.")
        return None
    
    max_cols = max(len(row) for row in all_data)
    print(f"Max columns found: {max_cols}")

    headers = [
        "Owner", "Station_Unit", "Zone", "PTID", "Town", "County", "State",
        "In_Service", "Nameplate_MW", "CRIS_MW", "Summer_MW", "Winter_MW",
        "Dual_Fuel", "Unit_Type", "Fuel_1", "Fuel_2", "Net_Energy_GWh", "Notes"
    ]

    if max_cols > len(headers):
        for i in range(len(headers), max_cols):
            headers.append(f"Extra_Col_{i}")

    padded_data = [row + [""] * (max_cols - len(row)) for row in all_data]
    df_full = pd.DataFrame(padded_data, columns=headers)

    cols_to_numeric = ["Nameplate_MW", "Summer_MW", "Winter_MW", "Net_Energy_GWh"]
    for col in cols_to_numeric:
        if col in df_full.columns:
            df_full[col] = pd.to_numeric(df_full[col].str.replace(",", ""), errors="coerce")

    df_full.to_csv(output_path, index=False)
    print(f"Success! Saved {len(df_full)} rows.")
    return df_full


# ======================================================================
# Census Data Functions
# ======================================================================

def load_gazetteer(gaz_path):
    """Load and clean the Census Gazetteer file."""
    df_gaz = pd.read_csv(gaz_path, sep="\t")
    df_gaz.columns = df_gaz.columns.str.strip()
    df_gaz["GEOID"] = df_gaz["GEOID"].astype(str).str.zfill(5)
    return df_gaz


def fetch_census_population():
    """Fetch population data from Census ACS API."""
    print("Fetching population data from Census ACS API...")
    url = "https://api.census.gov/data/2020/acs/acs5?get=B01003_001E&for=zip%20code%20tabulation%20area:*"
    
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f"Census API request failed: {response.status_code}")
    
    data = response.json()
    df_pop = pd.DataFrame(data[1:], columns=data[0])
    df_pop = df_pop.rename(columns={"B01003_001E": "POPULATION", "zip code tabulation area": "GEOID"})
    return df_pop


def create_ny_load_nodes(gaz_path, output_path):
    """Create NY load nodes from Census data."""
    df_gaz = load_gazetteer(gaz_path)
    ny_gaz = df_gaz[df_gaz["GEOID"].str.startswith(("10", "11", "12", "13", "14"))].copy()
    
    df_pop = fetch_census_population()
    ny_final = pd.merge(ny_gaz, df_pop[["GEOID", "POPULATION"]], on="GEOID", how="inner")
    
    ny_final["POPULATION"] = pd.to_numeric(ny_final["POPULATION"])
    ny_final = ny_final[["GEOID", "INTPTLAT", "INTPTLONG", "POPULATION"]]
    ny_final.columns = ["ZCTA", "LAT", "LON", "POP"]
    ny_final["LOAD_MW"] = ny_final["POP"] * 0.002
    
    print(f"Success! Created {len(ny_final)} NY nodes.")
    ny_final.to_csv(output_path, index=False)
    return ny_final


def create_tx_load_nodes(gaz_path, output_path):
    """Create Texas load nodes from Census data."""
    df_gaz = load_gazetteer(gaz_path)
    tx_prefixes = ("73", "75", "76", "77", "78", "79")
    tx_gaz = df_gaz[df_gaz["GEOID"].str.startswith(tx_prefixes)].copy()
    
    print("Fetching Texas population data...")
    df_pop = fetch_census_population()
    
    tx_final = pd.merge(tx_gaz, df_pop[["GEOID", "POPULATION"]], on="GEOID", how="inner")
    tx_final["POPULATION"] = pd.to_numeric(tx_final["POPULATION"])
    tx_final["LOAD_MW"] = tx_final["POPULATION"] * 0.002
    
    print(f"Success! Created {len(tx_final)} Texas nodes.")
    tx_final.to_csv(output_path, index=False)
    return tx_final


def clip_tx_to_boundary(tx_file_path):
    """Clip Texas nodes to actual state boundary."""
    df_tx = pd.read_csv(tx_file_path)
    original_count = len(df_tx)
    
    print("Downloading official Texas boundary...")
    url = "https://www2.census.gov/geo/tiger/GENZ2018/shp/cb_2018_us_state_5m.zip"
    states = gpd.read_file(url)
    tx_poly = states[states["STUSPS"] == "TX"].geometry.values[0]
    
    geometry = [Point(xy) for xy in zip(df_tx["INTPTLONG"], df_tx["INTPTLAT"])]
    gdf_tx = gpd.GeoDataFrame(df_tx, geometry=geometry)
    
    mask = gdf_tx.within(tx_poly)
    df_tx = df_tx.loc[mask].copy()
    
    print(f"Removed {original_count - len(df_tx)} artifacts.")
    df_tx.to_csv(tx_file_path, index=False)
    return df_tx


def plot_ny_nodes(file_path):
    """Plot NY load nodes."""
    df = pd.read_csv(file_path)
    plt.figure(figsize=(12, 10))
    scatter = plt.scatter(df["LON"], df["LAT"], c=df["POP"], cmap="viridis", s=15, alpha=0.7,
                          norm=colors.LogNorm(vmin=df["POP"].min()+1, vmax=df["POP"].max()))
    plt.colorbar(scatter).set_label("Population (Log Scale)")
    plt.title("NY Synthetic Load Nodes")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.xlim([-80, -71.5])
    plt.ylim([40, 45.5])
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.savefig(os.path.join(OUTPUT_DIR, "ny_load_nodes.png"), dpi=150, bbox_inches="tight")
    plt.close()


def plot_tx_nodes(file_path):
    """Plot Texas load nodes."""
    df_tx = pd.read_csv(file_path)
    plt.figure(figsize=(12, 10))
    scatter = plt.scatter(df_tx["INTPTLONG"], df_tx["INTPTLAT"], c=df_tx["POPULATION"],
                          cmap="magma", s=12, alpha=0.6,
                          norm=colors.LogNorm(vmin=1, vmax=df_tx["POPULATION"].max()))
    plt.colorbar(scatter).set_label("Population (Log Scale)")
    plt.title(f"Texas Synthetic Load Nodes (n={len(df_tx)})")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.xlim([-107, -93])
    plt.ylim([25.5, 37])
    plt.grid(True, linestyle=":", alpha=0.4)
    plt.savefig(os.path.join(OUTPUT_DIR, "tx_load_nodes.png"), dpi=150, bbox_inches="tight")
    plt.close()


# ======================================================================
# Clustering Functions
# ======================================================================

def birchfield_cluster(state_name, input_file, n_substations, output_dir):
    """Cluster ZCTAs into substations using agglomerative clustering."""
    print(f"Clustering {state_name} into {n_substations} substations...")

    df = pd.read_csv(input_file)
    rename_map = {"INTPTLAT": "LAT", "INTPTLONG": "LON", "POPULATION": "POP"}
    df = df.rename(columns=rename_map)

    if "LAT" not in df.columns or "LON" not in df.columns:
        raise ValueError(f"Missing coordinate columns. Found: {df.columns.tolist()}")

    coords = df[["LAT", "LON"]].values
    cluster_model = AgglomerativeClustering(n_clusters=n_substations, linkage="ward")
    df["cluster_id"] = cluster_model.fit_predict(coords)

    def get_substation_data(group):
        total_pop = group["POP"].sum()
        if total_pop == 0:
            w_lat = group["LAT"].mean()
            w_lon = group["LON"].mean()
        else:
            w_lat = np.average(group["LAT"], weights=group["POP"])
            w_lon = np.average(group["LON"], weights=group["POP"])
        return pd.Series({"SUB_LAT": w_lat, "SUB_LON": w_lon, "TOTAL_POP": total_pop, "LOAD_MW": total_pop * 0.002})

    substations = df.groupby("cluster_id").apply(get_substation_data).reset_index()
    output_path = os.path.join(output_dir, f"{state_name}_Substations.csv")
    substations.to_csv(output_path, index=False)
    print(f"Saved substations to {output_path}")
    return substations


# ======================================================================
# Topology Functions
# ======================================================================

def generate_initial_topology(state_name, file_path):
    """Generate initial Delaunay triangulation topology."""
    print(f"Generating initial triangulation for {state_name}...")
    df = pd.read_csv(file_path)
    points = df[["SUB_LON", "SUB_LAT"]].values
    tri = Delaunay(points)

    edges = set()
    for simplex in tri.simplices:
        for i in range(3):
            edge = tuple(sorted((simplex[i], simplex[(i+1)%3])))
            edges.add(edge)

    n, m = len(points), len(edges)
    print(f"{state_name} Stats: Nodes={n}, Lines={m}, Ratio={m/n:.2f}")
    return points, tri, edges


def birchfield_prune_v2(state_name, points, edges, target_ratio=1.22):
    """Prune topology with MST connectivity guarantee."""
    print(f"Pruning {state_name} with Connectivity Guard...")

    G_full = nx.Graph()
    for i in range(len(points)):
        G_full.add_node(i, pos=(points[i,0], points[i,1]))

    for u, v in edges:
        dist = haversine(points[u,0], points[u,1], points[v,0], points[v,1])
        G_full.add_edge(u, v, weight=dist)

    mst = nx.minimum_spanning_tree(G_full, weight="weight")
    mst_edges = set(mst.edges())
    prunable_edges = list(set(G_full.edges()) - mst_edges)
    prunable_edges = sorted(prunable_edges, key=lambda x: G_full[x[0]][x[1]]["weight"], reverse=True)

    G_final = G_full.copy()
    for u, v in prunable_edges:
        if G_final.number_of_edges() / G_final.number_of_nodes() <= target_ratio:
            break
        G_final.remove_edge(u, v)

    print(f"{state_name} Result: Connected={nx.is_connected(G_final)}, Ratio={G_final.number_of_edges()/G_final.number_of_nodes():.2f}")
    return G_final


# ======================================================================
# EIA Generator Functions
# ======================================================================

def load_eia_data(eia_dir):
    """Load EIA 860 generator and plant data."""
    print("Loading EIA Data...")
    
    plant_file = os.path.join(eia_dir, "2___Plant_Y2023.xlsx")
    gen_file = os.path.join(eia_dir, "3_1_Generator_Y2023.xlsx")
    
    print(f"Reading {plant_file}...")
    df_plants_raw = pd.read_excel(plant_file, skiprows=1)
    df_plants_raw.columns = df_plants_raw.columns.str.strip().str.lower()
    
    p_cols = {}
    for c in df_plants_raw.columns:
        if "plant code" in c: p_cols[c] = "Plant Code"
        elif "state" in c and "guidelines" not in c: p_cols[c] = "State"
        elif "latitude" in c: p_cols[c] = "Latitude"
        elif "longitude" in c: p_cols[c] = "Longitude"
        elif "voltage" in c and "kv" in c: p_cols[c] = "Grid Voltage (kV)"
    
    df_plants = df_plants_raw.rename(columns=p_cols)
    df_plants = df_plants.loc[:, ~df_plants.columns.duplicated()]
    target_cols = ["Plant Code", "State", "Latitude", "Longitude", "Grid Voltage (kV)"]
    valid_cols = [c for c in target_cols if c in df_plants.columns]
    df_plants = df_plants[valid_cols]
    
    print(f"Reading {gen_file}...")
    df_gens_raw = pd.read_excel(gen_file, skiprows=1)
    df_gens_raw.columns = df_gens_raw.columns.str.strip().str.lower()
    
    g_cols = {}
    for c in df_gens_raw.columns:
        if "plant code" in c: g_cols[c] = "Plant Code"
        elif "nameplate" in c and "mw" in c: g_cols[c] = "Nameplate Capacity (MW)"
        elif "status" in c: g_cols[c] = "Status"
    
    df_gens = df_gens_raw.rename(columns=g_cols)
    df_gens = df_gens.loc[:, ~df_gens.columns.duplicated()]
    valid_g_cols = [c for c in ["Plant Code", "Nameplate Capacity (MW)", "Status"] if c in df_gens.columns]
    df_gens = df_gens[valid_g_cols]
    
    df_plants = df_plants.drop_duplicates(subset=["Plant Code"])
    df_all_gens = pd.merge(df_gens, df_plants, on="Plant Code", how="left")
    df_all_gens = df_all_gens[df_all_gens["Status"] == "OP"].copy()
    
    if "Grid Voltage (kV)" not in df_all_gens.columns:
        df_all_gens["Grid Voltage (kV)"] = 115
    else:
        df_all_gens["Grid Voltage (kV)"] = df_all_gens["Grid Voltage (kV)"].fillna(115)
    
    print(f"Success! Loaded {len(df_all_gens)} operating generators.")
    return df_all_gens


def add_generation_to_topology(state_code, G_backbone, subs_df, df_all_gens, capture_miles=7):
    """Add generation nodes to the topology."""
    print(f"Integrating Generation for {state_code}...")

    state_gens = df_all_gens[df_all_gens["State"] == state_code].copy()
    if state_gens.empty:
        print(f"Warning: No generators found for {state_code}!")
        return G_backbone

    sub_coords = subs_df[["SUB_LON", "SUB_LAT"]].values
    tree = cKDTree(sub_coords)
    state_gens = state_gens.dropna(subset=["Latitude", "Longitude"])

    gen_coords = state_gens[["Longitude", "Latitude"]].values
    dists, indices = tree.query(gen_coords)

    state_gens["nearest_sub_idx"] = indices
    state_gens["dist_miles"] = dists * 69

    captured = state_gens[state_gens["dist_miles"] <= capture_miles]
    remote = state_gens[state_gens["dist_miles"] > capture_miles]

    for idx, row in captured.iterrows():
        sub_id = int(row["nearest_sub_idx"])
        if "gen_mw" not in G_backbone.nodes[sub_id]:
            G_backbone.nodes[sub_id]["gen_mw"] = 0.0
            G_backbone.nodes[sub_id]["type"] = "l"
        G_backbone.nodes[sub_id]["gen_mw"] += row["Nameplate Capacity (MW)"]
        G_backbone.nodes[sub_id]["type"] = "b"

    start_id = max(G_backbone.nodes()) + 1
    for i, (idx, row) in enumerate(remote.iterrows()):
        new_node_id = start_id + i
        G_backbone.add_node(new_node_id, pos=(row["Longitude"], row["Latitude"]),
                            type="g", gen_mw=row["Nameplate Capacity (MW)"],
                            voltage=row["Grid Voltage (kV)"])
        target_sub = int(row["nearest_sub_idx"])
        G_backbone.add_edge(new_node_id, target_sub, type="spur", weight=row["dist_miles"])

    print(f"  - Captured: {len(captured)}, Remote: {len(remote)} (new spurs)")
    return G_backbone


def remove_outliers(G, lat_min, lat_max, lon_min, lon_max):
    """Remove nodes outside the bounding box."""
    nodes_to_remove = []
    for node, data in G.nodes(data=True):
        lon, lat = data["pos"]
        if not (lat_min <= lat <= lat_max) or not (lon_min <= lon <= lon_max):
            nodes_to_remove.append(node)
    if nodes_to_remove:
        print(f"Removing {len(nodes_to_remove)} outlier nodes...")
        G.remove_nodes_from(nodes_to_remove)
    return G


# ======================================================================
# Voltage Assignment Functions
# ======================================================================

def birchfield_voltage_refinement(G, state_name, load_percentile=0.85):
    """Assign voltages based on generation and load centers."""
    print(f"Refining Voltage for {state_name}...")

    gen_nodes = [n for n, d in G.nodes(data=True) if d.get("gen_mw", 0) > 0]
    loads = [d.get("LOAD_MW", 0) for n, d in G.nodes(data=True) if "LOAD_MW" in d]
    load_threshold = np.percentile(loads, load_percentile * 100) if loads else 0
    load_nodes = [n for n, d in G.nodes(data=True) if d.get("LOAD_MW", 0) >= load_threshold]

    seeds = set(gen_nodes + load_nodes)
    print(f"  - Seeds: {len(gen_nodes)} (Gen), {len(load_nodes)} (Load)")

    for n in G.nodes():
        G.nodes[n]["kv"] = 345 if n in seeds else 115

    hv_count = 0
    for u, v in G.edges():
        if G.nodes[u]["kv"] == 345 and G.nodes[v]["kv"] == 345:
            G.edges[u, v]["edge_type"] = "HV"
            hv_count += 1
        else:
            G.edges[u, v]["edge_type"] = "LV"

    print(f"  - Result: {hv_count} HV lines created.")
    return G


def connect_high_voltage_backbone(G, state_name):
    """Ensure the high voltage backbone is connected."""
    print(f"Building Connected Backbone for {state_name}...")

    while True:
        hv_nodes = [n for n, d in G.nodes(data=True) if d.get("kv") == 345]
        if not hv_nodes:
            print("  - No HV nodes found.")
            return G

        H = G.subgraph(hv_nodes)
        components = list(nx.connected_components(H))
        components.sort(key=len, reverse=True)

        print(f"  - Found {len(components)} HV clusters.")
        if len(components) <= 1:
            print("  - Backbone is connected!")
            break

        main_comp, isolated_comp = components[0], components[1]
        best_path, min_dist = [], float("inf")

        for u in list(main_comp)[:20]:
            for v in list(isolated_comp)[:20]:
                try:
                    dist = nx.shortest_path_length(G, u, v, weight="weight")
                    if dist < min_dist:
                        min_dist = dist
                        best_path = nx.shortest_path(G, u, v, weight="weight")
                except nx.NetworkXNoPath:
                    continue

        if not best_path:
            print("  - Warning: Could not find path between clusters.")
            break

        print(f"  - Bridging clusters via {len(best_path)} nodes.")
        for n in best_path:
            G.nodes[n]["kv"] = 345
        for i in range(len(best_path) - 1):
            u, v = best_path[i], best_path[i+1]
            if G.has_edge(u, v):
                G.edges[u, v]["edge_type"] = "HV"

    return G


# ======================================================================
# RNG Functions
# ======================================================================

def load_and_standardize(path):
    """Load and standardize column names."""
    df = pd.read_csv(path)
    cols = df.columns
    rename_map = {}
    if "LAT" in cols: rename_map["LAT"] = "SUB_LAT"
    elif "INTPTLAT" in cols: rename_map["INTPTLAT"] = "SUB_LAT"
    if "LON" in cols: rename_map["LON"] = "SUB_LON"
    elif "INTPTLONG" in cols: rename_map["INTPTLONG"] = "SUB_LON"
    if "POP" in cols: rename_map["POP"] = "POPULATION"
    df = df.rename(columns=rename_map)
    if "SUB_LAT" not in df.columns or "SUB_LON" not in df.columns:
        raise ValueError(f"Could not find coordinate columns. Found: {df.columns.tolist()}")
    return df


def relative_neighborhood_filter(G_delaunay):
    """Apply RNG filter to Delaunay edges."""
    print(f"  - Filtering {G_delaunay.number_of_edges()} edges (RNG)...")
    edges_to_remove = []
    nodes = list(G_delaunay.nodes(data=True))
    coords = {n: np.array(data["pos"]) for n, data in nodes}
    check_nodes = nodes[::2]

    for u, v in G_delaunay.edges():
        pu, pv = coords[u], coords[v]
        d_uv = np.linalg.norm(pu - pv)
        is_rng = True
        for w, _ in check_nodes:
            if w == u or w == v: continue
            pw = coords[w]
            if np.linalg.norm(pu - pw) < d_uv and np.linalg.norm(pv - pw) < d_uv:
                is_rng = False
                break
        if not is_rng:
            edges_to_remove.append((u, v))

    G_rng = G_delaunay.copy()
    G_rng.remove_edges_from(edges_to_remove)
    print(f"  - Removed {len(edges_to_remove)} edges. Remaining: {G_rng.number_of_edges()}")
    return G_rng


def build_birchfield_topology(df_nodes, state_name):
    """Build topology using Delaunay + RNG filtering."""
    print(f"Building Topology for {state_name}...")
    points = df_nodes[["SUB_LON", "SUB_LAT"]].values
    tri = Delaunay(points)

    G = nx.Graph()
    for idx, row in df_nodes.iterrows():
        G.add_node(idx, pos=(row["SUB_LON"], row["SUB_LAT"]),
                   POPULATION=row.get("POPULATION", 0), type="l")

    for simplex in tri.simplices:
        G.add_edge(simplex[0], simplex[1])
        G.add_edge(simplex[1], simplex[2])
        G.add_edge(simplex[0], simplex[2])

    for u, v in G.edges():
        p1, p2 = np.array(G.nodes[u]["pos"]), np.array(G.nodes[v]["pos"])
        G.edges[u, v]["weight"] = np.linalg.norm(p1 - p2) * 69

    print(f"  - Initial Mesh: {G.number_of_edges()} edges.")
    return relative_neighborhood_filter(G)


# ======================================================================
# Visualization Functions
# ======================================================================

def plot_substations(ny_subs, tx_subs, output_dir):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 8))
    ax1.scatter(ny_subs["SUB_LON"], ny_subs["SUB_LAT"], s=ny_subs["LOAD_MW"]*0.5, alpha=0.5, c="blue")
    ax1.set_title("NY Synthetic Substations (n=600)")
    ax2.scatter(tx_subs["SUB_LON"], tx_subs["SUB_LAT"], s=tx_subs["LOAD_MW"]*0.5, alpha=0.5, c="red")
    ax2.set_title("TX Synthetic Substations (n=1250)")
    plt.savefig(os.path.join(output_dir, "substations.png"), dpi=150, bbox_inches="tight")
    plt.close()


def plot_backbone(G_ny, G_tx, output_dir):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(22, 10))
    pos_ny = nx.get_node_attributes(G_ny, "pos")
    nx.draw_networkx_nodes(G_ny, pos_ny, ax=ax1, node_size=5, node_color="navy", alpha=0.7)
    nx.draw_networkx_edges(G_ny, pos_ny, ax=ax1, edge_color="royalblue", width=0.8, alpha=0.5)
    ax1.set_title("NY Synthetic Backbone")
    ax1.set_axis_off()

    pos_tx = nx.get_node_attributes(G_tx, "pos")
    nx.draw_networkx_nodes(G_tx, pos_tx, ax=ax2, node_size=5, node_color="darkred", alpha=0.7)
    nx.draw_networkx_edges(G_tx, pos_tx, ax=ax2, edge_color="indianred", width=0.8, alpha=0.5)
    ax2.set_title("TX Synthetic Backbone")
    ax2.set_axis_off()
    plt.savefig(os.path.join(output_dir, "backbone.png"), dpi=150, bbox_inches="tight")
    plt.close()


def plot_voltage_maps(ny_G, tx_G, output_dir):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(22, 10))
    for G, ax, title in [(ny_G, ax1, "NY Grid"), (tx_G, ax2, "TX Grid")]:
        pos = nx.get_node_attributes(G, "pos")
        lv_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("edge_type") != "HV"]
        hv_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("edge_type") == "HV"]
        hv_nodes = [n for n, d in G.nodes(data=True) if d.get("kv") == 345]
        nx.draw_networkx_edges(G, pos, edgelist=lv_edges, edge_color="cornflowerblue", alpha=0.3, width=0.8, ax=ax)
        nx.draw_networkx_edges(G, pos, edgelist=hv_edges, edge_color="firebrick", alpha=0.9, width=2.5, ax=ax)
        nx.draw_networkx_nodes(G, pos, nodelist=hv_nodes, node_size=20, node_color="firebrick", ax=ax)
        ax.set_title(title)
        ax.set_axis_off()
    plt.savefig(os.path.join(output_dir, "voltage_maps.png"), dpi=150, bbox_inches="tight")
    plt.close()


# ======================================================================
# Main Execution
# ======================================================================

def main():
    print("=" * 60)
    print("Dartboard Analysis - Synthetic Grid Topology Generator")
    print("=" * 60)
    
    ny_load_nodes_path = os.path.join(OUTPUT_DIR, "NY_Load_Nodes.csv")
    tx_load_nodes_path = os.path.join(OUTPUT_DIR, "TX_Load_Nodes.csv")
    ny_generators_path = os.path.join(OUTPUT_DIR, "NY_Generators_Full.csv")
    
    # Step 1: Gold Book
    if os.path.exists(PDF_PATH):
        print("\n--- Step 1: Extracting Gold Book Data ---")
        extract_gold_book_full(PDF_PATH, ny_generators_path)
    else:
        print(f"\n--- Step 1: Skipping Gold Book (not found at {PDF_PATH}) ---")
    
    # Step 2: Census Data
    print("\n--- Step 2: Creating Load Nodes ---")
    if not os.path.exists(GAZ_PATH):
        print(f"ERROR: Gazetteer file not found at {GAZ_PATH}")
        return
    
    ny_load_nodes = create_ny_load_nodes(GAZ_PATH, ny_load_nodes_path)
    plot_ny_nodes(ny_load_nodes_path)
    
    tx_load_nodes = create_tx_load_nodes(GAZ_PATH, tx_load_nodes_path)
    tx_load_nodes = clip_tx_to_boundary(tx_load_nodes_path)
    plot_tx_nodes(tx_load_nodes_path)
    
    # Step 3: Clustering
    print("\n--- Step 3: Clustering into Substations ---")
    ny_subs = birchfield_cluster("NY", ny_load_nodes_path, 600, OUTPUT_DIR)
    tx_subs = birchfield_cluster("TX", tx_load_nodes_path, 1250, OUTPUT_DIR)
    plot_substations(ny_subs, tx_subs, OUTPUT_DIR)
    
    # Step 4: Topology
    print("\n--- Step 4: Generating Initial Topology ---")
    ny_subs_path = os.path.join(OUTPUT_DIR, "NY_Substations.csv")
    tx_subs_path = os.path.join(OUTPUT_DIR, "TX_Substations.csv")
    
    ny_pts, ny_tri, ny_edges = generate_initial_topology("NY", ny_subs_path)
    tx_pts, tx_tri, tx_edges = generate_initial_topology("TX", tx_subs_path)
    
    # Step 5: Pruning
    print("\n--- Step 5: Pruning Topology ---")
    ny_G_final = birchfield_prune_v2("NY", ny_pts, ny_edges)
    tx_G_final = birchfield_prune_v2("TX", tx_pts, tx_edges)
    plot_backbone(ny_G_final, tx_G_final, OUTPUT_DIR)
    
    # Step 6: Add Generation
    print("\n--- Step 6: Adding Generation ---")
    if not os.path.exists(EIA_DIR):
        print(f"ERROR: EIA data directory not found at {EIA_DIR}")
        return
    
    df_all_gens = load_eia_data(EIA_DIR)
    ny_G_integrated = add_generation_to_topology("NY", ny_G_final.copy(), ny_subs, df_all_gens)
    tx_G_integrated = add_generation_to_topology("TX", tx_G_final.copy(), tx_subs, df_all_gens)
    ny_G_integrated = remove_outliers(ny_G_integrated, 40.0, 45.5, -80.0, -71.0)
    
    # Step 7: Voltage
    print("\n--- Step 7: Assigning Voltages ---")
    ny_G_refined = birchfield_voltage_refinement(ny_G_integrated.copy(), "NY")
    tx_G_refined = birchfield_voltage_refinement(tx_G_integrated.copy(), "TX")
    
    ny_G_connected = connect_high_voltage_backbone(ny_G_refined.copy(), "NY")
    tx_G_connected = connect_high_voltage_backbone(tx_G_refined.copy(), "TX")
    plot_voltage_maps(ny_G_connected, tx_G_connected, OUTPUT_DIR)
    
    # Step 8: RNG Topology
    print("\n--- Step 8: Building RNG-Based Topology ---")
    df_ny = load_and_standardize(ny_load_nodes_path)
    df_tx = load_and_standardize(tx_load_nodes_path)
    
    ny_G_rng = build_birchfield_topology(df_ny, "NY")
    tx_G_rng = build_birchfield_topology(df_tx, "TX")
    
    ny_G_spurred = add_generation_to_topology("NY", ny_G_rng.copy(), df_ny, df_all_gens)
    tx_G_spurred = add_generation_to_topology("TX", tx_G_rng.copy(), df_tx, df_all_gens)
    
    ny_G_voltage = birchfield_voltage_refinement(ny_G_spurred, "NY", load_percentile=0.85)
    tx_G_voltage = birchfield_voltage_refinement(tx_G_spurred, "TX", load_percentile=0.85)
    
    ny_G_final_rng = connect_high_voltage_backbone(ny_G_voltage, "NY")
    tx_G_final_rng = connect_high_voltage_backbone(tx_G_voltage, "TX")
    
    print("\n" + "=" * 60)
    print("Analysis Complete! Output files saved to:", OUTPUT_DIR)
    print("=" * 60)


if __name__ == "__main__":
    main()
