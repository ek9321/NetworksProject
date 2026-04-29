"""
Phase 4: Initial Topology Generation

Generates initial Delaunay triangulation topology from substations.

Input: NY_Substations.csv, TX_Substations.csv
Output: NY_Topology.gpickle, TX_Topology.gpickle
"""

import os
import pandas as pd
import numpy as np
import networkx as nx
from scipy.spatial import Delaunay

from . import config
from .utils import haversine, save_graph


def generate_initial_topology(state_name, file_path, output_path):
    """Generate initial Delaunay triangulation topology."""
    print(f"  Generating initial triangulation for {state_name}...")
    df = pd.read_csv(file_path)
    points = df[["SUB_LON", "SUB_LAT"]].values
    tri = Delaunay(points)

    # Build graph
    G = nx.Graph()
    for i, row in df.iterrows():
        G.add_node(i, pos=(row["SUB_LON"], row["SUB_LAT"]),
                   LOAD_MW=row.get("LOAD_MW", 0), TOTAL_POP=row.get("TOTAL_POP", 0), type="l")

    edges = set()
    for simplex in tri.simplices:
        for i in range(3):
            edge = tuple(sorted((simplex[i], simplex[(i+1)%3])))
            edges.add(edge)

    for u, v in edges:
        dist = haversine(points[u,0], points[u,1], points[v,0], points[v,1])
        G.add_edge(u, v, weight=dist)

    n, m = G.number_of_nodes(), G.number_of_edges()
    print(f"  {state_name} Stats: Nodes={n}, Lines={m}, Ratio={m/n:.2f}")
    
    save_graph(G, output_path)
    return G


def run(skip_if_exists=False):
    """Run Phase 4: Initial topology generation."""
    print("\n" + "=" * 60)
    print("Phase 4: Initial Topology Generation")
    print("=" * 60)
    
    config.ensure_directories()
    
    # Check inputs exist
    if not os.path.exists(config.NY_SUBSTATIONS_PATH):
        raise FileNotFoundError(f"Run Phase 3 first: {config.NY_SUBSTATIONS_PATH} not found")
    if not os.path.exists(config.TX_SUBSTATIONS_PATH):
        raise FileNotFoundError(f"Run Phase 3 first: {config.TX_SUBSTATIONS_PATH} not found")
    
    # NY Topology
    if skip_if_exists and os.path.exists(config.NY_TOPOLOGY_PATH):
        print(f"Skipping NY: {config.NY_TOPOLOGY_PATH} already exists")
        from .utils import load_graph
        ny_G = load_graph(config.NY_TOPOLOGY_PATH)
    else:
        ny_G = generate_initial_topology("NY", config.NY_SUBSTATIONS_PATH, config.NY_TOPOLOGY_PATH)
    
    # TX Topology
    if skip_if_exists and os.path.exists(config.TX_TOPOLOGY_PATH):
        print(f"Skipping TX: {config.TX_TOPOLOGY_PATH} already exists")
        from .utils import load_graph
        tx_G = load_graph(config.TX_TOPOLOGY_PATH)
    else:
        tx_G = generate_initial_topology("TX", config.TX_SUBSTATIONS_PATH, config.TX_TOPOLOGY_PATH)
    
    return ny_G, tx_G


if __name__ == "__main__":
    run()
