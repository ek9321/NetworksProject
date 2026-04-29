# Paper Index

Navigation overlay for *Diagnosing Resilience in the ERCOT Transmission Network*
(Hasker, Souder, Kong — ORF 387, Princeton, Spring 2026).

This file is an index. It does not move or modify any existing files; every link
points back to the original artifacts at the repo root.

## Sections

- [§3 Network Construction](analysis/3_network_construction/README.md)
- [§4 Structural Diagnosis](analysis/4_structural_diagnosis/README.md)
  - [§4.1 Articulation points and population at risk](analysis/4_structural_diagnosis/4.1_articulation_points/README.md)
  - [§4.2 Attack curves](analysis/4_structural_diagnosis/4.2_attack_curves/README.md)
  - [§4.3 Unsupervised link prediction and simulated line trips](analysis/4_structural_diagnosis/4.3_link_prediction/README.md)
  - [§4.4 Spectral bisection and bottleneck capacity](analysis/4_structural_diagnosis/4.4_spectral_bisection/README.md)
- [§5 N–1 Contingency Stress](analysis/5_n1_contingency/README.md)
- [§6 Upper Bound: A Topology-Optimal Grid](analysis/6_topology_optimal/README.md)

## Other

- [Visualization](visualization/README.md) — grid map of the constructed network
- [Appendix](appendix/README.md) — full inventory of scripts, data files, figures, and notebooks

## Project root

- [README.md](README.md) — original repo README
- [build_network.py](build_network.py) — constructs the graph from `nodes.csv` / `edges.csv`
- [analyze_network.py](analyze_network.py) — runs structural diagnostics
- [nodes.csv](nodes.csv), [edges.csv](edges.csv) — graph data
- [figures/](figures/) — all 10 generated PNGs
- [notebooks/](notebooks/) — `graph_simulations.ipynb`, `simulation.ipynb`
