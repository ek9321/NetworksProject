# ERCOT Transmission Grid — Network Analysis

A network science analysis of the real ERCOT (Electric Reliability Council of Texas) transmission grid, built from OpenStreetMap data and public ERCOT filings.

## The Network

| | |
|---|---|
| **Nodes** | 3,878 substations (345/230/138 kV) |
| **Edges** | 4,501 transmission lines |
| **Zones** | NORTH (1,309), SOUTH (1,170), WEST (916), HOUSTON (483) |
| **Generation** | 159,742 MW nameplate across Nuclear, Coal, Gas, Wind, Solar |
| **Connectivity** | Single connected component (100%) |

Edge attributes: voltage (kV), line length (km), thermal capacity (MVA), reactance.
Node attributes: zone, voltage level, lat/lng, aggregated generation (MW + fuel type), load.

## Data Pipeline

```
OSM GeoJSON → bus.csv / branch.csv / gen.csv → build_network.py → nodes.csv, edges.csv, ercot_network.graphml
```

Source data lives in `../grid_data/sced_inputs/SourceData/`. The build script reads those CSVs, computes line lengths via haversine, assigns capacity ratings, aggregates generators onto bus nodes, and exports the simplified network.

## Analyses

Run `build_network.py` first, then `analyze_network.py`. Figures are saved to `figures/`.

1. **Basic topology** — Degree distribution, clustering coefficient, density. Power grids are sparse, planar-ish, low clustering — distinct from social or biological networks.

2. **Betweenness centrality** — Capacity-weighted betweenness identifies bottleneck corridors. Geographic heatmap shows which substations are critical for power flow.

3. **Community detection** — Louvain algorithm on the topology, compared side-by-side with ERCOT's actual load zone boundaries. Tests whether network structure alone recovers the operational zones.

4. **Cascading failure** — Remove edges (targeted by betweenness vs random), simulate overload cascades. Measures giant component fragmentation under each strategy.

5. **Grid visualization** — Geographic map with voltage-colored edges and fuel-type generation markers.

6. **Random graph comparison** — ERCOT vs Erdos-Renyi vs Barabasi-Albert of matched size. Degree distribution, clustering, and connectivity compared.

## Requirements

```
pip install networkx matplotlib numpy
```

## File Manifest

```
build_network.py        — reads SCED CSVs, writes nodes.csv + edges.csv + graphml
analyze_network.py      — all analyses, writes figures/
nodes.csv               — node table (generated)
edges.csv               — edge table (generated)
ercot_network.graphml   — NetworkX graph (generated)
figures/                — output plots (generated)
```
