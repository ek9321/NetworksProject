# Visualizer: Graph Topology & Voltage Toggle Plan

## Current State

`generate_visualizer.py` builds a simplified graph by:
1. Clustering all HV line endpoints within 150 m into "junctions"
2. Building a junction-to-junction graph from OSM line segment endpoints
3. BFS-contracting that graph: trace through non-substation junctions until reaching a
   substation junction (within SNAP_KM = 0.75 km of an OSM substation centroid)
4. Recording the resulting substation-to-substation edges

## Diagnosed Problems

### Problem 1 — Self-loops and spurious intra-complex edges

Large 345 kV switching yards are mapped as multiple separate OSM point features
a few hundred metres apart (main bus, auto-transformer bank, series-capacitor bay, etc.).
The BFS traces between them, creating self-loops and very short phantom edges:

```
0.08 km  345kV  'Mulberry Creek Substation' ↔ 'Mulberry Creek Substation'
0.12 km  345kV  'Big Hill Substation'        ↔ 'Big Hill Substation'
```

### Problem 2 — Snap radius too large for dense areas

SNAP_KM = 0.75 km means any junction within 750 m of substation A could snap to
substation B if B is slightly closer. Substations in Waco, Houston, etc. are often
300–700 m apart, well inside the ambiguity zone. The result is false connections
between substations that are not directly linked.

### Problem 3 — T-junction / split point topology lost in contraction

When the BFS contracts through non-substation junctions, a T-shaped branch:

```
  Substation A
       |
  (tower chain)
       |
   Junction X   ← real physical branch point, not a substation
      / \
     /   \
   Sub B  Sub C
```

…collapses to two direct edges A–B and A–C.  The straight-line simplified view
then draws two lines both departing from A toward B and C, giving the false
impression that A–B and A–C are two fully independent corridors.  The shared
infrastructure A→X is invisible.  Showing X as an explicit "split node" restores
topological accuracy.

### Problem 4 — 345 kV and 138 kV handled in one pass

138 kV is an order of magnitude denser, with more ambiguous OSM endpoint mapping.
Mixing them contaminates the cleaner 345 kV topology.

---

## Proposed Fix

### Step 1 — Deduplicate OSM substation features (intra-complex merging)

Before building the node set, cluster OSM substation features within **200 m of each
other at the same voltage tier** and keep only one representative per cluster.

- Prefer named features over unnamed; otherwise take the one with highest `osm_id`
  (most recently mapped, typically more accurate)
- Apply to all voltage tiers independently (a 345 kV feature 150 m from a 138 kV
  feature represents two separate bus sections, not a duplicate)

This removes the root cause of Problem 1 without any post-hoc edge filtering.

### Step 2 — Separate 345 kV+ and 138 kV passes

Process the two voltage tiers independently:

| Pass | Voltage filter | Junction CLUSTER_R | SNAP_KM |
|------|---------------|--------------------|---------|
| HV   | ≥ 345 kV      | 150 m              | 0.25 km |
| MV   | 115–230 kV    | 100 m              | 0.15 km |

The tighter snap for the HV pass exploits the fact that 345 kV substations are large
(well-mapped) and spaced kilometres apart.  A 250 m snap leaves a clear safety margin
against false-positive snaps while still reaching the centroid of any 345 kV station.

The MV pass is deferred until the HV pass is validated (Phase 2).

### Step 3 — Non-substation split nodes

After building the junction adjacency graph, identify every junction J that:
1. Does **not** snap to any substation within SNAP_KM (i.e. `J ∉ sub_juncs`)
2. Has **degree ≥ 3** in the junction adjacency graph

These are real physical branch points (T-junctions, tap points, bus sections mapped
mid-line).  Treat them as first-class nodes in the simplified graph:

- Include them in the **stop set** for BFS contraction (alongside substation junctions)
- Assign them output node indices continuing from the substation count
- Emit them as `split: true` node objects with `{i, lat, lon, kv}` fields

Edge building then produces the correct topology for the A→X→{B,C} case:
edges A–X, X–B, X–C instead of the spurious A–B, A–C.

**Geographic position of split nodes:**  each split junction's coordinates are the
cluster centroid of the converging line endpoints — a real geographic location on the
transmission corridor.  No inferred or synthetic positions.

**Rendering split nodes:**
- Small circle, radius 2 px regardless of voltage
- Fill: same voltage-tier colour as adjacent lines, opacity 0.5
- No popup (or one-line tooltip showing kV only)
- Separate Leaflet layer group `layerSplits`, toggleable independently

### Step 4 — Post-build edge filters (safety net)

Even after Steps 1–3, apply:
- Drop self-loops: `a == b`
- Drop edges shorter than **300 m** (intra-complex artefacts that slipped through
  deduplication)

### Step 5 — Voltage-level node toggles

Add controls to show/hide nodes at each voltage tier:

| Toggle ID | Tier       | Default |
|-----------|------------|---------|
| `togN345` | 345 kV+    | on      |
| `togN230` | 230 kV     | on      |
| `togN138` | 138–161 kV | on      |
| `togN115` | 115 kV     | on      |

Implemented as separate Leaflet `layerGroup` objects.

Add a **"Colour by"** radio selector in the panel:

| Mode           | Node colour meaning                        |
|----------------|--------------------------------------------|
| Match quality  | green/amber/orange/blue (current scheme)   |
| Voltage level  | violet(345)/blue(230)/teal(138)/cyan(115)  |

The voltage-level colour map reuses the existing line colours so nodes and their
connecting lines are visually consistent.

---

## Implementation Order

1. **Step 1** — Deduplicate intra-complex OSM features in `load_nodes()`
2. **Step 2** — Separate HV/MV junction passes in `process_lines()`; implement HV first
3. **Step 3** — Split node detection, output, and rendering
4. **Step 4** — Post-build edge filters
5. **Step 5** — Voltage toggle UI

All changes are confined to `ERCOT/generate_visualizer.py`.

---

## Key Numbers (current state, for reference)

| Metric | Value |
|--------|-------|
| OSM substations in ERCOT (≥115 kV, connected) | 3,306 |
| Graph edges total | 5,027 |
| Isolated nodes (0 edges) | 142 (4.3%) |
| Edges < 300 m (almost certainly artefacts) | 282 |
| 345 kV+ edges | 977 |
| 345 kV+ edges < 300 m | ~25 |
