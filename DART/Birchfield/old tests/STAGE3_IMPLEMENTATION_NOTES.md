## Stage 3: Topology Generation - Implementation Notes

### Methodology

Implements the Birchfield et al. (2017) iterative line placement algorithm from
"Grid Structural Characteristics as Validation Criteria for Synthetic Networks" (IEEE Trans. Power Systems).

**Core module**: `core/topology_generation.py` → `TopologyGenerator` class  
**Pipeline scripts**: `pipelines/7_generate_topology.py` (batch), `pipelines/8_visualize_topology.py` (generate + visualize)

---

### Validated Results

#### New York (630 substations)

| Metric | 345 kV | 115 kV | Birchfield Target |
|--------|--------|--------|-------------------|
| Nodes | 94 | 630 | — |
| Lines | 115 | 774 | — |
| m/n ratio | 1.223 | 1.229 | 1.22 |
| Connected | ✅ | ✅ | ✅ |
| Intersection rate | 1.74% | 4.01% | ≤ 5% |
| Runtime | 0.5s | 18.2s | — |

#### Texas (1,312 substations)

| Metric | 345 kV | 115 kV | Birchfield Target |
|--------|--------|--------|-------------------|
| Nodes | 197 | 1,312 | — |
| Lines | 240 | 1,612 | — |
| m/n ratio | 1.218 | 1.229 | 1.22 |
| Connected | ✅ | ✅ | ✅ |
| Intersection rate | 4.58% | 3.23% | ≤ 5% |
| Runtime | 1.7s | 77.0s | — |

#### Category Quotas (Birchfield Table VI)

| Category | Target | NY 345 | NY 115 | TX 345 | TX 115 |
|----------|--------|--------|--------|--------|--------|
| MST | 50% | 54.8% | 54.9% | 55.0% | 54.7% |
| Delaunay | 20% | 28.7% | 25.6% | 24.6% | 25.6% |
| 2-neighbor | 25% | 14.8% | 16.1% | 17.1% | 18.2% |
| 3-neighbor | 5% | 1.7% | 3.4% | 3.3% | 1.6% |

---

### Algorithm Architecture

#### Two-Phase Scoring (Key Performance Optimization)

The naive Birchfield approach rescores ALL candidates (including expensive intersection checks and DC flow solves) every iteration. This is O(candidates × added_edges) per iteration, which becomes prohibitive at ~400+ edges.

Our implementation uses two-phase scoring per iteration:

1. **Phase 1 — Cheap scoring** (all candidates): Distance penalty + connectivity bonus + category quota penalty. O(1) per candidate.
2. **Phase 2 — Expensive refinement** (top K×5 only): Intersection check against all added edges. Then top K×3 get DC power flow estimation via sparse linear solve.

This reduces per-iteration cost from ~3 seconds to ~0.14 seconds for NY 115 kV.

#### Algorithm Flow

```
For each voltage level (345 kV, 115 kV) independently:

1. CANDIDATE GENERATION
   - Delaunay triangulation → edges categorized as 'delaunay'
   - Euclidean MST on Delaunay subgraph → 'mst' edges
   - 2nd-nearest & 3rd-nearest neighbors → 'neighbor_2', 'neighbor_3'
   - Distance pruning: 95th percentile threshold
     (MST edges EXEMPT — critical for connectivity)
   - Compute electrical parameters (X_pu, MVAmax) per candidate

2. TEMPORARY MST INITIALIZATION
   - Add temp MST edges with very low impedance (0.05 × median X_pu)
   - Ensures B matrix is invertible for DC flow from iteration 1
   - Impedances increase by ×1.2 each iteration; removed once real graph connects

3. ITERATIVE LINE PLACEMENT
   while added_edges < target_m:
     Phase 1: score = -w_dist × length_km + connectivity_bonus - quota_penalty
     Phase 2: top K×5 get intersection check (+w_intersect penalty)
              top K×3 get DC flow solve (+w_dc × P_estimated)
     Select top K candidates, add to graph
     Update node degrees (O(1) dict), union-find, temp MST impedances

4. VALIDATION
   - Verify graph connectivity (union-find)
   - Report m/n ratio, intersection rate, category quotas
```

#### Penalty Structure (Birchfield Table V)

| Penalty | Weight | Description |
|---------|--------|-------------|
| w_dist | +2/mile | Distance cost (converted from km internally) |
| w_dc | -0.5 × P_est | DC flow corridor incentive |
| w_cat | +200 | Category quota over-subscription penalty |
| w_conn_v | -300 | Connects two components or to radial node |
| w_conn_overall | -1000 | Would connect last two components |
| w_intersect | +500 | Geographic line crossing penalty |

---

### Key Implementation Decisions

#### 1. Line Parameters (115 kV vs 138 kV)
Used 138 kV parameters from `global.yaml` for the 115 kV level, per user instruction. Structural topology is unaffected.
- 115 kV: R=0.105, X=0.800, B=3.28e-06, MVA=174
- 345 kV: R=0.0393, X=0.653, B=6.02e-06, MVA=1082

#### 2. Voltage Level Independence
345 kV and 115 kV topologies generated completely independently — separate candidate generation, scoring, and iteration loops.

#### 3. MST Edge Protection
MST edges are **exempt** from the 95th-percentile distance pruning filter. Without this, long MST edges get pruned, the temp MST is incomplete, and the B matrix becomes singular (crashes the DC flow solver).

#### 4. Node Degree Tracking
Maintained via `self.node_degree` dict (O(1) lookup per candidate) rather than scanning all added edges each iteration.

#### 5. Temp MST Impedance Sync
The stored `self.temp_mst_edges` list is rebuilt each iteration after updating `self.temp_mst_X_pu`, ensuring the B matrix builder uses current impedance values.

#### 6. Category Quotas (Birchfield Table VI)
```yaml
quota_mst: 0.50       # 50% MST
quota_delaunay: 0.20   # 20% Delaunay
quota_neighbor_2: 0.25 # 25% 2-neighbor
quota_neighbor_3: 0.05 # 5% 3-neighbor
```

---

### Performance

| Network | Nodes | Lines | Runtime |
|---------|-------|-------|---------|
| NY 345 kV | 94 | 115 | 0.5s |
| NY 115 kV | 630 | 774 | 18.2s |
| TX 345 kV | 197 | 240 | 1.7s |
| TX 115 kV | 1,312 | 1,612 | 77.0s |

Total pipeline runtime: ~98s for both regions. Memory usage: < 50 MB per voltage level.

---

### Output Files

**Line CSVs** (`data/synthetic/<region>_lines_<voltage>kv.csv`):
- `from_sub`, `to_sub`: Substation IDs
- `voltage_kv`: 345 or 115
- `length_km`: Great-circle distance
- `category`: mst, delaunay, neighbor_2, neighbor_3
- `circuits`: 1 (default)
- `X_pu`: Per-unit reactance
- `MVAmax`: Thermal limit
- `intersects`: Boolean flag

**Visualizations** (`data/synthetic/<region>_topology_*.png`):
- Combined dual-voltage map
- Per-voltage detail maps color-coded by category

---

### References

- Birchfield et al., "Grid Structural Characteristics as Validation Criteria for Synthetic Networks," IEEE Trans. Power Systems, 2017
- `plans/TopologyGenerationAlgoPlan.md` — Detailed specification
- Table V: Penalty structure
- Table VI: Structural validation criteria and category quotas
