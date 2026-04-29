# §4.1 Articulation points and population at risk

Among the 3,000 non-synthetic substations, 352 are articulation points — nodes
whose removal disconnects the graph. Nearly all are 138 kV substations in the
Houston metropolitan area, where radial sub-transmission runs from the 345 kV
network out to urban and suburban pockets. Each one strands downstream load on
failure.

The V3 bridge ratio of 14.4% is the load-bearing input here: V1/V2 pipelines
(66%) would have over-counted articulation points; ignoring synthetic junctions
(0%) would have under-counted them.

## Figure

- [figures/02_betweenness_map.png](../../../figures/02_betweenness_map.png) —
  betweenness centrality map; high-betweenness nodes overlap heavily with the
  articulation-point set

## Code

- [analyze_network.py](../../../analyze_network.py) — articulation-point and
  centrality computation

## Related

- [§4.2 Attack curves](../4.2_attack_curves/README.md)
- [§5 N–1 Contingency Stress](../../5_n1_contingency/README.md) — 13 of the 199
  sampled contingencies islanded load by removing exactly these articulation
  edges
