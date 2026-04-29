#!/usr/bin/env python3
"""
Display pipeline results summary.
"""

import pandas as pd
from pipeline.config import *
import networkx as nx
import pickle
import os

def show_results():
    print('=' * 60)
    print('DARTBOARD PIPELINE - FINAL RESULTS SUMMARY')
    print('=' * 60)
    
    # Load and show generator data
    print('\n1. NY ISO Gold Book Generator Data:')
    ny_gen = pd.read_csv(NY_GENERATORS_PATH)
    print(f'   - Total generators extracted: {len(ny_gen)}')
    print(f'   - Total capacity: {ny_gen["MW"].sum():.0f} MW')
    print(f'   - Capacity range: {ny_gen["MW"].min():.1f} - {ny_gen["MW"].max():.1f} MW')
    
    # Load and show load node data
    print('\n2. Census Load Node Data:')
    ny_load = pd.read_csv(NY_LOAD_NODES_PATH) 
    tx_load = pd.read_csv(TX_LOAD_NODES_PATH)
    print(f'   - NY load nodes: {len(ny_load)} (from ZCTA population data)')
    print(f'   - TX load nodes: {len(tx_load)} (from ZCTA population data)')
    
    # Load and show substation data
    print('\n3. Clustered Substations:')
    ny_subs = pd.read_csv(NY_SUBSTATIONS_PATH)
    tx_subs = pd.read_csv(TX_SUBSTATIONS_PATH) 
    print(f'   - NY substations: {len(ny_subs)} (clustered from {len(ny_load)} load nodes)')
    print(f'   - TX substations: {len(tx_subs)} (clustered from {len(tx_load)} load nodes)')
    
    # Load and show final network topology
    print('\n4. Final Network Topology:')
    with open(NY_VOLTAGE_PATH, 'rb') as f:
        ny_graph = pickle.load(f)
    with open(TX_VOLTAGE_PATH, 'rb') as f:
        tx_graph = pickle.load(f)
    
    ny_hv_lines = [e for e in ny_graph.edges(data=True) if e[2].get('voltage', 115) == 345]
    tx_hv_lines = [e for e in tx_graph.edges(data=True) if e[2].get('voltage', 115) == 345]
    
    print(f'   - NY: {len(ny_graph.nodes)} nodes, {len(ny_graph.edges)} lines')
    print(f'     • 345kV lines: {len(ny_hv_lines)}')
    print(f'     • 115kV lines: {len(ny_graph.edges) - len(ny_hv_lines)}')
    print(f'     • Line/node ratio: {len(ny_graph.edges)/len(ny_graph.nodes):.2f}')
    
    print(f'   - TX: {len(tx_graph.nodes)} nodes, {len(tx_graph.edges)} lines') 
    print(f'     • 345kV lines: {len(tx_hv_lines)}')
    print(f'     • 115kV lines: {len(tx_graph.edges) - len(tx_hv_lines)}')
    print(f'     • Line/node ratio: {len(tx_graph.edges)/len(tx_graph.nodes):.2f}')
    
    print('\n5. EIA Generator Integration:')
    eia_data = pd.read_csv(EIA_GENERATORS_PATH)
    print(f'   - Total EIA generators processed: {len(eia_data):,}')
    ny_eia = eia_data[eia_data['State'] == 'NY']
    tx_eia = eia_data[eia_data['State'] == 'TX']
    print(f'   - NY generators: {len(ny_eia):,}')  
    print(f'   - TX generators: {len(tx_eia):,}')
    
    print('\n' + '=' * 60)
    print('Pipeline completed successfully! Check the visualizations folder.')
    print(f'Visualizations: {VIZ_DIR}')
    print('=' * 60)

if __name__ == "__main__":
    show_results()