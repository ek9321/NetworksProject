# HypothesesTestedOn2k: Testing High-Priority Hypotheses Against Birchfield's Own Network

## Motivation

We now have Birchfield's actual Texas2k_series2025 output — the 2000-bus synthetic case produced by the same team that wrote the algorithm. This is the ground truth for what the algorithm *should* produce. Comparing against Texas-7k was comparing apples to oranges (Hypothesis 1 confirmed: Texas-7k was never a Birchfield output).

**Texas2k reference statistics (from `Texas2k_series2025/texas2k_stats.txt`):**

| Metric | 500 kV | 230 kV | 115 kV |
|---|---|---|---|
| Substations | 182 | 197 | 1549 |
| Unique lines | 281 | 329 | 2566 |
| m/n ratio | 1.544 | 1.670 | 1.657 |
| Mean degree | 3.09 | 3.34 | 3.31 |
| Meshedness | 0.279 | 0.342 | 0.329 |
| deg1 fraction | 13.2% | 9.6% | 6.6% |
| deg3+ fraction | 58.2% | 62.9% | 64.4% |
| Mean length (km) | 55.7 | 37.2 | 17.1 |
| Median length (km) | 42.0 | 30.6 | 13.2 |

**Critical discovery:** Birchfield's own output has m/n = 1.54–1.67, NOT 1.22 as Table III of the paper suggests. The paper's 1.22 is an average over Eastern Interconnect utilities — the algorithm apparently targets higher ratios when generating a full synthetic case. This reframes all calibration work.

---

## Infrastructure: Texas2k Test Harness

### Step 0: Build Texas2k substation loader

**File to create:** `Calibration/texas2k_io.py`

Parse the Texas2k AUX file to extract substations and bus-to-substation mapping. Build `SubstationNode` objects compatible with `TopologyGenerator`.

```python
def load_texas2k_substations() -> list[SubstationNode]:
    """Load Texas2k substations from AUX file, return SubstationNode list.

    Parse:
    - AUX Substation block: Number, Name, Latitude, Longitude
    - AUX Bus block: Number, NomkV, SubNumber (bus-to-substation mapping)
    - RAW Generator block: bus number, Pgen (for total_gen_mw per substation)
    - RAW Load block: bus number, Pload (for mw_load per substation)

    Voltage mapping:
    - 500 kV buses → has_345kv = True (treat as HV level)
    - 230 kV buses → neither (we'll add a has_230kv flag or handle separately)
    - 115 kV buses → has_115kv = True

    A substation gets has_345kv=True if ANY of its buses is ≥ 300 kV.
    A substation gets has_115kv=True if ANY of its buses is in [100, 200) kV.
    """
```

**Also build:** `load_texas2k_reference_network(voltage_class: str) -> Network`
- Returns the reference topology (from RAW branch data) filtered by voltage class
- Uses `Calibration/network_io.py`'s `Network` / `NetworkEdge` types
- Voltage classes: `"500kv"` (buses ≥ 300 kV), `"230kv"` (200–299 kV), `"115kv"` (100–199 kV)

### Step 0b: Add 500 kV / 230 kV support to TopologyGenerator

**File:** `core/topology_generation.py`

The generator currently only handles `voltage_kv in {345, 115}`. For Texas2k we need:
- Accept `voltage_kv=500` → filter `has_345kv` (reuse the HV flag), use 500 kV line params
- Optionally accept `voltage_kv=230` with a new `has_230kv` flag
- Add `params_500kv` and `params_230kv` to `TopologyConfig` (or just reuse 345 kV params scaled by voltage ratio — impedance scales as V²)

**Simplest approach:** Map Texas2k's voltage levels onto the existing 345/115 framework:
- 500 kV → run as `voltage_kv=345` with `has_345kv=True` (182 subs, target m/n=1.544)
- 115 kV → run as `voltage_kv=115` with `has_115kv=True` (1549 subs, target m/n=1.657)
- 230 kV → defer (intermediate voltage, not in our current framework)

This avoids modifying the generator core. The line impedance params affect DC flow magnitude but not the relative ranking of candidates, so using 345 kV params for 500 kV is acceptable for calibration purposes.

---

## Experiment 1: Baseline on Texas2k Positions

**Hypothesis tested:** None — establishes the baseline gap.

**Procedure:**
1. Load Texas2k substations via `texas2k_io.py`
2. Run `TopologyGenerator` with default paper parameters:
   - `target_mn_ratio = 1.544` (matching Texas2k 500 kV reference)
   - All other params at Birchfield defaults (w_dist=1.242, w_dc=0.5, w_conn_v=300, w_conn_overall=1000, K=5)
   - DC flow **enabled**
3. Compute full metrics via `network_stats.py`: m/n, deg1_frac, deg3+_frac, meshedness, mean/median line length, degree entropy
4. Compare against Texas2k 500 kV reference

**Do the same for 115 kV:**
   - `target_mn_ratio = 1.657`
   - DC flow **enabled** (this is critical — we disabled it for Texas-7k 138 kV for speed, but we need it here)
   - K_per_iteration = 5 (paper default, not the inflated K=32 we used before)

**Success metric:** Quantify the baseline gap. This tells us how far off we are when running the algorithm faithfully on the correct type of spatial input.

**Expected runtime:** 500 kV ~30 sec, 115 kV with DC flow ~10–30 min (1549 nodes, DC solve is O(n²) per iteration). If 115 kV is too slow, run at K=5 but with a 60-minute timeout.

---

## Experiment 2: Fix "Radial Substation" Interpretation (Hypothesis 2)

**Hypothesis:** The paper's Table V says "-300 if segment connects to a radial substation." Our code gives +300 (w_conn_v) only when `degree == 0`. If "radial" means degree ≤ 1, the bonus should persist until degree 2, suppressing the spur factory.

**Code change in** `core/topology_generation.py`, `_compute_score_cheap()` (line ~622):

Current:
```python
if degree_i == 0 or degree_j == 0:
    score += self.config.w_conn_v
```

Change to:
```python
if degree_i <= 1 or degree_j <= 1:
    score += self.config.w_conn_v
```

**Procedure:**
1. Apply the one-line change
2. Run on Texas2k 500 kV positions with baseline config from Exp 1
3. Run on Texas2k 115 kV positions with baseline config from Exp 1
4. Compare deg1_frac, deg3+_frac, degree distribution shape against reference AND against Exp 1 baseline

**Success metric:** deg1_frac should drop. At 500 kV, target is 13.2% — if baseline has >15% and this drops to <15%, partial success. If it drops to <13%, strong success. At 115 kV, target is 6.6%.

**Rollback:** If deg1_frac drops too far (below target), this is over-correction. Can adjust to give partial bonus at degree 1 instead of full bonus.

---

## Experiment 3: Proper N-1 Connectivity Bonus (Hypothesis 4)

**Hypothesis:** `w_conn_overall = +1000` is applied when an edge merges two disconnected components (`_find(i) != _find(j)`). But the paper says this bonus is for "full system connectivity under single node removal" — i.e., eliminating articulation points (biconnectivity). Our implementation wastes the +1000 on the same condition as the +300 component-merge bonus.

The correct behavior: an edge that creates a cycle around an articulation point makes the graph more biconnected. These cycle-forming edges should get +1000. Currently they get +0 from connectivity.

**Code changes in** `core/topology_generation.py`:

### 3a. Add articulation point tracking

Add an incremental articulation point tracker to `TopologyGenerator`:
```python
def _find_articulation_points(self) -> set[int]:
    """Find articulation points in the current graph using Tarjan's algorithm.

    Returns set of node indices that are articulation points.
    O(V + E) via DFS.
    """
```

Call this once per iteration (after adding edges), cache the result. The set of articulation points changes as edges are added, but recomputing is O(V+E) which is fast for <2000 nodes.

### 3b. Separate the two connectivity bonuses

In `_compute_score_cheap()`:

```python
# Component-merge bonus (basic connectivity)
if self._find(idx_i) != self._find(idx_j):
    score += self.config.w_conn_v  # +300

# Biconnectivity bonus (N-1 robustness)
# Applied when edge creates a redundant path around an articulation point
elif idx_i in self._articulation_points or idx_j in self._articulation_points:
    score += self.config.w_conn_overall  # +1000
```

Key insight: the `elif` means this bonus ONLY applies to edges that do NOT merge components (both endpoints already connected). These are cycle-forming edges. The bonus fires when at least one endpoint is currently an articulation point — adding this edge creates a cycle that provides an alternative path, eliminating that articulation point.

### 3c. Update articulation points after each batch

After adding K edges per iteration, recompute `self._articulation_points`. This is O(V+E) ≈ O(n + m), fast enough.

**Procedure:**
1. Implement Tarjan's algorithm in `TopologyGenerator`
2. Separate the two connectivity bonuses as described
3. Run on Texas2k 500 kV and 115 kV
4. Compare against Exp 1 baseline and reference

**Success metric:** The +1000 bonus now incentivizes mesh-forming edges. We expect:
- Higher meshedness (more cycles)
- Lower deg1_frac (articulation points at spur tips get bonus for second edge)
- Degree distribution closer to reference
- Potentially more line intersections (mesh structure crosses more)

**This is the highest-impact architectural fix.** If it works, it explains why our topology was too tree-like despite having the correct m/n ratio.

---

## Experiment 4: Combined Fix (Experiments 2 + 3)

**Hypothesis:** The radial bonus fix (Exp 2) and biconnectivity bonus fix (Exp 3) address different but complementary problems. Together they should:
- Exp 2 prevents spur creation by keeping the w_conn_v bonus active until degree 2
- Exp 3 incentivizes cycle formation by correctly applying w_conn_overall

**Procedure:**
1. Apply both fixes simultaneously
2. Run on Texas2k 500 kV and 115 kV
3. Full metric comparison against reference

**Success metric:** Combined error (weighted sum of metric deviations) should be lower than either fix alone.

---

## Experiment 5: DC Flow at 115 kV with K=5 (Hypothesis 7 / User Flag)

**Hypothesis:** DC flow was disabled at 138 kV in prior calibration runs for speed. But DC flow is the only mechanism that creates long-distance corridor structure. Without it, line selection is purely distance + connectivity, which strongly favors short local connections.

The Texas2k 115 kV network has 1549 substations — significantly more than our Texas-7k 138 kV (3270 substations). This makes DC flow more tractable. With K=5 (not K=32), runtime should be manageable.

**Procedure:**
1. Run Exp 4's combined fix on Texas2k 115 kV with DC flow **enabled** and K=5
2. Set a 60-minute timeout
3. Compare line length distribution against reference (mean 17.1 km, median 13.2 km)
4. Compare deg1_frac against reference (6.6%)

**Success metric:** Line length distribution should better match reference. Without DC flow, we expect too many short lines and not enough medium-length corridor lines. With DC flow, the algorithm should favor edges that carry power over long distances.

**If runtime is prohibitive:** Try K=3 or K=2 to reduce per-iteration batch size. The paper used K=5 for ~225 nodes; scaling down for 1549 nodes may be appropriate.

---

## Experiment 6: K=1 Fine-Grained Selection at 115 kV

**Hypothesis:** Batch size K controls how many edges are added per score-recompute cycle. At K=5, 5 short edges can be added simultaneously before scores update. At K=1, each edge addition triggers a full rescore, allowing the algorithm to react to each addition.

At 115 kV (1549 nodes, target ~2566 edges), K=5 means ~513 iterations. K=1 means ~2566 iterations but with more precise selection.

**Procedure:**
1. Run Exp 4's combined fix on Texas2k 115 kV with K=1 and DC flow enabled
2. Compare degree distribution granularity against K=5 run (Exp 5)
3. Compare against reference

**Success metric:** If K=1 produces meaningfully different (better) degree distribution than K=5, batch size is a factor worth tuning. If results are similar, K is not critical.

**Runtime note:** K=1 means 5x more iterations than K=5, but each iteration scores fewer candidates in the top pool. Net runtime may be similar or longer. Set 90-minute timeout.

---

## Metrics Framework

All experiments report the following metrics, computed by `Calibration/network_stats.py`:

| Metric | Description | Texas2k 500kV Target | Texas2k 115kV Target |
|---|---|---|---|
| m/n ratio | edges / nodes | 1.544 | 1.657 |
| mean_degree | 2 * m/n | 3.09 | 3.31 |
| meshedness | (m-n+1)/(2n-5) | 0.279 | 0.329 |
| deg1_frac | fraction of degree-1 nodes | 0.132 | 0.066 |
| deg3plus_frac | fraction of degree ≥ 3 nodes | 0.582 | 0.644 |
| mean_length_km | mean line length | 55.7 | 17.1 |
| median_length_km | median line length | 42.0 | 13.2 |
| intersection_rate | fraction of edges that cross another edge | (compute from reference) | (compute from reference) |
| degree_entropy | Shannon entropy of degree distribution | (compute from reference) | (compute from reference) |

**Composite error score:**
```python
error = sum(abs(generated - target) / target for metric in metrics) / len(metrics)
```

Weight shape metrics (deg1_frac, deg3plus_frac, degree_entropy) 2x relative to aggregate metrics (m/n, meshedness) since shape is what we're trying to fix.

---

## Execution Order

```
Step 0:  Build texas2k_io.py (loader + reference network builder)
         Add intersection_rate and degree_entropy to Texas2k reference stats

Step 1:  Experiment 1 — Baseline (500 kV, then 115 kV)
         → Establishes gap. All subsequent experiments compare to this.

Step 2:  Experiment 2 — Radial fix only (500 kV, then 115 kV)
         → Quick test, one-line change. If deg1_frac improves, keep the change.

Step 3:  Experiment 3 — Biconnectivity fix only (500 kV first)
         → Larger code change. Test on 500 kV first (faster).
         → If deg1_frac and meshedness improve, proceed to 115 kV.

Step 4:  Experiment 4 — Combined (500 kV, then 115 kV)
         → Both fixes together. This is the main result.

Step 5:  Experiment 5 — Combined + DC at 115 kV with K=5
         → Only run if Exp 4 shows improvement. Tests DC flow contribution.

Step 6:  Experiment 6 — Combined + DC + K=1 at 115 kV
         → Only run if Exp 5 shows improvement. Tests batch size effect.
```

**Early stopping:** If Experiment 1 baseline already matches the reference well (error < 0.10), the algorithm may already be correct on Birchfield-style inputs and the prior calibration failure was purely due to wrong comparison target (Hypothesis 1). In that case, skip Experiments 2–6 and document the finding.

**Branching:** If Experiment 2 makes deg1_frac worse (over-correction), revert and proceed to Experiment 3 alone. If Experiment 3 alone solves the shape problem, Experiment 2 may be unnecessary.

---

## Output Files

All results saved under `Calibration/outputs/texas2k_hypotheses/`:

```
baseline_500kv_stats.json
baseline_115kv_stats.json
exp2_radial_500kv_stats.json
exp2_radial_115kv_stats.json
exp3_biconn_500kv_stats.json
exp3_biconn_115kv_stats.json
exp4_combined_500kv_stats.json
exp4_combined_115kv_stats.json
exp5_dc_115kv_stats.json
exp6_k1_115kv_stats.json
summary_table.csv          # all experiments, all metrics, one row per run
comparison_500kv.png       # map: reference vs best experiment
comparison_115kv.png
degree_dist_overlay.png    # degree distributions: reference vs each experiment
```

---

## What This Plan Does NOT Cover

- **230 kV level:** Texas2k has a 230 kV network (197 subs, m/n=1.67). Our generator doesn't support 230 kV natively. Deferring to avoid scope creep.
- **Quota interpretation (Hypothesis 6):** Ranked LOW priority. If the combined fix (Exp 4) solves the shape problem, quota interpretation is moot.
- **Spatial distribution effects (Hypothesis 3):** By testing on Texas2k substations (which ARE Birchfield-generated positions), we implicitly control for this. If results match on Texas2k but not Texas-7k, Hypothesis 3 is confirmed.
- **Line impedance parameters:** Using 345 kV impedance params for 500 kV lines. Affects DC flow magnitude scaling but not relative candidate ranking. Acceptable for calibration.
