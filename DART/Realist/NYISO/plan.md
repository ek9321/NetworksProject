# NYISO DC-SCED Model — Build Plan

## Goal

Build a DC-SCED model of NYISO from public data, following the same pipeline architecture as the ERCOT model in `Realist/ERCOT/`.

---

## NYISO vs ERCOT — Key Differences

| Dimension | ERCOT | NYISO |
|-----------|-------|-------|
| Load zones | 4 (NORTH, HOUSTON, SOUTH, WEST) | 11 (A–K) |
| Capacity regions | Same as zones | 4 (ROS, LHV, NYC, LI) |
| Backbone voltage | 345 kV | 345 kV + one 765 kV corridor |
| Sub-transmission | 138 kV | 138 kV + 115 kV |
| Interconnection | Islanded (DC ties only) | AC-interconnected (PJM, ISO-NE, HQ) |
| Key constraint | WESTEX export corridor | Central East, UPNY-SENY interfaces |
| Peak load | ~75 GW | ~32 GW |
| Generator fleet | ~1,200 units, 159 GW | ~500–700 units, ~40 GW |
| Storage | 18 GW (large, growing) | <1 GW grid-scale (growing) |

### Interconnection Handling

NYISO is AC-interconnected with PJM, ISO-NE, and Hydro-Quebec. For the SCED model, we model these as **fixed DC-tie injections** at boundary buses (same approach as ERCOT's OKLAUNION/MONTICELLO ties). NYISO publishes scheduled interchange data that gives us reasonable fixed values.

---

## Data Sources

### 1. Transmission Network (geometry)
- **Primary:** HIFLD national transmission lines, NY extract
  - URL: `https://opdgig.dos.ny.gov/datasets/NYSDOS::electric-transmission-lines-hifld/about`
  - Format: GeoJSON/Shapefile — includes voltage, owner, line geometry
  - Advantage over raw OSM: owner info, better voltage tagging, official source
- **Supplement:** OSM Overpass API for substations (same query pattern as Texas)
  - Overpass query: `area["name"="New York"]->.a; (node["power"="substation"](area.a); way["power"="substation"](area.a);); out center;`
- **Verification:** Open Infrastructure Map (openinframap.org)

### 2. Zone Boundaries
- **NYSERDA ArcGIS MapServer** — queryable GeoJSON
  - `https://services.nyserda.ny.gov/arcgis/rest/services/Electric/Utility_and_Load_Zones/MapServer`
  - Query layer for load zones, export as GeoJSON
- **Fallback:** County-to-zone mapping from NYISO Sub-Zone Boundaries PDF

### 3. Generator Fleet
- **NYISO Gold Book 2025** — unit-level capacity, fuel, zone
  - Excel: `https://www.nyiso.com/documents/20142/51231901/2025-Gold-Book-Baseline-Forecast-Tables.xlsx`
- **EIA-860** — lat/lon coordinates for geo-snapping to OSM buses
  - Filter `State == "NY"` from national file
  - Already available at `Birchfield/data/processed/eia860_generators.csv` (need to check if NY included)

### 4. Hourly Load Data
- **NYISO MIS archive** — integrated real-time actual load by zone
  - `http://mis.nyiso.com/public/csv/pal/` (monthly ZIPs, CSV with zones A–K)

### 5. Storage
- **EIA-860 Form 3.4** — utility-scale BESS with lat/lon (same file as ERCOT, filter for NY)
- **NYSERDA DER data** — supplement for projects not yet in EIA-860

### 6. Renewable Profiles
- **NYISO Real-Time Fuel Mix** — `http://mis.nyiso.com/public/P-63list.htm`
  - Gives total wind/solar/hydro generation by timestamp; derive CFs

---

## Pipeline Scripts (mirror ERCOT structure)

### Phase 1: Data Acquisition

#### `fetch_ny_substations.py`
- Query OSM Overpass API for NY state substations
- Output: `grid_data/ny_substations.geojson`

#### `fetch_ny_transmission.py`
- Download HIFLD transmission lines for NY (GeoJSON from ArcGIS)
- Supplement with OSM Overpass for any missing lines
- Output: `grid_data/ny_hv_lines.geojson`

#### `fetch_nyiso_zones.py`
- Query NYSERDA ArcGIS MapServer for zone boundaries
- Output: `grid_data/nyiso_zones.geojson`

#### `fetch_nyiso_load.py`
- Download hourly zonal load from NYISO MIS archive
- Output: `grid_data/nyiso_load_YYYY.csv`

#### `fetch_gold_book.py`
- Download Gold Book Excel tables
- Parse generator fleet (unit name, zone, fuel, summer/winter MW)
- Output: `grid_data/gold_book_generators.csv`

### Phase 2: Network Build

#### `generate_visualizer.py`
- Adapted from ERCOT version
- Input: ny_hv_lines.geojson, ny_substations.geojson, nyiso_zones.geojson
- Voltage filter: ≥115 kV (not 138 kV — NYISO has significant 115 kV)
- Output: `ny_grid_visualizer.html` with NODES/EDGES arrays

#### `build_osm_bus_table.py`
- Parse NODES from visualizer HTML
- Assign each bus to one of 11 NYISO zones (A–K) via point-in-polygon
- Select reference bus: Zone C (Central) or Zone F (Capital) ≥345 kV substation
- Output: `grid_data/sced_inputs/SourceData/bus.csv`

#### `build_osm_branch_table.py`
- Parse EDGES from visualizer HTML
- Impedance model:
  - 765 kV: 0.25 ohm/km, 2400 MVA per circuit
  - 345 kV: 0.32 ohm/km, 1200 MVA per circuit
  - 230 kV: 0.35 ohm/km, 600 MVA per circuit
  - 138 kV: 0.38 ohm/km, 400 MVA per circuit
  - 115 kV: 0.40 ohm/km, 200 MVA per circuit
- **Interface protection:** Do NOT blanket-upgrade 345 kV lines.
  Instead, identify Central East and UPNY-SENY corridor lines and
  calibrate their ratings to reproduce known TTC limits.
- Output: `grid_data/sced_inputs/SourceData/branch.csv`

#### `build_gen_table.py`
- Gold Book generators → assign to OSM buses
- Bus assignment pipeline (adapted from ERCOT):
  1. Gold Book zone + name → EIA-860 plant match → lat/lon → nearest OSM sub
  2. EIA-860 plant_code direct match → lat/lon → nearest OSM sub
  3. County centroid fallback
- Fuel mapping: Gas CC/CT/ST, Nuclear, Coal, Oil, Wind, Solar, Hydro
  - Note: NYISO has significant **hydro** (Niagara, St. Lawrence) and **oil** (NYC peakers)
- Output: `grid_data/sced_inputs/SourceData/gen.csv`, `init_state.csv`

#### `build_storage_table.py`
- EIA-860 Form 3.4 filtered for NY
- Same schema as ERCOT storage
- Output: `grid_data/sced_inputs/SourceData/storage.csv`

### Phase 3: SCED Execution

#### `run_sced.py`
- Adapted from ERCOT version
- Changes:
  - 11 zones instead of 4 for load distribution
  - Interconnection ties as fixed injections (PJM, ISO-NE, HQ)
  - Hydro generators need special treatment (run-of-river vs dispatchable)
- Output: `results_{tag}/` with hourly_summary, bus_detail, line_detail, etc.

#### `prepare_calibration_day.py`
- Parse NYISO actual load CSVs
- Parse NYISO fuel mix for wind/solar CFs
- Output: `hourly_load_YYYYMMDD.csv`, `hourly_cf_YYYYMMDD.csv`

---

## Calibration Strategy

### Calibration Metrics (analogous to ERCOT)

1. **Zone LMP ordering** — NYC (J) and LI (K) should have highest LMPs; upstate (A–D) lowest. This is the fundamental NYISO congestion pattern.
2. **Load shedding** — target <50 MW on a normal operations day
3. **Central East interface flow** — should bind during high-export periods
4. **LMP spread magnitude** — NYC vs upstate spread should be within 3× of actual

### Calibration Target Days
- **Summer peak** (July/August) — highest load, NYC peakers running, import constraints bind
- **High-wind shoulder** (spring/fall) — upstate wind export vs Central East constraint
- **Typical winter** — moderate load, gas constraints possible

### Key Physics to Reproduce
1. NYC is a **load pocket** — imports most power through constrained 345 kV corridors
2. Long Island is islanded except for two 345 kV cables + Neptune DC cable
3. Upstate NY has cheap hydro + wind; downstate has expensive gas peakers
4. Central East interface separates cheap upstate from expensive downstate

---

## Execution Order

1. **Data fetch** — Download all raw data (substations, lines, zones, generators, load)
2. **Visualizer** — Build topology, verify visually
3. **Bus table** — Extract nodes, assign zones
4. **Branch table** — Build impedance model, set ratings
5. **Gen table** — Assign generators to buses
6. **Storage table** — Assign BESS to buses
7. **First SCED run** — Constant load, constant CFs, verify it solves
8. **Calibration** — Hourly profiles, interface tuning, LMP validation

---

## Known Challenges

1. **115 kV inclusion** — NYISO relies on 115 kV more than ERCOT uses sub-138 kV. May need to include it to avoid phantom congestion.
2. **NYC underground** — Much of NYC transmission is underground and poorly mapped in OSM. May need manual bus/branch entries for Zone J.
3. **Interconnection modeling** — AC ties to PJM/ISO-NE are not simple DC injections; phase angle differences matter. Start with fixed injections, iterate.
4. **Hydro dispatch** — Niagara and St. Lawrence are must-run with seasonal variation. Need special dispatch rules, not just CF scaling.
5. **HIFLD vs OSM reconciliation** — Two transmission geometry sources may conflict. Need a merge/dedup strategy.
