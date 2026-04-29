# Build to DC-SCED Plan

**Goal:** Assemble Vatic input tables (`bus.csv`, `branch.csv`, `gen.csv`, `storage.csv`) from public sources already in this repo, sufficient to run a DC Security-Constrained Economic Dispatch using `Birchfield/vatic/`.

---

## What Vatic Actually Requires (Minimum)

From reading `Birchfield/vatic/` source — Vatic reads more columns than it uses. The true minimum for DC-SCED:

| Table | Required Fields |
|-------|----------------|
| `bus.csv` | Bus ID, Bus Name, Zone, BaseKV, MW Load, lat, lng |
| `branch.csv` | UID, From Bus, To Bus, X (p.u.), Cont Rating (MVA) |
| `gen.csv` | GEN UID, Bus ID, Fuel, PMin MW, PMax MW, Ramp Rate MW/Min, MW Break 1–5, MWh Price 1–5, Min Up/Down Time Hr, Start Heat Cold/Warm/Hot MBTU, Fuel Price $/MMBTU, Fixed Cost($/hr) |
| storage (native element) | p_charge_max, p_discharge_max, energy_capacity, initial_state_of_charge, bus |

R, B, voltage/angle, and reactive power fields are present in the Texas-7k source files but **not used** in DC-SCED.

Vatic natively supports storage as a first-class element type — bidirectional (p_charge / p_discharge timeseries + state-of-charge). No separate CSV; it's added directly to the model template's `elements['storage']` dict.

---

## Current Assets

| Asset | File | Status |
|-------|------|--------|
| Electrical bus catalog | `grid_data/Electrical_Bus_to_Hub_Lists/Full_Electrical_Bus_*.csv` | ~5,000 buses, no coordinates |
| Bus → hub, voltage, zone | `grid_data/Electrical_Bus_to_Hub_Lists/Electrical_BusMap_To_HUB_*.csv` | voltage + hub mapping |
| Settlement point → bus | `grid_data/SP_List_EB_Mapping/Settlement_Points_*.csv` | PSSE bus name, voltage, substation, zone |
| Generator → resource node | `grid_data/SP_List_EB_Mapping/Resource_Node_to_Unit_*.csv` | unit name → resource node |
| Matched substation geo | `grid_data/matching_results/texas_matched_substations_v6.csv` | 4,955 substations, lat/lon, ~50% high/med confidence |
| HV line geometry | `grid_data/texas_hv_lines.geojson` | 22,913 independent LineStrings, voltage, length — no bus IDs |
| Generator capacities | `grid_data/MORA_April2026_unit_capacities.csv` | name, fuel, zone, installed MW |
| Battery storage (BESS) | `grid_data/MORA_April2026_unit_capacities.csv` (storage section) | 279 operational BESS units, county + zone + MW |
| Interconnection queue | `grid_data/IX_queue.xlsx` | in-queue BESS and generation with location data |

---

## Network Scale Decision

**How many nodes do we actually need for a meaningful SCED?**

Our `lmp_test.csv` contains **1,070 ERCOT LMP resource nodes** (plus 8 zones, 7 hubs, 4 DC ties). This is the natural anchor for our model — every resource node has a published price, generators are natively assigned to these nodes in ERCOT's system, and BESS/storage units are registered at them too. This raises the question: should we model the full ~5,000 electrical bus network, or aggregate to just the ~1,070 LMP nodes?

### Comparison to Texas A&M reference cases

| Model | Nodes | Branches | Basis | Primary Use |
|-------|-------|----------|-------|-------------|
| Texas-2K | ~2,000 | ~3,000 | Synthetic (Birchfield) | Standard academic ERCOT benchmark; widely cited in production cost and market studies |
| Texas-7K | ~7,000 | ~9,140 | Synthetic (Birchfield) | High-fidelity ERCOT studies; used in NREL wind integration work |
| Ours (full OSM) | ~3,000–5,000 est. | ~10,000–20,000 est. | Real OSM topology + ERCOT buses | Geographically grounded; higher resolution than 2K |
| Ours (LMP-anchored) | ~1,070 | TBD | Real ERCOT pricing nodes | Directly comparable to published prices; smaller scope |

Texas-2K is the accepted floor for academic SCED in ERCOT — it's coarse enough that some intra-zonal congestion is invisible, but it captures the major inter-regional constraints and has been validated in numerous papers. Our 1,070-node model would sit slightly below that floor by node count.

### The case for the LMP-anchored (~1,070 node) model

- Every bus corresponds to a real ERCOT pricing point — LMP validation is direct, not approximate.
- Generators and BESS are already natively assigned to resource nodes by ERCOT.
- This is a genuinely novel contribution: the existing Texas-2K/7K are **synthetic** — nodes placed at county centroids, generators assigned probabilistically. Ours would be the first public DC-SCED model anchored to real ERCOT pricing topology.
- Academic precedent: the IEEE 300-bus is considered a meaningful benchmark at roughly this scale.

### The case against

- At ~1,070 nodes, intra-zonal congestion on 138 kV lines is largely invisible — this is the dominant binding constraint category in ERCOT.
- Resource nodes are pricing aggregations, not physical buses. Multiple electrical buses roll up to a single resource node, so some topology is flattened by design.
- The branch network between 1,070 resource nodes is harder to construct from OSM data, which is organized around physical substations (not pricing nodes).

### Recommendation

Build the **full OSM electrical bus topology** (Step 1 as written — ~5,000 buses + synthetic junctions from Step 2). This gives a model comparable to or exceeding Texas-2K in resolution, and keeps the network physically grounded in real geography. At the output/validation stage, aggregate results to the 1,070 LMP node level for direct price comparison against published ERCOT data. This makes the model both academically rigorous and directly validatable — the two approaches are complementary, not competing.

If compute or data assembly proves intractable at full scale, the 1,070-node model is the fallback and is still publishable as a pricing-node reduced model.

---

## Step 1 — Bus Table

**Input:** `Full_Electrical_Bus_*.csv`, `Electrical_BusMap_To_HUB_*.csv`, `Settlement_Points_*.csv`, `texas_matched_substations_v6.csv`

**Method:**
1. Start from the full electrical bus list (~5,000 entries).
2. Join `Electrical_BusMap_To_HUB` → get `BaseKV` and load zone.
3. Join `Settlement_Points` on `ELECTRICAL_BUS` → get `PSSE_BUS_NAME` and `SUBSTATION`.
4. Match `SUBSTATION` → `ercot_substation` in v6 to get `lat`, `lon`.
5. Assign sequential integer `Bus ID`. Default `Bus Type = PQ`; override to PV for generator buses in Step 3.

**Gap:** Buses with no v6 coordinate match inherit zone centroid coordinates. Acceptable for DC-SCED — topology matters more than precise geography.

Plus synthetic junction buses added in Step 2 below.

**Output:** `Realist/grid_data/sced_inputs/bus.csv`

---

## Step 2 — Branch Table and Junction Buses

This is the most complex step. OSM HV lines are stored as independent LineStrings — they do not share coordinate references at junctions. Connections are inferred by proximity.

### 2a. Endpoint Extraction and Clustering

Repurpose the clustering logic from `ERCOT/hv_matching.py` Pass 9B (already written):
1. For each of the 22,913 OSM lines, extract the **first and last coordinate** of the geometry.
2. Pool all 45,826 endpoints.
3. Cluster endpoints within **150 m** of each other (same radius used in Pass 9B). Each cluster represents a physical connection point — a substation, a T-tap, or a splice.

### 2b. Assign Bus IDs to Clusters

For each cluster:
- **Check for nearby named substation:** if any matched substation from v6 is within **1 km** (same threshold as V6 snap), assign that substation's Bus ID.
- **No nearby substation:** if the cluster has **≥ 3 incident line endpoints** (a true junction) — create a **synthetic bus**: auto-generated Bus ID, no load, no generation, voltage inherited from the highest-voltage incident line, coordinates = cluster centroid.
- **Isolated endpoint pairs** (clusters with exactly 2 endpoints and no named substation within 1 km): these are mid-line intermediate points, not true junctions. **Drop them** — they don't represent distinct buses.

This gives every line a `From Bus` and `To Bus` assignment.

### 2c. Impedance and Thermal Limits

- **X (per-unit reactance):** Standard per-km values by voltage tier (overhead line):
  - 138 kV: 0.38 Ω/km → `X_pu = 0.38 × length_km / (138² / 100)`
  - 230 kV: 0.35 Ω/km → `X_pu = 0.35 × length_km / (230² / 100)`
  - 345 kV: 0.32 Ω/km → `X_pu = 0.32 × length_km / (345² / 100)`
  - 500 kV: 0.28 Ω/km → `X_pu = 0.28 × length_km / (500² / 100)`
  - Base: `S_base = 100 MVA`.
  - Note: Vatic's loader divides X by 100 internally — pass raw p.u. values.
- **Cont Rating (MVA):** Standard tier defaults:
  - 138 kV: 300 MVA | 230 kV: 600 MVA | 345 kV: 1,200 MVA | 500 kV: 2,000 MVA
- Set `R = 0`, `B = 0` (unused in DC model).

**Output:** `Realist/grid_data/sced_inputs/branch.csv`
Plus updated `bus.csv` with synthetic junction buses appended.

---

## Step 3 — Generator Table

**Input:** `MORA_April2026_unit_capacities.csv` (non-storage rows), `Resource_Node_to_Unit_*.csv`, `Settlement_Points_*.csv`, `bus.csv`

**Method:**
1. **Bus assignment chain:** `MORA unit_name` → `Resource_Node_to_Unit.UNIT_NAME` → `RESOURCE_NODE` → `Settlement_Points.RESOURCE_NODE` → `ELECTRICAL_BUS` → `Bus ID`.
2. **PMin/PMax:** From MORA `installed_mw` as PMax. PMin ratios by fuel:
   - Nuclear: 0.90 × PMax | Coal: 0.40 × PMax | Gas CC: 0.30 × PMax | Gas CT: 0.10 × PMax
   - Wind/Solar: PMin = 0, PMax = installed_mw (non-dispatchable)
3. **Cost curves:** ERCOT publishes actual submitted offer curves via the **60-Day SCED Disclosure** (NP3-965-ER), including "SCED Energy Offer Curve Updates in Operating Hour" — MW breakpoints and $/MWh prices per unit, lagged 60 days. This is the preferred source and makes the cost curve assumption unnecessary. Fetch the disclosure report for a target operating day, join on `GEN UID`, and use the actual offer curve. Fallback for units not in the disclosure (e.g., new entrants or missing data): EIA 2023 average heat rates × fuel price:
   - Nuclear: $8/MWh | Coal: $25/MWh | Gas CC: $28/MWh | Gas CT: $42/MWh | Wind/Solar: $0/MWh
4. **Ramp rates** (MW/min): Nuclear 0.5% PMax | Coal 1% PMax | Gas CC 2% PMax | Gas CT 8% PMax
5. **Commitment:** Min Up/Down = 4 hr for thermal. Startup heats = 0 for baseline run.
6. Set `MustRun = True` for Nuclear.

**Output:** `Realist/grid_data/sced_inputs/gen.csv`

---

## Step 4 — Storage Table

MORA contains **279 operational BESS units** as of April 2026, with county, zone, and MW.

**Input:** `MORA_April2026_unit_capacities.csv` (storage section, `fuel = "STORAGE"`), `Resource_Node_to_Unit_*.csv`, `Settlement_Points_*.csv`, `bus.csv`

**Method:**
1. **Bus assignment:** Same chain as Step 3 — `unit_name` → `RESOURCE_NODE` → `ELECTRICAL_BUS` → `Bus ID`. BESS units that are operational should appear in the Resource Node table.
2. **Fallback if no resource node match:** assign to nearest matched substation in the same county and zone. If no county match, assign to zone hub bus.
3. **Power bounds:** `p_charge_max = p_discharge_max = installed_mw` (ERCOT BESS are typically symmetric).
4. **Energy capacity:** MORA does not report duration. Use **2-hour default** (`energy_capacity = 2 × installed_mw` MWh). This is conservative for the current ERCOT fleet (most units are 2–4 hour); flag as an assumption.
5. **Initial SOC:** Assume 50% of energy capacity as the SCED starting state.
6. **Cost curve:** BESS offer curves are also included in the 60-Day SCED Disclosure under "ESR Data in SCED." Use the actual submitted charge/discharge offers for the same target operating day as the generator data. Fallback if ESR data is missing or unit not listed: treat as free arbitrage (marginal cost = 0 discharge, marginal value = 0 charge), which overstates BESS dispatch — flag this in the paper.

**Output:** Storage entries added to the Vatic model template's `elements['storage']` dict in `run_sced.py`, not a standalone CSV (matching Vatic's native structure).

---

## Step 5 — Load Distribution

**Input:** ERCOT public zonal demand (ercot.com, hourly), `bus.csv`

**Method:**
1. Pull a representative hour (e.g., a recent peak).
2. Distribute zonal MW uniformly across buses within each zone.

**Output:** `MW Load` column populated in `bus.csv`.

---

## Step 6 — Initial Conditions

Use Vatic's built-in fallback (no init-state CSV required):
- All thermal units start off.
- Nuclear: `MustRun = True`.
- BESS: `initial_state_of_charge = 0.5 × energy_capacity`.

---

## Step 7 — Integration with Vatic

1. Place assembled files in `Realist/grid_data/sced_inputs/`.
2. Write `Realist/ERCOT/run_sced.py`:
   - Load bus/branch/gen CSVs using Vatic's parser.
   - Populate `elements['storage']` from BESS data.
   - Set `S_base = 100 MVA`, designate slack bus (highest-degree bus, or HB_BUSAVG's Bus ID).
   - Run single-period DC-SCED.
   - Write: dispatch by unit, line flows, shadow prices.
3. Sanity check: compare shadow prices on named constraints against `ERCOT_SCED_Shadowprices.csv`.

---

## Key Assumptions Summary

| Assumption | Justification |
|-----------|---------------|
| 150 m clustering radius for junction detection | Inherited from Pass 9B; validated against 345 kV line topology |
| 1 km threshold for cluster → named substation assignment | Inherited from V6 snap logic |
| Synthetic buses at ≥3-way junction clusters | Standard practice in grid model construction; preserves topology |
| Per-km reactance by voltage tier | Standard overhead line parameters; actual values require ERCOT's non-public network model |
| Flat MVA ratings by voltage tier | ERCOT line ratings not public; tier defaults are standard academic practice |
| Intra-zone load uniform distribution | No bus-level demand data available publicly |
| Cost curves from 60-day SCED disclosure | Preferred; ERCOT publishes actual submitted offer curves at 60-day lag (NP3-965-ER). EIA heat rates used only as fallback for missing units. |
| BESS offer data from 60-day SCED disclosure | ESR Data in SCED report covers energy storage resources. Fallback: free arbitrage (overstates dispatch). |
| BESS duration = 2 hours | MORA does not report duration; 2-hour is conservative for current ERCOT fleet |

---

## Output Files

```
Realist/grid_data/sced_inputs/
├── bus.csv          (ERCOT electrical buses + synthetic junction buses)
├── branch.csv       (OSM lines with from/to bus, X, Cont Rating)
└── gen.csv          (MORA generators with cost curves)

Realist/ERCOT/
└── run_sced.py      (Vatic runner; also builds storage elements inline)
```

---

## Open Questions Before Starting

- Single-period SCED only, or multi-period UC + SCED?
- Should wind/solar be curtailable (dispatchable down to 0) or fixed injection?
- What's the acceptable snap miss rate for branch connectivity — how many of the 22,913 OSM lines is it OK to drop if endpoints don't cluster to any bus?
- BESS 2-hour default: should we try to recover actual durations from IX queue or published ERCOT reports?
- Which operating day should the 60-day SCED disclosure data be pulled for? (Must be ≥60 days in the past; pick a day with notable congestion for interesting results.)
