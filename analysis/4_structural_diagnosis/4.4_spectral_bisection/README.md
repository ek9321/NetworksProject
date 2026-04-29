# §4.4 Spectral bisection and bottleneck capacity

The graph Laplacian's second eigenvalue λ₂ = 0.001045 (algebraic connectivity)
indicates a low-conductance cut. The Fiedler vector partitions the graph by
sign, and the bipartition lines up cleanly with ERCOT's operational zones:
{North, West} on one side, {Houston, South} on the other. The cut is 2-way,
not 4-way; ~20 bottleneck edges (~20 GVA) mediate nearly all coupling between
the halves. This is the same Houston/South region flagged by §4.1 and §4.2.

## Figure

- [figures/03_zones_vs_communities.png](../../../figures/03_zones_vs_communities.png) —
  ERCOT operational zones vs. spectrally-detected communities

## Code

- [analyze_network.py](../../../analyze_network.py) — Laplacian construction,
  λ₂, and Fiedler-vector partition

## Related

- [§4.1 Articulation points](../4.1_articulation_points/README.md) — same
  geographic concentration
- [§5 N–1 Contingency Stress](../../5_n1_contingency/README.md) — top
  contingencies cluster on lines crossing this cut
- [§6 Topology-Optimal Grid](../../6_topology_optimal/README.md) — uses
  Δλ₂/cost as the greedy edge-selection criterion
