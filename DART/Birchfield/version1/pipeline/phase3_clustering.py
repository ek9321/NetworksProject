"""
Phase 3: Clustering

Clusters ZCTAs into substations using agglomerative clustering.

Input: NY_Load_Nodes.csv, TX_Load_Nodes.csv
Output: NY_Substations.csv, TX_Substations.csv
Visualizations: substations.png
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.cluster import AgglomerativeClustering

from . import config


def birchfield_cluster(state_name, input_file, n_substations, output_path):
    """Cluster ZCTAs into substations using agglomerative clustering."""
    print(f"  Clustering {state_name} into {n_substations} substations...")

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
    substations.to_csv(output_path, index=False)
    print(f"  Saved {len(substations)} substations -> {output_path}")
    return substations


def plot_substations(ny_subs, tx_subs, output_dir):
    """Plot substations for both states."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 8))
    ax1.scatter(ny_subs["SUB_LON"], ny_subs["SUB_LAT"], s=ny_subs["LOAD_MW"]*0.5, alpha=0.5, c="blue")
    ax1.set_title(f"NY Synthetic Substations (n={len(ny_subs)})")
    ax1.set_xlabel("Longitude")
    ax1.set_ylabel("Latitude")
    
    ax2.scatter(tx_subs["SUB_LON"], tx_subs["SUB_LAT"], s=tx_subs["LOAD_MW"]*0.5, alpha=0.5, c="red")
    ax2.set_title(f"TX Synthetic Substations (n={len(tx_subs)})")
    ax2.set_xlabel("Longitude")
    ax2.set_ylabel("Latitude")
    
    out_path = os.path.join(output_dir, "substations.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved visualization: {out_path}")


def run(skip_if_exists=False):
    """Run Phase 3: Clustering."""
    print("\n" + "=" * 60)
    print("Phase 3: Clustering into Substations")
    print("=" * 60)
    
    config.ensure_directories()
    
    # Check inputs exist
    if not os.path.exists(config.NY_LOAD_NODES_PATH):
        raise FileNotFoundError(f"Run Phase 2 first: {config.NY_LOAD_NODES_PATH} not found")
    if not os.path.exists(config.TX_LOAD_NODES_PATH):
        raise FileNotFoundError(f"Run Phase 2 first: {config.TX_LOAD_NODES_PATH} not found")
    
    # NY Substations
    if skip_if_exists and os.path.exists(config.NY_SUBSTATIONS_PATH):
        print(f"Skipping NY: {config.NY_SUBSTATIONS_PATH} already exists")
        ny_subs = pd.read_csv(config.NY_SUBSTATIONS_PATH)
    else:
        ny_subs = birchfield_cluster("NY", config.NY_LOAD_NODES_PATH, 
                                      config.NY_SUBSTATIONS_COUNT, config.NY_SUBSTATIONS_PATH)
    
    # TX Substations
    if skip_if_exists and os.path.exists(config.TX_SUBSTATIONS_PATH):
        print(f"Skipping TX: {config.TX_SUBSTATIONS_PATH} already exists")
        tx_subs = pd.read_csv(config.TX_SUBSTATIONS_PATH)
    else:
        tx_subs = birchfield_cluster("TX", config.TX_LOAD_NODES_PATH,
                                      config.TX_SUBSTATIONS_COUNT, config.TX_SUBSTATIONS_PATH)
    
    # Visualization
    plot_substations(ny_subs, tx_subs, config.VIZ_DIR)
    
    return ny_subs, tx_subs


if __name__ == "__main__":
    run()
