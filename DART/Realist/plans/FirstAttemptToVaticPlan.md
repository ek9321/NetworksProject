# First Attempt to Vatic Plan

## Executive Summary

The goal is to assemble Vatic input tables (`bus.csv`, `branch.csv`, `gen.csv`) from public ERCOT sources and OSM line geometry and run a DC Security-Constrained Economic Dispatch using `Birchfield/vatic/`.

**Architecture (as of March 2026 — OSM-native):** Use the topology already built by `generate_visualizer.py` as the SCED network. OSM substations are the buses. The website's BFS-contracted edges are the branches. ERCOT PSSE bus numbers are **not** used as the primary node set — see the historical section at the bottom for why this approach was tried and abandoned.

**Current status:**
- Step 1 (bus table from OSM nodes): not yet done under new architecture
- Step 2 (branch table from website edges): not yet done under new architecture
- Step 3 (generator assignment to OSM nodes): not yet done under new architecture
- Step 4 (load distribution): framework done; needs port to OSM bus IDs
- Step 5 (run SCED): framework done; needs port to OSM bus IDs

The old PSSE-based scripts (`build_bus_table.py`, `build_branch_table.py`, `build_gen_table.py`) are present in `Realist/ERCOT/` but are **not the right starting point** for the new architecture. Do not attempt to fix them. See the historical section.

---

## Why OSM-Native

`generate_visualizer.py` already solves the hardest problem — building a topologically correct, BFS-contracted transmission graph from OSM HV line geometry. It produces:

| Component | Count |
|-----------|-------|
| OSM substations (138 kV+, inside ERCOT, within 500 m of a line) | 3,037 |
| T-junction split points (degree ≥ 3 junctions without a matching substation) | 1,266 |
| **Total nodes** | **4,303** |
| Edges ≥ 345 kV | 674 |
| Edges 200–344 kV | 58 |
| Edges 138–199 kV | 3,924 |
| **Total edges** | **4,656** |

4,303 nodes and 4,656 edges is a reasonable HV transmission model (~1.1 edges/node average — slightly sparse but real). The BFS in `_graph_pass()` walks full interior polyline coordinates and promotes T-junctions to stop nodes, which is the correct topology. This is already validated and rendered on the live website.

The PSSE bus approach required bridging from OSM geography to ERCOT's internal bus numbering via the V6 matching pipeline. That bridge covers only 763 of 3,037 OSM substations (25%). The other 75% of the transmission network — including most of the 138 kV backbone — has no PSSE mapping. Any SCED network built on PSSE buses is missing 75% of its nodes by construction. OSM substations are the right primary node set.

PSSE bus numbers are only needed to compare model LMPs to ERCOT's official bus-level LMP publications. That comparison is a future validation step, not a prerequisite for a feasibility run.

---

## Architecture

### Node set

All 4,303 nodes from `generate_visualizer.py`'s NODES array:
- Substations: OSM physical substations ≥ 138 kV, inside ERCOT, within 500 m of a line endpoint
- Split points: T-junction clusters (degree ≥ 3) that don't snap to any substation

Bus IDs: use a sequential integer index (0–4302). The OSM `osm_id` is stored as metadata but is too large and inconsistent for use as a Vatic bus integer.

Voltage (BaseKV): directly from OSM `kv` property. Split points inherit the max kV of their incident edges.

Zone: point-in-polygon against `Realist/grid_data/ercot_zones.geojson`. Every node gets the ERCOT load zone (NORTH, SOUTH, WEST, HOUSTON) containing its lat/lon. Nodes outside any zone polygon get the nearest zone by centroid distance.

### Branch set

All 4,656 edges from EDGES_HIGH + EDGES_MID_HI + EDGES_MID_LO. Each edge carries `a` (node index), `b` (node index), `kv`. Map to sequential bus IDs. Impedance (X_pu) computed from haversine distance between node coordinates using the same voltage-tier formula as the old `build_branch_table.py`.

Split-point nodes (the 1,266 T-junctions) participate in branches exactly like substation nodes. They are real physical branch points in the OSM topology and should be retained in the SCED model. They will carry zero generation and receive a small population-weighted load.

### Generator assignment

MORA generators do not have OSM node IDs. Assignment chain:

1. **V6 bridge (primary):** The 763 V6-matched OSM substations have an `ercot` field (ERCOT substation name). MORA generators have a `RESOURCE_NODE` that maps to a Settlement Point, which has a substation name. Fuzzy-match MORA substation names to the `ercot` field on V6-matched OSM nodes. This covers generators at the ~763 matched substations.

2. **Name-to-name fallback:** For unmatched generators, fuzzy-match the MORA substation name directly against OSM node `name` fields (not the ERCOT crosswalk, just raw OSM names). Catches generators at substations OSM named consistently with MORA but that V6 didn't match.

3. **Geographic snap (last resort):** For remaining unmatched generators, snap to the nearest OSM substation node within 5 km. Do not snap to split-point nodes (they have no substation name and their location is an OSM artifact, not a real facility).

Log counts at each stage. Generators with no assignment after all three stages are dropped; log them.

### Load distribution

Same population-weighted approach as the current `run_sced.py`: assign each of the 254 Texas counties a weight proportional to Census 2020 population, then distribute ERCOT total system load to buses by their county's weight. Bus-to-county assignment is nearest-county by haversine. This still works with OSM bus IDs — only the bus list changes.

DC tie injections (OKLAUNION, MONTICELLO, EAGLE, MCALLEN, LAREDO) remain as negative load offsets on the nearest OSM substation node to each tie point.

### Data lineage

| Component | Source |
|-----------|--------|
| Bus locations and topology | OSM substations + HV lines via `generate_visualizer.py` |
| Bus voltage levels | OSM `voltage_kv` property |
| Bus zone assignments | Point-in-polygon against `ercot_zones.geojson` |
| Transmission line geometry | OSM HV lines (OIM/OpenStreetMap) |
| Generators | ERCOT MORA capacity file (public) |
| Generator bus assignment | MORA substation name → OSM node name (V6 bridge then fuzzy) |
| Load distribution | Census 2020 county populations (254 counties) |
| Impedance | Voltage-tier formula × haversine distance (no public ERCOT impedance data) |

---

## Step 1 — Bus Table (needs new script)

Write `build_osm_bus_table.py`. It should:

1. Parse `Realist/grid_visualizer.html` and extract the `const NODES = [...]` array. (The HTML is the canonical output of `generate_visualizer.py` and is already validated. Parsing it avoids re-running the expensive BFS.)
2. Assign sequential integer Bus IDs (0-indexed).
3. Assign load zones via point-in-polygon against `ercot_zones.geojson`.
4. Output `sced_inputs/osm_bus.csv` with columns: `Bus ID`, `Bus Name`, `BaseKV`, `Bus Type`, `MW Load`, `MVAR Load`, `V Mag`, `V Angle`, `Area`, `Zone`, `lat`, `lon`, `osm_id`, `is_split`.

`MW Load` and `MVAR Load` are left as 0.0 at this stage — filled by `run_sced.py`'s `distribute_load()`.

`Bus Type` = 3 for the reference bus (pick the highest-kV substation in ERCOT NORTH zone, or the node nearest to the ERCOT market hub), 2 for all generator buses, 1 for all others. Reference bus selection must be documented and consistent across runs.

**Do not reuse** `build_bus_table.py` — it builds PSSE buses, not OSM nodes. See historical section.

---

## Step 2 — Branch Table (needs new script)

Write `build_osm_branch_table.py`. It should:

1. Parse `grid_visualizer.html` and extract `NODES`, `EDGES_HIGH`, `EDGES_MID_HI`, `EDGES_MID_LO`.
2. For each edge `{a, b, kv}`: look up lat/lon for nodes `a` and `b`, compute haversine distance, compute X_pu using the voltage-tier formula.
3. Add synthetic transformer branches: for each OSM substation node that has another OSM substation node at a different voltage level within 500 m and sharing a name prefix (i.e., physically the same substation complex), add a transformer branch with X = 0.12 p.u.
4. Output `sced_inputs/SourceData/branch.csv` with columns: `UID`, `From Bus`, `To Bus`, `R`, `X`, `B`, `Cont Rating`.

Voltage-tier parameters (same as old `build_branch_table.py`):
```
138 kV: x = 0.38 Ω/km, cont_rating = 300 MVA
230 kV: x = 0.35 Ω/km, cont_rating = 600 MVA
345 kV: x = 0.32 Ω/km, cont_rating = 1200 MVA
500 kV: x = 0.28 Ω/km, cont_rating = 2000 MVA
```
Z_base = kV² / 100. X_pu = x_ohm_per_km × length_km / z_base.

Also output `sced_inputs/SourceData/bus.csv` — a copy of `osm_bus.csv` in the format Vatic's `GridLoader` expects.

**Expected output:** ~4,656 line branches + some transformer branches. If significantly more, something is wrong — check for duplicate edge entries in the HTML parsing step.

**Do not reuse** `build_branch_table.py` — it uses PSSE buses as stop nodes and produces an overcrowded graph. See historical section.

---

## Step 3 — Generator Table (needs rewrite)

Rewrite `build_gen_table.py` (or write `build_osm_gen_table.py` alongside it) to assign generators to OSM node Bus IDs instead of PSSE bus IDs.

Assignment algorithm: see "Generator assignment" under Architecture above.

Output files remain the same format as current `gen.csv` and `init_state.csv` — Vatic's format hasn't changed, only the bus IDs. After assignment, filter to generators whose assigned Bus ID is in `osm_bus.csv`. Log dropped generators.

Cost curves and renewable PMax simplifications carry forward unchanged:
- Flat marginal cost per fuel type (EIA heat rate fallback)
- Renewable PMax = capacity factor × installed MW (CF_WIND = 0.45, CF_SOLAR = 0.05 for the target hour)

---

## Step 4 — Load Distribution (port existing logic)

`run_sced.py`'s `distribute_load()` uses a bus list to assign load. Update it to read `osm_bus.csv` instead of the PSSE `bus.csv`. Logic is otherwise unchanged. Verify that all 4,303 OSM nodes get a county assignment and a nonzero load share.

DC tie offsets: snap to nearest OSM substation node (not split point) for each tie location.

---

## Step 5 — Run SCED (port RealistLoader)

`run_sced.py` and `RealistLoader` need the `data_path` updated to point at the new OSM-based SourceData files. The Vatic framework itself is unchanged. Confirm:
- `RealistLoader.data_path` points to `sced_inputs/SourceData/`
- `process_actuals()` is implemented (static abstract in `GridLoader`)
- Reference bus is consistent with the Bus Type = 3 assignment from Step 1

Cluster upload bundle:
```
realist_sced/
  vatic/              ← copy from Birchfield/vatic/
  SourceData/
    bus.csv           ← 4,303 rows (from Step 2, copy of osm_bus.csv)
    branch.csv        ← ~4,656+ rows (from Step 2)
    gen.csv           ← generators assigned to OSM buses (from Step 3)
    init_state.csv
  run_realist_sced.ipynb
```

Solver: Gurobi (cluster) or CBC (fallback).

---

## Immediate Next Steps

**Priority 1 — Write `build_osm_bus_table.py` and `build_osm_branch_table.py`.** These extract the already-validated network from `grid_visualizer.html` into Vatic CSV format. Straightforward parsing work. Output: `osm_bus.csv`, `branch.csv`.

**Priority 2 — Rewrite generator assignment.** Update `build_gen_table.py` to assign generators to OSM node Bus IDs via the three-stage assignment chain (V6 bridge → name fuzzy → geo snap). This is the most uncertain step — log match counts at each stage and inspect the unmatched tail.

**Priority 3 — Port `run_sced.py` and run on cluster.** Check: does Vatic converge? What are zone LMP spreads? Is the West–North spread positive (West Texas export constraint binding)?

**Priority 4 (after feasibility confirmed) — Improve data quality:**
- Use NP4-126-M actual wind/solar output for the target hour instead of capacity factors.
- Attempt ERCOT LDF pull from market portal for load distribution.
- Cross-check OSM topology against HIFLD "U.S. Electric Power Transmission Lines" for missing Permian Basin 345 kV expansion lines.
- Revisit V6 PSSE bus crosswalk for the 763 matched nodes to enable LMP comparison against official ERCOT bus-level prices.

---

## Known Limitations

| Gap | Severity | Status |
|-----|----------|--------|
| OSM topology is incomplete (Permian Basin 345 kV expansion lines missing) | Significant | Flag in paper; cross-check HIFLD as Priority 4 |
| Flat cost curves (no SCED disclosure offer data) | Moderate | Acceptable for feasibility; flag in paper |
| Renewable PMax from CF not actual output | Moderate | Acceptable for feasibility; flag in paper |
| No ERCOT LDFs (using Census pop instead) | Moderate | Reasonable; LDFs preferred; flag in paper |
| Synthetic transformer X = 0.12 p.u. | Moderate | Standard academic practice; no public ERCOT impedance data |
| Split-point nodes carry no generation | Low | Correct — they're T-junctions, not generator sites |
| No BESS/storage modeled | Low for first run | Generators only; BESS is future work |
| No ORDC adder | Low | Out of scope for first attempt |
| No direct PSSE bus LMP comparison | Low for first run | OSM bus IDs ≠ ERCOT bus IDs; comparison deferred to Priority 4 |
| Reference bus choice | Moderate | Document selection; re-reference LMPs post-run for comparison |

---

---

# Historical Record: What Was Tried Before and Why It Was Abandoned

*This section is for future agents and researchers. Do not delete it. The mistakes documented here are not obvious and have been made twice.*

---

## Attempt 1: Endpoint-Only Branch Matching (→ 657 branches)

### What was built

`build_bus_table.py` loaded all 7,755 PSSE buses from the ERCOT Settlement Points file and assigned locations via the V6 OSM matching pipeline. `build_branch_table.py` then tried to build branches by taking the first and last coordinate of each OSM HV LineString and checking whether each endpoint was within 1 km of a PSSE bus.

**Result:** 657 branches for 7,755 buses. Far too sparse — a connected HV network should have ~1.5–2× as many branches as buses.

### Why it failed

OSM transmission lines are not discrete substation-to-substation segments. A single LineString like "Odessa to Fort Worth 345 kV" is one continuous polyline that passes *through* multiple substations without starting or ending at them. Taking only the first and last coordinate of that polyline misses every intermediate substation. Most branches simply had no PSSE bus near either endpoint.

### Lesson

Never use OSM LineString endpoints as branch terminals. OSM encodes lines as geographic paths, not electrical connections. The topological structure must be recovered by clustering endpoints and running BFS contraction, not by checking proximity of endpoints to nodes.

---

## Attempt 2: PSSE-Bus BFS (→ 22,571 branches)

### What was built

`build_branch_table.py` was completely rewritten to use BFS graph contraction, adapted from `generate_visualizer.py`. The algorithm:

1. Clusters all OSM HV line **endpoints** (first and last coordinate only) within 150 m into junction nodes.
2. Builds a junction adjacency graph from those clusters.
3. Loads `sced_inputs/bus.csv` filtered to 138 kV+ AND high/medium V6 confidence (~2,405 buses).
4. Snaps junction clusters to PSSE buses within 1 km — those become BFS stop nodes.
5. BFS from every stop node, stopping at other stop nodes. Each path → one branch.

**Result:** 22,571 branches for 2,405 buses (~9.4 branches/bus). Roughly 5–10× too many.

### Why it failed

The BFS algorithm was correct in structure but the junction graph it operated on was wrong. `generate_visualizer.py`'s `_graph_pass()` walks **all interior coordinates** of each LineString to build the junction graph. Attempt 2 only clustered the first and last coordinate. This means the junction graph had far fewer intermediate nodes than reality — each long polyline was represented as just two endpoint clusters with a single edge between them. With this sparse intermediate structure, the BFS could traverse from any stop node to almost any other stop node in a few hops, discovering O(N²) bus-pair paths that are not real direct transmission connections.

### Why the fix would not have been straightforward

The obvious fix — walk interior coordinates — would have made Attempt 2 essentially identical to re-running `generate_visualizer.py` with PSSE buses substituted as stop nodes. But this brings a deeper problem: only 763 of 3,037 OSM substations have a V6-confirmed PSSE bus mapping (25%). The other 75% of the transmission network has no PSSE stop node to halt the BFS. The BFS would therefore traverse through most of the real network unimpeded, connecting distant PSSE buses via phantom paths that skip real intermediate substations.

### Lesson

Do not substitute a different node set into `generate_visualizer.py`'s BFS unless that node set covers the full topology. If 75% of real substations have no corresponding stop node, the BFS will freely cross the gaps and produce garbage. The stop nodes must be dense enough that the BFS never needs to jump more than one real substation span.

---

## Root Cause: The PSSE Bus Dependency Was Wrong

### Why PSSE buses were used

The motivating logic was: ERCOT publishes real-time LMPs indexed by PSSE bus number. To compare our model LMPs against real ERCOT prices, we need PSSE bus IDs in our model. The Settlement Points file gives us a canonical list of 7,755 PSSE buses with names and zone assignments.

This is a valid *future validation* goal. It is not a prerequisite for building the model.

### Why the dependency created an unsolvable problem

The PSSE bus list is a purely administrative dataset. It contains bus names and zone assignments, but **no geographic coordinates**. The only way to get locations for PSSE buses is the V6 matching pipeline, which matches PSSE substation names to OSM substation names using string similarity and geographic heuristics.

V6 confidence breakdown for 7,755 PSSE buses:

| Confidence | Count | Meaning |
|-----------|-------|---------|
| High | 2,176 | Multiple signals agree; location trustworthy |
| Medium | 1,880 | Name similarity + geographic check; generally reliable |
| Low | 3,133 | Name-only match; location may be wrong by km |
| None | 566 | No match found; uses zone centroid |

3,699 buses (48%) have low-confidence or no-match locations. Their coordinates are either wrong by kilometers or are zone centroids (not real substation positions). A BFS that uses these as stop nodes will place branch terminals at wrong locations.

More critically: the V6 match only covers 763 OSM substations out of 3,037. So even if we fix the PSSE bus locations, the junction graph between them has huge gaps where real substations exist in OSM but have no PSSE stop node. The BFS cannot recover correct topology from a node set that covers only 25% of the physical network.

### The correct frame

The V6 pipeline was built to label OSM substations with ERCOT names for the website visualization. It was never designed to be the geographic backbone of a SCED model. Using it that way inverted the dependency: the SCED model was constrained by the coverage limits of a name-matching heuristic.

OSM substations are the primary geographic reality. PSSE buses are secondary administrative labels on top of a subset of those substations. Build the SCED on OSM substations directly. If you later want PSSE LMP comparison, add the V6 crosswalk as a lookup table on top of the model — don't build the model on top of the crosswalk.

---

## What Was Preserved from the PSSE Approach

These components from the old pipeline are still correct and carry forward:

- **`run_sced.py` / `RealistLoader` framework** — Vatic-compatible SCED runner. Needs bus ID updates but the structure is correct.
- **`run_realist_sced.ipynb`** — Self-contained cluster notebook. Update input paths.
- **Load distribution logic** (`distribute_load()`) — Population-weighted Census 2020 county assignment. Works with any bus list; just update the bus CSV it reads.
- **DC tie offsets** — OKLAUNION, MONTICELLO, EAGLE, MCALLEN, LAREDO. Keep; just re-snap to nearest OSM node.
- **Generator cost curves** — Flat marginal cost per fuel type using EIA heat rates. Fuel strings ("Nuclear", "Coal", "Gas", "Wind", "Solar") match Vatic's expected format.
- **Renewable PMax method** — CF × installed MW is acceptable for feasibility. Flag in paper.
- **`build_bus_table.py`** — Kept as an artifact. The 7,755-row `sced_inputs/bus.csv` is a useful reference (V6 crosswalk embedded, zone assignments, names). Do not use as the SCED bus table; do use as a lookup when you later need PSSE bus IDs for LMP comparison.
- **`build_gen_table.py`** — The join logic (MORA → Resource Node → Settlement Point → PSSE bus) is correct for what it does. The generator *list* and cost parameters are reusable. What needs to change is the final bus ID assignment step.
