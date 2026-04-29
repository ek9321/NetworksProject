# Jun 17 Summer Peak Testing Plan

## What we know so far

**Nov 5 (51 GW constant load):** Solved. Zero shedding with 41 targeted line upgrades at 250 MVA base. Pop-weighted load allocation gives correct WEST < NORTH ordering.

**Jan 8 (40-50 GW hourly, high wind):** Solved. Zero shedding with the same 41 upgrades. WEST < NORTH 24/24 hours. Wind-driven price separation emerges naturally.

**Jun 17 (50-74 GW hourly, summer peak):** Not solved. 19,228 MW·h shedding with the 41 upgrades. Floor-rated (cap 800) cuts to 5,198 MW·h. Houston is the problem zone ($215 median LMP). Peak demand at 74 GW is 45% higher than Nov 5 — stresses everything.

## The three levers

### 1. Line ratings
What we've tried:
- 250 MVA baseline (single-circuit Drake ACSR) — too low for Jun 17
- 41 targeted line upgrades (250→500) — not enough for 74 GW peak
- Floor-rated cap 800 (min(flow×1.1, 800)) — helps but cap is too conservative
- Blanket 600 MVA — helps differently (spreads pain thinner)

What we haven't tested:
- Floor-rated at higher caps (1200, 1600, uncapped) — how much shedding is from the 800 cap vs other issues?
- Floor-rated at lower caps (400, 600) — where's the diminishing returns curve?

What we learned from ERCOT RPG filings: real 138 kV lines range 148–838 MVA (5.7× range). 250 MVA is the low end, not the median. Many urban lines are 400-600+ MVA due to larger conductors (Osprey, Cardinal, Bluejay vs Drake).

What the floor run showed: 1,730 lines where unconstrained flow exceeds 250 MVA. Max flow: 4,700 MVA on a single branch (impossible physically — this is a missing parallel path, not an underrated conductor). Cap at 800 MVA still leaves lines where flow × 1.1 > 800.

### 2. Load distribution
What we've tried (Nov 5):
- Pop-weighted (linear county population) → best zone LMP ordering (W-N = -$7.7)
- Sqrt → lowest shedding but unrealistic W-N spread (-$52.6)
- Uniform → shifts shedding to Houston
- Cap75 → kills price signal (W-N = +$0.4)

What we haven't tested:
- Pop^0.8 (slightly sub-linear) — gentler than sqrt, might reduce DFW concentration while preserving zone ordering
- Pop-weighted on Jun 17 with different rating approaches (all Jun 17 runs so far use pop)

Key insight: population-weighted puts 94% of NORTH into DFW and 93% of HOUSTON into the Houston metro. Both are high but Houston only breaks under high load. The allocation is probably too concentrated for both metros, but changing it risks distorting zone ordering.

### 3. Network topology
What we have: v3 pipeline (4,268 nodes, 5,323 edges, 14.4% effective bridge ratio)
What we capture: 81% of ERCOT circuit-km

Where we're missing connectivity:
- The floor run's 4,700 MVA line is physically impossible — there must be 3-5 parallel circuits in the real grid on that corridor that we map as one edge
- Urban areas (Houston, DFW) have the densest parallel circuits AND the most OSM mapping gaps
- Underground cables at road crossings (623 cable segments now in our data, but not yet used in topology building)

What we could try:
- Nothing immediate — topology changes require re-running the pipeline
- But the floor-rated approach effectively compensates for missing parallel paths by raising the single-edge rating to approximate the aggregate corridor capacity

### Are these the only three levers?

Mostly yes for Jun 17 network congestion. Other factors:
- **Generation fleet:** Using MORA (158 GW), missing 19 GW wind. But total capacity far exceeds 74 GW peak — not the binding constraint.
- **Renewable CFs:** Hourly profiles from ERCOT public data. Could be slightly off but not the primary issue.
- **Storage dispatch:** 17 GW of BESS. Already included. Helps with peak shaving but doesn't fix line congestion.
- **DC ties:** 1,106 MW fixed import. Small relative to 74 GW demand.

The network congestion is fundamentally a mismatch between where power is generated (rural wind/solar, coastal gas plants) and where it's consumed (DFW and Houston metros). The three levers all address different aspects of this mismatch.

## Testing plan

### Goal
Find the minimum set of calibration adjustments that produce a workable Jun 17 result (low shedding, realistic zone ordering, reasonable LMP distribution).

### Experiment grid

**Rating sensitivity (pop allocation, v3 topology):**

| Task | Tag | Rating approach | Expected insight |
|------|-----|----------------|-----------------|
| 57 | v3-j17-base | 250 MVA baseline, no upgrades | Clean baseline for Jun 17 |
| 58 | v3-j17-f400 | Floor-rated cap 400 | Low-end floor correction |
| 59 | v3-j17-f600 | Floor-rated cap 600 | Mid-range floor correction |
| — | v3-jun17-flr | Floor-rated cap 800 | Already ran (task 56) |
| 60 | v3-j17-f1200 | Floor-rated cap 1200 | High-end: does raising cap past 800 help? |
| 61 | v3-j17-fmax | Floor-rated no cap (9999) | Upper bound: all rating problems eliminated |

**Load allocation sensitivity (floor-rated cap 800, v3 topology):**

| Task | Tag | Load method | Expected insight |
|------|-----|-------------|-----------------|
| — | v3-jun17-flr | Pop | Already ran (task 56) |
| 62 | v3-j17-f8p8 | Floor cap 800 + pop^0.8 | Does gentler sub-linear help without breaking zone ordering? |

**Combined best case:**

| Task | Tag | Config | Expected insight |
|------|-----|--------|-----------------|
| 63 | v3-j17-best | Floor no cap + pop^0.8 | Best available: if this doesn't work, we need topology changes |

### What to measure for each experiment
1. Total shedding (MW·h over 24 hours)
2. Peak hour shedding (MW)
3. Zone median LMPs (W, N, H, S)
4. WEST < NORTH hours (out of 24)
5. W-N spread
6. Shed buses count
7. Negative LMP buses count
8. Extreme (>$1k) buses count
9. Houston median LMP (the problem zone)

### Expected outcomes

**Rating sensitivity curve:** Shedding should decrease monotonically as floor cap rises. The curve should flatten at some cap level — that's the "good enough" default rating. If the curve doesn't flatten until cap > 2000, we have a topology problem (missing parallel paths).

**Pop^0.8 effect:** Should reduce urban concentration slightly. If W-N spread stays negative (WEST < NORTH), it's a safe adjustment. If W-N flips positive, it's too aggressive.

**Best case:** If floor no cap + pop^0.8 produces near-zero shedding with good zone ordering, we know the topology is adequate and the remaining work is just rating/load calibration. If it still sheds significantly, we need topology improvements.
