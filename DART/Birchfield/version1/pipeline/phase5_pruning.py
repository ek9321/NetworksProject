"""
Phase 5: Topology Pruning (Birchfield RNG Approach)

Prunes the Delaunay topology using Relative Neighborhood Graph filtering
followed by additional pruning to achieve target edge-to-node ratio.

Based on Birchfield et al., "Grid Structural Characteristics as Validation 
Criteria for Synthetic Networks" (IEEE Trans. Power Systems, 2017).

The RNG approach removes edges where a third point exists closer to BOTH 
endpoints than they are to each other. RNG has inherent connectivity 
properties without requiring explicit MST preservation.

Input: NY_Topology.gpickle, TX_Topology.gpickle
Output: NY_Pruned.gpickle, TX_Pruned.gpickle
Visualizations: backbone.png
"""

import os
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from . import config
from .utils import load_graph, save_graph


def relative_neighborhood_filter(G_delaunay, state_name):
    """
    Apply Relative Neighborhood Graph (RNG) filter to Delaunay edges.
    
    An edge (u, v) is in the RNG if and only if there is no third point w
    such that d(u,w) < d(u,v) AND d(v,w) < d(u,v).
    
    This is the key geometric filtering step from Birchfield's approach.
    """
    print(f"  Applying RNG filter for {state_name}...")
    print(f"    Initial edges: {G_delaunay.number_of_edges()}")
    
    # Build coordinate lookup
    coords = {n: np.array(data["pos"]) for n, data in G_delaunay.nodes(data=True)}
    all_nodes = list(coords.keys())
    
    edges_to_remove = []
    total_edges = G_delaunay.number_of_edges()
    
    for i, (u, v) in enumerate(G_delaunay.edges()):
        if i % 500 == 0:
            print(f"    Processing edge {i}/{total_edges}...", end='\r')
        
        pu, pv = coords[u], coords[v]
        d_uv = np.linalg.norm(pu - pv)
        
        # Check ALL other nodes (this is the correct RNG definition)
        is_rng_edge = True
        for w in all_nodes:
            if w == u or w == v:
                continue
            pw = coords[w]
            d_uw = np.linalg.norm(pu - pw)
            d_vw = np.linalg.norm(pv - pw)
            
            # If w is closer to both u and v than they are to each other,
            # then (u,v) is NOT an RNG edge
            if d_uw < d_uv and d_vw < d_uv:
                is_rng_edge = False
                break
        
        if not is_rng_edge:
            edges_to_remove.append((u, v))
    
    print()  # Clear the carriage return
    
    G_rng = G_delaunay.copy()
    G_rng.remove_edges_from(edges_to_remove)
    
    print(f"    RNG removed {len(edges_to_remove)} edges")
    print(f"    RNG edges remaining: {G_rng.number_of_edges()}")
    
    return G_rng


def ratio_based_pruning(G, state_name, target_ratio=1.22):
    """
    Further prune the graph to achieve target edge-to-node ratio.
    
    Per Birchfield: target ratio should be 1.1-1.4 per voltage level.
    We use 1.22 as a reasonable middle ground for the combined network.
    
    Removes longest edges first. RNG already provides connectivity guarantees.
    """
    print(f"  Ratio-based pruning for {state_name}...")
    
    current_ratio = G.number_of_edges() / G.number_of_nodes()
    print(f"    Current ratio: {current_ratio:.2f}, Target: {target_ratio:.2f}")
    
    if current_ratio <= target_ratio:
        print(f"    Already at or below target ratio, no additional pruning needed.")
        return G
    
    # Get all edges sorted by weight descending (longest first)
    all_edges = list(G.edges())
    all_edges = sorted(all_edges, 
                      key=lambda x: G[x[0]][x[1]].get("weight", 0), 
                      reverse=True)
    
    G_pruned = G.copy()
    removed_count = 0
    
    for u, v in all_edges:
        if G_pruned.number_of_edges() / G_pruned.number_of_nodes() <= target_ratio:
            break
        G_pruned.remove_edge(u, v)
        removed_count += 1
    
    final_ratio = G_pruned.number_of_edges() / G_pruned.number_of_nodes()
    print(f"    Removed {removed_count} additional edges")
    print(f"    Final ratio: {final_ratio:.2f}")
    print(f"    Connected: {nx.is_connected(G_pruned)}")
    
    return G_pruned


def birchfield_prune(G_full, state_name, target_ratio=1.22):
    """
    Full Birchfield pruning pipeline:
    1. RNG filtering (geometric)
    2. Ratio-based pruning (to hit target)
    """
    print(f"  Birchfield Pruning for {state_name}...")
    
    # Step 1: RNG filtering
    G_rng = relative_neighborhood_filter(G_full, state_name)
    
    # Step 2: Additional ratio-based pruning if needed
    G_final = ratio_based_pruning(G_rng, state_name, target_ratio)
    
    return G_final


def plot_backbone(G_ny, G_tx, output_dir):
    """Plot backbone topology for both states."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(22, 10))
    
    pos_ny = nx.get_node_attributes(G_ny, "pos")
    nx.draw_networkx_nodes(G_ny, pos_ny, ax=ax1, node_size=5, node_color="navy", alpha=0.7)
    nx.draw_networkx_edges(G_ny, pos_ny, ax=ax1, edge_color="royalblue", width=0.8, alpha=0.5)
    ratio_ny = G_ny.number_of_edges() / G_ny.number_of_nodes()
    ax1.set_title(f"NY Backbone ({G_ny.number_of_nodes()} nodes, {G_ny.number_of_edges()} edges, ratio={ratio_ny:.2f})")
    ax1.set_axis_off()

    pos_tx = nx.get_node_attributes(G_tx, "pos")
    nx.draw_networkx_nodes(G_tx, pos_tx, ax=ax2, node_size=5, node_color="darkred", alpha=0.7)
    nx.draw_networkx_edges(G_tx, pos_tx, ax=ax2, edge_color="indianred", width=0.8, alpha=0.5)
    ratio_tx = G_tx.number_of_edges() / G_tx.number_of_nodes()
    ax2.set_title(f"TX Backbone ({G_tx.number_of_nodes()} nodes, {G_tx.number_of_edges()} edges, ratio={ratio_tx:.2f})")
    ax2.set_axis_off()
    
    out_path = os.path.join(output_dir, "backbone.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved visualization: {out_path}")


def run(skip_if_exists=False):
    """Run Phase 5: Topology pruning using Birchfield RNG approach."""
    print("\n" + "=" * 60)
    print("Phase 5: Topology Pruning (Birchfield RNG)")
    print("=" * 60)
    
    config.ensure_directories()
    
    # Check inputs exist
    if not os.path.exists(config.NY_TOPOLOGY_PATH):
        raise FileNotFoundError(f"Run Phase 4 first: {config.NY_TOPOLOGY_PATH} not found")
    if not os.path.exists(config.TX_TOPOLOGY_PATH):
        raise FileNotFoundError(f"Run Phase 4 first: {config.TX_TOPOLOGY_PATH} not found")
    
    # NY Pruning
    if skip_if_exists and os.path.exists(config.NY_PRUNED_PATH):
        print(f"Skipping NY: {config.NY_PRUNED_PATH} already exists")
        ny_G = load_graph(config.NY_PRUNED_PATH)
    else:
        ny_G_full = load_graph(config.NY_TOPOLOGY_PATH)
        ny_G = birchfield_prune(ny_G_full, "NY", config.PRUNE_TARGET_RATIO)
        save_graph(ny_G, config.NY_PRUNED_PATH)
    
    # TX Pruning
    if skip_if_exists and os.path.exists(config.TX_PRUNED_PATH):
        print(f"Skipping TX: {config.TX_PRUNED_PATH} already exists")
        tx_G = load_graph(config.TX_PRUNED_PATH)
    else:
        tx_G_full = load_graph(config.TX_TOPOLOGY_PATH)
        tx_G = birchfield_prune(tx_G_full, "TX", config.PRUNE_TARGET_RATIO)
        save_graph(tx_G, config.TX_PRUNED_PATH)
    
    # Visualization
    plot_backbone(ny_G, tx_G, config.VIZ_DIR)
    
    return ny_G, tx_G


if __name__ == "__main__":
    run()
