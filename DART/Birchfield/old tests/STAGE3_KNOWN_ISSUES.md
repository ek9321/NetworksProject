## Stage 3: Topology Generation — Resolved Issues

All issues from the initial implementation have been fixed. This file documents what was wrong and how it was resolved.

---

### Issue 1: Singular B Matrix (DC Flow Crash) — RESOLVED

**Problem**: MST edges were being pruned by the 95th-percentile distance filter. Long MST edges (needed for spanning connectivity) got removed, leaving the temporary MST incomplete. The resulting B matrix was singular, so `scipy.sparse.linalg.spsolve` failed and DC flow returned 0 everywhere.

**Fix**: MST edges are now exempt from distance pruning:
```python
if c.length_km <= prune_threshold or c.category == 'mst':
    # keep
```

---

### Issue 2: DC Flow Disabled — RESOLVED

**Problem**: Previous implementation commented out DC flow entirely with `# Skip DC flow for now (causing solver issues)`. This removed the corridor-identification incentive that is central to the Birchfield methodology.

**Fix**: DC flow re-enabled with two-phase scoring. Only the top K×3 candidates per iteration get a DC flow solve, making it affordable.

---

### Issue 3: O(n) Degree Lookup Per Candidate — RESOLVED

**Problem**: `_compute_score_fast` scanned all added edges to count each node's degree. With 774 added edges and ~2,900 remaining candidates, this was O(added × candidates) per iteration.

**Fix**: Replaced with `self.node_degree` dict (O(1) lookup). Updated on each edge addition.

---

### Issue 4: Intersection Check Bottleneck — RESOLVED

**Problem**: `_update_intersections()` checked ALL remaining candidates (~2,900) against ALL added edges per iteration — O(added × remaining) segment-segment intersection tests per iteration. At 400+ edges added, each iteration took ~3 seconds and growing.

**Fix**: Restructured to two-phase scoring:
- Phase 1: Score all candidates cheaply (no intersection check)
- Phase 2: Only top K×5 candidates (~30) get intersection checked
- Result: 0.14s per iteration instead of 3s+

---

### Issue 5: Wrong Category Quotas — RESOLVED

**Problem**: Config had `quota_mst: 0.20, quota_delaunay: 0.50` — inverted from the paper. MST edges were penalized too aggressively while Delaunay edges dominated. This caused the graph to not connect (isolated nodes joined only by long MST edges that got deprioritized).

**Fix**: Updated `config/global.yaml` to match Birchfield Table VI:
```yaml
quota_mst: 0.50
quota_delaunay: 0.20
quota_neighbor_2: 0.25
quota_neighbor_3: 0.05
```

---

### Issue 6: N-1 Enforcement Over-Aggressive — RESOLVED (by removal)

**Problem**: Previous implementation added a post-loop N-1 enforcement phase that tried to eliminate all articulation points by adding extra edges. For NY 345 kV (94 nodes), this added 71 extra edges, inflating m/n from 1.22 to 1.98.

**Fix**: Removed the N-1 enforcement phase. The corrected algorithm (with proper quotas and MST protection) naturally produces well-connected graphs without articulation point issues. The Birchfield paper does not prescribe N-1 enforcement as part of topology generation.

---

### Issue 7: Temp MST Impedance Not Synced — RESOLVED

**Problem**: `self.temp_mst_X_pu` was updated each iteration (×1.2), but the stored tuples in `self.temp_mst_edges` kept their original impedance values. The B matrix builder used stale impedances.

**Fix**: Rebuild the edge list each iteration:
```python
self.temp_mst_edges = [(i, j, self.temp_mst_X_pu) for i, j, _ in self.temp_mst_edges]
```

---

### Current Status

✅ All issues resolved  
✅ NY 345 kV: 94 nodes, 115 lines, m/n=1.223, connected, 1.7% intersections, 0.5s  
✅ NY 115 kV: 630 nodes, 774 lines, m/n=1.229, connected, 4.0% intersections, 17.6s  
✅ All metrics within Birchfield validation criteria
