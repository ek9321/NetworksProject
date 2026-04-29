# §4.3 Unsupervised link prediction and simulated line trips

Jaccard coefficient and common-neighbors heuristics are used to propose new
edges; each candidate is then evaluated under a Monte-Carlo line-trip
simulation that assigns failure probability per edge as

    P_fail = 0.01 + 0.14 × [0.4(1 − V_norm) + 0.3 L_norm + 0.3(1 − C_norm)].

50 trials per candidate vs. 50 baseline trials. The headline finding is
counterintuitive: several top-ranked candidates make the grid *worse* under
the simulation — a possible Braess's-Paradox manifestation, though the
connectivity-improvement magnitudes are small enough that simulation noise is
the more likely explanation. Geography is also ignored, so candidates may not
be economically buildable.

## Figures

- [figures/05_link_prediction_top10.png](../../../figures/05_link_prediction_top10.png) —
  top-10 predicted links overlaid on the grid
- [figures/04_ego_network_visualization.png](../../../figures/04_ego_network_visualization.png) —
  ego-network view used in candidate inspection

## Notebooks

- [notebooks/graph_simulations.ipynb](../../../notebooks/graph_simulations.ipynb) —
  full link-prediction + Monte-Carlo simulation pipeline
- [notebooks/simulation.ipynb](../../../notebooks/simulation.ipynb) — earlier
  simulation prototype

## Related

- [§4.2 Attack curves](../4.2_attack_curves/README.md)
- [§6 Topology-Optimal Grid](../../6_topology_optimal/README.md) — alternative
  (geographically-aware, budget-constrained) candidate-edge selection
