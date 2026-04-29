# Dartboard

Open-source ERCOT market analysis — geographically grounded DC-SCED from entirely public data.

---

## What This Is

A DC Security-Constrained Economic Dispatch (DC-SCED) model of the real ERCOT grid, built from:
- **OpenStreetMap** — transmission line geometries and substation locations
- **ERCOT public data** — MORA generator registry, settlement point mappings, SCED disclosure offer curves
- **EIA-860** — generator coordinates and energy storage capacities
- **Vatic** (Texas A&M) — DC-SCED solver with Gurobi on Princeton Adroit cluster

Every bus is anchored to a real OSM substation location. Every generator is a registered ERCOT resource. No synthetic nodes, no Census centroids.

The project is an active research effort. An AI agent (Claude Code) implements improvements, runs experiments on the cluster, analyzes results, and iterates. Session logs track full history; this README is the current-state anchor.

---

## Current Model State

*Last updated: 2026-03-29*

Three topology versions exist. V3 is current.

### V3 Topology (current — geometry-based line splitting)

Built by `generate_visualizer_v3.py` + `build_osm_branch_table_v3.py` from re-fetched OSM (49,392 features: power lines, cables, minor lines).

- **3,786 buses**: 3,368 OSM substations + 418 T-junction split points
- **4,817 branches** (post connectivity filter)
- **Branch ratings** (baked into branch.csv):
  - 138 kV: 250 MVA/circuit (single-circuit Drake ACSR; OSM `cables=3` confirms single-circuit for 89% of 138 kV)
  - 230 kV: 600 MVA/circuit
  - 345 kV: 1,200 MVA/circuit (2,400 MVA for double-circuit per GeoJSON cable count)
  - 500 kV: 2,000 MVA/circuit (4,000 MVA double-circuit)
  - All 345 kV upgraded to 2,400 MVA **except L1605_1612** (Morgan Creek→Tonkawa, WESTEX)
  - SPL junctions: voltage-tier rated (no compensating-error inflation)
- **Topology health**: E/N 1.46, mean degree 2.93, bridge ratio 14.4%, 99.0% in main connected component
- **Benchmark**: exceeds real ERCOT aggregate (E/N ~1.31, mean degree 2.61; Aksoy 2018)

### V1 Topology (clean-build baseline)

Built by `generate_visualizer.py` + `build_osm_branch_table.py` from original OSM fetch (22,913 HV lines).

- **3,878 buses**, **4,501 branches**
- 138 kV: 600 MVA (compensating error for sparser topology); SPL at 999,999 MVA
- Canonical result: 81.7 MW steady-state shed on Nov 5 2025

### Generation Fleet (gen.csv)
Sourced from MORA April 2026 via 4-stage bus matching. **PMax = nameplate MW** (no CF pre-scaling).

| Fuel | Units | MW |
|---|---|---|
| Gas (CC/GT/ST/IC) | 449 | 61,543 |
| Wind | 384 | 40,534 |
| Solar | 327 | 37,684 |
| Coal | 21 | 14,713 |
| Nuclear | 4 | 5,268 |
| **Total** | **1,185** | **159,742** |

CFs are applied in `run_sced.py` at dispatch time only. Renewable matching covers >98% of MORA capacity.

### Energy Storage (storage.csv)
Sourced from MORA April 2026 + EIA-860 Form 3.4. 289 units, 17,458 MW discharge, 54,320 MWh capacity. Bus assignment uses same 4-stage pipeline as gen.csv. Efficiency: 0.96 one-way. Present in sced_inputs_v3/ and injected into model via monkey-patch, but **Egret does not dispatch the storage elements** — needs investigation into StorageData format.

### Calibration Results (tuning days)

| Tag | Topology | Date | Shed (MW) | Price ($/MWh) | Notes |
|---|---|---|---|---|---|
| v1 | V1 | Nov 5 | 27,242 (h0) / 8,622 (SS) | $19.66 | Baseline; cold start, PSSE buses |
| clean-build | V1 | Nov 5 | **81.7** | $21.31 | 600 MVA 138 kV; baked SPL+plant fixes |
| v3r2-nov5 | V3 | Nov 5 | **1,195** | $24.26 | V3 baseline at 250 MVA; 29 DFW buses shed |
| **v3-j17-t135f-r15** | **V3** | **Jun 17** | **0** | **$2–59** | **135 upgr + f1200 + r=0.15. SOLVED. 24/24 W<N.** |
| v3-jan08-t135f-r15 | V3 | Jan 8 | **0** | — | Regression check passed |
| v3-nov5-t135f-r15 | V3 | Nov 5 | **0** | — | Regression check passed |

### Validation Results (unseen days — model never tuned to these)

| Tag | Date | Peak GW | Shed MW | W<N | Verdict |
|---|---|---|---|---|---|
| val-mar29 | 2024-03-29 | 42.3 | **0** | 21/24 | PASS — high wind, massive curtailment, correct W<N |
| val-oct29 | 2024-10-29 | 58.4 | **0** | 22/24 | PASS — fall wind, clean dispatch |
| val-apr13 | 2024-04-13 | 46.1 | **0** | 20/24 | PASS — spring balanced renewables |
| val-jul23 | 2024-07-23 | 58.1 | 2 | 11/24 | PASS — low wind, correctly flat LMPs |
| val-sep29 | 2024-09-29 | 61.1 | 254 | 9/24 | PARTIAL — 240 MW evening ramp scarcity |
| val-aug20 | 2024-08-20 | 77.3 | **6,282** | 15/24 | FAIL (expected) — record peak, Houston corridor saturation |

Full table: `Realist/ERCOT_Calibration_Experiments/experiments.md` (80+ experiments).

### Key Physics Results

**3 tuning days solved, 4/6 unseen validation days pass clean.** The winning config generalizes across seasons and wind regimes without overfitting.

The winning configuration (v3-j17-t135f-r15) combines:
- V3 geometry-based topology (3,786 buses, 4,817 branches)
- 135 targeted line upgrades (250→500 MVA) identified iteratively from binding-line analysis
- f1200 floor ratings (cap 1,200 MVA from unconstrained Kirchhoff flows)
- 15% spinning reserve requirement (forces adequate thermal commitment for morning ramp)

**WESTEX export constraint is working.** On June 17, 2024 (74.4 GW peak), WEST LMP < NORTH LMP all 24 hours. WEST drops to $1–6/MWh during peak wind while NORTH holds at $25–29 and HOUSTON reaches $50–59 — the correct ERCOT congestion pattern.

**Low-wind physics correct.** Jul 23 and Sep 29 show flat LMPs ($28 = marginal gas) during thermal-only hours. No artificial WEST cheapness when wind isn't generating.

**Aug 20 failure is congestion, not capacity.** At 77 GW, 11.6 GW thermal headroom + 4.6 GW curtailed renewables available — the system has ~99 GW. The problem is 18 binding transmission lines (Houston import corridors at 2,400 MVA). The 135 targeted upgrades were tuned to 74 GW; at 77 GW new bottlenecks emerge. T175 config (additional 40 upgrades) reduces Aug 20 shed to 26 MW but weakens W<N ordering.

**Shedding confirmed 100% congestion-driven.** Feedback-based commitment experiments (force-committing thermal near shedding buses) produced identical or slightly worse results. The RUC is already committing the right generators.

**Tract+degree load allocation regression.** More granular population data (census tract vs county) concentrates load on urban core buses behind congested corridors. The county-level uniform allocation accidentally matches the simplified topology. Population allocation is a compensating simplification.

### Known Issues (priority order)

1. **Houston corridor saturation at >74 GW** — At record peak (77 GW, Aug 20), 18 binding 345 kV lines into Houston cause 6,282 MW shed. T175 config reduces to 26 MW but weakens W<N. The 345 kV corridors are a hard ceiling — doubling them eliminates realistic congestion pricing. Likely needs storage dispatch (item 2) to resolve.
2. **Storage dispatch non-functional** — storage.csv (17.5 GW) present in sced_inputs_v3/ and monkey-patched into Egret model dict, but solver does not dispatch storage elements. Needs investigation into Egret StorageData format. Real ERCOT has ~10 GW of batteries that would absorb Houston peak demand.
3. **Wind capacity gap** — OSM captures ~23 GW wind vs 42 GW in MORA. Many wind farms unmapped in OSM. EIA-860 cross-reference needed.
4. **Coal retirement filtering** — gen.csv includes 14.7 GW coal, some of which is retired. OSM carries historical plants.
5. **LMP magnitudes** — zone ordering correct; magnitudes may be off vs real ERCOT. Driven by offer curve staleness and network topology simplification.
6. **Load allocation is a compensating simplification** — county-population uniform allocation works because it accidentally matches the simplified topology's capacity. More realistic (tract-level) allocation causes regressions.

---

## Pipeline

```
OSM / ERCOT public data
        |
        v
generate_visualizer_v3.py     → grid_visualizer_v3.html (3,368 subs, 4,927 edges)
        |
        v  [run on adroit]
build_osm_bus_table.py        → sced_inputs/osm_bus.csv
build_osm_branch_table_v3.py  → sced_inputs/SourceData/branch.csv, bus.csv
build_gen_table.py            → sced_inputs/SourceData/gen.csv, init_state.csv
build_storage_table.py        → sced_inputs/SourceData/storage.csv
        |
        v  [adroit SLURM]
run_sced.py                   → results_<TAG>/  (hourly_summary, bus_detail, line_detail, ...)
```

All pipeline scripts: `Realist/ERCOT/`. All data: `Realist/grid_data/`. SLURM array: `run_sced_array.slurm` (tasks 0–103 defined; extend for new experiments).

### Env vars for run_sced.py

| Var | Default | Purpose |
|---|---|---|
| `SCED_DATE` | `2025-11-05` | Simulation date (YYYY-MM-DD) |
| `HOURLY_LOAD_CSV` | _(none)_ | Path to hourly zone load CSV (hour, NORTH, HOUSTON, SOUTH, WEST) |
| `HOURLY_CF_CSV` | _(none)_ | Path to hourly wind/solar CF CSV (hour, Wind, Solar) |
| `DARTBOARD_SCRATCH` | _(none)_ | Adroit scratch path; overrides all local paths |
| `EXPERIMENT_TAG` / `SCED_INSTANCE` | _(none)_ | Results subdir tag |
| `BRANCH_SCALE` | `1` | Multiply all branch ratings by this factor |
| `SCALE_345KV` | _(none)_ | Multiply 345 kV ratings only |
| `SCALE_138KV` | _(none)_ | Multiply 138 kV ratings only |
| `LOAD_ALLOC` | `pop` | Load allocation method: pop, uniform, sqrt, cap75 |
| `UPGRADE_LINES` | _(none)_ | Comma-separated branch UIDs to double (250→500 MVA) |
| `FLOOR_RATINGS_CSV` | _(none)_ | CSV of per-branch floor ratings from unconstrained flows |
| `RESERVE_FACTOR` | `0.05` | Spinning reserve requirement as fraction of demand |
| `RESERVE_PENALTY` | `1e3` | Reserve shortfall penalty ($/MWh) |
| `SCED_DIR_OVERRIDE` | _(none)_ | Custom SCED input directory |
| `VIZ_HTML` | _(none)_ | Custom visualizer HTML path (for bus/branch build) |

### Preparing a calibration day

```bash
python3 Realist/ERCOT/prepare_calibration_day.py \
    --date 2024-06-17 \
    --native-load Native_Load_2024.csv \
    --wind-output wind_actual_2024.csv \
    --solar-output solar_actual_2024.csv \
    --gen-csv sced_inputs/SourceData/gen.csv \
    --out-dir /scratch/network/js0735/dartboard
```

### Calibration & validation days

| Day | Date | Load range | Condition | Data location |
|---|---|---|---|---|
| Nov 5 | 2025-11-05 | 50.9 GW constant | Moderate wind baseline | (constant; no CSV needed) |
| Jun 17 | 2024-06-17 | 52–76 GW hourly | Summer peak + high wind/solar | ERCOT_Calibration_Experiments/june17_2024/ |
| Jan 8 | 2024-01-08 | 41–51 GW hourly | Extreme wind (25+ GW) | ERCOT_Calibration_Experiments/jan08_2024/ |
| Aug 20 | 2024-08-20 | 51–79 GW hourly | 2024 record peak, low wind | ERCOT_Calibration_Experiments/validation_days/ |
| Sep 29 | 2024-09-29 | 37–62 GW hourly | Worst wind day of 2024 | ERCOT_Calibration_Experiments/validation_days/ |
| Mar 29 | 2024-03-29 | 34–43 GW hourly | Best wind day of 2024 | ERCOT_Calibration_Experiments/validation_days/ |
| Oct 29 | 2024-10-29 | 43–60 GW hourly | Fall high wind | ERCOT_Calibration_Experiments/validation_days/ |
| Apr 13 | 2024-04-13 | 33–47 GW hourly | Spring balanced renewables | ERCOT_Calibration_Experiments/validation_days/ |
| Jul 23 | 2024-07-23 | 42–59 GW hourly | Summer low wind | ERCOT_Calibration_Experiments/validation_days/ |

---

## Data Sources

| File | Source | Contents |
|---|---|---|
| `grid_data/texas_hv_lines.geojson` | OSM Overpass API | 49,392 transmission features (lines, cables, minor lines; all voltages) |
| `grid_data/texas_substations.geojson` | OSM Overpass API | 5,786 Texas substation locations |
| `grid_data/ercot_zones.geojson` | ERCOT public | Load zone boundaries (point-in-polygon for bus zones) |
| `grid_data/MORA_April2026_unit_capacities.csv` | ERCOT MORA report | 1,778 registered generation units + 418 storage units |
| `grid_data/3_4_Energy_Storage_Y2024.xlsx` | EIA-860 Form 3.4 | Texas storage nameplate MW + MWh (136 operable units) |
| `grid_data/sced_disclosure_20251105_gen_resource.csv` | ERCOT MIS | Nov 5 2025 SCED offer curves (HSL, offer segments, ancillary) |
| `grid_data/matching_results/texas_matched_substations_v6.csv` | This project | OSM↔ERCOT substation bridge (4,955 rows, 9-pass algorithm) |
| `grid_data/SP_List_EB_Mapping/` | ERCOT public | Resource node → electrical bus → substation |
| `Birchfield/data/processed/eia860_generators.csv` | EIA-860 2023 | Generator coordinates for geo-snap fallback |

---

## Repository Structure

```
Dartboard/
├── Realist/
│   ├── ERCOT/                        # All pipeline scripts
│   │   ├── generate_visualizer_v3.py  # OSM → grid_visualizer_v3.html (current)
│   │   ├── generate_visualizer.py     # v1 (original)
│   │   ├── build_osm_bus_table.py     # grid_visualizer.html → osm_bus.csv
│   │   ├── build_osm_branch_table.py  # v1 branch builder (600 MVA 138 kV)
│   │   ├── build_osm_branch_table_v2.py  # v2 (bridge compensation)
│   │   ├── build_osm_branch_table_v3.py  # v3 (250 MVA baseline, no comp. errors)
│   │   ├── build_gen_table.py         # MORA + EIA-860 → gen.csv, init_state.csv
│   │   ├── build_storage_table.py     # MORA + EIA-860 → storage.csv
│   │   ├── compute_floor_ratings.py   # Unconstrained flow → floor rating CSVs
│   │   ├── prepare_calibration_day.py # ERCOT public data → hourly load/CF CSVs
│   │   ├── run_sced.py               # Vatic DC-SCED runner
│   │   ├── run_sced_array.slurm      # SLURM array (tasks 0–103)
│   │   ├── hv_matching.py            # OSM↔ERCOT substation matching (9 passes)
│   │   └── v6_crosswalk_and_snap.py  # Final substation crosswalk → v6
│   │
│   ├── grid_data/                    # All input data (see Data Sources above)
│   │   ├── sced_inputs/              # V1 topology (clean-build)
│   │   ├── sced_inputs_v2/           # V2 topology (bridge compensation)
│   │   ├── sced_inputs_v3/           # V3 topology (geometry-based)
│   │   │   └── SourceData/           # bus.csv, branch.csv, gen.csv, etc.
│   │
│   ├── vatic/                        # Vatic DC-SCED library (Texas A&M fork)
│   ├── OIM/                          # OSM fetch + LMP scraping utilities
│   ├── plans/                        # Design documents
│   ├── ERCOT_Calibration_Experiments/ # Session logs and experiment results
│   │   ├── experiments.md             # All experiments quick-reference table
│   │   ├── build_diagnostics.py       # Diagnostic engine (see Diagnostic Tools below)
│   │   ├── compare.py                 # Legacy terminal comparison (superseded by engine)
│   │   ├── diagnostics.html           # Generated output — Map + Scorecard tabs
│   │   ├── session_2026-03-*.md       # Daily session logs
│   │   ├── results/                   # Pulled from adroit (80+ experiment folders)
│   │   ├── june17_2024/              # Jun 17 calibration day data
│   │   ├── jan08_2024/               # Jan 8 calibration day data
│   │   └── validation_days/          # 6 out-of-sample validation day CSVs
│   │
│   ├── NYISO/                        # Parallel NY grid build (proof-of-concept)
│   ├── correspondence/               # Literature review, outreach
│   ├── grid_visualizer_v3.html       # V3 interactive map (current)
│   ├── grid_visualizer_v2.html       # V2 interactive map
│   ├── grid_visualizer.html          # V1 interactive map
│   └── sced_diagnostic.html          # Shedding/LMP diagnostic map
│
├── Birchfield/                       # Archival: synthetic grid (Birchfield et al.)
│   └── data/processed/eia860_generators.csv  # ← still used by Realist pipeline
│
├── INDEX.md                          # Full repo index & glossary
├── README.md                         # This file — current model state anchor
├── CLAUDE.md                         # Agent instructions
├── CLUSTER_README.md                 # Princeton Adroit setup
└── report_draft.md                   # Academic paper draft
```

---

## Adroit Cluster

SSH alias: `adroit` (Princeton Research Computing, `adroit.princeton.edu`)
Scratch: `/scratch/network/js0735/dartboard/`
Conda env: `/home/js0735/.conda/envs/vatic-test`
Gurobi license: `/usr/licensed/gurobi/license/gurobi.lic`

Submit a run:
```bash
ssh adroit "sbatch --array=98-103 /scratch/network/js0735/dartboard/run_sced_array.slurm"
```

Check status:
```bash
ssh adroit "squeue -u js0735"
```

Pull results:
```bash
scp -r adroit:/scratch/network/js0735/dartboard/sced_inputs_<TAG>/results_<TAG>/ \
    Realist/ERCOT_Calibration_Experiments/results/<TAG>/
```

---

## Visualization & Diagnostics

Three interactive HTML tools, each serving a different purpose. All are self-contained Leaflet maps — no server needed, just open in a browser.

### 1. Grid Visualizer (`grid_visualizer_v3.html`)

**What it shows:** The full OSM topology and all SCED model inputs — the "what goes into the model" view.

**Layers (toggleable):**

| Layer | Contents | Default |
|-------|----------|---------|
| OSM Network | 5,506 OSM substations + raw transmission line geometry (color = voltage tier) | ON |
| SCED Network | 3,786 SCED buses + visualizer-derived edges (dashed, color = voltage) | ON |
| Real SCED Branches | 5,292 actual branch.csv edges used by the solver (dashed, color = rating tier) | OFF |
| MORA Gen → Bus | 347 generator bus dots (1,186 MORA generators aggregated per bus, color = dominant fuel, size = total MW). Click for per-generator popup. Snap lines show matching distance. | OFF |
| OSM Plants | 736 OSM `power=plant` features (NOT used by SCED — display only) | OFF |
| SCED Results | Utilization-colored edges + shedding/LMP nodes from one embedded experiment | OFF |
| Zone Boundaries | ERCOT load zone polygons | OFF |

**Color modes** (radio buttons): Voltage tier or Generator type — applies to both OSM and SCED node layers.

**Generated by:** `Realist/ERCOT/generate_visualizer_v3.py` (topology) + programmatic injection of `GEN_BUSES` and `SCED_BRANCHES` data arrays.

**Key caveat — two edge sets:** The "SCED Network" layer shows edges derived by `generate_visualizer_v3.py` (5,323 edges), which differ from the actual SCED branches in `branch.csv` (5,292 edges via `build_osm_branch_table_v3.py`). The "Real SCED Branches" layer shows the correct solver edges. These diverged because the two scripts use different line-splitting algorithms on the same OSM data. The Real SCED Branches layer is authoritative.

**Generator data:** The "MORA Gen → Bus" layer shows all 1,186 generators from `gen.csv` (sourced from ERCOT MORA registry), aggregated to 347 bus locations. This is what the SCED actually dispatches. The "OSM Plants" layer (736 plants) is a separate OSM dataset NOT used by the SCED — it's kept for reference but is misleading if compared to SCED results.

### 2. SCED Diagnostic Map (`sced_diagnostic.html`)

**What it shows:** SCED results overlaid on the real solver topology — the "what came out of the model" view.

**Features:**
- Dropdown to switch between experiments (each is a single-hour snapshot)
- Bus circles colored by LMP (blue = cheap → red = expensive/shedding)
- Lines colored by utilization (green → orange → red/binding)
- Zone labels with median/average LMP
- Legend with demand, shedding, curtailment, binding line count

**Generated by:** `Realist/ERCOT/build_sced_diagnostic.py`

```bash
cd Realist/ERCOT

python build_sced_diagnostic.py \
  'final-j17:14:Jun 17 — final config' \
  'final-aug20:17:Aug 20 — stress test' \
  'final-mar29:12:Mar 29 — high wind' \
  'final-jul23:15:Jul 23 — low wind'

# Each argument: TAG:HOUR:LABEL
open ../sced_diagnostic.html
```

~1.3 MB per experiment. Also serves as the topology source for `diagnostics.html` (the 5,292 lines with coordinates and ratings are the authoritative representation of the real SCED network).

### 3. Experiment Scorecard (`diagnostics.html`)

**What it shows:** Side-by-side comparison of multiple experiments — the "which config is better" view.

**Tabs:**
- **Map** — Same Leaflet map as `sced_diagnostic.html` with experiment dropdown
- **Scorecard** — Comparison table (shed, curtailment, price, W<N hours), zone LMP table, hourly sparkline charts

**Generated by:** `Realist/ERCOT_Calibration_Experiments/build_diagnostics.py`

```bash
cd Realist/ERCOT_Calibration_Experiments

# Terminal quick-check
python build_diagnostics.py compare --tags final-j17 final-aug20 val-aug20

# Build interactive HTML
python build_diagnostics.py build --tags final-j17 final-aug20 val-aug20 --hour 17
python build_diagnostics.py build -n 10         # 10 most recent experiments
python build_diagnostics.py list --detail       # show all available with stats

open diagnostics.html
```

### Data flow between the three tools

```
gen.csv + bus.csv + branch.csv (on adroit)
        |
        v  [SCED run]
results/<TAG>/  (hourly_summary, bus_detail, line_detail)
        |
        +--→ build_sced_diagnostic.py → sced_diagnostic.html (map + topology source)
        |                                       |
        +--→ build_diagnostics.py  ←────────────+  (reads topology from sced_diagnostic)
                |
                v
           diagnostics.html (scorecard + map)

generate_visualizer_v3.py → grid_visualizer_v3.html (topology explorer)
        + GEN_BUSES from gen_matching.csv  (injected by build_gen_table.py)
        + SCED_BRANCHES from sced_diagnostic.html  (injected programmatically)
```

### Topology note

The local `sced_inputs_v3/SourceData/branch.csv` (4,817 lines, voltage-suffixed UIDs) does NOT match the branch.csv on adroit that the SCED actually uses (5,292 lines, no voltage suffix, different bus IDs). The authoritative topology lives in `sced_diagnostic.html` (extracted from actual SCED results). When adding new features to the visualizer, use the 5,292-line topology from `sced_diagnostic.html`, not the local branch.csv.

### Future: layer overlays

The visualizer architecture supports adding new toggleable layers. To overlay SCED results on the grid visualizer (combining "what goes in" with "what comes out"):

1. **Load allocation** — show bus load as sized circles (data available from `run_sced.py` zone allocation at runtime, not yet exported)
2. **LMP heatmap** — color SCED nodes by LMP from a specific experiment's `bus_detail.csv`
3. **Flow animation** — color Real SCED Branches by utilization from `line_detail.csv`
4. **Congestion diff** — compare two experiments' binding lines to see which upgrades relieved which constraints

Each would be a new `const DATA = [...]` array + rendering block + toggle checkbox, following the same pattern as `GEN_BUSES` and `SCED_BRANCHES`.

### File reference

| File | Location | Purpose |
|------|----------|---------|
| `grid_visualizer_v3.html` | `Realist/` | Topology explorer + model inputs |
| `sced_diagnostic.html` | `Realist/` | SCED results map (authoritative topology source) |
| `diagnostics.html` | `Realist/ERCOT_Calibration_Experiments/` | Experiment scorecard + comparison |
| `build_sced_diagnostic.py` | `Realist/ERCOT/` | Generates sced_diagnostic.html |
| `build_diagnostics.py` | `Realist/ERCOT_Calibration_Experiments/` | Generates diagnostics.html |
| `generate_visualizer_v3.py` | `Realist/ERCOT/` | Generates grid_visualizer_v3.html (topology) |
| `build_gen_table.py` | `Realist/ERCOT/` | Generates gen.csv + gen_matching.csv (generator data + snap coords) |
| `compute_floor_ratings.py` | `Realist/ERCOT/` | Derives line ratings from unconstrained flow runs |

---

## What's Next

**Calibration target: MET up to 74 GW.** All three tuning days show 0 MW shed with correct zone ordering. 4/6 unseen validation days pass clean. Model validated across seasons and wind regimes. Above 74 GW, Houston corridor saturation causes shedding — a known limitation pending storage dispatch.

**Immediate:**

1. **Fix Egret storage dispatch** — Monkey-patch injects 17.5 GW storage into model dict but Egret doesn't dispatch it. This is the most impactful improvement remaining — real ERCOT has ~10 GW of batteries that absorb peak demand and would likely fix the Aug 20 Houston corridor problem.

2. **Statistical validation against RTM SPP** — Compare WEST-NORTH LMP spread distribution across the 9 simulated days against ERCOT RTM SPP data (`RTMLZHBSPP_2024.zip`). The per-day results are available; the statistical comparison hasn't been done yet.

**Data quality:**

3. **Wind capacity gap** — OSM captures ~23 GW of 42 GW real wind. Cross-reference EIA-860 to identify unmapped farms.

4. **Coal retirement filtering** — gen.csv carries ~14.7 GW coal, including retired plants. Filter against ERCOT MORA retirement dates.

**Scenario analysis (longer term):**
- Data center load addition experiment (add 5–20 GW in DFW/Houston)
- West TX wind buildout tipping-point curve
- Transmission expansion cost-benefit (which upgrades have highest value?)

---

## Legal Note

`Realist/OIM/WhyThisIsntCEII.md` documents why combining EIA-860, OSM, and ERCOT public price data does not produce Critical Energy Infrastructure Information. This project never uses ERCOT's non-public network model.
