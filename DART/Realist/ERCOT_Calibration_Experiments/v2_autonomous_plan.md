# V2 Autonomous Loop Plan

**Starting state:** V2 topology pipeline built and tested. Job 3042790 (v2-nov5 with edge-splice) running on adroit. Bridge ratio reduced from 66.4% → 18.4%.

**Goal:** Iterate toward <100 MW shed on Nov 5, <500 MW on Jun 17, with correct WEST < NORTH LMP ordering.

---

## Step 1: Analyze v2-nov5 results (job 3042790)

```bash
ssh adroit "sacct -u js0735 -j 3042790"
# When complete:
scp -r adroit:/scratch/network/js0735/dartboard/sced_inputs_v2-nov5/results_v2-nov5/ \
    Realist/ERCOT_Calibration_Experiments/results/v2-nov5/
```

Read `hourly_summary.csv`. Key metrics:
- Steady-state shed (hours 9-23 average)
- Curtailment levels (wind/solar trapped behind congestion)
- System price profile
- Zone LMP ordering (need WEST < NORTH)

Read `line_detail.csv` to find binding branches. Classify by:
- 138 kV tree bottlenecks (remaining bridges)
- 345 kV backbone congestion (WESTEX and others)
- SPL branch limits

**Decision point:**
- If shed < 200 MW: proceed to Step 3 (multi-day validation)
- If shed 200-2000 MW: go to Step 2 (targeted fixes)
- If shed > 2000 MW: investigate — something fundamental still broken

## Step 2: Targeted fixes (if needed)

### 2a. Check remaining bottleneck bridges
```python
# Recompute bridge analysis on the v2 branch.csv (post-component-filter)
# Identify which bridges are still overloaded
# Cross-reference with line_detail.csv binding branches
```

### 2b. Tune parameters (one at a time, verify each)
Priority order:
1. **SPL_MULT** — if binding branches are SPL, try 6× or 8× (currently 4×)
2. **BRIDGE_DIVISOR** — if bridges overloaded, try 2 instead of 3
3. **SPLICE_MAX_OFFSET_RATIO** — if many substations still orphaned near corridors, relax from 0.3 to 0.4
4. **138 kV base rating** — if many non-SPL 138 kV branches bind, consider 400 MVA base

For each change:
- Rebuild branch.csv locally
- Deploy to adroit
- Run single task, pull results
- Compare to previous run
- Only keep the change if it helps without breaking LMP ordering

### 2c. Visual inspection
Open `grid_visualizer_v2.html` and check:
- Houston area: are edges reasonable?
- WEST area: are Morgan Creek→Tonkawa and the export corridors intact?
- Any obviously wrong connections?

## Step 3: Multi-day validation

Submit Jun 17 and Jan 8:
```bash
ssh adroit "sbatch --array=32-33 /scratch/network/js0735/dartboard/run_sced_array.slurm"
```

Pull and analyze:
- Jun 17: shed should be < 500 MW (was 593-1923 in v1 clean-build)
- Jan 8: shed should be < 200 MW (was 0-178 in v1 clean-build)
- WESTEX should bind on high-wind days (Jun 17, Jan 8)
- WEST < NORTH LMP ordering on all three days

## Step 4: Update state

- Update `experiments.md` with new rows
- Update `v2_grid_summary.md` with final results
- Update `README.md` "Current Model State" section
- Update session log `session_2026-03-24b.md`

## Step 5: Iterate or declare success

If all three days pass calibration:
- WEST < NORTH on high-wind days ✓
- Shed < 100 MW (Nov 5) ✓
- Shed < 500 MW (Jun 17) ✓
- WESTEX binding on wind days ✓

Then: update README as "v2 baseline established" and move to next priorities (storage deployment validation, additional calibration days, data center load experiments).

---

## Principles (from user feedback)
1. **Careful heuristics, not slapshod** — every parameter must be physically motivated and scale naturally
2. **One change at a time** — verify each change before stacking
3. **Sanity check everything** — visual inspection + statistical checks + SCED results
4. **Write things down** — session log, experiments table, grid summary
5. **Don't destroy old pipeline** — all v2 work in separate files
