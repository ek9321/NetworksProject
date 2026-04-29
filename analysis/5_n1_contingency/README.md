# §5 N–1 Contingency Stress

Single-step N–1 stress test on 200 sampled lines (top 100 by edge betweenness +
100 uniformly random). For each line we trip it, re-solve DC power flow once
on the reduced network, and record max overload ratio, # overloaded branches,
total MW-over-rating, and whether the trip islanded any load. We do *not*
iterate (the earlier cascade approach mis-ranked stress because the base-case
dispatch already overloaded 191 branches at t = 0).

The top 10 stress contributors are all 345 kV lines clustered in the Houston
network — the same region flagged by §4. Correlation of post-trip stress with
edge betweenness is r = +0.32 (modest, positive, as first principles expect).

Absolute MW-over-rating numbers (~30 GW) are inflated by the simplified
dispatch and should be read as *relative ranks*, not predictions.

## Figures

No dedicated figure in the paper. The Fiedler-bottleneck map in §4.4 (Fig 4
in the paper) is the closest geographic companion.

## Code and data

- [analyze_network.py](../../analyze_network.py) — DC power flow and N–1 sweep
- [nodes.csv](../../nodes.csv), [edges.csv](../../edges.csv) — graph inputs

## Related

- [§4.1 Articulation points](../4_structural_diagnosis/4.1_articulation_points/README.md) —
  the 13 islanding contingencies are exactly the articulation edges
- [§4.4 Spectral bisection](../4_structural_diagnosis/4.4_spectral_bisection/README.md) —
  top-stress lines fall on or near the Fiedler-cut bottleneck
