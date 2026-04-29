# Diagnosing Resilience in the ERCOT Transmission Network

Network science analysis of the ERCOT (Electric Reliability Council of Texas) transmission grid.
See `DART/report.tex` for the full paper.

## The Network (V3 pipeline)

| | |
|---|---|
| **Nodes** | 3,786 (3,000 real substations + 786 synthetic T-junctions) |
| **Edges** | 4,817 transmission lines |
| **Zones** | NORTH (1,319), SOUTH (1,081), WEST (909), HOUSTON (477) |
| **Generation** | 159 GW nameplate, 1,185 units (MORA April 2026) |
| **Connectivity** | Single connected component (100%), bridge ratio 14.4% |

## Data Pipeline

```
OpenStreetMap (OSM)   ──► build_osm_bus_table.py        ─┐
ERCOT MORA April 2026 ──► extract_mora.py                ─┼─► sced_inputs_v3/
Census 2020 pop.      ──► (inline in network_analysis.py) ─┘
                                    │
                         build_osm_branch_table_v3.py
                         (V3: 50 m proximity snap + T-junctions)
                                    │
                         network_analysis.py   ──► figures/, network_analysis_results.json
                         optimal_grid.py       ──► figures/real_vs_optimal_attack_curves.png
```

Source data lives in `DART/Realist/grid_data/sced_inputs_v3/SourceData/`.

## Analyses

| Script | Output | Section in paper |
|---|---|---|
| `network_analysis.py` | `figures/attack_curves.png` | §4 Attack curves |
| `network_analysis.py` | `figures/spectral_analysis.png` | §4 Spectral bisection |
| `network_analysis.py` | `figures/n1_stress.png` | §5 N–1 contingency |
| `optimal_grid.py` | `figures/real_vs_optimal_attack_curves.png` | §6 Topology-optimal grid |
| `notebooks/graph_simulations.ipynb` | `sim.png` | §4 Link prediction simulation |

## Requirements

```
pip install networkx matplotlib numpy scipy pandas geopandas shapely
```

## File Manifest

```
DART/report.tex                                  — paper source
DART/Realist/ERCOT/
  network_analysis.py                            — attack curves, spectral, N–1, null model
  optimal_grid.py                                — greedy λ₂-optimal grid + attack-curve comparison
  build_osm_bus_table.py                         — OSM substation extraction
  build_osm_branch_table_v3.py                   — V3 line extraction (50 m proximity snap)
  extract_mora.py                                — MORA generation unit ingestion
  figures/                                       — output plots
  network_analysis_results.json                  — numerical results
  optimal_grid_results.json
  n1_stress_results.csv
DART/Realist/grid_data/
  sced_inputs_v3/SourceData/{bus,branch,gen}.csv — V3 grid inputs
  MORA_April2026_unit_capacities.csv             — generation nameplate
  texas_tract_pop_2020.csv                       — Census 2020 load allocation
  ercot_zones.geojson                            — ERCOT zone boundaries
notebooks/graph_simulations.ipynb                — link prediction simulation
```
