# Calibration Plan: Branch Ratings and Nodal Load via Vatic SCED

**Goal:** Determine which transmission constraints are physically real vs. modeling artifacts,
find defensible capacity values for the real ones, and validate numerically against ERCOT's
actual SCED outcome on 2025-11-05.

---

## What Is Already Implemented

**Branch ratings:** `build_osm_branch_table.py` assigns ratings via cables-based lookup:
`cont_rating = base_mva_per_circuit × (cables // 3)`. Current base: 138 kV = 300 MVA/circuit,
345 kV = 1,200 MVA/circuit. Untagged lines default to 1 circuit.

Current v5 rating distribution (from adroit `sced_inputs/SourceData/branch.csv`):

| MVA | Count | Meaning |
|---|---|---|
| 300 | 2,448 | 138 kV single-circuit |
| 600 | 1,016 | 138 kV double-circuit |
| 900 | 17 | 138 kV triple-circuit |
| 1,200 | 661 | 345 kV single-circuit |
| 2,000 | 5 | 500 kV single-circuit |
| 2,400 | 347 | 345 kV double-circuit |
| 3,600 | 7 | 345 kV triple-circuit |

**Load distribution:** `run_sced.py:distribute_load()` weights load by Census 2020 county
population, applied only to 138 kV non-split-point substations. In every run since v2.

**Offer curve data:** Downloaded and saved at
`Realist/grid_data/sced_disclosure_20251105_gen_resource.csv` — 134,016 rows covering 1,426
resources on 2025-11-05. Contains actual ERCOT submitted offer curves (MW breakpoints +
$/MWh prices, up to 35 segments, at each SCED interval). Resource types: WIND, PVGR, PWRSTR,
CCGT90, SCLE90, SCGT90, CLLIG, NUC, and more.

---

## Key Finding: The Binding Branches Are Not East-West Corridors

Before designing any capacity experiment, we analyzed which branches actually bind in v5
steady-state hours (9–23). The result was unexpected.

**47 branches hit ≥98% utilization. Their distribution:**

| Zone pair | Count | Ratings | Implied length range |
|---|---|---|---|
| NORTH–NORTH | 27 | 300 MVA (23), 600 MVA (1), 1,200 MVA (3) | 0.44 – 52 km |
| HOUSTON–HOUSTON | 15 | 300 MVA (12), 600 MVA (3) | 0.36 – 6.5 km |
| SOUTH–SOUTH | 3 | 300 MVA | 0.5 – 1.5 km |
| WEST–WEST | 2 | 300 MVA (1), 1,200 MVA (1) | 0.4 km, 31 km |

**Zero inter-zone (east-west) branches are binding.** The congestion is entirely intra-zone.

More importantly, **32 of 47 binding branches have at least one SPL_ (synthetic split point)
endpoint**, and most are very short:

- Shortest: 0.36 km (SOUTH MIDLAND SUBSTATION → SPL_3922)
- Median: ~2.5 km
- Notable: COMANCHE PEAK STATION → SPL_3078 (345 kV, **0.68 km**, 1,200 MVA — nuclear
  plant outlet segment fully saturated)

These synthetic junction segments are artifacts of how `build_osm_branch_table.py` splits
OSM lines at T-junctions. A branch like `COMANCHE PEAK → SPL_3078` is the 0.68 km wire
from the nuclear plant to the nearest T-junction on the 345 kV ring. Comanche Peak has
~2,500 MW of nameplate capacity. Every MW it generates must pass through this 1,200 MVA
segment — which immediately saturates, preventing the plant from dispatching fully.

**The same artifact appears in NORTH (RATTLESNAKE ROAD → SPL_3125, 2.4 km, 1,200 MVA) and
throughout the 138 kV DFW and Houston networks.** Short radial segments from real substations
to junction nodes are acting as system-wide bottlenecks.

**Only 4 binding branches are long enough (>10 km) with both endpoints real substations:**

| Line | Zone | KV | Rating | Length | From | To |
|---|---|---|---|---|---|---|
| L1116_1512 | HOUSTON | 138 | 300 MVA | 15 km | ROSHARON | KARSTEN |
| L1605_1612 | WEST | 345 | 1,200 MVA | 31 km | MORGAN CREEK | TONKAWA |
| L801_1633 | NORTH | 345 | 1,200 MVA | 52 km | HICKS | WILLOW CREEK |
| L1054_1055 | NORTH | 138 | 300 MVA | 2 km | MISTLETOE HEIGHTS | HEMPHILL |

Of these, MORGAN CREEK → TONKAWA (WEST, 345 kV) and HICKS → WILLOW CREEK (NORTH, 345 kV)
are genuine candidate constraints worth investigating. ROSHARON → KARSTEN is Houston south,
may be real. MISTLETOE HEIGHTS → HEMPHILL is Fort Worth urban 138 kV.

---

## The Right Experimental Sequence

Given the above, the calibration experiments fall into two distinct phases:

**Phase 1: Diagnose — find the real constraints by removing the artifact ones.**
**Phase 2: Calibrate — test defensible capacity values for the real constraints.**

---

## Phase 1 — Remove the SPL Artifact (Experiment: `no-spl-cap`)

### What to change

In `build_osm_branch_table.py` or in `run_sced.py` at load time: for any branch where at
least one endpoint is a synthetic split point (`is_split = True`), set `Cont Rating` to
a very large value (e.g., 999,999 MVA — effectively unconstrained).

The physical justification: a split point is a T-junction on a wire, not a substation with
equipment-rated terminals. The thermal limit on a T-junction segment is determined by the
weakest line connected to it, which is already captured by the ratings of the non-junction
branches. Constraining the junction segment separately double-counts the bottleneck.

**Implementation:** Add a post-processing step in `build_osm_branch_table.py` after
the main branch construction loop:

```python
# SPL endpoints are synthetic junctions — unconstrain them.
# The real capacity constraint is on the non-junction lines feeding into the node.
spl_mask = (
    branch_df['From Bus'].isin(split_bus_ids) |
    branch_df['To Bus'].isin(split_bus_ids)
)
branch_df.loc[spl_mask, 'Cont Rating'] = 999_999
```

Where `split_bus_ids` is the set of Bus IDs where `is_split = True` in `bus.csv`.

**Expected outcome:** Most of the 47 current binding branches disappear. The remaining
binding branches reveal the true capacity constraints in the topology — real substation-to-
substation lines where the cable count and base rating matter.

**What to watch for after this change:** Does the system still shed load? If yes, the real
constraints (MORGAN CREEK→TONKAWA, HICKS→WILLOW CREEK, etc.) are binding. If no, the
ENTIRE 6,298 MW shedding was an artifact of SPL junction ratings, and the network is
effectively uncongested at current cable-based ratings.

Experiment tag: **`no-spl-cap`**

---

## Phase 2 — Targeted Corridor Sensitivity

Run Phase 2 only after `no-spl-cap` establishes which real branches bind.

### Candidate corridors to target

Based on the v5 analysis and known ERCOT congestion patterns, the candidates are:

**MORGAN CREEK → TONKAWA (WEST, 345 kV, 31 km, currently 1,200 MVA)**
This is in the WEST zone and could be part of the WESTEX nomogram — the main structural
constraint on West Texas exports. If it binds in `no-spl-cap`, it's the most important
single branch for east-west flow calibration.

**HICKS → WILLOW CREEK (NORTH, 345 kV, 52 km, currently 1,200 MVA)**
A long 345 kV line within NORTH. Could be part of the Dallas import path. If it binds in
`no-spl-cap`, test at 1,200 vs 2,400 MVA (single vs double circuit).

**ROSHARON → KARSTEN (HOUSTON, 138 kV, 15 km, currently 300 MVA)**
South Houston, likely serving the petrochemical corridor. If it binds, test at 300 vs 600 MVA.

**MISTLETOE HEIGHTS → HEMPHILL (NORTH, 138 kV, 2 km, 300 MVA)**
Fort Worth urban 138 kV. Short enough that it may still be an artifact even without SPL
endpoints; worth checking in place before targeting.

### How to run targeted sensitivity

Rather than sweeping all ratings up uniformly, change one corridor at a time:

1. After `no-spl-cap`, pull `line_detail.csv` and identify which of the candidate branches
   above remain binding.
2. For each binding candidate, create a variant that doubles only that branch's rating.
   Compare load shedding and LMP spread to `no-spl-cap`.
3. If doubling one branch eliminates or significantly reduces shedding, that branch is the
   bottleneck. Document its real-world context (OSM cables count, nearby ERCOT constraint
   names) and decide on a defensible rating.

Experiment tags: **`no-spl+morgan2x`**, **`no-spl+hicks2x`**, etc.

---

## Phase 3 — Numerical Validation with Hourly Inputs and Real Offers

Once Phase 1-2 establish which constraints matter, switch to hourly inputs for numerical
comparison. This is the final calibration step, not the first.

### Prerequisites

**Hourly zonal load for 2025-11-05:** Pull from ERCOT Grid Info → Load → Historical Load
Data. Replace the constant `ZONE_LOAD_MW` dict in `run_sced.py` with a 24-entry hourly
dict per zone.

**Hourly wind/solar CFs for 2025-11-05:** Pull from ERCOT Wind Power Production and Solar
Power Production reports. Scale each generator's pmax timeseries by the actual zonal CF for
that hour rather than using a flat constant.

**Actual submitted offer curves:** Already downloaded and saved at
`Realist/grid_data/sced_disclosure_20251105_gen_resource.csv`. 1,426 resources, 134,016
rows, SCED1/SCED2 offer curves at each interval, plus Output Schedule, HSL/LSL, and startup
costs. Apply to `gen.csv` via `build_gen_table.py`:
- Join `Resource Name` to `GEN UID` (fuzzy match on unit name)
- Use the first SCED interval of each operating hour as that hour's offer curve
- For unmatched units (<10% expected), retain EIA fallback

Experiment tag: **`hrl-real-offers`** (builds on best Phase 2 result)

### Numerical calibration targets

Pull from ERCOT for 2025-11-05 (all public, no lag for settlement prices):

| Metric | Source | Target |
|---|---|---|
| Zonal LMP ordering | ERCOT Historical RTM SPPs | Correct ordinal ranking ≥3/4 zones in ≥18/24 hours |
| WEST vs. NORTH price gap | ERCOT Historical RTM SPPs | Within 2× of actual magnitude |
| System marginal price (mean) | ERCOT Historical RTM SPPs | Within ±$5/MWh with real offers |
| Top binding constraints | ERCOT Binding Transmission Constraints report | ≥2/5 top corridors match geographically |
| Load shedding | Our SCED output | < 500 MW |
| Renewable curtailment | ERCOT Wind report | Non-zero iff ERCOT actually curtailed |

---

## What NOT to Do

**Do not sweep all 138 kV ratings uniformly before fixing the SPL artifact.** A uniform
2× sweep happened to clear the system (floor = 2x = 0 shed), but that doesn't mean 600 MVA
is the right 138 kV rating — it may just mean the doubled rating is large enough to also
hide the SPL artifact. We need to separate the two effects.

**Do not add hourly load/CFs before establishing which constraints bind.** Hourly inputs
change the load level and renewable injection in each hour, which changes which branches
are stressed and by how much. Debug the topology first on the constant-load baseline so
we know exactly what we're looking at.

---

## Experiment Summary Table

| Tag | SPL caps | Branch ratings | Load | CFs | Cost curves | Purpose |
|---|---|---|---|---|---|---|
| `v5` | constrained | cables-based, 300/circuit | constant | constant | EIA | Current baseline |
| `floor` | constrained | unlimited | constant | constant | EIA | Done — congestion upper bound |
| `2x` | constrained | cables × 2 | constant | constant | EIA | Done — 2× clears system |
| **`no-spl-cap`** | **unconstrained** | cables-based, 300/circuit | constant | constant | EIA | **Phase 1: remove junction artifact** |
| `no-spl+morgan2x` | unconstrained | Morgan Creek→Tonkawa 2,400 MVA; rest cables | constant | constant | EIA | Phase 2: WEST 345 kV sensitivity |
| `no-spl+hicks2x` | unconstrained | Hicks→Willow Creek 2,400 MVA; rest cables | constant | constant | EIA | Phase 2: NORTH 345 kV sensitivity |
| `hrl-real-offers` | best from Phase 2 | best from Phase 2 | **hourly actual** | **hourly actual** | **NP3-965-ER** | Phase 3: numerical validation |
