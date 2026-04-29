# §3 Network Construction

How the ERCOT transmission graph (3,786 nodes — 3,000 real substations plus
786 synthetic split junctions — and 4,817 branches) was built from public data:
OpenStreetMap (topology), ERCOT MORA April 2026 (generators), and Census 2020
(population-weighted load).

The pipeline projects every substation onto every line geometry, splits lines
within 50 m of a substation, snaps remaining endpoints within 500 m, and
constructs synthetic T-junctions where unsnapped ends sit within 150 m of each
other.

## Figure

- [figures/05_grid_map.png](../../figures/05_grid_map.png) — geographic plot of
  the constructed graph

## Code and data

- [build_network.py](../../build_network.py) — V3 topology extractor
- [nodes.csv](../../nodes.csv) — node table (substations + synthetic junctions)
- [edges.csv](../../edges.csv) — branch table with voltage tier and length

## Subsections

- §3.1 Data — OSM, ERCOT MORA, Census 2020
- §3.2 Topology extraction — V3 pipeline
- §3.3 Load and generation — population-weighted allocation, four-stage
  generator matching

## Related

- [Visualization](../../visualization/README.md)
- [§4 Structural Diagnosis](../4_structural_diagnosis/README.md) — uses this graph
