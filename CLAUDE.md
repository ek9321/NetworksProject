# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Network science analysis of the ERCOT (Electric Reliability Council of Texas) transmission grid. The network has ~3,878 substations (nodes) and ~4,501 transmission lines (edges) across four load zones (NORTH, SOUTH, WEST, HOUSTON), built from OpenStreetMap data and public ERCOT SCED filings.

## Commands

```bash
# Install dependencies
pip install networkx matplotlib numpy

# Build the network (must run first — reads source CSVs, produces nodes.csv, edges.csv, ercot_network.graphml)
python build_network.py

# Run all analyses (requires build_network.py output; produces figures in figures/)
python analyze_network.py
```

## Architecture

**Two-stage pipeline:** `build_network.py` → `analyze_network.py`

**build_network.py** reads raw SCED CSVs from `../grid_data/sced_inputs/SourceData/` (bus.csv, branch.csv, gen.csv), computes edge attributes (haversine line lengths, capacity ratings, reactance), aggregates generators onto bus nodes, and exports:
- `nodes.csv` / `edges.csv` — flat tables
- `ercot_network.graphml` — NetworkX graph with all node/edge attributes

Parallel edges between the same bus pair are aggregated (summed capacity, circuit count). Isolated nodes are removed. The 999999 sentinel in `Cont Rating` is replaced with voltage-class defaults.

**analyze_network.py** loads `ercot_network.graphml`, extracts the giant connected component, and runs six analyses sequentially (each producing a figure):
1. Degree distribution (linear + log-log)
2. Capacity-weighted betweenness centrality (geographic heatmap)
3. Louvain community detection vs actual ERCOT load zones
4. Cascading failure simulation — targeted (by edge betweenness) vs random removal with overload propagation
5. Geographic grid map — voltage-colored edges + fuel-type generation markers
6. Random graph comparison — ERCOT vs Erdos-Renyi vs Barabasi-Albert

The cascade simulation (`simulate_cascade`) uses edge betweenness as a DC power flow proxy, tripping edges whose relative betweenness exceeds a capacity-proportional threshold, iterating up to 10 rounds.

## Key Details

- GraphML stores node IDs as strings; `analyze_network.py` converts them back to int after loading.
- Edge weight for betweenness = `1/capacity_mva` (high-capacity lines = shorter paths).
- Matplotlib backend is set to `Agg` (non-interactive, file output only).
- All generated files (CSVs, graphml, figures/) are in `.gitignore`.
