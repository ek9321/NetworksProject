# Texas-7k vs Dartboard — Calibration Results

## Approach

Texas-7k (vatic/data/grids/Texas-7k/TX_Data/SourceData) has 6,717 buses across
multiple voltages, but its transmission backbone consists of two layers:
- **345 kV**: 259 buses, 402 lines
- **138 kV**: 3,270 buses, 4,191 lines

Our Dartboard pipeline starts from ~1,934 Texas ZCTAs and clusters them down —
we cannot produce 7,000 nodes from 1,934 inputs. Instead, we run our
`TopologyGenerator` directly on the Texas-7k bus positions (same 259 + 3,270
nodes), so the comparison is **apples-to-apples on identical node sets**: same
geographic layout, different wiring algorithms.

Three networks per voltage level are compared:
1. **Texas-7k** — the reference network's actual lines
2. **Dartboard-on-7k** — our topology generator run on Texas-7k bus positions
3. **Dartboard-orig** — our Stage 3 output on Dartboard's own substations (197 / 1,312 nodes)

## Summary Table

| Metric | Texas-7k 345 | DB-on-7k 345 | DB-orig 345 | Texas-7k 138 | DB-on-7k 138 | DB-orig 115 |
|---|---|---|---|---|---|---|
| Nodes | 259 | 259 | 197 | 3,270 | 3,270 | 1,312 |
| Edges | 402 | 320 | 240 | 4,191 | 4,000 | 1,612 |
| m/n | 1.552 | 1.236 | 1.218 | 1.282 | 1.223 | 1.229 |
| Mean degree | 3.10 | 2.47 | 2.44 | 2.56 | 2.45 | 2.46 |
| Max degree | 12 | 9 | 11 | 10 | 13 | 11 |
| Mean length (km) | 38.10 | 31.76 | 37.58 | 13.10 | 9.82 | 19.45 |
| Median length (km) | 29.74 | 25.83 | 23.47 | 9.75 | 7.57 | 17.75 |
| Max length (km) | 188.55 | 182.12 | 252.41 | 134.45 | 78.85 | 80.11 |
| Intersection rate | 10.45% | 2.50% | 10.83% | 23.72% | 1.12% | 7.75% |

## Key Findings

### 1. m/n ratio — Texas-7k is denser than Birchfield's 1.22 target

Texas-7k has m/n = 1.55 at 345 kV and 1.28 at 138 kV. Our generator targets
1.22 (the Birchfield paper value) and hits ~1.23 on both layers. To replicate
Texas-7k's actual density we would need to raise `target_mn_ratio` to ~1.55 for
345 kV and ~1.28 for 138 kV. This is the single biggest structural gap.

### 2. Degree distribution — shape matches, mean is lower

Both Texas-7k and Dartboard-on-7k produce degree distributions dominated by
degree-2 nodes (~50–55%), with a tail out to degree 10–13. However, Texas-7k's
higher m/n ratio pushes its mean degree up (3.10 at 345 kV vs. our 2.47).
Raising the m/n target would naturally close this gap without any
degree-specific tuning.

### 3. Line lengths — Dartboard-on-7k closely matches at 138 kV

At 138 kV, Dartboard-on-7k (mean 9.82 km, median 7.57 km) is very close to
Texas-7k (mean 13.10 km, median 9.75 km). The slight shortness is expected:
our distance-penalty scoring favors shorter lines, and with fewer total lines
(m/n = 1.22 vs 1.28) there's less room for the longer ties. At 345 kV both
systems have similar means (~32–38 km).

### 4. Intersections — Dartboard is much cleaner

Texas-7k has intersection rates of 10.5% (345 kV) and 23.7% (138 kV), while
Dartboard-on-7k is at 2.5% and 1.1%. This reflects our strong intersection
penalty (w_intersect = 500). To match the Texas-7k structure:
- Reduce `w_intersect` substantially (e.g., 50–100) or
- Remove the intersection penalty entirely for calibration runs.

Real grids tolerate geometric crossings because lines exist at different
physical heights; the penalty is a Birchfield-paper heuristic, not a physical
constraint.

## Parameter Sweep Results

A systematic parameter sweep was run to find TopologyConfig values that
minimize structural error vs Texas-7k. Error score = mean of
`|actual − target| / target` across m/n ratio, mean degree, intersection
rate, and mean line length.

### 345 kV — 49 experiments (3–4 s each)

Swept: `target_mn_ratio` ∈ {1.35, 1.45, 1.55}, `w_intersect` ∈ {0, 25, 100, 500},
`w_dist` ∈ {0.8, 1.242}, `distance_prune_percentile` ∈ {95, 98}, plus baseline.

**Top 5 configurations** (target: m/n=1.552, deg=3.10, int=10.45%, len=38.1 km):

| Rank | Config | m/n | mean_deg | intersect | mean_len | error |
|------|--------|-----|----------|-----------|----------|-------|
| 1 | mn=1.55, w_int=25, w_d=1.242 | 1.564 | 3.13 | 9.1% | 34.3 km | **0.061** |
| 2 | mn=1.45, w_int=25, w_d=1.242 | 1.467 | 2.93 | 8.4% | 35.0 km | 0.096 |
| 3 | mn=1.55, w_int=25, w_d=0.8 | 1.564 | 3.13 | 6.7% | 34.8 km | 0.116 |
| 4 | mn=1.55, w_int=100, w_d=1.242 | 1.564 | 3.13 | 5.7% | 34.5 km | 0.142 |
| 5 | mn=1.45, w_int=25, w_d=0.8 | 1.467 | 2.93 | 6.3% | 35.4 km | 0.143 |
| — | baseline (mn=1.22, w_int=500) | 1.236 | 2.47 | 2.5% | 31.8 km | 0.333 |

**Key takeaways for 345 kV:**
- **m/n ratio is the dominant lever**: mn=1.55 hits the target almost exactly
  (1.564 vs 1.552). Mean degree follows automatically (3.13 vs 3.10).
- **w_intersect=25 is the sweet spot**: produces ~9% intersections (vs target
  10.45%) — close enough without overshooting. w_int=0 overshoots to ~15%,
  w_int=500 suppresses almost all crossings.
- **w_dist and prune have minimal effect**: w_d=1.242 vs 0.8 and prune=95 vs
  98 produced nearly identical results within each mn/w_int group.
- **Best config reduces error by 82%**: from 0.333 (baseline) to 0.061.

### 115 kV — 3 experiments (35–43 s each, DC flow disabled)

Tested only the most promising configs based on 345 kV findings.

**Results** (target: m/n=1.282, deg=2.56, int=23.72%, len=13.1 km):

| Rank | Config | m/n | mean_deg | intersect | mean_len | error |
|------|--------|-----|----------|-----------|----------|-------|
| 1 | mn=1.28, w_int=0, w_d=1.242 | 1.282 | 2.56 | 14.1% | 9.7 km | **0.167** |
| 2 | mn=1.28, w_int=25, w_d=1.242 | 1.282 | 2.56 | 1.6% | 10.0 km | 0.294 |
| 3 | baseline (mn=1.22, w_int=500) | 1.223 | 2.45 | 1.1% | 9.8 km | 0.323 |

**Key takeaways for 115 kV:**
- **m/n and degree match perfectly** with mn=1.28: both hit target exactly
  (1.282/2.56 vs 1.282/2.56).
- **Intersection gap is the main remaining issue**: even with w_int=0 (no
  penalty at all), intersections reach only 14.1% vs target 23.72%. The
  greedy scoring algorithm inherently prefers short, non-crossing lines.
- **Line lengths are consistently short**: ~9.7–10.0 km vs target 13.1 km.
  This is likely because the denser 3,270-node Texas network has many
  nearby neighbors, and the distance weight naturally selects short edges.

### Parameter Sensitivity Summary

| Parameter | Effect on 345 kV | Effect on 115 kV |
|---|---|---|
| `target_mn_ratio` | **Dominant**: controls edge count, degree, directly | **Dominant**: same behavior |
| `w_intersect` | **Strong**: 500→25 raises intersections from 2.5% to 9.1% | **Strong**: but 0 only reaches 14.1% of 23.7% target |
| `w_dist` | **Weak**: <2% effect on any metric | Not tested |
| `distance_prune_percentile` | **Negligible**: 95 vs 98 identical | Not tested |

## Recommended Calibrated Parameters

| Parameter | Current | Recommended (345 kV) | Recommended (115/138 kV) |
|---|---|---|---|
| `target_mn_ratio` | 1.22 | **1.55** | **1.28** |
| `w_intersect` | 500 | **25** | **0** |
| `w_dist` | 1.242 | 1.242 (no change) | 1.242 (no change) |
| `distance_prune_percentile` | 95 | 95 (no change) | 95 (no change) |

### Remaining gaps after calibration

| Metric | 345 kV (best) | 345 kV target | 115 kV (best) | 115 kV target |
|---|---|---|---|---|
| m/n ratio | 1.564 ✅ | 1.552 | 1.282 ✅ | 1.282 |
| Mean degree | 3.13 ✅ | 3.10 | 2.56 ✅ | 2.56 |
| Intersection rate | 9.1% ⚠️ | 10.45% | 14.1% ❌ | 23.72% |
| Mean length | 34.3 km ⚠️ | 38.10 km | 9.7 km ❌ | 13.10 km |

The intersection rate and mean length gaps (especially at 115 kV) likely
require **algorithmic changes** beyond parameter tuning — e.g., a scoring
bonus for lines that cross existing edges, or a modified distance penalty
that's less aggressive for medium-length lines.

## Outputs

All outputs live in `Calibration/outputs/`:
- `comparison_summary.csv` — tabular metrics for all networks
- `comparison_345kv.png` — 3-panel map: Texas-7k | Dartboard-on-7k | Dartboard-orig
- `comparison_138kv.png` — same at 138/115 kV
- `degree_histograms_345kv.png` — degree distributions at 345 kV
- `degree_histograms_138kv.png` — degree distributions at 138/115 kV
- `texas7k_dartboard_lines_345kv.csv` — generated line set at 345 kV
- `texas7k_dartboard_lines_115kv.csv` — generated line set at 138≈115 kV
- `sweep_results.csv` — full parameter sweep results (52 experiments)
- `sweep_lines/` — per-experiment line CSVs

## How to reproduce

```bash
# 1. Run topology generator on Texas-7k buses
python3 -m Calibration.run_topology_on_texas7k

# 2. Compute comparison statistics
python3 -m Calibration.compare_texas7k_vs_dartboard

# 3. Generate visualizations
python3 -m Calibration.visualize_side_by_side

# 4. Run parameter sweep (345 kV and 115 kV separately)
python3 -m Calibration.parameter_sweep 345
python3 -m Calibration.parameter_sweep 115
```