# SCED Version Summary
**Date:** 2026-03-06
**Simulation date (all runs):** 2025-11-05, 24 hours
**Solver:** Gurobi (cluster), CBC (local)
**Demand (all runs):** ~50,894 MW constant (ZONE_LOAD_MW fallback, not hourly)

---

## Load Shedding by Version

| Version | Hr 0 Shed (MW) | Steady-state Shed (MW) | Curtailment (MW) | Price ($/MWh) | Key change |
|---|---|---|---|---|---|
| v.1 | 27,242 | 8,622 | 13,543 | $19.66 | Baseline: PSSE-bus network, cold start (UnitOnT0State = −1 all thermal) |
| cluster_v1 | 27,242 | 8,622 | 13,543 | $19.66 | Re-run of v.1 on Princeton Adroit; identical outputs |
| v2 | 2,976 | 2,976 | 11,117 | $21.56 | OSM-native network (build_osm_bus/branch_table.py); warm start thermal |
| v3 | 5,431 | 5,431 | 11,396 | $20.92 | OSM network rebuild (generation or topology change, details not logged) |
| v4 | 6,299 | 6,299 | 13,009 | $20.96 | OSM network rebuild |
| v5 | **6,298** | **6,298** | **13,009** | **$20.96** | **Latest run; near-identical to v4** |

"Steady-state" = hours 9–23 average. Shedding is flat in v2–v5 (no cold-start transient) because thermal warm start is applied in all OSM-native runs.

---

## Current Script Assumptions (as of 3/6/26)

| Parameter | Value | File |
|---|---|---|
| Nuclear UnitOnT0State | 1,000 (always on) | `build_gen_table.py:724` |
| Renewable UnitOnT0State | 1 (always on) | `build_gen_table.py:726` |
| Thermal UnitOnT0State | 24 (warm) | `build_gen_table.py:728` |
| 138 kV line rating | 300 MVA (flat) | `build_osm_branch_table.py:49` |
| 230 kV line rating | 600 MVA (flat) | `build_osm_branch_table.py:50` |
| 345 kV line rating | 1,200 MVA (flat) | `build_osm_branch_table.py:51` |
| Load profile | Constant 24h (ZONE_LOAD_MW) | `run_sced.py:62` |
| Renewable CF | Constant (pmax timeseries) | `run_sced.py` |
| Network basis | OSM nodes from grid_visualizer.html | `build_osm_bus_table.py` |

---

## What v5 Is Telling Us

With warm start applied, the cold-start spike (27,242 MW at hour 0 in v.1) is gone. What remains is **6,298 MW of persistent steady-state shedding** — 12.4% of the 50,894 MW constant demand.

The curtailment picture is unchanged: **13,009 MW of renewables are simultaneously curtailed** while load goes unserved. This is the same network delivery problem identified in the v.1 audit: 138 kV intra-zone lines at the 300 MVA flat default are creating bottlenecks that prevent West Texas wind from reaching East Texas load.

The regression from v2 (2,976 MW) to v3–v5 (5,431–6,299 MW) suggests that v2's lower shedding may reflect a different network topology (possibly fewer or shorter 138 kV branches, which would reduce congestion artificially rather than resolve it correctly). The exact change between versions is not logged.

---

## Highest-Value Open Experiments

| Experiment | Expected impact | Effort |
|---|---|---|
| Set 138 kV rating to 600 MVA (one-line change) | Primary sensitivity; may cut shedding by half | 5 min + cluster run |
| Run with no branch limits (floor case) | Reveals whether any shedding persists without congestion | 5 min + cluster run |
| Add hourly load profile (ERCOT public data) | Fixes constant-demand distortion; reduces overnight overload | ~2 hrs |
| Add hourly wind/solar CFs | Fixes solar-at-night; improves dispatch timing | ~2 hrs |
