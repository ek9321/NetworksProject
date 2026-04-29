# Appendix — Full Inventory

Every script, data file, notebook, and figure in the repo, with the paper
section that uses it. Nothing has been moved; all links point back to the
original location at the repo root.

## Scripts

| File | Used by |
|------|---------|
| [build_network.py](../build_network.py) | §3 Network Construction |
| [analyze_network.py](../analyze_network.py) | §4.1, §4.2, §4.4, §5, §6 |

## Data

| File | Used by |
|------|---------|
| [nodes.csv](../nodes.csv) | §3, §4, §5, §6 |
| [edges.csv](../edges.csv) | §3, §4, §5, §6 |

## Notebooks

| File | Used by |
|------|---------|
| [notebooks/graph_simulations.ipynb](../notebooks/graph_simulations.ipynb) | §4.3 Link prediction & simulated trips |
| [notebooks/simulation.ipynb](../notebooks/simulation.ipynb) | §4.3 (earlier prototype) |

## Figures

| File | Used by |
|------|---------|
| [figures/01_degree_distribution.png](../figures/01_degree_distribution.png) | §3 / §4 (degree statistics) |
| [figures/02_betweenness_map.png](../figures/02_betweenness_map.png) | §4.1 Articulation points |
| [figures/03_centrality_distributions.png](../figures/03_centrality_distributions.png) | §4 (centrality summary) |
| [figures/03_zones_vs_communities.png](../figures/03_zones_vs_communities.png) | §4.4 Spectral bisection |
| [figures/04_ego_network_visualization.png](../figures/04_ego_network_visualization.png) | §4.3 Link prediction |
| [figures/04_resilience_targeted_vs_random.png](../figures/04_resilience_targeted_vs_random.png) | §4.2 Attack curves |
| [figures/05_grid_map.png](../figures/05_grid_map.png) | §3 / Visualization |
| [figures/05_link_prediction_top10.png](../figures/05_link_prediction_top10.png) | §4.3 Link prediction |
| [figures/06_random_graph_comparison.png](../figures/06_random_graph_comparison.png) | §4.2 Attack curves |
| [figures/06_robustness_analysis.png](../figures/06_robustness_analysis.png) | §4.2 Attack curves |
| [output.png](../output.png) | misc / debug output from `build_network.py` |

## Other

- [README.md](../README.md) — original repo README
- [DART/](../DART/) — Dartboard sub-project (network construction precursor;
  see Acknowledgments in the paper)
