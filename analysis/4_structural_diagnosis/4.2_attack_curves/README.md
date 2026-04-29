# §4.2 Attack curves

Following Albert–Barabási–Jeong, we track the giant connected component as
nodes are removed under five strategies: random, highest degree, highest
betweenness, highest eigenvector centrality, and highest population-weighted
load. The grid is roughly 4× more vulnerable to degree-targeted removal than
to random failure (f* = 0.05 vs. 0.21). Population-weighted removal is the
*least* effective attack — high-load substations in DFW and Houston are
well-meshed precisely because they serve dense populations.

A configuration-model null with the same degree sequence is included for
context, with the caveat that such nulls ignore geographic embedding and so
flag any real spatial network as pathological.

## Figures

- [figures/04_resilience_targeted_vs_random.png](../../../figures/04_resilience_targeted_vs_random.png) —
  GCC fraction vs. fraction of nodes removed, all five strategies
- [figures/06_random_graph_comparison.png](../../../figures/06_random_graph_comparison.png) —
  ERCOT vs. configuration-model nulls
- [figures/06_robustness_analysis.png](../../../figures/06_robustness_analysis.png) —
  robustness summary

## Code

- [analyze_network.py](../../../analyze_network.py) — attack-curve and
  null-model computation

## Related

- [§4.1 Articulation points](../4.1_articulation_points/README.md)
- [§6 Topology-Optimal Grid](../../6_topology_optimal/README.md) — uses the
  same attack curves to compare real vs. cost-equivalent optimal grid
