# §4 Structural Diagnosis

Four topology-only diagnostics applied to the V3 graph. None uses power-flow
physics; each is imperfect, but together they converge on a consistent risk:
fragility concentrated in the Houston 138 kV sub-transmission and in a narrow
345 kV corridor between {North, West} and {Houston, South}.

## Subsections

- [§4.1 Articulation points and population at risk](4.1_articulation_points/README.md)
- [§4.2 Attack curves](4.2_attack_curves/README.md)
- [§4.3 Unsupervised link prediction and simulated line trips](4.3_link_prediction/README.md)
- [§4.4 Spectral bisection and bottleneck capacity](4.4_spectral_bisection/README.md)

## Code

- [analyze_network.py](../../analyze_network.py) — produces the centrality,
  attack-curve, and spectral metrics used in this section

## Related

- [§3 Network Construction](../3_network_construction/README.md) — input graph
- [§5 N–1 Contingency Stress](../5_n1_contingency/README.md) — physics-based
  follow-up to the topology-only findings here
