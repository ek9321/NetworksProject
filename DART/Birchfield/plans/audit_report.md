# Birchfield Algorithm Implementation Audit Report

**Region**: Texas 345 kV
**Date**: 2026-02-13
**Scope**: Parts 1, 2, 4, 5, 6 (code audit, no experiments)

---

## PART 1 — Structural Fidelity to Paper

### A. Candidate Edge Set

**Verdict: CORRECT with minor concern**

The implementation at `core/topology_generation.py:215-367` generates candidates via:

| Source | Method | Correctly Implemented |
|---|---|---|
| Delaunay triangulation | `scipy.spatial.Delaunay` on (lat, lng) | YES |
| MST | `scipy.sparse.csgraph.minimum_spanning_tree` on Delaunay-edge distances | YES |
| 2-neighbors | BFS-2 from Delaunay adjacency | YES |
| 3-neighbors | BFS-3 from Delaunay adjacency | YES |

No other edge sources are considered. Categories are mutually exclusive with correct priority: MST > Delaunay > neighbor_2 > neighbor_3 (lines 322-330).

**Counts (Texas 345 kV, n=197):**

| Category | Candidates | Final Lines | Final % | Target Quota |
|---|---|---|---|---|
| MST | 196 | 132 | 55.0% | 50% |
| Delaunay | 383 | 59 | 24.6% | 20% |
| neighbor_2 | variable | 41 | 17.1% | 25% |
| neighbor_3 | variable | 8 | 3.3% | 5% |
| **Total** | ~579+ | **240** | 100% | 100% |

**Minor concern**: Neighbor computation is capped at `max_neighbors_2 = min(n, 5000)` and `max_neighbors_3 = min(n, 3000)` (lines 268-269). For the 197-node Texas 345 kV network this is not binding. For the 1312-node 115 kV network it could truncate the candidate pool, particularly 3-neighbors.

### B. Penalty Structure

**Verdict: 5 of 6 terms correctly implemented. One term (`w_conn_overall`) is dead code.**

#### 1. Distance Penalty

```
score -= w_dist * length_km
```
- **w_dist** = 1.242 per km (paper: +2 per mile; 2/1.609 = 1.242). **CORRECT.**
- Applied at line 579.

#### 2. DC Flow Reward

```
score += w_dc * |flow_MW|
```
- **w_dc** = 0.5 (paper: -0.5 x Pest as penalty, sign-flipped to bonus). **CORRECT formula.**
- Applied at lines 512-516, but **only for top K*5 candidates** (see critical finding below).

#### 3. Delaunay Category Quota Penalty

```
if current_fraction > target + tolerance: score -= w_cat
```
- **w_cat** = 200. **CORRECT.**
- Applied at lines 598-610.

#### 4. Voltage-Level Connectivity Reward

```
if connects_two_components: score += w_conn_v
if either_node_isolated: score += w_conn_v
```
- **w_conn_v** = 300. **CORRECT.**
- Applied at lines 583-596.

#### 5. Overall Connectivity Reward

```python
w_conn_overall: float = 1000.0  # DEFINED at line 78
# NEVER REFERENCED in any scoring function
```

- **w_conn_overall = 1000 is DEAD CODE.** It is defined in `TopologyConfig` but never used in `_compute_score_cheap()` or anywhere else. Grep confirms: no reference outside the config definition, plan docs, and calibration config mirror.
- The plan (`TopologyGenerationAlgoPlan.md:117-120`) specifies this as a large bonus for "full-system connectivity under single-node removal." Its absence removes a 1000-point incentive that would have strongly favored edges that merge disconnected regions.

#### 6. Line Intersection Penalty

```
if intersects_existing_edge: score -= w_intersect
```
- **w_intersect** = 500. **CORRECT.**
- Applied at lines 505-509 (phase 2 only).

---

### Penalty Magnitude Table (Texas 345 kV)

Computed at three stages: iteration 0 (temp MST only), mid-process (~120 edges), and final network (240 edges).

#### Iteration 0 (temp MST only, no real edges)

| Term | Formula | Mean | Median | Max | Min |
|---|---|---|---|---|---|
| Distance penalty | -1.242 * km | -90.8 | -44.6 | -1208 | -1.2 |
| DC bonus (if evaluated) | +0.5 * MW | +78.4 | +39.9 | +1143 | ~0 |
| Category quota | -200 if over | 0 | 0 | -200 | 0 |
| Connectivity (per-V) | +300 | +300 | +300 | +600 | 0 |
| Connectivity (overall) | +1000 | **N/A (dead code)** | | | |
| Intersection | -500 | 0 | 0 | 0 | 0 |

#### Final Network (240 edges)

| Term | Formula | Mean | Median | Max | Min |
|---|---|---|---|---|---|
| Distance penalty | -1.242 * km | -46.7 | -29.1 | -313.5 | -3.7 |
| DC bonus | +0.5 * MW | +167.5 | +83.9 | +1556 | ~0 |
| Category quota | -200 if over | varies | | -200 | 0 |
| Connectivity (per-V) | +300 | 0 (connected) | 0 | +300 | 0 |
| Intersection | -500 | varies | | -500 | 0 |

**Key finding**: On added lines in the final network, the DC bonus (mean 167.5) exceeds the distance penalty (mean 46.7) by 3.6x. This appears to suggest DC flow is dominant — but see critical finding in Part 2 about why this is misleading.

---

## PART 2 — DC Power Flow Implementation Audit

### Standard DC PF: CORRECT

The implementation at `_build_base_dc_system()` (lines 390-445) correctly implements:

```
B[i,i] += 1/X_pu    B[i,j] -= 1/X_pu    (for each edge)
P_inj[i] = (gen_dispatch_i - load_i) / S_base_MVA
theta = B_reduced^{-1} * P_reduced         (slack bus 0 removed)
```

- Generation scaled so total_gen matches total_load: **CORRECT**
- Slack bus at index 0: **CORRECT**
- Sparse solve via `scipy.sparse.linalg.spsolve`: **CORRECT**

### Pest Calculation: CORRECT

```python
flow_pu = (theta[i] - theta[j]) / X_pu        # line 461
flow_mw = abs(flow_pu) * S_base_MVA            # line 462
```

- This is the standard DC power flow formula: P = dtheta / X.
- Units: theta in radians (from DC solve), X_pu in per-unit, result in per-unit, scaled by S_base to MW.
- **Multiplication/division is correct** (divides by X, not multiplies).
- The audit prompt's formula `Pest = xl * d21 * (theta2 - theta1)` is consistent only if `xl` denotes susceptance per unit length (b = 1/x), not reactance.

### Temporary MST Impedances

| Property | Specification | Implementation | Status |
|---|---|---|---|
| Added when disconnected | Yes | All MST edges added as temp at init | CORRECT |
| Initial impedance | c_init * median(X_pu) | 0.05 * median(X_pu) | CORRECT |
| Progressive weakening | X *= f_increase each iter | X *= 1.2 each iter | CORRECT |
| Removal when connected | Remove when graph connects | Only removes duplicates of real edges | DEVIATION |

The temp MST edges are never explicitly removed upon graph connectivity. Instead, they weaken exponentially. After 50 iterations: X_temp = 0.05 * median_X * 1.2^50 = 455 * median_X — effectively open circuit. This is functionally equivalent to removal, but takes many iterations.

### DC Flow Distribution (Iteration 0, temp MST only)

| Metric | Value |
|---|---|
| Theta range | [-0.15, +36.16] degrees |
| Theta std | 10.33 degrees |
| Max angle difference (any pair) | ~36 degrees |
| Mean Pest (all candidates) | 156.7 MW |
| Max Pest | 2285.9 MW |

### CRITICAL FINDING: Two-Phase Scoring Filters Long Lines Before DC Evaluation

The iteration loop (lines 469-565) uses a two-phase scoring architecture:

1. **Phase 1** (line 496-497): ALL remaining candidates scored with `_compute_score_cheap()` — includes distance penalty, connectivity bonus, and category penalty. **No DC flow.**
2. **Sort** by cheap score (line 499).
3. **Phase 2** (lines 504-516): Only the **top K*5 candidates** (25 for Texas 345 kV) get intersection checking and DC flow evaluation.

This means: **a candidate must rank in the top 25 by cheap score (distance-dominated) before its DC flow is ever computed.**

Long lines cannot compete on cheap score:

| Candidate | Cheap Score (no connectivity bonus) | Cheap Score (with +300) |
|---|---|---|
| 10 km line | -12.4 | +287.6 |
| 50 km line | -62.1 | +237.9 |
| 100 km line | -124.2 | +175.8 |
| 200 km line | -248.4 | +51.6 |

Once connectivity bonuses are exhausted (most nodes connected), long lines are simply excluded from the candidate pool that gets DC-evaluated.

**Even if long lines were DC-evaluated**, at iteration 0:

| Long candidates (>50 km) | Value |
|---|---|
| Count | 242 |
| Mean DC bonus | 51.55 |
| Mean distance penalty | 182.17 |
| DC/distance ratio (mean) | 0.369 |
| % where DC bonus > distance penalty | **9.5%** |

Only 9.5% of long candidates have DC flow strong enough to overcome their distance penalty. The DC weight (w_dc = 0.5) is too low to drive corridor formation for long lines.

---

## PART 4 — Voltage-Level Node Selection Audit

### Implementation (`core/voltage_partition.py:138-210`)

- **Selection weight**: `score = max(mw_load, total_gen_mw)` (line 180)
- **Sampling**: Weighted random without replacement (`numpy.random.choice` with `p=scores/sum`) (line 202)
- **Target**: 15% of substations (from `texas.yaml`)

### Results (Texas)

| Metric | Value |
|---|---|
| Total substations | 1312 |
| 345 kV substations | 197 (15.02%) |
| Selection bias | Proportional to max(load, gen) |

**Is probability proportional to load?** Partially. Score = max(load, gen), so both high-load AND high-generation nodes are preferentially selected. Generation-heavy Type B and Type g substations have equal or higher selection probability than pure-load Type A substations.

**Spatial distribution concern**: Since selection is weighted by max(load, gen), 345 kV nodes cluster where population and large generators are concentrated. For Texas, this means higher density in the Dallas-Fort Worth, Houston, San Antonio, and Austin metro corridors, with sparse coverage in West Texas.

This spatial distribution is reasonable for Texas but does NOT create the extreme load/generation separation needed for strong directional corridors. If 345 kV nodes are already co-located with their loads, there is less need for long-distance bulk transfer, and the DC flow signal is weaker.

---

## PART 5 — Iterative Selection Mechanics

### Lines per iteration

```python
K = max(self.config.K_per_iteration, self.n // 100)  # line 475
```

| Voltage | n | K |
|---|---|---|
| 345 kV | 197 | max(5, 1) = **5** |
| 115 kV | 1312 | max(5, 13) = **13** |

### Rescoring after each addition

- **Between iterations**: YES — all remaining candidates are fully rescored (line 497: `c.score = self._compute_score_cheap(c)`).
- **Within a batch of K**: NO — the K best are selected from the same scoring, then all added simultaneously (lines 523-535).

**Implication**: Within a batch, two candidates might both receive +300 connectivity bonus for connecting the same isolated node. Only the first truly earns it, but both get credited. This double-counting could add up to 300 * K = 1500 points of phantom connectivity bonus per iteration.

### Quota enforcement

Dynamic — uses `self.category_counts[candidate.category] / len(self.added_edges)` (lines 599-600), updated after each batch. Tolerance of 5% before penalty kicks in.

### Penalty recalculation

**Fresh each iteration** (not cumulative). Each call to `_compute_score_cheap()` computes all terms from scratch.

---

## PART 6 — Quantitative Corridor Diagnosis

### Line Length Distribution (Texas 345 kV)

| Metric | Dartboard-orig | Texas-7k | Dartboard-on-7k |
|---|---|---|---|
| Nodes | 197 | 259 | 259 |
| Edges | 240 | 402 | 320 |
| m/n | 1.218 | 1.552 | 1.236 |
| Mean length (km) | 37.58 | 38.10 | 31.76 |
| Median length (km) | 23.47 | 29.74 | 25.83 |
| 90th percentile (km) | 85.53 | — | — |
| 95th percentile (km) | 113.48 | — | — |
| Max length (km) | 252.41 | 188.55 | 182.12 |
| Intersection rate | 4.58% | 10.45% | 2.50% |

### Length Bucket Distribution

| Range (km) | Dartboard-orig |
|---|---|
| 0–10 | 49 (20.4%) |
| 10–20 | 58 (24.2%) |
| 20–30 | 36 (15.0%) |
| 30–50 | 33 (13.8%) |
| 50–75 | 32 (13.3%) |
| 75–100 | 12 (5.0%) |
| 100–150 | 15 (6.3%) |
| 150–300 | 5 (2.1%) |

### Edge Orientation Analysis

| Metric | Dartboard TX 345 kV |
|---|---|
| PCA eigenvalues | 0.1706, 0.1036 |
| Anisotropy ratio (major/minor) | **1.648** |
| Principal axis | -5.1 deg from E-W |

An anisotropy ratio of 1.648 indicates **near-isotropic** edge placement. For comparison, a network with strong east-west corridors would show anisotropy > 3.0.

### Orientation Histogram (all 240 lines)

```
  0- 15 deg:  24  ########################
 15- 30 deg:  21  #####################
 30- 45 deg:  23  #######################
 45- 60 deg:  17  #################
 60- 75 deg:  16  ################
 75- 90 deg:  22  ######################
 90-105 deg:  14  ##############
105-120 deg:  11  ###########
120-135 deg:  23  #######################
135-150 deg:  21  #####################
150-165 deg:  20  ####################
165-180 deg:  28  ############################
```

The distribution is essentially uniform. No preferred corridor direction.

### Long Lines (>50 km) Orientation

```
  0- 30 deg:  12
 30- 60 deg:  10
 60- 90 deg:  11
 90-120 deg:   5
120-150 deg:  12
150-180 deg:  14
```

Also near-uniform. Even long lines show no directional preference, confirming DC flow is not driving corridor formation.

### Diagnosis: What's Driving the Topology Differences?

| Factor | Evidence | Impact |
|---|---|---|
| **DC-driven** | DC bonus is large on added lines but long candidates never get DC-evaluated (two-phase filtering) | **PRIMARY** |
| **Geometric** | Distance penalty grows linearly; anisotropy = 1.648 (isotropic) | **PRIMARY** |
| **Quota-driven** | Quotas are approximately met (MST 55% vs 50% target) | **MINOR** |
| **Voltage assignment** | 345 kV selection is load/gen-weighted, reasonable spatial distribution | **CONTEXTUAL** |

---

## Deliverable

### 1. Numerical Diagnostic Summary

| Diagnostic | Value | Interpretation |
|---|---|---|
| Anisotropy ratio | 1.648 | Near-isotropic, no corridors |
| Long lines (>50 km) | 64 of 240 (26.7%) | Present but undirected |
| DC/distance ratio at iter 0 (long candidates) | 0.369 mean | DC too weak for long lines |
| % long candidates where DC > distance | 9.5% | Overwhelming majority dominated by distance |
| w_conn_overall usage | 0 (dead code) | Missing 1000-point corridor incentive |
| Theta range (iter 0) | [-0.15, 36.16] deg | Modest angle spread |
| Theta range (final network) | [-107, 525] deg | Unphysical (numerical instability) |

### 2. Why Long Corridors Are Suppressed

The absence of long directional corridors is caused by a **compound mechanism** involving three interacting defects:

1. **Two-phase scoring eliminates long candidates before DC evaluation.** The cheap score (phase 1) ranks all candidates by distance + connectivity. Long lines always lose on distance. Only the top K*5 = 25 candidates get DC flow computed. Long candidates with potentially high DC flow are systematically excluded from phase 2.

2. **DC weight is too low relative to distance penalty for long lines.** Even when DC flow IS computed for long candidates, at iteration 0 only 9.5% have DC bonus exceeding their distance penalty (mean DC/distance ratio = 0.369 for >50 km lines). The paper's w_dc = 0.5 is insufficient to overcome w_dist = 1.242 per km for lines beyond ~30 km unless angle differences are extreme.

3. **w_conn_overall = 1000 bonus is dead code.** This large connectivity bonus was designed to strongly incentivize edges that merge disconnected components — exactly the kind of long edges that form corridors. Its absence removes the single largest scoring term that would favor long lines.

### 3. Ranked List of Causes

| Rank | Cause | Mechanism | Fix Difficulty |
|---|---|---|---|
| **1** | Two-phase scoring architecture | Long candidates filtered before DC evaluation | Medium (expand phase 2 pool or apply DC to all) |
| **2** | `w_conn_overall = 1000` is dead code | Missing 1000-point bonus for component-merging edges | Easy (implement the scoring term) |
| **3** | DC weight too low for long lines | w_dc = 0.5 cannot overcome w_dist = 1.242/km beyond ~30 km | Easy (increase w_dc or decrease w_dist for long lines) |
| **4** | m/n ratio too low (1.22 vs 1.55 for Texas-7k) | Fewer total edges means fewer opportunities for long ties | Easy (increase target_mn_ratio to 1.55) |
| **5** | Intersection penalty too aggressive (w_intersect=500) | Suppresses crossing lines that form realistic corridor patterns | Easy (reduce to 25 per calibration) |
| **6** | Batch scoring within K (no inter-batch rescoring) | Double-counted connectivity bonuses for short lines | Low impact |

**Causes #1-#3 are the structural issues.** Causes #4-#5 are parameter issues already identified in the calibration study. Cause #6 is minor.

---

## Appendix: Code References

| Finding | File | Line(s) |
|---|---|---|
| w_conn_overall defined | `core/topology_generation.py` | 78 |
| w_conn_overall never used | `core/topology_generation.py` | (absent from 574-615) |
| Two-phase scoring | `core/topology_generation.py` | 496-519 |
| Top K*5 pool | `core/topology_generation.py` | 504 |
| DC flow fast estimation | `core/topology_generation.py` | 447-467 |
| Temp MST init | `core/topology_generation.py` | 368-388 |
| Temp MST weakening | `core/topology_generation.py` | 538 |
| Temp MST removal (duplicates only) | `core/topology_generation.py` | 543-553 |
| Cheap score function | `core/topology_generation.py` | 574-615 |
| Voltage selection weights | `core/voltage_partition.py` | 180 |
| Batch K computation | `core/topology_generation.py` | 475 |
