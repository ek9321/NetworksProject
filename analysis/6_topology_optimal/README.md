# §6 Upper Bound: A Topology-Optimal Grid

What would a fresh, topology-first design buy at the same total construction
cost ($88.8 B with 1.3× ROW multiplier)? Starting from the 3,000 real
substations, we generate Delaunay + 5-NN candidate edges (≤ 500 km), build a
geographic MST for connectivity, then greedily add edges in order of Δλ₂/cost
until the budget is exhausted. Voltage tier is assigned by distance: < 80 km
→ 138 kV; 80–300 km → 345 kV single; > 300 km → 345 kV double.

Headline result: the optimizer spends 82% of the budget on local 138 kV mesh
(vs. 35% in the real grid). Degree-targeted attack resilience f* ≈ doubles
(0.06 → 0.14); population-weighted resilience drops slightly (the optimizer
isn't given population). λ₂ improves ≈1.3× after fair node-count matching
(splits contracted), not the 3.2× headline.

The takeaway is *not* that ERCOT built the wrong grid — the optimizer ignores
wind export, voltage support, substation thermal limits, N–1, and dispatch.
The takeaway is the strategy: more 138 kV mesh in the Houston-area radial
sub-transmission, the same fix the targeted articulation-bypass ranking
identifies in §4.

## Figures

No dedicated figure in this folder; Fig 5 in the paper (real vs. optimal
attack curves) does not currently have a saved PNG in `figures/`.

## Code and data

- The greedy-optimization pipeline is currently part of the analysis flow but
  is not exported to a standalone script in the repo root yet. The
  load/generation inputs come from [nodes.csv](../../nodes.csv) and
  [edges.csv](../../edges.csv); Fiedler-vector machinery is in
  [analyze_network.py](../../analyze_network.py).

## Related

- [§4.4 Spectral bisection](../4_structural_diagnosis/4.4_spectral_bisection/README.md) —
  same λ₂ machinery, used here as the greedy objective
- [§7 Conclusion](../../PAPER_INDEX.md) — top-10 articulation-bypass upgrades
  recover most of the same gain for ~$45 M (29 km of new 138 kV line)
