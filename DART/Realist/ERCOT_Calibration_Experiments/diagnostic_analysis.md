# SCED Diagnostic Analysis — Where Are We Going Wrong?

**Date:** 2026-03-24
**Scope:** Cross-experiment analysis of 35+ SCED runs across v1 and v2 topologies
**Purpose:** Identify root causes of load shedding and calibration failures

---

## Executive Summary

After analyzing all available experiments, the picture is clear but nuanced:

1. **The 138 kV base rating is the dominant control variable.** The topology (v1 vs v2), SPL treatment, and 345 kV ratings are all second-order effects. Going from 250 → 600 MVA for 138 kV reduces Nov 5 shed by 50-100× on any topology.

2. **600 MVA is a compensating error, not a physical rating.** It works because OSM captures ~40-50% of the real 138 kV mesh. Each captured line must carry 2-3× its fair share.

3. **v2 topology + 600 MVA achieves 0 MW shed on Nov 5 and 30 MW on Jan 8 — but breaks WESTEX on Jun 17.** The bridge-load compensation creates super-highway branches at the WEST zone boundary that bypass the Morgan Creek→Tonkawa export corridor.

4. **Jun 17 remains the hardest calibration day** (582 MW avg shed on v2-600), and WESTEX doesn't bind at all (11% utilization). This is a regression on the most important calibration metric.

---

## The Rating Ladder

Here is every Nov 5 experiment ranked by shed, grouped by 138 kV rating:

### 250 MVA 138 kV base (physical single-circuit)

| Experiment | Topology | Other changes | Shed (MW) | Curtail (MW) |
|---|---|---|---|---|
| v5 | v1 | SPL at 300 MVA | 6,298 | 12,965 |
| spl-fix | v1 | SPL at tier rating | 6,129 | 8,184 |
| xfmr-nov5 | v1 | SPL near 345→138 at 1000 MVA | 6,052 | 8,930 |
| v2-nov5-presplice | v2 (no splice) | 4× SPL, bridge comp | 5,254 | ~7,500 |
| xfmr2-nov5 | v1 | xfmr + SPL T-junc at 500 | 4,842 | 11,528 |
| v2-nov5 | v2 (with splice) | 4× SPL, bridge comp | 4,306 | 6,966 |
| real-ratings | v1 | More conservative | 3,432 | 13,078 |
| xfmr3-nov5 | v1 | Broad 345→138 proxy + 500 SPL | 1,381 | 8,473 |

### 600 MVA 138 kV base (compensating for missing mesh)

| Experiment | Topology | Other changes | Shed (MW) | Curtail (MW) |
|---|---|---|---|---|
| clean-build | v1 | SPL at 999k, stubs at 999k | 82 | 9,048 |
| hv-default2 | v1 | +345 kV default=2 circuits | 80 | 9,859 |
| best-so-far | v1 | SPL at 999k, plant outlets free, 138 kV 2× | 87 | 8,174 |
| no-spl+138kv2x | v1 | SPL at 999k, all 138 kV doubled to 600 | 136 | 6,393 |
| hv2400 | v1 | +SCALE_345KV=2 | 24 | 5,456 |
| all345-2400 | v1 | +all 345 at 2400 except WESTEX | 19 | 6,253 |
| v2-600-nov5 | v2 | 600 MVA base on v2 topo | **0** | **0** |

### Unconstrained

| Experiment | Topology | Shed (MW) | Curtail (MW) | Price |
|---|---|---|---|---|
| floor | v1 | 0 | 0 | $13.86 |
| 2x | v1 | 0 | 0 | $13.86 |

**Key insight:** The jump from 250 → 600 MVA reduces shed by 50×. The jump from v1 → v2 at 600 MVA reduces it by another 80× (82 → 0). But v1 → v2 at 250 MVA only reduces it 1.5× (6,298 → 4,306).

**The rating is the first-order effect. The topology is second-order.**

---

## The Curtailment Story (Often Overlooked)

Load shedding gets the attention, but **curtailment** tells a more complete story:

| Experiment | Shed | Curtailment | Renewables Used | % of Available |
|---|---|---|---|---|
| v5 (v1, 300 MVA) | 6,298 | 12,965 | 6,853 | 34.6% |
| v2-nov5 (v2, 250 MVA) | 4,306 | 6,966 | 13,158 | 65.4% |
| clean-build (v1, 600 MVA) | 82 | 9,048 | 10,770 | 54.3% |
| v2-600-nov5 (v2, 600 MVA) | 0 | 0 | 20,125 | **100%** |
| floor (unconstrained) | 0 | 0 | 19,818 | 100% |

Even **clean-build** (v1, 600 MVA, 82 MW shed) curtails **9,048 MW** — 46% of available renewables. The network can serve load (only 82 MW shed) but it can't deliver cheap wind to load centers. The optimizer runs expensive thermal near load instead of cheap renewables far away.

**v2-600-nov5 matches the unconstrained floor** — zero curtailment, all renewables dispatched. The v2 topology eliminates the delivery bottlenecks that v1 still has even at 600 MVA.

This matters enormously for price accuracy: v1 clean-build prices at $21.31/MWh (thermal on the margin), while v2-600 prices at $14.11 (renewables on the margin). Real ERCOT Nov 5 2025 prices were likely in the $15-25 range, so both are plausible, but for very different reasons.

---

## The WESTEX Problem

### What should happen
On high-wind days, Morgan Creek→Tonkawa (the WESTEX export corridor) should be a binding constraint. This is well-documented in real ERCOT data and is our #1 calibration metric.

### What actually happens

| Experiment | Day | WESTEX Utilization | WESTEX Flow | Binding? |
|---|---|---|---|---|
| clean-build | Nov 5 | 94.5% | 1,134 MW | Near-binding |
| jun17-hourly (v1) | Jun 17 peak | 100% | 1,200 MW | **YES** |
| jun17-all345 (v1) | Jun 17 peak | 100% | 1,200 MW | **YES** |
| v2-600-nov5 | Nov 5 | ~10% | ~130 MW | No |
| v2-600-jun17 | Jun 17 peak | 11.2% | 134 MW | **NO** |

**WESTEX binds on v1 but NOT on v2.** The v2 topology diverts flow away from the Morgan Creek→Tonkawa corridor.

### Root cause: Bridge-load compensation over-compensates at zone boundaries

The v2 build script rates bridge branches at `max(tier_default, downstream_load / BRIDGE_DIVISOR)`. At the WEST-NORTH boundary, this created:

| Branch | v1 Rating | v2 Rating | Physical max |
|---|---|---|---|
| L1622_3041_345 (Parker→OSM) | 999k (SPL) | **9,600 MVA** | 2,400 MVA |
| L2619_2974_138 (OSM→OSM) | (different ID) | **1,314 MVA** | 250-500 MVA |

The 9,600 MVA branch at the WEST-NORTH boundary provides more capacity than Morgan Creek→Tonkawa (1,200 MVA) by 8×. Power naturally flows through this super-highway instead of WESTEX.

**Total WEST cross-boundary capacity:**
- v1: 19,200 MVA (excluding 999k SPL branches)
- v2: 35,514 MVA (nearly 2× v1)

**WEST exports on Jun 17 peak (v2-600-jun17):**
Total: 13,129 MW through 17 branches, well-distributed. None even close to their limits. The WESTEX corridor is irrelevant — power has many better alternatives.

### The fix

**Cap bridge-load compensation** at a reasonable physical maximum:
- 345 kV: max 4,800 MVA (double-circuit, which is what 2,400 already implies)
- 138 kV: max 1,200 MVA (double the 600 MVA base)

This would prevent single-branch super-highways while still compensating for moderate tree bottlenecks. The 9,600 MVA branch would drop to 4,800 MVA, and the total WEST cross-boundary capacity would be more constrained, pushing flow back toward WESTEX.

---

## The 30 Binding Branches in v2-nov5

All 30 binding branches at 250 MVA on v2 topology are 138 kV. Their geographic distribution:

| Zone | Count | Key locations |
|---|---|---|
| NORTH | 19 | DFW urban core (Rhome, Hickory, Mesquite, East Mesquite), NE Texas (OSM_2342/2346 near Paris TX, OSM_2744/2745 near Bonham TX) |
| HOUSTON | 6 | Inner Houston (Eureka, Airline, Blodgett, Rosharon, Underwood), Galveston County (Caddo, Heights) |
| SOUTH | 4 | Hill Country (Boerne Cico→Talley Road, Wirtz→Ferguson, Esperanza→Fair Oaks, Mountain Top→Miller Creek) |
| WEST | 1 | Upton County (Castillo→Upton County Solar) |

**Most are degree-2 bus connections** — one endpoint has only 2-3 connections. In a well-meshed network, these buses would have 4-6 connections. OSM captures the trunk line but not the parallel circuits and urban mesh.

**The single WEST binding branch** (L128_129_138, Castillo→Upton County Solar) is a solar plant outlet, not a backbone constraint. WEST internal congestion is minimal.

---

## Multi-Day Calibration Results

### v2 topology + 600 MVA (current best configuration)

| Day | Avg Shed | Peak Shed | Curtail | Price Avg | Renewables % | WESTEX |
|---|---|---|---|---|---|---|
| Nov 5 | 0 MW | 0 MW | 0 MW | $14.1 | 100% | Not binding (10%) |
| Jan 8 | 30 MW | 57 MW | 119 MW | $5.8 | 99.6% | Not checked |
| Jun 17 | 582 MW | 1,429 MW | 1,971 MW | $10.2 | 94.9% | **Not binding (11%)** |

### vs. v1 topology + 600 MVA

| Day | v1 Shed | v2 Shed | v1 Curtail | v2 Curtail | v1 WESTEX |
|---|---|---|---|---|---|
| Nov 5 | 82 MW | 0 MW | 9,048 | 0 | Near-binding (94.5%) |
| Jan 8 | 110 MW | 30 MW | 5,165 | 119 | Not checked |
| Jun 17 | 989 MW | 582 MW | 3,139 | 1,971 | **Binding (100%)** |

### Calibration targets

| Metric | Target | v1+600 | v2+600 | Status |
|---|---|---|---|---|
| WEST < NORTH LMP | Must hold | YES | YES | Both pass |
| Nov 5 shed | < 50 MW | 82 | 0 | v2 passes, v1 borderline |
| Jun 17 shed | < 300 MW | 989 | 582 | Both fail |
| WESTEX binding (wind days) | Must bind | YES | **NO** | **v2 regresses** |
| LMP spread magnitude | Within 3× | ~OK | Unknown | Need analysis |

---

## The Fundamental Tension

There is a tension between two goals:

1. **Low shedding** → needs high 138 kV ratings (600 MVA) and good mesh → favors v2 topology
2. **WESTEX binding** → needs constrained WEST export paths → the v2 bridge-load compensation eliminates this

The v1 topology accidentally gets WESTEX right (94.5% on Nov 5, 100% on Jun 17) because its tree-like structure forces flow through a few corridors. The v2 topology disperses flow across many routes, which is physically more realistic but eliminates the specific congestion pattern we're trying to reproduce.

**This is the compensating error dilemma:** v1 has unrealistic topology but realistic congestion patterns. v2 has more realistic topology but unrealistic (too little) congestion.

---

## Recommendations

### Immediate fix: Cap bridge-load compensation

In `build_osm_branch_table_v2.py`, add a maximum to the bridge-load formula:

```python
# Current:
bridge_rating = max(tier_default, downstream_load / BRIDGE_DIVISOR)

# Proposed:
MAX_BRIDGE_RATING = {345: 4800, 230: 2400, 138: 1200}  # physical double-circuit max
bridge_rating = min(
    max(tier_default, downstream_load / BRIDGE_DIVISOR),
    MAX_BRIDGE_RATING.get(voltage, tier_default * 2)
)
```

This caps the 9,600 MVA super-highway at 4,800 MVA. Test on Jun 17 — if WESTEX still doesn't bind, further reduce the cap or increase BRIDGE_DIVISOR.

### Experiment: v2-capped-jun17

Run Jun 17 on v2 topology with bridge-load cap. Check:
- Does WESTEX bind?
- What is the shed? (Should be between v2-600's 582 MW and v1's 989 MW)
- Is the WEST-NORTH LMP spread reasonable?

### Longer-term: Principled cross-zone capacity

Rather than bridge-load compensation (which over-compensates at zone boundaries), consider:
1. **Explicitly rate cross-zone branches** based on known ERCOT transfer limits (~15-20 GW WEST→rest)
2. **Cap intra-zone bridge compensation** to prevent single branches from exceeding double-circuit physical limits
3. **Use the 250 MVA base + targeted bridge compensation** as the primary approach, rather than blanket 600 MVA

### The philosophical question

For a "first-of-a-kind public synthetic ERCOT grid," which is more important:
- **Reproducing specific congestion patterns** (WESTEX binding) → argues for v1 topology with its accidental constraints
- **Having physically realistic topology** (low bridge ratio, good mesh) → argues for v2 topology

The answer is probably: v2 topology with parameter constraints that reproduce the known congestion patterns. The bridge-load cap is the first step.

---

## Root Cause: OSM 138 kV Data Is Inherently Tree-Like

### The raw OSM junction graph (before any extraction)

We built the raw 138 kV junction graph directly from OSM endpoints (100m clustering)
— no snap, no BFS, no filters. The result:

| Metric | Raw OSM | Model v2 | Real ERCOT (est.) |
|--------|---------|----------|-------------------|
| Nodes | 10,096 | 3,664 | ~5,000 |
| Edges | 10,746 | 4,420 | ~7,000 |
| Edge/node ratio | 1.06 | 1.21 | 1.4-1.8 |
| Mean degree | 2.13 | 2.41 | 2.5-3.5 |
| Pendant nodes | 30% | 20% | 10-15% |
| Bridge ratio | **49.7%** | **66.4%** (pre-splice) / **18.4%** (post-splice) | <20% |
| Connected components | 382 | 1 | 1 |

**The OSM data itself has a 49.7% bridge ratio.** Even a perfect parser would produce a
tree-like 138 kV network. Our extraction pipeline makes it slightly worse (49.7% → 66.4%)
through snap failures and split cleanup, but the v2 edge-splice then over-corrects it
down to 18.4%.

### Where OSM edges are lost in the pipeline

| Step | Features/Edges | Lost | Why |
|------|---------------|------|-----|
| Raw OSM 138 kV features | 19,144 | — | Input |
| Self-loops (endpoints <100m apart) | — | 6,189 (32%) | Substation internals, correctly dropped |
| Unique junction edge pairs | 10,746 | — | After dedup |
| Parallel circuits lost to dedup | — | 24 (<1%) | Different cables tags, same pair |
| Unsnapped degree-1 endpoints | — | 354 | No substation within 400m → edge dropped |
| BFS contraction (degree-2 chains) | ~6,941 | ~3,805 nodes contracted | Correct behavior |
| Split cleanup + filtering | ~4,500 | ~2,400 | Phantom splits, short edges |
| Edge-splice (v2 only) | +129 | — | Recovered connections |
| **Final model edges** | **~3,273** | | |

The dominant loss is legitimate: self-loops (substation internals) and BFS contraction
(chain merging). Only 354 edges are lost to snap failures, and 24 to parallel circuit dedup.

### Why the 600 MVA default is necessary

The raw OSM 138 kV mesh has ~50% of the edges of the real grid. Each captured edge
must carry power for itself plus ~1 missing parallel path. A 2× rating multiplier
(250 MVA × 2.4 = 600 MVA) compensates for this missing mesh. This is a principled
compensating error, not a hack.

### Possible improvements

1. **Better OSM data**: Contributing missing 138 kV segments to OpenStreetMap
   (especially urban mesh connections) would directly reduce the bridge ratio.

2. **Wider snap radius**: Increasing from 400m to 1 km would recover 641 more
   cluster snaps (reducing unsnapped from 1,813 to 1,172).

3. **Synthetic mesh augmentation**: For large 138 kV subtrees (>50 nodes behind
   a bridge), algorithmically add 2-3 cross-connections to nearby backbone nodes.
   This is the most impactful change possible without new OSM data.

4. **Parallel circuit recovery**: When two OSM ways at the same voltage connect
   the same pair of clusters, keep both as separate edges (currently deduped).
   Only 24 cases exist, so impact is minimal.

---

## Data Inventory

All results are in `Realist/ERCOT_Calibration_Experiments/results/<tag>/`.

Interactive map: `diagnostics.html` (Leaflet map with binding branch overlays, switchable between experiments).

Key files per experiment:
- `hourly_summary.csv` — system-level metrics per hour
- `line_detail.csv` — branch flows per hour (pull from adroit if missing)
- `bus_detail.csv` — bus LMPs per hour
- `bus.csv` — bus metadata (zone, coordinates, load)
- `branch.csv` — branch metadata (rating, impedance)

Adroit results: 35+ experiment directories in `/scratch/network/js0735/dartboard/sced_inputs_*/results_*/`
