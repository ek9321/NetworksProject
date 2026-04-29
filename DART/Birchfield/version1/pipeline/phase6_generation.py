"""
Phase 6: Generation Integration

Adds EIA generator data to the topology.

Input: NY_Pruned.gpickle, TX_Pruned.gpickle, NY_Substations.csv, TX_Substations.csv, EIA data
Output: NY_Integrated.gpickle, TX_Integrated.gpickle, EIA_Generators.csv
"""

import os
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree

from . import config
from .utils import load_graph, save_graph, remove_outliers


def load_eia_data(eia_dir, output_path=None):
    """Load EIA 860 generator and plant data."""
    print("  Loading EIA Data...")
    
    plant_file = os.path.join(eia_dir, "2___Plant_Y2023.xlsx")
    gen_file = os.path.join(eia_dir, "3_1_Generator_Y2023.xlsx")
    
    print(f"    Reading {plant_file}...")
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
    
    print(f"    Reading {gen_file}...")
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
    
    if output_path:
        df_all_gens.to_csv(output_path, index=False)
    
    print(f"  Success! Loaded {len(df_all_gens)} operating generators.")
    return df_all_gens


def add_generation_to_topology(state_code, G_backbone, subs_df, df_all_gens, capture_miles=7):
    """Add generation nodes to the topology."""
    print(f"  Integrating Generation for {state_code}...")

    state_gens = df_all_gens[df_all_gens["State"] == state_code].copy()
    if state_gens.empty:
        print(f"    Warning: No generators found for {state_code}!")
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
        if sub_id not in G_backbone.nodes:
            continue
        if "gen_mw" not in G_backbone.nodes[sub_id]:
            G_backbone.nodes[sub_id]["gen_mw"] = 0.0
        G_backbone.nodes[sub_id]["gen_mw"] += row["Nameplate Capacity (MW)"]
        G_backbone.nodes[sub_id]["type"] = "b"

    start_id = max(G_backbone.nodes()) + 1
    for i, (idx, row) in enumerate(remote.iterrows()):
        new_node_id = start_id + i
        G_backbone.add_node(new_node_id, pos=(row["Longitude"], row["Latitude"]),
                            type="g", gen_mw=row["Nameplate Capacity (MW)"],
                            voltage=row["Grid Voltage (kV)"])
        target_sub = int(row["nearest_sub_idx"])
        if target_sub in G_backbone.nodes:
            G_backbone.add_edge(new_node_id, target_sub, type="spur", weight=row["dist_miles"])

    print(f"    Captured: {len(captured)}, Remote: {len(remote)} (new spurs)")
    return G_backbone


def run(skip_if_exists=False):
    """Run Phase 6: Generation integration."""
    print("\n" + "=" * 60)
    print("Phase 6: Generation Integration")
    print("=" * 60)
    
    config.ensure_directories()
    
    # Check inputs exist
    if not os.path.exists(config.NY_PRUNED_PATH):
        raise FileNotFoundError(f"Run Phase 5 first: {config.NY_PRUNED_PATH} not found")
    if not os.path.exists(config.TX_PRUNED_PATH):
        raise FileNotFoundError(f"Run Phase 5 first: {config.TX_PRUNED_PATH} not found")
    if not os.path.exists(config.EIA_DIR):
        raise FileNotFoundError(f"EIA data not found: {config.EIA_DIR}")
    
    # Load EIA data
    if skip_if_exists and os.path.exists(config.EIA_GENERATORS_PATH):
        print(f"Loading cached EIA data: {config.EIA_GENERATORS_PATH}")
        df_all_gens = pd.read_csv(config.EIA_GENERATORS_PATH)
    else:
        df_all_gens = load_eia_data(config.EIA_DIR, config.EIA_GENERATORS_PATH)
    
    # Load substations
    ny_subs = pd.read_csv(config.NY_SUBSTATIONS_PATH)
    tx_subs = pd.read_csv(config.TX_SUBSTATIONS_PATH)
    
    # NY Integration
    if skip_if_exists and os.path.exists(config.NY_INTEGRATED_PATH):
        print(f"Skipping NY: {config.NY_INTEGRATED_PATH} already exists")
        ny_G = load_graph(config.NY_INTEGRATED_PATH)
    else:
        ny_G = load_graph(config.NY_PRUNED_PATH)
        ny_G = add_generation_to_topology("NY", ny_G, ny_subs, df_all_gens, config.CAPTURE_MILES)
        ny_G = remove_outliers(ny_G, **config.NY_BOUNDS)
        save_graph(ny_G, config.NY_INTEGRATED_PATH)
    
    # TX Integration
    if skip_if_exists and os.path.exists(config.TX_INTEGRATED_PATH):
        print(f"Skipping TX: {config.TX_INTEGRATED_PATH} already exists")
        tx_G = load_graph(config.TX_INTEGRATED_PATH)
    else:
        tx_G = load_graph(config.TX_PRUNED_PATH)
        tx_G = add_generation_to_topology("TX", tx_G, tx_subs, df_all_gens, config.CAPTURE_MILES)
        save_graph(tx_G, config.TX_INTEGRATED_PATH)
    
    return ny_G, tx_G


if __name__ == "__main__":
    run()
