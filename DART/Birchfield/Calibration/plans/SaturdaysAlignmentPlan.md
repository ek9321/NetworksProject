# Saturday's Alignment Plan: Fixing Topology Shape

## Problem Statement

The parameter sweep (commit cb292d6) found configurations that match **aggregate** metrics well:
- 345 kV best: m/n=1.564 (target 1.552), mean_degree=3.13 (target 3.10), error=0.0607
- 138 kV best: m/n=1.282 (target 1.282), mean_degree=2.56 (target 2.56), error=0.1674

But the generated topology has the wrong **shape**:
- Too many degree-1 nodes (spurs/stubs) and too few degree-3+ nodes (mesh/cycles)
- Line lengths too short (mean 34.3 km vs target 38.1 km at 345 kV)
- Insufficient meshing: the graph is tree-like where it should have loops

The aggregate mean degree can match while the **distribution** is wrong — e.g., many degree-1 and a few high-degree hubs average to 3.1, but the real grid has most nodes at degree 2-4.

---

## 1. Quantitative Gap Analysis

### 1.1 Data Sources

All data is already on disk:

| File | Contents |
|------|----------|
| `Calibration/outputs/sweep_results.csv` | 53 experiment rows with aggregate metrics |
| `Calibration/outputs/comparison_summary.csv` | Side-by-side Dartboard vs Texas-7k aggregates |
| `Calibration/outputs/sweep_lines/*.csv` | Per-experiment line CSVs (from_sub, to_sub, length_km, category, intersects) |
| `vatic/data/grids/Texas-7k/TX_Data/SourceData/branch.csv` | Texas-7k reference lines |
| `vatic/data/grids/Texas-7k/TX_Data/SourceData/bus.csv` | Texas-7k reference bus positions |

### 1.2 Key Gaps (345 kV, best sweep run `mn1.55_wint25_wd1.242_pr95.0`)

| Metric | Dartboard | Texas-7k | Gap |
|--------|-----------|----------|-----|
| m/n ratio | 1.564 | 1.552 | +0.8% |
| Mean degree | 3.13 | 3.10 | +1.0% |
| Max degree | 11 | 12 | -8.3% |
| Mean length (km) | 34.27 | 38.10 | -10.1% |
| Median length (km) | 26.35 | 29.74 | -11.4% |
| Intersection rate | 9.14% | 10.45% | -12.5% |

**Not yet measured** (these are the shape metrics that matter):
- Degree distribution shape (fraction at each degree 1, 2, 3, 4, 5+)
- Meshedness coefficient (cycles / max possible cycles)
- Fraction of degree-1 nodes (leaf/spur fraction)
- Line length distribution (histogram shape, not just mean/median)
- Category breakdown in final topology (MST vs Delaunay vs neighbor fractions)

---

## 2. Extended Metrics Framework

Add these functions to `Calibration/network_stats.py`. Each returns a simple dict or float that can be serialized to CSV.

### 2.1 Degree Distribution Shape

```python
def compute_degree_distribution(network: Network) -> Dict[int, float]:
    """Return {degree: fraction_of_nodes} for degrees 1..max.

    Usage: compare Dartboard distribution vs Texas-7k distribution.
    Key diagnostic: if Dartboard has too many degree-1 nodes, the topology
    is too tree-like (spurs instead of mesh).
    """
```

**Key derived scalars** (for CSV columns):
- `deg1_frac`: fraction of nodes with degree 1 (leaf nodes / spurs)
- `deg2_frac`: fraction of nodes with degree 2 (pass-through)
- `deg3plus_frac`: fraction of nodes with degree >= 3 (branching / mesh)
- `degree_entropy`: Shannon entropy of the degree distribution (higher = more spread)

### 2.2 Meshedness Coefficient

```python
def compute_meshedness(network: Network) -> float:
    """Meshedness = (m - n + 1) / (2n - 5) for a connected planar graph.

    Range: 0 = tree, 1 = maximally planar.
    For disconnected graphs, compute per component and weight by node count.

    This is the single most important shape metric: it measures how many
    independent cycles exist relative to the theoretical maximum.
    """
```

**Key derived scalar**: `meshedness` (float, 0-1)

### 2.3 Line Length Distribution Distance

```python
def compute_length_histogram_distance(
    network: Network,
    reference_lengths: List[float],
    n_bins: int = 20,
) -> float:
    """Earth Mover's Distance (or histogram intersection) between the
    generated and reference line length distributions.

    Returns a scalar distance (lower = more similar distributions).
    Uses numpy histogram + scipy wasserstein_distance.
    """
```

**Key derived scalar**: `length_emd` (float, lower is better)

### 2.4 Category Breakdown

```python
def compute_category_breakdown(edges_with_category: List[dict]) -> Dict[str, float]:
    """Return {category: fraction} from line CSVs that include a 'category' column.

    Categories: mst, delaunay, neighbor_2, neighbor_3.
    Compare actual fractions vs TopologyConfig quota targets.
    """
```

**Key derived scalars**: `cat_mst_frac`, `cat_delaunay_frac`, `cat_neighbor2_frac`, `cat_neighbor3_frac`

### 2.5 Updated NetworkStats Dataclass

Add new fields to `NetworkStats`:

```python
@dataclass
class NetworkStats:
    # existing
    num_nodes: int
    num_edges: int
    mn_ratio: float
    degree_stats: DegreeStats
    length_stats: LengthStats
    intersection_rate: float
    # new
    meshedness: float
    deg1_frac: float
    deg2_frac: float
    deg3plus_frac: float
    degree_entropy: float
```

### 2.6 Implementation Notes

- `scipy.stats.wasserstein_distance` for length EMD (already a dependency)
- Meshedness uses Euler's formula: independent cycles = m - n + c (c = connected components)
- All new metrics are O(n+m) except intersection_rate which is already O(m^2)
- No new dependencies needed

---

## 3. Infrastructure Updates to `parameter_sweep.py`

### 3.1 Add New Columns to `sweep_results.csv`

In `parameter_sweep.py`, after computing `stats = compute_network_stats(net)`, also compute and record:

```python
row = {
    # ... existing columns ...
    # New shape metrics
    "meshedness": round(stats.meshedness, 4),
    "deg1_frac": round(stats.deg1_frac, 4),
    "deg2_frac": round(stats.deg2_frac, 4),
    "deg3plus_frac": round(stats.deg3plus_frac, 4),
    "degree_entropy": round(stats.degree_entropy, 4),
}
```

### 3.2 Add New Columns to TARGETS

Compute Texas-7k reference values for the new metrics and add to `TARGETS`:

```python
TARGETS: Dict[str, Dict[str, float]] = {
    "345": {
        # ... existing ...
        "meshedness": <compute from Texas-7k 345 kV>,
        "deg1_frac": <compute from Texas-7k 345 kV>,
        "deg3plus_frac": <compute from Texas-7k 345 kV>,
    },
    "138": {
        # ... existing ...
        "meshedness": <compute from Texas-7k 138 kV>,
        "deg1_frac": <compute from Texas-7k 138 kV>,
        "deg3plus_frac": <compute from Texas-7k 138 kV>,
    },
}
```

**Action**: Write a one-off script `Calibration/compute_reference_targets.py` that loads the Texas-7k network, computes all new metrics, and prints the values for pasting into TARGETS.

### 3.3 Update `_score_vs_target()`

Add new metrics to the error score with appropriate weights:

```python
def _score_vs_target(stats: NetworkStats, target_key: str) -> float:
    t = TARGETS[target_key]
    errors = []
    # existing
    if t["mn_ratio"] > 0:
        errors.append(abs(stats.mn_ratio - t["mn_ratio"]) / t["mn_ratio"])
    if t["mean_degree"] > 0:
        errors.append(abs(stats.degree_stats.mean_degree - t["mean_degree"]) / t["mean_degree"])
    if t["mean_length_km"] > 0:
        errors.append(abs(stats.length_stats.mean_km - t["mean_length_km"]) / t["mean_length_km"])
    if t["intersection_rate"] > 0:
        errors.append(abs(stats.intersection_rate - t["intersection_rate"]) / t["intersection_rate"])
    # new shape metrics (weight 2x since these are the critical gaps)
    if t.get("meshedness", 0) > 0:
        errors.append(2.0 * abs(stats.meshedness - t["meshedness"]) / t["meshedness"])
    if t.get("deg1_frac", 0) > 0:
        errors.append(2.0 * abs(stats.deg1_frac - t["deg1_frac"]) / t["deg1_frac"])
    if t.get("deg3plus_frac", 0) > 0:
        errors.append(2.0 * abs(stats.deg3plus_frac - t["deg3plus_frac"]) / t["deg3plus_frac"])
    return sum(errors) / len(errors) if errors else 999.0
```

### 3.4 Add ExperimentConfig Fields for New Parameters

As experiments below introduce new parameters (degree penalty, quota overrides, etc.), add corresponding fields to `ExperimentConfig` and `_build_topology_config()`.

---

## 4. Experiments

All experiments target 345 kV first (259 nodes, ~4 seconds per run). Only the best configuration from each experiment propagates to 138 kV.

### Experiment 0: Baseline Measurement with Extended Metrics

**Goal**: Establish quantitative baseline for all new metrics on the best existing sweep run and on Texas-7k reference.

**Hypothesis**: The degree-1 fraction in Dartboard is significantly higher than Texas-7k, and meshedness is significantly lower.

**Actions**:
1. Implement all functions from Section 2 in `Calibration/network_stats.py`
2. Write `Calibration/compute_reference_targets.py` to compute Texas-7k values
3. Run it, record reference values
4. Re-run best sweep config (`mn1.55_wint25_wd1.242_pr95.0`) with extended metrics
5. Record gap table

**Code changes**: `Calibration/network_stats.py` (add functions), `Calibration/compute_reference_targets.py` (new file)

**Success metric**: All new metrics computed without error. Gap table shows degree distribution and meshedness differences.

**Depends on**: Nothing.

---

### Experiment 1: Degree-Aware Scoring (Spur Suppression)

**Goal**: Reduce degree-1 fraction by penalizing candidates that would create or maintain leaf nodes.

**Hypothesis**: The scoring function (`_compute_score_cheap` at `core/topology_generation.py:572-614`) currently has no penalty for creating degree-1 nodes. Adding a penalty will shift edges away from spurs and toward forming cycles.

**Mechanism**: In `_compute_score_cheap()`, after the connectivity check (line 590-595), add:

```python
# Degree-balancing penalty: penalize candidates where BOTH endpoints
# already have degree >= threshold (concentrates edges on hubs) OR
# where adding this edge still leaves an endpoint at degree 1
# (i.e., the other endpoint already has degree >= 2, creating a stub)

# Bonus for connecting to low-degree nodes (encourages mesh fill-in)
if degree_i == 1 and degree_j >= 2:
    score += config.w_deg1_bonus  # new param
if degree_j == 1 and degree_i >= 2:
    score += config.w_deg1_bonus

# Penalty for creating excessively high-degree hubs
if degree_i >= config.max_preferred_degree and degree_j >= config.max_preferred_degree:
    score -= config.w_hub_penalty  # new param
```

**New TopologyConfig parameters**:
- `w_deg1_bonus: float` — bonus for connecting to a degree-1 node (default 0, sweep [50, 100, 200])
- `w_hub_penalty: float` — penalty when both endpoints already have degree >= max_preferred_degree (default 0, sweep [50, 100, 200])
- `max_preferred_degree: int` — degree above which hub penalty applies (default 5, sweep [4, 5, 6])

**Parameter space** (345 kV only): 3 x 3 x 3 = 27 configs.
Hold fixed: `target_mn_ratio=1.55, w_intersect=25, w_dist=1.242, distance_prune_percentile=95.0`

**Code changes**: `core/topology_generation.py` (TopologyConfig + _compute_score_cheap), `Calibration/parameter_sweep.py` (ExperimentConfig + sweep grid)

**Success metric (computable)**:
- `deg1_frac` decreases by >= 20% relative to Experiment 0 baseline
- `meshedness` increases
- `error_score` (updated with shape metrics) decreases

**Depends on**: Experiment 0 (need baseline values and extended metrics).

---

### Experiment 2: Quota Rebalancing (More Delaunay, Less MST)

**Goal**: Shift the category mix to produce more mesh edges (Delaunay, neighbor_2) and fewer tree edges (MST).

**Hypothesis**: The default quotas (MST 50%, Delaunay 20%, neighbor_2 25%, neighbor_3 5%) over-represent MST edges, which are by definition tree edges that cannot create cycles. Shifting quota toward Delaunay and neighbor_2 will increase meshedness.

**Mechanism**: Sweep quota parameters in `TopologyConfig` (lines 82-85):

**Parameter space**:
| Config | quota_mst | quota_delaunay | quota_neighbor_2 | quota_neighbor_3 |
|--------|-----------|----------------|-------------------|-------------------|
| baseline | 0.50 | 0.20 | 0.25 | 0.05 |
| shift_1 | 0.35 | 0.30 | 0.30 | 0.05 |
| shift_2 | 0.25 | 0.35 | 0.30 | 0.10 |
| shift_3 | 0.20 | 0.40 | 0.30 | 0.10 |
| no_quota | (disable category penalty entirely: set w_cat=0) | | | |

5 configs at 345 kV.
Hold fixed: best config from Experiment 1 (or baseline if Exp 1 fails).

**Code changes**: `Calibration/parameter_sweep.py` (sweep grid with quota overrides), `core/topology_generation.py` (add quota params to ExperimentConfig passthrough if not already)

**Success metric (computable)**:
- `meshedness` increases by >= 10% relative to Experiment 1 best
- `cat_mst_frac` in output lines decreases
- `deg1_frac` does not regress

**Depends on**: Experiment 1 (use best degree-penalty config as base).

---

### Experiment 3: Distance Weight Tuning (Fix Short Lines)

**Goal**: Increase mean and median line length to match Texas-7k.

**Hypothesis**: The distance penalty `w_dist=1.242` (per km) is too aggressive — it over-selects short edges. Reducing it (or switching to a sublinear penalty like `w_dist * sqrt(length)`) will allow longer lines to survive scoring.

**Mechanism**: Two approaches to test:

**Approach A — Reduce w_dist** (simpler):
Sweep `w_dist` in [0.4, 0.6, 0.8, 1.0, 1.242] with best config from Exp 2.

**Approach B — Sublinear distance penalty** (targets distribution shape):
Replace the linear penalty in `_compute_score_cheap()` line 577:
```python
# Current: score -= self.config.w_dist * candidate.length_km
# Proposed: score -= self.config.w_dist * (candidate.length_km ** self.config.dist_exponent)
```
New param: `dist_exponent: float` — sweep [0.5, 0.7, 1.0]

**Combined space**: 5 (w_dist values) x 3 (exponents) = 15 configs at 345 kV. Or if Approach A alone closes the gap, skip Approach B.

**Code changes**: `core/topology_generation.py` (TopologyConfig + _compute_score_cheap line 577), `Calibration/parameter_sweep.py` (sweep grid)

**Success metric (computable)**:
- `mean_length_km` within 5% of Texas-7k target (38.1 km)
- `median_length_km` within 10% of target (29.74 km)
- `length_emd` (if computed) decreases vs Experiment 2 best

**Depends on**: Experiment 2 (use best quota config as base).

---

### Experiment 4: Connectivity Bonus Decay

**Goal**: Prevent the connectivity bonus from dominating scoring throughout the entire run.

**Hypothesis**: `w_conn_v=300` and `w_conn_overall=1000` are very large relative to the distance penalty (~1.2/km * 30km = ~36). In early iterations they correctly prioritize connecting components, but once the graph is connected, they still reward connecting degree-0 nodes at any distance, creating long spurs. Decaying the bonus after connectivity is achieved should improve shape.

**Mechanism**: In `_iteration_loop()` (around line 480), after checking connectivity:

```python
# After K edges are added, check if graph is connected
if self._is_connected():
    # Decay connectivity weights (one-time or per-iteration)
    self.config.w_conn_v = max(self.config.w_conn_v * 0.5, 50)
    self.config.w_conn_overall = max(self.config.w_conn_overall * 0.5, 100)
```

**Parameter space**:
- `conn_decay_factor`: [0.3, 0.5, 0.7] — multiplicative decay per iteration after connected
- `conn_floor_v`: [0, 25, 50] — minimum w_conn_v value
- `conn_floor_overall`: [0, 50, 100] — minimum w_conn_overall value

9 configs at 345 kV. Use best config from Experiment 3 as base.

**Code changes**: `core/topology_generation.py` (TopologyConfig + _iteration_loop), `Calibration/parameter_sweep.py` (sweep grid)

**Success metric (computable)**:
- `deg1_frac` further decreases
- `max_length_km` decreases (fewer long spur lines)
- `meshedness` does not regress

**Depends on**: Experiment 3 (use best distance config as base).

---

### Experiment 5: Distance Prune Percentile + K Tuning

**Goal**: Explore whether the candidate pool and batch size affect topology shape.

**Hypothesis**: `distance_prune_percentile=95` removes 5% of the longest candidates, which may include legitimate long-haul lines. `K_per_iteration=5` (or n//100) means many short lines get selected before long ones get a chance.

**Mechanism**:
- `distance_prune_percentile`: sweep [90, 95, 98, 100]
- `K_per_iteration`: sweep [1, 3, 5, 10]

16 configs at 345 kV. Use best config from Experiment 4 as base.

**Code changes**: `Calibration/parameter_sweep.py` only (these are already TopologyConfig params)

**Success metric (computable)**:
- `mean_length_km` improves toward target
- `error_score` (with shape metrics) is lowest seen

**Depends on**: Experiment 4 (use best connectivity decay config as base).

---

## 5. Execution Order

```
Experiment 0: Baseline Measurement
    |
    v
Experiment 1: Degree-Aware Scoring
    |
    v
Experiment 2: Quota Rebalancing
    |
    v
Experiment 3: Distance Weight Tuning
    |
    v
Experiment 4: Connectivity Bonus Decay
    |
    v
Experiment 5: Distance Prune + K Tuning
    |
    v
Final: Re-run winner at 138 kV
```

Each experiment:
1. Reads best config from previous experiment
2. Defines its own parameter grid
3. Runs sweep at 345 kV only (~4s per run)
4. Records all metrics (old + new) to sweep_results.csv
5. Identifies best config by `error_score`
6. Reports gap table vs Texas-7k reference

The final winner runs at 138 kV (one run, ~40s) to verify generalization.

### Time Estimate

| Experiment | Configs | Time @ 345 kV (~4s each) |
|------------|---------|--------------------------|
| 0 | 2 | ~10s (compute reference + 1 run) |
| 1 | 27 | ~2 min |
| 2 | 5 | ~20s |
| 3 | 15 | ~1 min |
| 4 | 9 | ~36s |
| 5 | 16 | ~1 min |
| Final 138 kV | 1 | ~40s |
| **Total** | **75** | **~6 min** |

---

## 6. Detailed File Change Summary

### Files to modify:

1. **`Calibration/network_stats.py`** — Add:
   - `compute_degree_distribution(network) -> Dict[int, float]`
   - `compute_meshedness(network) -> float`
   - `compute_length_histogram_distance(network, reference_lengths, n_bins) -> float`
   - `compute_category_breakdown(edges_with_category) -> Dict[str, float]`
   - Update `NetworkStats` dataclass with new fields
   - Update `compute_network_stats()` to populate new fields

2. **`Calibration/parameter_sweep.py`** — Add:
   - New fields to `TARGETS` (after computing reference values)
   - New columns in `row` dict
   - Updated `_score_vs_target()` with shape metrics
   - New fields to `ExperimentConfig` (for quota overrides, degree penalty, etc.)
   - Updated `_build_topology_config()` to pass new params
   - New experiment grid functions per experiment

3. **`core/topology_generation.py`** — Add:
   - New fields to `TopologyConfig` (w_deg1_bonus, w_hub_penalty, max_preferred_degree, dist_exponent, conn_decay_factor, conn_floor_v, conn_floor_overall)
   - Degree-penalty logic in `_compute_score_cheap()` (Experiment 1)
   - Sublinear distance option in `_compute_score_cheap()` (Experiment 3)
   - Connectivity decay logic in `_iteration_loop()` (Experiment 4)

### New files:

4. **`Calibration/compute_reference_targets.py`** — One-off script to compute Texas-7k extended metrics

### Files NOT modified:
- `Calibration/network_io.py` — no changes needed
- All pipeline files — untouched
- All config YAML files — untouched

---

## 7. Validation Criteria

The plan succeeds when the best configuration achieves **all** of the following at 345 kV:

| Metric | Target | Tolerance |
|--------|--------|-----------|
| m/n ratio | 1.552 | +/- 2% |
| Mean degree | 3.10 | +/- 3% |
| Mean length (km) | 38.10 | +/- 10% |
| Intersection rate | 10.45% | +/- 30% |
| Meshedness | (Texas-7k value) | +/- 20% |
| deg1_frac | (Texas-7k value) | +/- 30% |
| deg3plus_frac | (Texas-7k value) | +/- 20% |

All metrics are computable from CSV data. No visual inspection needed.
