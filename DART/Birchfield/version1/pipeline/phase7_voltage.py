"""
Phase 7: Voltage Assignment

Assigns voltage levels and connects the high-voltage backbone.

Input: NY_Integrated.gpickle, TX_Integrated.gpickle
Output: NY_Voltage.gpickle, TX_Voltage.gpickle
Visualizations: voltage_maps.png
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx

from . import config
from .utils import load_graph, save_graph


def birchfield_voltage_refinement(G, state_name, load_percentile=0.85):
    """Assign voltages based on generation and load centers."""
    print(f"  Refining Voltage for {state_name}...")

    gen_nodes = [n for n, d in G.nodes(data=True) if d.get("gen_mw", 0) > 0]
    loads = [d.get("LOAD_MW", 0) for n, d in G.nodes(data=True) if "LOAD_MW" in d]
    load_threshold = np.percentile(loads, load_percentile * 100) if loads else 0
    load_nodes = [n for n, d in G.nodes(data=True) if d.get("LOAD_MW", 0) >= load_threshold]

    seeds = set(gen_nodes + load_nodes)
    print(f"    Seeds: {len(gen_nodes)} (Gen), {len(load_nodes)} (Load)")

    for n in G.nodes():
        G.nodes[n]["kv"] = 345 if n in seeds else 115

    hv_count = 0
    for u, v in G.edges():
        if G.nodes[u]["kv"] == 345 and G.nodes[v]["kv"] == 345:
            G.edges[u, v]["edge_type"] = "HV"
            hv_count += 1
        else:
            G.edges[u, v]["edge_type"] = "LV"

    print(f"    Result: {hv_count} HV lines created.")
    return G


def connect_high_voltage_backbone(G, state_name):
    """Ensure the high voltage backbone is connected."""
    print(f"  Building Connected Backbone for {state_name}...")

    iterations = 0
    max_iterations = 50
    
    while iterations < max_iterations:
        iterations += 1
        hv_nodes = [n for n, d in G.nodes(data=True) if d.get("kv") == 345]
        if not hv_nodes:
            print("    No HV nodes found.")
            return G

        H = G.subgraph(hv_nodes)
        components = list(nx.connected_components(H))
        components.sort(key=len, reverse=True)

        if len(components) <= 1:
            print(f"    Backbone is connected! ({iterations} iterations)")
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
            print(f"    Warning: Could not find path between clusters (iter {iterations}).")
            break

        for n in best_path:
            G.nodes[n]["kv"] = 345
        for i in range(len(best_path) - 1):
            u, v = best_path[i], best_path[i+1]
            if G.has_edge(u, v):
                G.edges[u, v]["edge_type"] = "HV"
    
    print(f"    Final HV clusters: {len(components)}")
    return G


def plot_voltage_maps(ny_G, tx_G, output_dir, filename="voltage_maps.png"):
    """Plot voltage maps for both states."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(22, 10))
    
    for G, ax, title in [(ny_G, ax1, "NY Grid"), (tx_G, ax2, "TX Grid")]:
        pos = nx.get_node_attributes(G, "pos")
        lv_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("edge_type") != "HV"]
        hv_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("edge_type") == "HV"]
        hv_nodes = [n for n, d in G.nodes(data=True) if d.get("kv") == 345]
        
        nx.draw_networkx_edges(G, pos, edgelist=lv_edges, edge_color="cornflowerblue", alpha=0.3, width=0.8, ax=ax)
        nx.draw_networkx_edges(G, pos, edgelist=hv_edges, edge_color="firebrick", alpha=0.9, width=2.5, ax=ax)
        nx.draw_networkx_nodes(G, pos, nodelist=hv_nodes, node_size=20, node_color="firebrick", ax=ax)
        ax.set_title(f"{title} ({len(hv_nodes)} HV nodes, {len(hv_edges)} HV lines)")
        ax.set_axis_off()
    
    out_path = os.path.join(output_dir, filename)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved visualization: {out_path}")


def run(skip_if_exists=False):
    """Run Phase 7: Voltage assignment."""
    print("\n" + "=" * 60)
    print("Phase 7: Voltage Assignment")
    print("=" * 60)
    
    config.ensure_directories()
    
    # Check inputs exist
    if not os.path.exists(config.NY_INTEGRATED_PATH):
        raise FileNotFoundError(f"Run Phase 6 first: {config.NY_INTEGRATED_PATH} not found")
    if not os.path.exists(config.TX_INTEGRATED_PATH):
        raise FileNotFoundError(f"Run Phase 6 first: {config.TX_INTEGRATED_PATH} not found")
    
    # NY Voltage
    if skip_if_exists and os.path.exists(config.NY_VOLTAGE_PATH):
        print(f"Skipping NY: {config.NY_VOLTAGE_PATH} already exists")
        ny_G = load_graph(config.NY_VOLTAGE_PATH)
    else:
        ny_G = load_graph(config.NY_INTEGRATED_PATH)
        ny_G = birchfield_voltage_refinement(ny_G, "NY", config.LOAD_PERCENTILE)
        ny_G = connect_high_voltage_backbone(ny_G, "NY")
        save_graph(ny_G, config.NY_VOLTAGE_PATH)
    
    # TX Voltage
    if skip_if_exists and os.path.exists(config.TX_VOLTAGE_PATH):
        print(f"Skipping TX: {config.TX_VOLTAGE_PATH} already exists")
        tx_G = load_graph(config.TX_VOLTAGE_PATH)
    else:
        tx_G = load_graph(config.TX_INTEGRATED_PATH)
        tx_G = birchfield_voltage_refinement(tx_G, "TX", config.LOAD_PERCENTILE)
        tx_G = connect_high_voltage_backbone(tx_G, "TX")
        save_graph(tx_G, config.TX_VOLTAGE_PATH)
    
    # Visualization
    plot_voltage_maps(ny_G, tx_G, config.VIZ_DIR)
    
    return ny_G, tx_G


if __name__ == "__main__":
    run()
