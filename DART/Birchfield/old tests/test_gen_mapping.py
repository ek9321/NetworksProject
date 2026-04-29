#!/usr/bin/env python3
"""Trace generator MW through transformers to HV buses in Texas-7k."""
import pandas as pd
from collections import Counter

bus = pd.read_csv('vatic/data/grids/Texas-7k/TX_Data/SourceData/bus.csv')
branch = pd.read_csv('vatic/data/grids/Texas-7k/TX_Data/SourceData/branch.csv')
gen = pd.read_csv('vatic/data/grids/Texas-7k/TX_Data/SourceData/gen.csv')

gen_buses = gen.groupby('Bus ID')['PMax MW'].sum().reset_index()
gen_buses.columns = ['bus_id', 'total_pmax']
print(f'Unique gen buses: {len(gen_buses)}')

xfmrs = branch[branch['Xfrmr'] == 'YES']
print(f'Transformers: {len(xfmrs)}')

bus_kv = bus.set_index('Bus ID')['BaseKV'].to_dict()

# Build adjacency through transformers (multi-hop)
from collections import defaultdict
xfmr_adj = defaultdict(set)
for _, row in xfmrs.iterrows():
    fb = row['From Bus']
    tb = row['To Bus']
    xfmr_adj[fb].add(tb)
    xfmr_adj[tb].add(fb)

# BFS from each gen bus to find nearest HV bus (>=100 kV)
def find_hv_bus(start_bus):
    visited = {start_bus}
    queue = [start_bus]
    while queue:
        current = queue.pop(0)
        kv = bus_kv.get(current, 0)
        if kv >= 100 and current != start_bus:
            return current, kv
        for neighbor in xfmr_adj[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return None, None

# Map gen capacity to HV buses
hv_gen = defaultdict(float)
unmapped = 0
for _, row in gen.iterrows():
    bus_id = row['Bus ID']
    pmax = row['PMax MW']
    my_kv = bus_kv.get(bus_id, 0)
    if my_kv >= 100:
        # Already an HV bus
        hv_gen[bus_id] += pmax
    else:
        hv_bus, hv_kv = find_hv_bus(bus_id)
        if hv_bus is not None:
            hv_gen[hv_bus] += pmax
        else:
            unmapped += 1

print(f'HV buses with aggregated gen: {len(hv_gen)}')
print(f'Total aggregated gen at HV: {sum(hv_gen.values()):.0f} MW')
print(f'Unmapped generators: {unmapped}')

# Distribution by kV
kv_counts = Counter()
kv_mw = defaultdict(float)
for hv_bus, gen_mw in hv_gen.items():
    kv = bus_kv.get(hv_bus, 0)
    kv_counts[kv] += 1
    kv_mw[kv] += gen_mw

for kv in sorted(kv_mw.keys()):
    print(f'  {kv:.0f} kV: {kv_counts[kv]} buses, {kv_mw[kv]:.0f} MW')
