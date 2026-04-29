# Saturday's Work: Topology Calibration Against Birchfield's Texas2k

## Summary

We spent the day calibrating Dartboard's Birchfield topology generator. The key breakthrough was discovering that our implementation of the `w_conn_overall` scoring bonus was fundamentally wrong — it rewarded component merging when it should have rewarded biconnectivity (cycle formation around articulation points). Fixing this single issue reduced composite error by **42% at 500 kV** and **49% at 115 kV** against Birchfield's own 2000-bus synthetic network.

---

## Timeline

### Phase 1: Parameter Sweep Against Texas-7k

We ran 6 experiments varying scoring weights, quotas, distance penalties, connectivity decay, and batch size against the Texas-7k reference grid. Best result at 345 kV: **43% error reduction** (w_dist=0.6). But the best config didn't generalize to 138 kV — deg1_frac was 22.5% vs target 7.7%.

**Output:** `Calibration/outputs/alignment/` — alignment_results.csv, 6 comparison PNGs.

### Phase 2: Root Cause Analysis

We read the Birchfield paper carefully and generated 8 ranked hypotheses (`Calibration/plans/hypotheses.md`). The three HIGH-priority hypotheses:

1. **H4: w_conn_overall misimplemented** — The +1000 bonus was applied on component merges (same condition as the +300 bonus). The paper says it's for "full system connectivity under single node removal" — biconnectivity, not basic connectivity. Cycle-forming edges that eliminate articulation points should get this bonus, but our code gave them +0.

2. **H2: "Radial substation" misinterpreted** — We gave the +300 w_conn_v bonus only to degree-0 nodes. The paper says "connects to a radial substation," which might mean degree ≤ 1.

3. **H1: Wrong comparison target** — Texas-7k is a hand-crafted grid mimicking real ERCOT. Birchfield's algorithm was never designed to reproduce it. The paper targets m/n ≈ 1.22; Texas-7k has m/n = 1.55.

### Phase 3: Texas2k Discovery

We found and parsed Birchfield's actual Texas2k_series2025 case — their own 2000-bus output. Key revelation:

| Metric | Paper Table III | Texas2k 500 kV | Texas2k 115 kV |
|---|---|---|---|
| m/n ratio | 1.22 | **1.544** | **1.657** |
| deg1_frac | — | 13.2% | 6.6% |
| deg3+_frac | — | 58.2% | 64.4% |

Birchfield's own output has m/n = 1.54–1.66, not 1.22. The paper's 1.22 is an average over Eastern Interconnect utilities, not what the algorithm actually produces. **H1 confirmed: we were calibrating against the wrong target.**

**Output:** `Texas2k_series2025/texas2k_voltage_lines.png`, `texas2k_voltage_panels.png`, `texas2k_degree_dist.png`, `texas2k_stats.txt`.

### Phase 4: Hypothesis Experiments on Texas2k

We implemented both fixes as configurable flags in `TopologyConfig` and ran 6 experiments against the Texas2k reference:

#### 500 kV Results (182 substations, target m/n = 1.544)

| Experiment | deg1% | deg3+% | <len> km | Error |
|---|---|---|---|---|
| **Target** | **13.2%** | **58.2%** | **55.7** | — |
| 1. Baseline | 3.9% | 69.8% | 41.9 | 0.308 |
| 2. Radial fix | 0.0% | 69.8% | 43.3 | 0.378 |
| **3. Biconnectivity fix** | **7.7%** | **60.4%** | **46.6** | **0.179** |
| 4. Combined | 6.0% | 61.0% | 48.0 | 0.209 |

#### 115 kV Results (1549 substations, target m/n = 1.657)

| Experiment | deg1% | deg3+% | <len> km | Error |
|---|---|---|---|---|
| **Target** | **6.6%** | **64.4%** | **17.1** | — |
| 1. Baseline | 3.4% | 72.4% | 17.6 | 0.161 |
| 2. Radial fix | 0.2% | 73.2% | 17.7 | 0.284 |
| **3. Biconnectivity fix** | **7.7%** | **65.3%** | **20.7** | **0.082** |
| 4. Combined | 2.9% | 70.6% | 18.9 | 0.184 |

**Output:** `Calibration/outputs/texas2k_hypotheses/summary_table.csv`, per-experiment JSONs.

---

## Key Findings

### The biconnectivity fix (Hypothesis 4) is the dominant improvement

The original code applied `w_conn_overall = +1000` on component merges — the same condition as `w_conn_v = +300`. This meant cycle-forming edges got **zero** connectivity bonus once the graph was connected. The fix applies the +1000 bonus to edges where at least one endpoint is an articulation point, incentivizing mesh/cycle formation.

Implementation: Tarjan's iterative articulation point algorithm, recomputed once per iteration batch. O(V+E) per call.

**At 115 kV, the biconnectivity fix essentially solves the degree distribution:** deg1_frac = 7.7% (target 6.6%), deg3+_frac = 65.3% (target 64.4%). Both within ~1 percentage point of Birchfield's own output.

### The radial fix (Hypothesis 2) is counterproductive

Extending the w_conn_v bonus to degree-1 nodes drives deg1_frac to 0%. The algorithm already aggressively connects isolated nodes; making the bonus persist longer eliminates ALL remaining spurs. The paper's "radial substation" likely means degree 0, not degree ≤ 1.

### DC flow was already enabled and working

Prior concern about DC flow being disabled at 138 kV was based on the Texas-7k calibration (where we disabled it for speed). On Texas2k positions, DC runs in ~15 seconds at 115 kV. No need to disable it.

### The K_per_iteration floor masks K experiments

`topology_generation.py:497` has `K = max(K_per_iteration, n // 100)`. For 1549 nodes this forces K ≥ 15, making K=1 and K=5 configs identical. Experiments 5 and 6 produced the same results as Experiment 4.

---

## Remaining Gap

The biconnectivity fix is a major improvement but doesn't fully close the gap:

- **500 kV deg1_frac:** 7.7% generated vs 13.2% target. Still too few spurs.
- **500 kV mean_length:** 46.6 km vs 55.7 km target. Still too short — the distance penalty continues to favor short edges.
- **115 kV mean_length:** 20.7 km vs 17.1 km target. Slightly too long (lines extend further to close cycles around articulation points).

Possible next steps:
- Tune w_dist lower (< 1.242/km) to allow longer edges
- Investigate the K floor — the paper uses K=5 for ~225 nodes; scaling to K=15+ for 1549 nodes may be too aggressive
- The 500 kV gap suggests the algorithm may inherently under-produce degree-1 nodes at the highest voltage level

---

## Code Changes

### `core/topology_generation.py`
- Added `TopologyConfig` fields: `radial_degree_threshold` (int, default 0), `use_biconnectivity_bonus` (bool, default False)
- Added `_compute_articulation_points()` — iterative Tarjan's algorithm, returns set of node indices
- Modified `_compute_score_cheap()` — separates component-merge bonus from biconnectivity bonus; configurable radial threshold
- Modified `_iteration_loop()` — recomputes articulation points after each batch when biconnectivity is enabled

### `Calibration/texas2k_io.py` (new)
- Parses Texas2k AUX/RAW files (substations, buses, loads, generators, branches)
- `load_texas2k_substations(hv_class)` → `List[SubstationNode]`
- `load_texas2k_reference_network(voltage_class)` → `Network`

### `Calibration/run_texas2k_experiments.py` (new)
- Runs 6 experiments on Texas2k positions, computes metrics, outputs CSV and JSON

### `Texas2k_series2025/plot_voltage_lines.py` (new)
- Parses and visualizes the Texas2k reference network by voltage level

---

## File Map

```
Calibration/
├── plans/
│   ├── SaturdaysAlignmentPlan.md    — Original experiment plan (Phase 1)
│   ├── hypotheses.md                — 8 ranked hypotheses for calibration failure
│   ├── HypothesesTestedOn2k.md      — Experiment plan for Texas2k testing
│   └── SaturdaysWork.md             — This file
├── texas2k_io.py                    — Texas2k data loader
├── run_texas2k_experiments.py       — Hypothesis experiment runner
├── run_alignment_experiments.py     — Phase 1 alignment sweep runner
├── visualize_alignment_best.py      — Phase 1 visualization
├── outputs/
│   ├── alignment/                   — Phase 1 results (6 PNGs, CSV)
│   └── texas2k_hypotheses/          — Phase 4 results (JSONs, CSV)

Texas2k_series2025/
├── plot_voltage_lines.py            — Texas2k reference visualization
├── texas2k_stats.txt                — Reference network statistics
├── texas2k_voltage_lines.png        — All voltages on one map
├── texas2k_voltage_panels.png       — Per-voltage panels with stats
├── texas2k_degree_dist.png          — Degree distributions by voltage
└── comparisons/                     — Side-by-side: our best vs reference
```
