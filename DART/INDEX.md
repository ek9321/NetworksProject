# Dartboard Repository Index & Glossary

> Comprehensive catalog of the Dartboard project: an open-source DC-SCED model of the real ERCOT grid built entirely from public data. Updated 2026-03-29.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Directory Map](#2-directory-map)
3. [Pipeline Scripts (Realist/ERCOT/)](#3-pipeline-scripts)
4. [Data Files (Realist/grid_data/)](#4-data-files)
5. [Calibration Experiments](#5-calibration-experiments)
6. [Visualizers & HTML Outputs](#6-visualizers--html-outputs)
7. [Supporting Modules](#7-supporting-modules)
8. [Birchfield (Archival)](#8-birchfield-archival)
9. [Root-Level Files](#9-root-level-files)
10. [Infrastructure & Cluster](#10-infrastructure--cluster)
11. [Glossary](#11-glossary)
12. [Data Lineage Diagram](#12-data-lineage-diagram)

---

## 1. Project Overview

**Dartboard** builds a DC Security-Constrained Economic Dispatch (DC-SCED) model of the ERCOT power grid from:

| Source | What it provides |
|--------|-----------------|
| OpenStreetMap | Transmission line geometries, substation locations |
| ERCOT public data | MORA generator registry, settlement point mappings, SCED offer curves |
| EIA-860 | Generator coordinates, energy storage capacities |
| Vatic (Texas A&M) | DC-SCED solver engine |

**Key result:** The model reproduces the real WESTEX export constraint -- WEST LMP < NORTH LMP on high-wind days, with Morgan Creek-Tonkawa binding correctly. Validated on 6 unseen days spanning all seasons and wind regimes (4/6 pass clean, 2 with expected limitations).

**Scale:** 3,786 buses (V3), 4,817 branches, 159,742 MW generation, 17,458 MW storage (289 units). 80+ calibration experiments across 9 days (3 tuning + 6 validation).

---

## 2. Directory Map

```
Dartboard/
|
|-- README.md                              Current-state anchor (trust over session logs)
|-- CLAUDE.md                              Agent operating instructions
|-- CLUSTER_README.md                      Princeton Adroit setup guide
|-- report_draft.md                        Academic paper draft (596 lines)
|-- INDEX.md                               This file
|
|-- Realist/                               === ACTIVE PROJECT ===
|   |
|   |-- ERCOT/                             Pipeline scripts (build, run, match, visualize)
|   |   |-- build_osm_bus_table.py           Step 1: OSM nodes -> bus.csv
|   |   |-- build_osm_branch_table.py        Step 2: OSM edges -> branch.csv (v1)
|   |   |-- build_osm_branch_table_v2.py     Step 2: v2 with bridge compensation
|   |   |-- build_osm_branch_table_v3.py     Step 2: v3 baseline (no compensating errors)
|   |   |-- build_gen_table.py               Step 3: MORA + EIA -> gen.csv
|   |   |-- build_storage_table.py           Step 4: MORA + EIA -> storage.csv
|   |   |-- run_sced.py                      Step 5: Vatic DC-SCED runner
|   |   |-- run_sced_array.slurm             SLURM array job for Adroit
|   |   |-- prepare_calibration_day.py       Build hourly load/CF from ERCOT data
|   |   |-- generate_visualizer.py           OSM -> grid_visualizer.html (v1)
|   |   |-- generate_visualizer_v2.py        v2: node merging, LMP overlay
|   |   |-- generate_visualizer_v3.py        v3: geometry-based line splitting
|   |   |-- pull_lmp_ercot.py                Fetch real-time LMPs from ERCOT API
|   |   |-- extract_mora.py                  Parse MORA PDF -> unit capacities CSV
|   |   |-- plot_network.py                  Static matplotlib network map
|   |   |-- test_storage_minimal.py          Unit test for Egret storage
|   |   |-- run_realist_sced.ipynb           Interactive SCED notebook
|   |   |-- (matching pipeline)
|   |   |   |-- gnis_matching.py               Pass 8: USGS place-name matching
|   |   |   |-- hv_matching.py                 Pass 9A/9B: 345 kV substation matching
|   |   |   |-- cp_matching.py                 Pass 10: CenterPoint Houston matching
|   |   |   |-- mora_matching.py               Pass 7: MORA unit -> location
|   |   |   |-- v6_crosswalk_and_snap.py       Final: V6 crosswalk + strict snap
|   |   |-- (legacy PSSE pipeline)
|   |       |-- build_bus_table.py             PSSE-based bus builder (superseded)
|   |       |-- build_branch_table.py          PSSE-based branch builder (superseded)
|   |
|   |-- grid_data/                          All input datasets
|   |   |-- texas_hv_lines.geojson            22,913 HV transmission lines (OSM)
|   |   |-- texas_substations.geojson         5,786 substations (OSM)
|   |   |-- ercot_zones.geojson               4 load zone boundaries
|   |   |-- MORA_April2026_unit_capacities.csv  1,778 gen + 418 storage units
|   |   |-- sced_disclosure_*.csv             ERCOT SCED offer curves (109 MB)
|   |   |-- lmp_snapshot.json                 Real-time LMP snapshot
|   |   |-- lmp_test.csv                      LMP validation series (21 MB)
|   |   |-- 3_4_Energy_Storage_Y2024.xlsx     EIA battery storage data
|   |   |-- SP_List_EB_Mapping/               Settlement point -> electrical bus
|   |   |-- Electrical_Bus_to_Hub_Lists/      Bus -> hub/zone mapping
|   |   |-- matching_results/                 Substation matching v2-v6 + reports
|   |   |-- sced_inputs/                      Built model (bus/branch/gen/storage CSVs)
|   |   |   |-- SourceData/                     Vatic input directory
|   |   |-- sced_inputs_v2/                   V2 topology variant
|   |   |-- sced_inputs_v3/                   V3 topology variant
|   |
|   |-- ERCOT_Calibration_Experiments/      Experiment logs & results
|   |   |-- experiments.md                    Master experiment table (80+ rows)
|   |   |-- session_2026-03-*.md              Daily session logs
|   |   |-- diagnostic_analysis.md            Cross-experiment root-cause analysis
|   |   |-- audit3_24_26.md                   Network construction audit
|   |   |-- calibrationViaVatic.md            High-level Vatic modeling overview
|   |   |-- branch_rating_research.md         IEEE rating standards research
|   |   |-- v2_grid_summary.md                V2 topology statistics
|   |   |-- build_diagnostics.py              Diagnostic engine: list/compare/build (see README)
|   |   |-- compare.py                        Legacy terminal comparison (superseded by engine)
|   |   |-- results/<tag>/                    Per-experiment output CSVs (80+ folders)
|   |   |-- june17_2024/                      Calibration day data (summer peak)
|   |   |-- jan08_2024/                       Calibration day data (extreme wind)
|   |   |-- validation_days/                  6 out-of-sample validation day CSVs
|   |
|   |-- OIM/                                OSM fetch + matching utilities
|   |   |-- fetch_hv_lines.py                 OSM Overpass -> texas_hv_lines.geojson
|   |   |-- fetch_substations.py              OSM Overpass -> texas_substations.geojson
|   |   |-- fetch_plants.py                   OSM Overpass -> texas_plants.geojson
|   |   |-- match_nodes.py                    Core fuzzy matching engine
|   |   |-- plot_hv_lines.py                  Line visualization
|   |   |-- plot_matched_nodes.py             Match quality visualization
|   |   |-- WhyThisIsntCEII.md                Legal: not Critical Energy Infrastructure
|   |   |-- GridStatus/                       Live LMP map tools
|   |
|   |-- vatic/                              DC-SCED solver library (Texas A&M fork)
|   |   |-- engines.py                        Core: Simulator (RUC + SCED)
|   |   |-- model_data.py                     VaticModelData (hierarchical dict)
|   |   |-- simulation_state.py               Hourly state tracking
|   |   |-- ptdf_manager.py                   Power Transfer Distribution Factors
|   |   |-- data/loaders.py                   CSV -> model data
|   |   |-- data/grids/Texas-7k/              Reference synthetic grid
|   |
|   |-- plans/                              Design documents (13 files)
|   |-- correspondence/                     Literature review, outreach drafts
|   |-- NYISO/                              Parallel NY grid build (lower priority)
|   |-- grid_visualizer.html                V1 interactive map
|   |-- grid_visualizer_v2.html             V2 interactive map
|   |-- grid_visualizer_v3.html             V3 interactive map (current)
|   |-- sced_diagnostic.html                Shedding/LMP diagnostic map
|   |-- index.html                          Redirect to grid_visualizer.html
|
|-- Birchfield/                            === ARCHIVAL (Phase 1) ===
    |-- core/                               Birchfield methodology modules
    |   |-- graph_types.py                    Bus/Branch/Generator data structures
    |   |-- load_nodes_clustering.py          Stage 1a: Census -> substations
    |   |-- generator_assignment.py           Stage 1b: EIA -> Type B substations
    |   |-- remaining_generator_clustering.py Stage 1c: Unassigned gen clustering
    |   |-- voltage_partition.py              Stage 2: 345/115 kV bus creation
    |   |-- topology_generation.py            Stage 3: Iterative line placement
    |-- pipelines/                          8 numbered execution scripts
    |-- config/                             YAML: global.yaml, texas.yaml, new_york.yaml
    |-- ingest/                             Census + EIA-860 data loaders
    |-- viz/                                Visualization modules
    |-- Calibration/                        Texas-7k and Texas-2k validation
    |-- data/                               Raw/processed/synthetic (mostly gitignored)
    |   |-- processed/eia860_generators.csv   Still used by Realist pipeline
    |-- plans/                              8 algorithm specification documents
    |-- 2k/                                 Texas-2k reference case
    |-- version1/                           Earlier prototype (archived)
```

---

## 3. Pipeline Scripts

### Build Pipeline (Execution Order)

| Step | Script | Input | Output | Purpose |
|------|--------|-------|--------|---------|
| 0 | `generate_visualizer_v3.py` | texas_hv_lines.geojson, texas_substations.geojson | grid_visualizer_v3.html | Extract OSM topology into renderable graph with NODES and EDGES arrays |
| 1 | `build_osm_bus_table.py` | grid_visualizer.html (NODES array), ercot_zones.geojson | osm_bus.csv, SourceData/bus.csv | Assign bus IDs, zones (PIP), names; select reference bus |
| 2 | `build_osm_branch_table.py` | grid_visualizer.html (EDGES), osm_bus.csv, texas_hv_lines.geojson | SourceData/branch.csv | Build branches with voltage-tier ratings, cables lookup, transformer proxies, 345 kV policy |
| 3 | `build_gen_table.py` | MORA CSV, EIA-860, v6 matching, bus.csv | SourceData/gen.csv, init_state.csv | 4-stage generator assignment (V6 osm_id -> EIA plant code -> county snap -> centroid) |
| 4 | `build_storage_table.py` | MORA CSV, EIA-860 Form 3.4, bus.csv | SourceData/storage.csv | BESS assignment to nearest OSM bus |
| 5 | `prepare_calibration_day.py` | ERCOT Native Load, wind/solar actuals, gen.csv | hourly_load_YYYYMMDD.csv, hourly_cf_YYYYMMDD.csv | Extract real ERCOT hourly profiles for simulation |
| 6 | `run_sced.py` | All SourceData CSVs, hourly load/CF | results_TAG/ (10 CSVs) | Run Vatic DC-SCED optimization |

### Branch Table Versions

| Version | File | 138 kV base | SPL treatment | Bridge compensation | Key feature |
|---------|------|-------------|---------------|--------------------|----|
| v1 | `build_osm_branch_table.py` | 250 MVA | 999k (unconstrained) | None | Cables lookup, transformer proxies, plant outlets |
| v2 | `build_osm_branch_table_v2.py` | 600 MVA | SPL_MULT env var (default 4x) | Yes (load-proportional) | Duplicate edge handling, explicit 345/138 transformers, bridge detection |
| v3 | `build_osm_branch_table_v3.py` | 250 MVA | 1x (constrained) | None | Baseline "no compensating errors"; clean physics |

### Substation Matching Pipeline (Cascading Passes)

| Pass | Script | Method | Input version | Output version |
|------|--------|--------|---------------|----------------|
| 1-6 | `match_nodes.py` (OIM/) | EIA-860 + OSM fuzzy name matching | Raw ERCOT SP list | v2 |
| 7 | `mora_matching.py` | MORA unit name -> county location | v2 | v3 |
| 8 | `gnis_matching.py` | USGS place-name database | v2 | v3 |
| 9A | `hv_matching.py` | PSSE name -> 345 kV OSM substations | v3 | v4 |
| 9B | `hv_matching.py` | 345 kV line endpoint clustering | v3 | v4 |
| 10 | `cp_matching.py` | CenterPoint Houston PSSE decode | v4 | v5 |
| V6 | `v6_crosswalk_and_snap.py` | Strict proximity snap + crosswalk | v5 | v6 (final) |

**Result:** 1,280 high/medium confidence matches out of 4,954 ERCOT substations (26%).

### Environment Variables (run_sced.py)

| Variable | Default | Purpose |
|----------|---------|---------|
| `SCED_DATE` | 2025-11-05 | Simulation date |
| `HOURLY_LOAD_CSV` | (none) | Hourly zone load profile path |
| `HOURLY_CF_CSV` | (none) | Hourly wind/solar capacity factor path |
| `DARTBOARD_SCRATCH` | (none) | Adroit scratch path (overrides all local paths) |
| `EXPERIMENT_TAG` | (none) | Results subdirectory tag |
| `BRANCH_SCALE` | 1 | Multiply all branch ratings |
| `SCALE_345KV` | (none) | Multiply 345 kV ratings only |
| `SCALE_138KV` | (none) | Multiply 138 kV ratings only |
| `LOAD_ALLOC` | pop | Load allocation: pop, uniform, sqrt, cap75 |
| `UPGRADE_LINES` | (none) | Comma-separated branch UIDs to double (250→500 MVA) |
| `FLOOR_RATINGS_CSV` | (none) | Per-branch floor ratings from unconstrained flows |
| `RESERVE_FACTOR` | 0.05 | Spinning reserve requirement as fraction of demand |
| `RESERVE_PENALTY` | 1e3 | Reserve shortfall penalty ($/MWh) |
| `FEEDBACK_COMMIT` | (none) | Enable feedback-based commitment (force thermal near shedding) |
| `SCED_DIR_OVERRIDE` | (none) | Custom SCED input directory |
| `VIZ_HTML` | (none) | Custom visualizer HTML path (for bus/branch build) |

---

## 4. Data Files

### Primary Geospatial Data (grid_data/)

| File | Source | Size | Contents |
|------|--------|------|----------|
| texas_hv_lines.geojson | OSM Overpass | 36 MB | 22,913 HV transmission line segments with voltage, geometry |
| texas_substations.geojson | OSM Overpass | 2.0 MB | 5,786 Texas substations with voltage tags |
| texas_plants.geojson | OSM Overpass | 260 KB | Power plants with generator attributes |
| ercot_zones.geojson | ERCOT public | 112 KB | 4 load zone boundary polygons |

### ERCOT Operational Data

| File | Source | Size | Contents |
|------|--------|------|----------|
| MORA_April2026_unit_capacities.csv | ERCOT MORA | 214 KB | 1,778 generators + 418 storage: name, fuel, capacity, zone |
| sced_disclosure_20251105_gen_resource.csv | ERCOT MIS | 109 MB | Nov 5 2025 SCED offers (HSL, segments, ancillary) |
| lmp_snapshot.json | ERCOT API | 35 KB | Real-time LMP at settlement points |
| lmp_test.csv | ERCOT API | 21 MB | ~1,070 settlement point LMP time series |
| 3_4_Energy_Storage_Y2024.xlsx | EIA-860 | 364 KB | Battery installations (279 operational) |
| ERCOT_SCED_Shadowprices.csv | ERCOT | 13 KB | Constraint shadow prices sample |
| IX_queue.xlsx | ERCOT | 670 KB | Interconnection queue (proposed projects) |

### ERCOT Mapping Files

| Directory/File | Contents |
|----------------|----------|
| SP_List_EB_Mapping/Settlement_Points_*.csv | ~1,070 settlement points: resource nodes, load zones, hubs with PSSE bus ID |
| SP_List_EB_Mapping/Resource_Node_to_Unit_*.csv | Resource node -> generator unit name crosswalk |
| Electrical_Bus_to_Hub_Lists/Full_Electrical_Bus_*.csv | ~5,000 ERCOT electrical buses |
| Electrical_Bus_to_Hub_Lists/Electrical_BusMap_To_HUB_*.csv | Bus -> hub, zone, voltage mapping |

### Matching Results (grid_data/matching_results/)

| File | Description |
|------|-------------|
| texas_matched_substations_v6.csv | Final matching output (4,955 rows, 9-pass algorithm) |
| texas_matched_substations_v{2-5}.csv | Intermediate matching versions |
| *_matching_report.md (4 files) | Per-pass match quality reports |
| *.png (4 files) | Match coverage visualizations by source, zone, quality |

### Built Model Inputs (grid_data/sced_inputs_v3/SourceData/)

| File | Rows | Key columns |
|------|------|-------------|
| bus.csv | ~3,786 | Bus ID, name, zone, baseKV, load MW, lat, lon |
| branch.csv | ~4,817 | From/to bus, reactance pu, continuous rating MVA |
| gen.csv | ~1,185 | Bus, fuel, pmin/pmax, ramp rate, heat rates, startup cost |
| init_state.csv | ~1,185 | Generator initial on/off state (thermal: 24h warm start) |
| storage.csv | ~289 | Bus, charge/discharge MW, MWh capacity, efficiency |

---

## 5. Calibration Experiments

### Experiment Registry (80+ runs)

All experiments documented in `Realist/ERCOT_Calibration_Experiments/experiments.md`.

#### Milestone Experiments

| Tag | Date | SS shed (MW) | Significance |
|-----|------|-------------|--------------|
| **v1** | Nov 5 | 8,622 | Baseline: PSSE buses, cold start |
| **clean-build** | Nov 5 | **81.7** | Canonical v1 baseline (600 MVA, SPL at 999k) |
| **spl-fix** | Nov 5 | 6,117 | 250 MVA + constrained SPL -> proves compensating error |
| **v3-j17-t135f-r15** | Jun 17 | **0** | **Winning config.** 135 upgrades + f1200 floor + r=0.15. 24/24 W<N. |
| val-mar29 | Mar 29 | **0** | Validation pass — high wind, 21k curtailment |
| val-aug20 | Aug 20 | 6,282 | Validation fail — record peak, Houston corridor saturation |
| upgr-aug20-t175 | Aug 20 | **26** | T175 config (90% shed reduction at 77 GW) |

#### Simulation Days (3 tuning + 6 validation)

| Day | Date | Condition | Purpose |
|-----|------|-----------|---------|
| Nov 5 | 2025-11-05 | Constant 50.9 GW, moderate wind | Primary baseline (simplest) |
| Jun 17 | 2024-06-17 | Hourly 52–76 GW, peak solar, high wind | Summer peak stress test |
| Jan 8 | 2024-01-08 | Hourly 41–51 GW, extreme wind 25+ GW | Winter wind extreme |
| Aug 20 | 2024-08-20 | Hourly 51–79 GW, low wind | 2024 record peak (validation) |
| Sep 29 | 2024-09-29 | Hourly 37–62 GW, CF 0.004–0.11 | Lowest wind day (validation) |
| Mar 29 | 2024-03-29 | Hourly 34–43 GW, CF 0.59–0.65 | Highest wind day (validation) |
| Oct 29 | 2024-10-29 | Hourly 43–60 GW, high wind | Fall high wind (validation) |
| Apr 13 | 2024-04-13 | Hourly 33–47 GW, balanced renewables | Spring balanced (validation) |
| Jul 23 | 2024-07-23 | Hourly 42–59 GW, CF 0.02–0.17 | Summer low wind (validation) |

#### Key Findings

1. **138 kV rating is the dominant control variable.** 250 -> 600 MVA = 50x shed reduction.
2. **SPL unconstrain is a compensating error** for the missing 138 kV mesh in OSM. Constraining SPL at realistic ratings without fixing mesh = catastrophic shedding.
3. **Targeted upgrades + floor ratings** solve congestion while preserving zone LMP ordering. 135 iteratively-identified upgrades + f1200 floor = 0 shed on all 3 tuning days.
4. **Model generalizes to unseen days.** 4/6 validation days pass clean (0 shed, correct zone ordering). Low-wind days correctly show flat LMPs.
5. **Above 74 GW, Houston corridor saturation is the binding limit.** 345 kV corridors at 2,400 MVA can't be doubled without losing congestion realism. Storage dispatch (17.5 GW) is the likely fix.
6. **Shedding is 100% congestion, not capacity.** Feedback commitment and must-run experiments confirm the RUC commits the right generators.

### Results Directory Inventory

80+ experiment folders in `ERCOT_Calibration_Experiments/results/`. Each may contain:

| File | Contents |
|------|----------|
| hourly_summary.csv | Per-hour: demand, shed, curtail, price, renewable output |
| bus_detail.csv | Per-bus per-hour: load, shed, LMP |
| line_detail.csv | Per-branch per-hour: flow MW, rating, utilization |
| thermal_detail.csv | Per-generator per-hour: dispatch, commitment status |
| renew_detail.csv | Per-renewable per-hour: available, dispatched, curtailed |
| branch.csv, bus.csv | Input copies (for self-contained reproducibility) |
| ruc_summary.csv | Unit commitment solution summary |
| daily_commits.csv | Generator commitment schedule |
| runtimes.csv | Solver timing |

### Session Logs

| File | Date | Key content |
|------|------|-------------|
| session_2026-03-20.md | Mar 20 | clean-build, jun17-hourly, hv2400 experiments |
| session_2026-03-24.md | Mar 24 | SPL-fix catastrophe, compensating error discovery |
| session_2026-03-24b.md | Mar 24 | V2 topology, edge-splice, bridge ratio reduction |
| session_2026-03-26.md | Mar 26 | V3 visualizer, OSM validation, topology benchmarking |
| session_2026-03-27.md | Mar 27 | V3 SCED calibration, targeted upgrades, floor ratings |
| session_2026-03-28.md | Mar 28 | 6-day validation, stress test, tract allocation regression, T175 upgrades |
| diagnostic_analysis.md | Mar 25 | Cross-experiment root-cause ranking |
| audit3_24_26.md | Mar 24 | 7-problem network construction audit |

---

## 6. Visualizers & HTML Outputs

| File | Location | Size | Description |
|------|----------|------|-------------|
| grid_visualizer.html | Realist/ | 2.3 MB | V1: Leaflet map of 4,303 nodes + 4,501 edges. Zoom, node popups, edge tooltips. |
| grid_visualizer_v2.html | Realist/ | 2.3 MB | V2: Adds LMP coloring, congestion heatmap, node merging. |
| grid_visualizer_v3.html | Realist/ | 3.4 MB | V3: Geometry-based line splitting, all-voltage substations (5,009). Current. |
| sced_diagnostic.html | Realist/ | 1.3 MB | Single-experiment SCED overlay + V3 topology source (bus coords, line geometry). |
| diagnostics.html | ERCOT_Calibration_Experiments/ | ~6.5 MB | Multi-experiment diagnostic: Map tab (Leaflet with experiment dropdown) + Scorecard tab (comparison table, zone LMPs, hourly sparklines). Generated by `build_diagnostics.py build`. |
| binding_branches_138kv2x.html | ERCOT_Calibration_Experiments/ | -- | Standalone map of 138 kV binding constraints. |
| ny_grid_visualizer.html | NYISO/ | 4.9 MB | NYISO parallel: NY transmission grid map. |
| index.html | Realist/ | 82 B | Meta-refresh redirect to grid_visualizer.html. |

---

## 7. Supporting Modules

### Vatic (Realist/vatic/) -- DC-SCED Solver

| Module | Purpose |
|--------|---------|
| engines.py | Core Simulator: orchestrates RUC (unit commitment) and SCED (dispatch) in rolling horizon |
| model_data.py | VaticModelData: hierarchical dict of buses, generators, branches, storage |
| simulation_state.py | Tracks hourly commitment, dispatch, SOC, shedding, LMP |
| ptdf_manager.py | Power Transfer Distribution Factor computation for DC flow constraints |
| data_providers.py | I/O abstraction (CSV, pickle backends) |
| stats_manager.py | Shedding, LMP, congestion statistics collection |
| time_manager.py | Time index and rolling UC window management |
| data/loaders.py | CSV -> VaticModelData construction |
| data/grids/Texas-7k/ | Reference 7,000-bus synthetic grid (TAMU) |

### OIM (Realist/OIM/) -- OpenStreetMap Utilities

| Module | Purpose |
|--------|---------|
| fetch_hv_lines.py | OSM Overpass API -> texas_hv_lines.geojson (36 MB) |
| fetch_substations.py | OSM Overpass API -> texas_substations.geojson (2.0 MB) |
| fetch_plants.py | OSM Overpass API -> texas_plants.geojson (260 KB) |
| match_nodes.py | Core fuzzy matching: ERCOT settlement points -> EIA-860 + OSM |
| WhyThisIsntCEII.md | Legal analysis: project does not constitute CEII |
| GridStatus/ | Live LMP map tools (plot_lmp_map.py) |

### Plans (Realist/plans/) -- 13 Design Documents

| Document | Scope |
|----------|-------|
| presentation_plan.md | Apr 3 professor presentation roadmap |
| buildToSCEDPlan.md | Bus/branch/gen CSV assembly guide |
| FirstAttemptToVaticPlan.md | Historical: why PSSE-bus approach failed |
| ERCOT_API_LMP_Integration.md | Real-time LMP ingestion proposal |
| TransformerBranchPlan.md | 345->138 kV explicit transformer design |
| visualizer_graph_topology.md | Interactive visualizer architecture |
| (+ 7 more) | Matching, snapping, OpenInfraMap, clustering |

### NYISO (Realist/NYISO/) -- Parallel NY Build

Functional proof-of-concept replicating the Realist pipeline for NYISO (New York). Lower priority than ERCOT. Includes fetch scripts, build scripts, run_sced.py, generate_visualizer.py, and ny_grid_visualizer.html.

### Correspondence (Realist/correspondence/)

| File | Contents |
|------|----------|
| ClaudeLitReview.md | Literature review: agentic AI for power systems, synthetic grid models, OSM-based extraction. Key gap: no prior work combines LLM agents with OSM for SCED-realistic grids. |
| emailswithERCOT.md | ERCOT data access communications |
| birchfield_email_draft.md | Outreach to TAMU synthetic grid creator |
| strategy.md | Market opportunity, stakeholders, publication roadmap |

---

## 8. Birchfield (Archival)

Phase 1 of the project: implementing the Birchfield et al. synthetic transmission grid methodology. **Archived** -- the Realist pipeline replaced this approach.

### Methodology (3 Stages)

| Stage | Module | Output |
|-------|--------|--------|
| 1a | load_nodes_clustering.py | Census ZCTAs -> 1,250 TX substations (Type A) |
| 1b | generator_assignment.py | 5.5% substations get generation (Type B) |
| 1c | remaining_generator_clustering.py | Unassigned generators -> Type-g substations |
| 2 | voltage_partition.py | 345/115 kV buses, internal transformers |
| 3 | topology_generation.py | Iterative Delaunay/MST/k-neighbor line placement, m/n target 1.22 |

### Key Finding
The Birchfield algorithm's density target (m/n = 1.22) was wrong -- parameter sweep showed real ERCOT requires m/n = 1.55. This revealed a circular calibration problem and motivated the switch to OSM-based topology.

### Still-Used File
`Birchfield/data/processed/eia860_generators.csv` -- EIA-860 generator coordinates, used as geo-snap fallback in the Realist pipeline.

---

## 9. Root-Level Files

| File | Purpose |
|------|---------|
| README.md | **Canonical current-state anchor.** Model state, pipeline, known issues, next steps. Trust over session logs. |
| CLAUDE.md | Agent operating instructions: read context first, key constraints, conventions |
| CLUSTER_README.md | Princeton Adroit setup: SSH, conda, Gurobi, SLURM submission |
| report_draft.md | Academic paper: "Towards an AI-Driven Methodology for Building More Realistic Synthetic Electric Grid Models" (596 lines) |
| README_BIRCHFIELD.md | Archival Phase 1 documentation |
| GithubPages.md | GitHub Pages deployment instructions |
| Dartboard.code-workspace | VS Code workspace config |
| .gitignore | Excludes: data dirs, venvs, .pyc, .pdf, .DS_Store |

### GitHub Actions

`.github/workflows/refresh_lmp.yml` -- Manual-trigger workflow: fetch ERCOT LMPs via API -> deploy to GitHub Pages. Requires ERCOT_USERNAME, ERCOT_PASSWORD, ERCOT_CLIENT_ID, ERCOT_API_KEY secrets.

---

## 10. Infrastructure & Cluster

### Princeton Adroit

| Setting | Value |
|---------|-------|
| SSH alias | `adroit` (adroit.princeton.edu) |
| Scratch | `/scratch/network/js0735/dartboard/` |
| Conda env | `/home/js0735/.conda/envs/vatic-test` |
| Gurobi license | `/usr/licensed/gurobi/license/gurobi.lic` |
| SLURM script | `run_sced_array.slurm` (in scratch dir) |
| Job email | js0735@princeton.edu |
| Resources per task | 1 node, 1 task, 8 CPUs, 32 GB memory, 4 hr walltime |

### Deploy Commands

```bash
# Push scripts to cluster
scp Realist/ERCOT/run_sced.py adroit:/scratch/network/js0735/dartboard/
scp Realist/ERCOT/run_sced_array.slurm adroit:/scratch/network/js0735/dartboard/
scp Realist/ERCOT/build_*.py adroit:/scratch/network/js0735/dartboard/

# Submit array job
ssh adroit "sbatch --array=N-M /scratch/network/js0735/dartboard/run_sced_array.slurm"

# Check status
ssh adroit "squeue -u js0735"

# Pull results
scp -r adroit:/scratch/network/js0735/dartboard/sced_inputs_<TAG>/results_<TAG>/ \
    Realist/ERCOT_Calibration_Experiments/results/<TAG>/
```

### Technology Stack

| Layer | Tools |
|-------|-------|
| Language | Python 3.10-3.12, HTML/JS |
| Geospatial | Shapely, OSM Overpass, Leaflet.js |
| Optimization | Pyomo, Gurobi (cluster), CBC (local), Egret (NREL) |
| Data | pandas, numpy |
| Matching | rapidfuzz (fuzzy string), pdfplumber |
| Visualization | Leaflet.js (web), matplotlib (static) |
| Infrastructure | SLURM, conda, GitHub Actions |

---

## 11. Glossary

### Power Systems Terms

| Term | Definition |
|------|-----------|
| **BESS** | Battery Energy Storage System. Modeled with charge/discharge MW limits, MWh capacity, round-trip efficiency. |
| **Branch** | Transmission line or transformer connecting two buses. Characterized by reactance (X pu) and continuous rating (MVA). |
| **Binding constraint** | A branch whose power flow equals its thermal rating limit. The binding set determines congestion patterns and LMP separation. |
| **Bus** | A node in the electrical network representing a substation or junction point. Has voltage level, zone, and load. |
| **Capacity Factor (CF)** | Ratio of actual output to nameplate capacity. Wind CF varies 0.45-0.79 seasonally; solar 0.05-0.25. Applied at dispatch time, not baked into PMax. |
| **Congestion** | When power flow is limited by branch ratings, causing price separation between zones. |
| **Curtailment** | Reduction of renewable generation below available capacity due to network constraints or oversupply. |
| **DC-SCED** | DC Security-Constrained Economic Dispatch. Linearized optimal power flow that dispatches generators to minimize cost subject to branch flow limits. |
| **LMP** | Locational Marginal Price. The cost of serving one additional MW of load at a specific bus. Equals energy + congestion + losses (losses = 0 in DC model). |
| **Load shedding** | Involuntary demand curtailment when supply + network capacity cannot serve all load. In the model, appears as a very expensive ($10k/MWh) virtual generator. |
| **MVA** | Mega Volt-Ampere. Branch thermal rating unit. |
| **PMax** | Maximum power output of a generator (nameplate MW). |
| **PTDF** | Power Transfer Distribution Factor. Matrix mapping generator injections to branch flows in a DC power flow. |
| **RUC** | Reliability Unit Commitment. Day-ahead optimization determining which generators to turn on/off. |
| **SCED** | Security-Constrained Economic Dispatch. Real-time optimization determining generator output levels. |
| **SPL** | Split-Point Line. Synthetic branch connecting a T-junction node in the OSM topology. Not a real transmission line. |
| **Steady-state shed** | Load shedding average over hours 9-23 (after thermal ramp-up transient). Primary calibration metric. |
| **UC** | Unit Commitment. Binary decision problem for generator on/off scheduling. |
| **WESTEX** | West Texas Export corridor. The real ERCOT congestion pattern where wind power in WEST zone is constrained by transmission capacity to eastern load centers. Morgan Creek-Tonkawa (L1605_1612) is the binding line. |
| **X pu** | Per-unit reactance. Transmission line impedance parameter used in DC power flow. |

### ERCOT-Specific Terms

| Term | Definition |
|------|-----------|
| **ERCOT** | Electric Reliability Council of Texas. Independent system operator managing the Texas grid. |
| **Load zones** | ERCOT's 4 settlement zones: **NORTH** (DFW), **HOUSTON**, **SOUTH** (San Antonio/Austin), **WEST** (West Texas wind corridor). |
| **MORA** | Modeling, Outages, and Reserves Analysis. ERCOT's public generator registry report published quarterly. |
| **PSSE bus** | Bus identifier from ERCOT's internal PSS/E power flow model. Not public; approximated via settlement point mapping. |
| **Resource Node (RN)** | ERCOT's pricing point for a generator or load serving entity. Maps to settlement points. |
| **RTM SPP** | Real-Time Market Settlement Point Price. ERCOT's published 15-minute LMP data. Ground truth for model validation. |
| **Settlement Point** | ERCOT's market node (~1,070 total). Includes resource nodes, load zones, and hubs. |

### Project-Specific Terms

| Term | Definition |
|------|-----------|
| **Bridge** (graph theory) | An edge whose removal disconnects the graph. High bridge ratio indicates a tree-like (radial) network with congestion vulnerability. |
| **Bridge-load compensation** | V2 branch table technique: inflate rating of bridge edges proportionally to downstream load they serve, compensating for missing parallel paths. |
| **Clean-build** | Canonical v1 experiment configuration: 600 MVA 138 kV, SPL/plant at 999k MVA, no runtime env vars. 81.7 MW steady-state shed on Nov 5. |
| **Compensating error** | When two modeling approximations (high 138 kV ratings + unconstrained SPL) cancel each other out to produce realistic results despite neither being physically correct individually. |
| **Edge-splice** (Fix 8) | V2 topology technique: convert bridge edges into meshed subgraphs by splicing new connections at junction points. Reduced bridge ratio from 66% to 18%. |
| **Mesh ratio** | E/N (edges per node). Values near 1.0 = tree (radial); values > 1.3 = well-meshed. Real ERCOT is ~1.31. |
| **T-junction** | Point where a transmission line branches or intersects. In OSM, these create synthetic nodes not present in ERCOT's model. |
| **V2 topology** | Second-generation OSM network extraction with 7 fixes from audit3_24_26.md (wider snap, nearest-match, dedup, cleanup, cross-voltage merge, edge-splice). |
| **V3 topology** | Third-generation using PyPSA-style geometry-based line splitting. Lines are split where they pass near substations rather than using BFS contraction. |
| **Voltage tier** | Standard transmission voltages: 138 kV (sub-transmission), 230 kV (intermediate), 345 kV (bulk), 500 kV (extra-high). Each tier has default impedance and rating. |

### Data & Matching Terms

| Term | Definition |
|------|-----------|
| **CEII** | Critical Energy Infrastructure Information. FERC-protected data that could be used to attack grid infrastructure. This project explicitly does not use or produce CEII. |
| **EIA-860** | Annual Electric Generator Report filed with the Energy Information Administration. Public source for plant locations, capacities, fuel types. |
| **GNIS** | Geographic Names Information System. USGS database of US place names used as fuzzy-match source for substation identification. |
| **Matching pass** | One stage of the cascading substation identification pipeline. Each pass uses a different data source or matching strategy to resolve previously unmatched ERCOT settlement points. |
| **OSM** | OpenStreetMap. Crowdsourced geographic database providing transmission line routes and substation positions. |
| **Point-in-polygon (PIP)** | Geometric test determining which ERCOT zone contains a given lat/lon coordinate. Used for bus zone assignment. |
| **Snap** | Assign an ERCOT node to the nearest OSM substation within a distance threshold. |
| **V6 matching** | Final matching version after all 10 passes. Contains 4,955 ERCOT substations with lat/lon, match source, and confidence level. |

### Infrastructure Terms

| Term | Definition |
|------|-----------|
| **Adroit** | Princeton Research Computing HPC cluster used for SCED optimization runs. |
| **CBC** | COIN-OR Branch and Cut. Open-source MIP solver used for local testing. Produces identical results to Gurobi for this model. |
| **Gurobi** | Commercial optimization solver used on the Adroit cluster. Required for production SCED runs. |
| **SLURM** | Simple Linux Utility for Resource Management. Job scheduler on Adroit. `run_sced_array.slurm` defines experiment configurations. |
| **Vatic** | Texas A&M DC-SCED engine (Pyomo wrapper). Implements rolling RUC + SCED with PTDF-based flow constraints. |

---

## 12. Data Lineage Diagram

```
PUBLIC DATA SOURCES
===================
OpenStreetMap ---------> fetch_hv_lines.py ----> texas_hv_lines.geojson (36 MB, 22,913 lines)
(Overpass API)           fetch_substations.py --> texas_substations.geojson (2 MB, 5,786 subs)
                         fetch_plants.py -------> texas_plants.geojson (260 KB)

ERCOT Public ----------> Settlement_Points.csv, Resource_Node_to_Unit.csv
(Data Portal)            Full_Electrical_Bus.csv, Electrical_BusMap_To_HUB.csv
                         MORA_April2026.pdf ---> extract_mora.py ---> MORA_unit_capacities.csv
                         Native_Load, wind/solar actuals
                         SCED disclosure (offer curves)
                         RTM SPP (validation LMPs)

EIA-860 Annual --------> eia860_generators.csv (Birchfield/data/processed/)
                         3_4_Energy_Storage_Y2024.xlsx

USGS GNIS -------------> DomesticNames_TX.txt (place-name database)


MATCHING PIPELINE (9 passes)
=============================
match_nodes.py --> mora_matching.py --> gnis_matching.py --> hv_matching.py --> cp_matching.py
     v2                v3                   v3                  v4                v5
                                                                                  |
                                                                    v6_crosswalk_and_snap.py
                                                                          |
                                                                          v
                                                        texas_matched_substations_v6.csv
                                                           (4,955 rows, 26% high/medium)


TOPOLOGY EXTRACTION
====================
texas_hv_lines.geojson + texas_substations.geojson
          |
          v
generate_visualizer_v3.py -----> grid_visualizer_v3.html
          |                       (3,368 subs + 4,927 edges embedded as JSON)
          v
build_osm_bus_table.py ---------> osm_bus.csv --> SourceData/bus.csv
build_osm_branch_table.py ------> SourceData/branch.csv
          |
          | + MORA_unit_capacities.csv + eia860_generators.csv + v6 matching
          v
build_gen_table.py --------------> SourceData/gen.csv + init_state.csv
build_storage_table.py ----------> SourceData/storage.csv


SIMULATION
===========
prepare_calibration_day.py ------> hourly_load_YYYYMMDD.csv
(from ERCOT Native Load,           hourly_cf_YYYYMMDD.csv
 wind/solar actuals)

bus.csv + branch.csv + gen.csv + storage.csv + hourly_load + hourly_cf
          |
          v  (Princeton Adroit, Gurobi solver)
     run_sced.py (via run_sced_array.slurm)
          |
          v
     results_<TAG>/
     |-- hourly_summary.csv    (demand, shed, curtail, price per hour)
     |-- bus_detail.csv        (per-bus LMP, load, shed)
     |-- line_detail.csv       (per-branch flow, rating, utilization)
     |-- thermal_detail.csv    (per-generator dispatch, commitment)
     |-- renew_detail.csv      (per-renewable available, dispatched, curtailed)
     |-- ruc_summary.csv       (unit commitment solution)
     |-- daily_commits.csv     (commitment schedule)
     |-- runtimes.csv          (solver timing)


ANALYSIS & VALIDATION
======================
build_diagnostics.py list ---------> terminal: all experiments with stats
build_diagnostics.py compare ------> terminal: comparison table (shed, price, W<N)
build_diagnostics.py build --------> diagnostics.html (Map + Scorecard tabs, up to 5 experiments)
sced_diagnostic.html <-------------- topology source (bus coords, line geometry for map)
compare.py -----------------------> comparison_summary.csv (legacy, superseded by engine)
RTM SPP data <-------------------> model LMPs (zone ordering validation)
```

---

*This index was auto-generated from a full read of the repository. For the authoritative current state, always consult `README.md` first.*
