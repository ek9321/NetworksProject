"""
Phase 2: Census Data Processing

Creates load nodes from Census Gazetteer and ACS population data.

Input: 2020_Gaz_zcta_national 2 (1).txt, Census API
Output: NY_Load_Nodes.csv, TX_Load_Nodes.csv
Visualizations: ny_load_nodes.png, tx_load_nodes.png
"""

import os
import pandas as pd
import numpy as np
import requests
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import geopandas as gpd
from shapely.geometry import Point

from . import config


def load_gazetteer(gaz_path):
    """Load and clean the Census Gazetteer file."""
    df_gaz = pd.read_csv(gaz_path, sep="\t")
    df_gaz.columns = df_gaz.columns.str.strip()
    df_gaz["GEOID"] = df_gaz["GEOID"].astype(str).str.zfill(5)
    return df_gaz


def fetch_census_population():
    """Fetch population data from Census ACS API."""
    print("  Fetching population data from Census ACS API...")
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
    print("  Creating NY load nodes...")
    df_gaz = load_gazetteer(gaz_path)
    ny_gaz = df_gaz[df_gaz["GEOID"].str.startswith(("10", "11", "12", "13", "14"))].copy()
    
    df_pop = fetch_census_population()
    ny_final = pd.merge(ny_gaz, df_pop[["GEOID", "POPULATION"]], on="GEOID", how="inner")
    
    ny_final["POPULATION"] = pd.to_numeric(ny_final["POPULATION"])
    ny_final = ny_final[["GEOID", "INTPTLAT", "INTPTLONG", "POPULATION"]]
    ny_final.columns = ["ZCTA", "LAT", "LON", "POP"]
    ny_final["LOAD_MW"] = ny_final["POP"] * 0.002
    
    ny_final.to_csv(output_path, index=False)
    print(f"  Success! Created {len(ny_final)} NY nodes -> {output_path}")
    return ny_final


def create_tx_load_nodes(gaz_path, output_path):
    """Create Texas load nodes from Census data."""
    print("  Creating TX load nodes...")
    df_gaz = load_gazetteer(gaz_path)
    tx_prefixes = ("73", "75", "76", "77", "78", "79")
    tx_gaz = df_gaz[df_gaz["GEOID"].str.startswith(tx_prefixes)].copy()
    
    df_pop = fetch_census_population()
    
    tx_final = pd.merge(tx_gaz, df_pop[["GEOID", "POPULATION"]], on="GEOID", how="inner")
    tx_final["POPULATION"] = pd.to_numeric(tx_final["POPULATION"])
    tx_final["LOAD_MW"] = tx_final["POPULATION"] * 0.002
    
    tx_final.to_csv(output_path, index=False)
    print(f"  Success! Created {len(tx_final)} TX nodes -> {output_path}")
    return tx_final


def clip_tx_to_boundary(tx_file_path):
    """Clip Texas nodes to actual state boundary."""
    print("  Clipping TX nodes to state boundary...")
    df_tx = pd.read_csv(tx_file_path)
    original_count = len(df_tx)
    
    url = "https://www2.census.gov/geo/tiger/GENZ2018/shp/cb_2018_us_state_5m.zip"
    states = gpd.read_file(url)
    tx_poly = states[states["STUSPS"] == "TX"].geometry.values[0]
    
    geometry = [Point(xy) for xy in zip(df_tx["INTPTLONG"], df_tx["INTPTLAT"])]
    gdf_tx = gpd.GeoDataFrame(df_tx, geometry=geometry)
    
    mask = gdf_tx.within(tx_poly)
    df_tx = df_tx.loc[mask].copy()
    
    df_tx.to_csv(tx_file_path, index=False)
    print(f"  Removed {original_count - len(df_tx)} artifacts, {len(df_tx)} remaining")
    return df_tx


def plot_ny_nodes(file_path, output_dir):
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
    out_path = os.path.join(output_dir, "ny_load_nodes.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved visualization: {out_path}")


def plot_tx_nodes(file_path, output_dir):
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
    out_path = os.path.join(output_dir, "tx_load_nodes.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved visualization: {out_path}")


def run(skip_if_exists=False):
    """Run Phase 2: Census data processing."""
    print("\n" + "=" * 60)
    print("Phase 2: Census Data Processing")
    print("=" * 60)
    
    config.ensure_directories()
    
    if not os.path.exists(config.GAZ_PATH):
        raise FileNotFoundError(f"Gazetteer file not found: {config.GAZ_PATH}")
    
    # NY Load Nodes
    if skip_if_exists and os.path.exists(config.NY_LOAD_NODES_PATH):
        print(f"Skipping NY: {config.NY_LOAD_NODES_PATH} already exists")
        ny_nodes = pd.read_csv(config.NY_LOAD_NODES_PATH)
    else:
        ny_nodes = create_ny_load_nodes(config.GAZ_PATH, config.NY_LOAD_NODES_PATH)
        plot_ny_nodes(config.NY_LOAD_NODES_PATH, config.VIZ_DIR)
    
    # TX Load Nodes
    if skip_if_exists and os.path.exists(config.TX_LOAD_NODES_PATH):
        print(f"Skipping TX: {config.TX_LOAD_NODES_PATH} already exists")
        tx_nodes = pd.read_csv(config.TX_LOAD_NODES_PATH)
    else:
        tx_nodes = create_tx_load_nodes(config.GAZ_PATH, config.TX_LOAD_NODES_PATH)
        # clip_tx_to_boundary(config.TX_LOAD_NODES_PATH)  # Temporarily disabled due to PROJ issue
        plot_tx_nodes(config.TX_LOAD_NODES_PATH, config.VIZ_DIR)
    
    return ny_nodes, tx_nodes


if __name__ == "__main__":
    run()
