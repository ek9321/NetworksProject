"""
Shared utility functions for the Dartboard pipeline.
"""

import numpy as np
import networkx as nx
import pickle


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


def save_graph(G, path):
    """Save a NetworkX graph to a pickle file."""
    with open(path, 'wb') as f:
        pickle.dump(G, f, pickle.HIGHEST_PROTOCOL)
    print(f"Saved graph to {path}")


def load_graph(path):
    """Load a NetworkX graph from a pickle file."""
    with open(path, 'rb') as f:
        G = pickle.load(f)
    print(f"Loaded graph from {path} ({G.number_of_nodes()} nodes, {G.number_of_edges()} edges)")
    return G


def remove_outliers(G, lat_min, lat_max, lon_min, lon_max):
    """Remove nodes outside the bounding box."""
    nodes_to_remove = []
    for node, data in G.nodes(data=True):
        if "pos" not in data:
            continue
        lon, lat = data["pos"]
        if not (lat_min <= lat <= lat_max) or not (lon_min <= lon <= lon_max):
            nodes_to_remove.append(node)
    if nodes_to_remove:
        print(f"Removing {len(nodes_to_remove)} outlier nodes...")
        G.remove_nodes_from(nodes_to_remove)
    return G
