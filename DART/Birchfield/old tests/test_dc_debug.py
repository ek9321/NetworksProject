#!/usr/bin/env python3
"""Quick diagnostic to check DC flow inputs."""
from core.topology_generation import SubstationNode
from Calibration.network_io import build_texas7k_substation_nodes_for_topology

subs = build_texas7k_substation_nodes_for_topology()

for label, filt in [("345kV", lambda s: s.has_345kv), ("115kV", lambda s: s.has_115kv)]:
    nodes = [s for s in subs if filt(s)]
    total_load = sum(n.mw_load for n in nodes)
    total_gen = sum(n.total_gen_mw for n in nodes)
    n_gen = sum(1 for n in nodes if n.total_gen_mw > 0)
    n_load = sum(1 for n in nodes if n.mw_load > 0)
    print(f"{label}: {len(nodes)} nodes, load={total_load:.1f} MW, gen={total_gen:.1f} MW")
    print(f"  Nodes with gen>0: {n_gen}, Nodes with load>0: {n_load}")
