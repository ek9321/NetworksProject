# NY SourceData Plan

Build a New York grid data package (`vatic/data/grids/NY-Dartboard/NY_Data/SourceData/`) that mirrors the Texas-7k SourceData format (`bus.csv`, `branch.csv`, `gen.csv`), using Dartboard's existing NY pipeline outputs plus EIA-860 data.

---

## 1. Reference Inventory

### 1.1 Texas-7k SourceData (the target format)

| File | Rows | Cols | Purpose |
|------|------|------|---------|
| `bus.csv` | 6,717 | 26 | Every bus: ID, location, zone, voltage, load, gen, shunts, bus type |
| `branch.csv` | 9,140 | 16 | Lines + transformers: endpoints, R/X/B, ratings |
| `gen.csv` | 731 | 54 | Generator units: dispatch limits, cost curves, ramp rates, startup params |

### 1.2 Dartboard NY outputs already produced

| File | Rows | Cols | Key content |
|------|------|------|-------------|
| `data/processed/new_york_buses.csv` | 724 | 6 | bus_id, substation_id, voltage_kv, role, connected_load_mw, connected_generator_ids |
| `data/processed/new_york_substations_with_buses.csv` | 630 | 9 | substation_id, lat, lng, mw_load, assigned_generators, substation_type, voltage flags |
| `data/processed/new_york_generator_assignments.csv` | 33 | 11 | Generator-hosting buses with assignment details |
| `data/processed/new_york_type_g_substations.csv` | 30 | 7 | Type-G (generator-only) substations with fuel type |
| `data/processed/new_york_transformers.csv` | 94 | 7 | transformer_id, from/to bus, from/to kV, rating_mva |
| `data/synthetic/new_york_lines_345kv.csv` | 115 | 9 | from_sub, to_sub, voltage_kv, length_km, X_pu, MVAmax |
| `data/synthetic/new_york_lines_115kv.csv` | 774 | 9 | same schema |
| `data/processed/eia860_generators.csv` | 23,766 (1,449 NY) | 15 | Plant code, capacity, min load, technology, prime_mover, energy_source, grid_voltage_kv |
| `data/processed/eia860_plants.csv` | 15,039 | 9 | Plant code, lat/lon, state, NERC region, balancing authority |

### 1.3 Vatic column consumption (columns actually used at runtime)

Not every Texas-7k column matters. Based on how `vatic/data/loaders.py` parses grid data:

**bus.csv — used columns:**
- `Bus ID`, `Bus Name`, `BaseKV`, `Bus Type`, `MW Load`, `Area`, `Sub Area`, `Zone`, `lat`, `lng`

**branch.csv — used columns:**
- `UID`, `From Bus`, `To Bus`, `X`, `Cont Rating`
- (`R`, `B` are loaded but not fed to the template)

**gen.csv — used columns:**
- `GEN UID`, `Bus ID`, `Fuel`, `Unit Type`, `PMin MW`, `PMax MW`
- `Ramp Rate MW/Min`, `Min Up Time Hr`, `Min Down Time Hr`
- `Start Time Cold/Warm/Hot Hr`, `Start Heat Cold/Warm/Hot MBTU`
- `Fuel Price $/MMBTU`, `Fixed Cost($/hr)`
- `MW Break 1–5`, `MWh Price 1–5` (piecewise linear cost curve)
- `BUS UID`, `Unit Group`

---

## 2. Column-by-Column Gap Analysis

### 2.1 bus.csv

| Target Column | Source | Notes |
|---------------|--------|-------|
| `Bus ID` | `new_york_buses.csv → bus_id` | Direct map |
| `Bus Name` | **derive**: `Sub_<substation_id>_<voltage_kv>_<bus_idx>` | Build a name from substation + voltage, matching Texas-7k naming convention (e.g., `GRAND_PRAIRIE_10_2`) |
| `lat` | `new_york_substations_with_buses.csv → lat` | Join bus → substation → lat |
| `lng` | `new_york_substations_with_buses.csv → lng` | Join bus → substation → lng |
| `Zone` | **derive** | Partition NY substations into ~8 zones (matching NYISO's A–K zones or using k-means clustering on lat/lng). See §3.1.2 |
| `Sub Name` | **derive**: `Sub_<substation_id>` | Substation label |
| `Area` | **derive** | Same as Zone for single-area or set all to 1 (NY is one interconnect) |
| `BaseKV` | `new_york_buses.csv → voltage_kv` | Direct map (345.0 or 115.0) |
| `PU Volt` | **default**: 1.0 | Flat-start assumption; not used by vatic |
| `Volt (kV)` | `BaseKV × PU Volt` | = BaseKV if PU Volt = 1.0 |
| `Angle (Deg)` | **default**: 0.0 | Not used by vatic |
| `MW Load` | `new_york_buses.csv → connected_load_mw` | Direct map; NaN → 0 |
| `Load Mvar` | **derive**: `MW Load × 0.33` (power factor ≈ 0.95) | Not used by vatic, but fill for completeness |
| `Gen MW` | **derive**: sum of assigned generator PMax at this bus | Not used by vatic, but fill for completeness |
| `Sub Num` | **derive**: sequential substation index | Not used by vatic |
| `Gen Mvar` | **default**: 0.0 | Not used by vatic |
| `Switched Shunts Mvar` | **default**: 0.0 | Not used by vatic |
| `Act G Shunt MW` | **default**: 0.0 | Not used by vatic |
| `Act B Shunt Mvar` | **default**: 0.0 | Not used by vatic |
| `Zone Num` | **derive**: integer zone index | Not used by vatic |
| `Bus Type` | **derive**: PQ for load-only, PV for generator buses, Slack for one large generator bus | **Used by vatic** for classification |
| `Mismatch MW/Mvar/MVA` | **default**: 0.0 each | Not used by vatic |
| `Bus Area` | = Area | Not used by vatic |
| `Sub Area` | **derive** | Used by vatic; can equal Zone or a simple partition |

### 2.2 branch.csv

| Target Column | Source | Notes |
|---------------|--------|-------|
| `UID` | **derive**: `A<sequential>` for lines, `T<sequential>` for transformers | Matches Texas-7k pattern (e.g., `A1`, `A2`, ...) |
| `From Bus` | Lines: map `from_sub` → bus_id at matching voltage; Transformers: `from_bus_id` | Lines currently use substation IDs — need sub→bus mapping |
| `From Name` | Look up Bus Name from bus.csv | Join |
| `To Bus` | Lines: map `to_sub` → bus_id at matching voltage; Transformers: `to_bus_id` | Same mapping |
| `To Name` | Look up Bus Name from bus.csv | Join |
| `Circuit` | **default**: 1 (or use `circuits` column from lines) | Multi-circuit lines should duplicate rows |
| `Status` | **default**: `Closed` | All active |
| `Branch Device Type` | `Line` for lines, `Transformer` for transformers | Categorical |
| `Xfrmr` | `YES` if transformer, `NO` if line | Boolean |
| `R` | Lines: `length_km × R_per_km / Z_base`; Transformers: 0.0 | Use `global.yaml` conductor parameters at matching voltage. Z_base = kV²/100 |
| `X` | Lines: already have `X_pu`; Transformers: typical transformer X (~0.001–0.01 pu) | Lines already computed; transformers need typical values |
| `B` | Lines: `length_km × B_per_km × Z_base`; Transformers: 0.0 | Derive from `global.yaml` |
| `Cont Rating` | Lines: `MVAmax` column; Transformers: `rating_mva` | Direct map |
| `Lim MVA B` | **default**: 0.0 | Not used by vatic |
| `Lim MVA C` | **default**: 0.0 | Not used by vatic |

**Row count estimate**: 115 (345 kV) + 774 (115 kV) + 94 (transformers) = **983 rows** (vs Texas-7k's 9,140). This is expected — our grid has ~724 buses vs 6,717.

### 2.3 gen.csv

This is the hardest file. Texas-7k has 54 columns of detailed unit economics. Our pipeline tracks generator IDs and capacities but not operational parameters.

| Target Column | Source | Notes |
|---------------|--------|-------|
| `BUS UID` | **derive**: `<bus_id>_<gen_index>` | Composite key |
| `Sub Num of Bus` | Sub Num from bus.csv | Join |
| `Bus ID` | From generator assignments | Direct |
| `Name of Bus` | Bus Name from bus.csv | Join |
| `ID` | Generator index within bus (1, 2, 3, ...) | Sequential per bus |
| `Status` | **default**: `Closed` | All operating |
| `Gen MW` | EIA-860 `summer_capacity_mw` or scale from current dispatch | Snapshot dispatch; can set = PMax for simplicity |
| `Gen Mvar` | **default**: 0.0 | Requires power flow; set zero |
| `PMin MW` | EIA-860 `minimum_load_mw` | **Direct from EIA-860** — this is available |
| `PMax MW` | EIA-860 `summer_capacity_mw` | **Direct from EIA-860** |
| `AGC` | **derive**: `YES` for thermal ≥ 50 MW, `NO` otherwise | Heuristic; Texas-7k has ~85% YES |
| `# Cost Curve Points` | **default**: 5 | Following Texas-7k convention |
| `IOB` | **derive** from heat rate lookup tables | See §3.3.2 |
| `IOC` | **derive** | See §3.3.2 |
| `Variable O&M` | **derive** from EIA technology-specific defaults | See §3.3.3 |
| `Fuel Price $/MMBTU` | **derive** from EIA energy_source → fuel price lookup | See §3.3.1 |
| `IOD` | **derive** | See §3.3.2 |
| `AVR` | **default**: `YES` | Automatic voltage regulator |
| `RegBus Num` | = Bus ID | Self-regulating |
| `Fuel` | EIA-860 `energy_source_1` → Texas-7k fuel labels | Map: NG→`NG (Natural Gas)`, SUN→`SUN (Solar)`, WAT→`WAT (Water)`, etc. |
| `Set Volt` | **default**: 1.0 | Per-unit voltage setpoint |
| `Min Mvar` | **derive**: `-0.5 × PMax` for thermal, 0 for renewables | Typical reactive limits |
| `Max Mvar` | **derive**: `+0.5 × PMax` for thermal, 0 for renewables | Typical reactive limits |
| `Enforce MW Limits` | **default**: `YES` | |
| `Part. Factor` | **default**: 1.0 | |
| `Cost Model` | **default**: `Piecewise Linear` | |
| `GEN UID` | **derive**: `<plant_code>_<UnitType>_<gen_index>` | E.g., `60902_OnshoreWindTurbine_1` |
| `Plant Code` | EIA-860 `plant_code` | Direct |
| `Unit Type` | EIA-860 `technology` | Direct — already matches Texas-7k vocabulary |
| `Ramp Rate MW/Min` | **derive** from technology-specific lookup table | See §3.3.4 |
| `Min Up Time Hr` | **derive** from technology-specific lookup table | See §3.3.4 |
| `Min Down Time Hr` | **derive** from technology-specific lookup table | See §3.3.4 |
| `Time from Cold Shutdown to Full Load` | **derive** | See §3.3.4 |
| `Unit Group` | **derive**: same as Unit Type or a simplified category | |
| `Start Time Cold/Warm/Hot Hr` | **derive** from technology-specific lookup table | See §3.3.4 |
| `Start Heat Cold/Warm/Hot MBTU` | **derive** from technology-specific lookup table | See §3.3.5 |
| `Non Fuel Start Cost $` | **derive** from technology-specific lookup table | See §3.3.5 |
| `Fixed Cost($/hr)` | **derive** from technology-specific lookup table | See §3.3.3 |
| `MW Break 1–5` | **derive**: even spacing from PMin to PMax | See §3.3.2 |
| `MWh Price 1–5` | **derive** from heat rate + fuel price | See §3.3.2 |
| `TCC_x` | **derive**: array of MW breakpoints | Not used by vatic |
| `TCC_y` | **derive**: array of $/hr at each breakpoint | Not used by vatic |

---

## 3. Implementation Steps

### 3.1 Stage A: Build `bus.csv` (Pipeline 9)

**Script**: `pipelines/9_build_ny_sourcedata.py` (or a dedicated `sourcedata/build_bus.py`)

#### 3.1.1 Join bus + substation data
```
buses ← read new_york_buses.csv
subs  ← read new_york_substations_with_buses.csv
merged ← left_join(buses, subs, on=substation_id)
```
This gives every bus its lat, lng, mw_load, substation metadata.

#### 3.1.2 Zone assignment
Two options:
- **Option A (preferred)**: Map substations to NYISO load zones (A–K) using lat/lng boundaries. The 11 NYISO zones have well-documented geographic boundaries.
- **Option B**: K-means clustering on (lat, lng) with k=8 to match Texas-7k's 8 zones.

Store zone both as label (`Zone`) and integer (`Zone Num`).

#### 3.1.3 Bus naming
Generate `Bus Name` as `<SUB_NAME>_<BaseKV/10>_<bus_index_within_sub>` (e.g., `SUB_381_34_1` for a 345 kV bus at substation 381).

#### 3.1.4 Bus type assignment
- Buses with generators and load: `PV`
- Buses with load only: `PQ`
- Single largest generator bus: `Slack`

#### 3.1.5 Fill defaults
Set `PU Volt=1.0`, `Angle=0.0`, and all shunt/mismatch columns to 0.0.

**Output**: `vatic/data/grids/NY-Dartboard/NY_Data/SourceData/bus.csv` (724 rows, 26 cols)

---

### 3.2 Stage B: Build `branch.csv` (Pipeline 9 continued)

#### 3.2.1 Lines: sub→bus mapping
Lines reference substations (`from_sub`, `to_sub`). Each substation has one bus per voltage level. Map:
```
line.From_Bus = bus_id where substation_id == from_sub AND voltage_kv == line.voltage_kv
line.To_Bus   = bus_id where substation_id == to_sub   AND voltage_kv == line.voltage_kv
```

#### 3.2.2 Compute R, B for lines
`X_pu` is already in the lines CSVs. Derive `R` and `B` from `global.yaml` conductor parameters:

For a line at voltage V with length L km:
```
Z_base = V² / S_base    (S_base = 100 MVA)
R_pu = L × R_per_km / Z_base
B_pu = L × B_per_km × Z_base
```
Where `R_per_km` and `B_per_km` come from `global.yaml` at matching voltage (345kV or 115kV → mapped to 138kV parameters as proxy).

#### 3.2.3 Transformers
Read `new_york_transformers.csv`. Set:
- `R = 0.0`, `X = 0.001` (typical), `B = 0.0`
- `Cont Rating = rating_mva`
- `Branch Device Type = Transformer`, `Xfrmr = YES`

#### 3.2.4 Merge and assign UIDs
Concatenate lines + transformers. Assign sequential UIDs: `A1, A2, ..., A889, A890, ..., A983`.

#### 3.2.5 Multi-circuit handling
If a line row has `circuits > 1`, duplicate that row with `Circuit` = 1, 2, etc. (or keep single row with combined rating — follow Texas-7k convention, which uses single rows per circuit).

**Output**: `branch.csv` (~983 rows, 16 cols)

---

### 3.3 Stage C: Build `gen.csv` (Pipeline 10 — most complex)

#### 3.3.1 Fuel price lookup table
Build a table mapping EIA `energy_source_1` to `Fuel Price $/MMBTU`:

| EIA Source | Texas-7k Fuel Label | Typical Price ($/MMBTU) |
|------------|---------------------|------------------------|
| NG | `NG (Natural Gas)` | 3.50–5.00 |
| SUN | `SUN (Solar)` | 0.00 |
| WAT | `WAT (Water)` | 0.00 |
| WND | `WND (Wind)` | 0.00 |
| NUC | `NUC (Nuclear)` | 0.75 |
| DFO | `DFO (Distillate Fuel Oil)` | 15.00 |
| KER | `KER (Kerosene)` | 16.00 |
| RFO | `RFO (Residual Fuel Oil)` | 10.00 |
| LFG | `OG (Other Gas)` | 2.00 |
| MSW | `OTH (Other)` | 2.50 |
| MWH | `MWH (Electricity use for Energy Storage)` | 0.00 |
| WDS/WDL | `WDS (Wood/Wood Waste Solids)` | 2.50 |
| BLQ | `AB (Agricultural By-Products)` | 2.50 |

Store in `config/fuel_prices.yaml` or hard-code in the builder.

Prices should reference EIA's latest "Electric Power Monthly" data for NYISO-region fuel costs. The values above are reasonable 2023 defaults.

#### 3.3.2 Cost curve construction
For thermal generators:
1. Create 5 evenly-spaced MW breakpoints from PMin to PMax.
2. Compute marginal cost at each break: `(Heat_Rate × Fuel_Price) + Variable_O&M`.
3. Heat rates by technology (BTU/kWh, typical):
   - Natural Gas Combined Cycle: 6,600–7,200
   - Natural Gas Combustion Turbine: 9,500–11,000
   - Natural Gas Steam Turbine: 9,800–11,500
   - Natural Gas Internal Combustion Engine: 8,500–10,000
   - Nuclear: 10,500
   - Coal/MSW: 10,000–11,000
   - Oil: 10,500–12,000
4. Convert: `MWh_Price = Heat_Rate / 1000 × Fuel_Price + Variable_O&M`
5. `IOB` (no-load cost intercept) ≈ `PMin × lowest_marginal_cost × 0.8`
6. `IOC`, `IOD` ≈ incremental cost coefficients (or 0 if using piecewise).

For renewables (wind, solar, hydro): set all cost curve values to 0 or near-zero marginal cost, PMin=0.

#### 3.3.3 O&M cost defaults ($/MWh Variable, $/hr Fixed)

| Technology | Variable O&M ($/MWh) | Fixed Cost ($/hr) |
|------------|----------------------|-------------------|
| Combined Cycle | 3.5–4.0 | per Texas-7k median |
| Combustion Turbine | 4.0–5.0 | per Texas-7k median |
| Steam Turbine | 4.0–5.0 | per Texas-7k median |
| ICE | 4.0–5.0 | per Texas-7k median |
| Nuclear | 2.0 | per Texas-7k median |
| Hydro | 0.0 | 0.0 |
| Wind | 0.0 | 0.0 |
| Solar | 0.0 | 0.0 |
| Storage | 0.0 | 0.0 |

Derive `Fixed Cost($/hr)` from Texas-7k medians by technology — extract actual values with a one-time script.

#### 3.3.4 Ramp rate and timing defaults

| Technology | Ramp Rate (MW/Min % PMax) | Min Up (Hr) | Min Down (Hr) | Start Cold (Hr) | Start Warm (Hr) | Start Hot (Hr) |
|------------|---------------------------|-------------|----------------|------------------|------------------|-----------------|
| Combined Cycle | 2–3% | 4 | 4 | 12 | 8 | 4 |
| Combustion Turbine | 8–10% | 1 | 1 | 2 | 1 | 0.5 |
| Steam Turbine | 1–2% | 8 | 8 | 24 | 12 | 6 |
| ICE | 10–15% | 0.5 | 0.5 | 0.5 | 0.25 | 0.1 |
| Nuclear | 0.5% | 24 | 24 | 72 | 48 | 24 |
| Hydro | 100% | 0 | 0 | 0 | 0 | 0 |
| Wind/Solar | 100% | 0 | 0 | 0 | 0 | 0 |

`Ramp Rate MW/Min` = `(% PMax) × PMax / 100`.

#### 3.3.5 Startup heat and cost defaults

| Technology | Start Heat Cold (MBTU) | Start Heat Warm (MBTU) | Start Heat Hot (MBTU) | Non Fuel Start ($) |
|------------|------------------------|------------------------|-----------------------|--------------------|
| Combined Cycle | 200 × PMax/500 | 150 × PMax/500 | 100 × PMax/500 | 500 |
| Combustion Turbine | 50 × PMax/100 | 30 × PMax/100 | 15 × PMax/100 | 100 |
| Steam Turbine | 300 × PMax/500 | 200 × PMax/500 | 100 × PMax/500 | 1000 |
| ICE | 10 | 5 | 2 | 50 |
| Nuclear | 0 | 0 | 0 | 0 |
| Renewables | 0 | 0 | 0 | 0 |

Scale startup heat proportionally to unit size. These can be calibrated against Texas-7k medians.

#### 3.3.6 Generator-to-bus mapping
Our pipeline assigns generators to substations. Each substation may have 1–2 buses (345 kV and/or 115 kV). Rules:
- If generator's EIA `grid_voltage_kv` ≥ 200 → assign to 345 kV bus (if exists), else 115 kV bus.
- If generator's EIA `grid_voltage_kv` < 200 → assign to 115 kV bus.
- Generators at Type-G substations: assign to whichever bus exists.

Use `connected_generator_ids` in `new_york_buses.csv` for the existing mapping; expand each generator ID back to its EIA-860 record.

#### 3.3.7 Expected generator count
Our pipeline assigns generators to 33 load+gen buses and 30 Type-G substations = 143 buses with generators (118 generator + 25 load_and_generator role buses).

EIA-860 has 1,449 NY operating generators, but many are small (488 solar PV, 388 hydro). For vatic compatibility, we may want to filter to generators ≥ 1 MW or aggregate small distributed generators into equivalent units, similar to how Texas-7k reduces to 731 units.

**Output**: `gen.csv` (estimated 200–500 rows after aggregation, 54 cols)

---

### 3.4 Stage D: Wind & Solar Maps (Optional — Pipeline 11)

Texas-7k includes NREL mapping files:
- `Texas7k_NREL_wind_map.csv` (153 rows): maps wind generators to NREL site IDs for timeseries dispatch.
- `Texas7k_NREL_solar_map.csv` (36 rows): maps solar generators to NREL site IDs.

For NY:
- **Wind**: 39 EIA-860 NY wind generators. Map to NREL wind sites using nearest-neighbor lat/lng matching against the [NREL Wind Integration National Dataset (WIND Toolkit)](https://www.nrel.gov/grid/wind-toolkit.html) or SAM datasets. Requires downloading NY-region NREL wind capacity factors.
- **Solar**: 488 EIA-860 NY solar generators (mostly small DG). Map to NREL NSRDB solar sites. Many are tiny — aggregate to substation level.

**Output**: `NY_NREL_wind_map.csv`, `NY_NREL_solar_map.csv`

**Priority**: LOW — only needed for variable renewable dispatch timeseries. Can be deferred until a vatic simulation run is attempted.

---

## 4. Implementation Order and Dependencies

```
                ┌──────────────────┐
                │  EIA-860 (NY)    │
                │  1,449 gens      │
                └────────┬─────────┘
                         │
                         ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ NY Buses     │   │ NY Subs      │   │ NY Generators│
│ (724 rows)   │   │ (630 rows)   │   │ Assignments  │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                   │
       ▼                  ▼                   ▼
  ┌─────────────────────────────────────────────┐
  │  Stage A: bus.csv (Pipeline 9)               │
  │  Join buses + subs + zones + bus types       │
  └───────────────────┬─────────────────────────┘
                      │
       ┌──────────────┴──────────────┐
       ▼                             ▼
  ┌──────────────┐            ┌──────────────┐
  │  Stage B:    │            │  Stage C:    │
  │  branch.csv  │            │  gen.csv     │
  │  (needs      │            │  (needs      │
  │  bus IDs)    │            │  bus IDs +   │
  └──────────────┘            │  EIA-860)    │
                              └──────────────┘
                                     │
                                     ▼
                              ┌──────────────┐
                              │  Stage D:    │
                              │  wind/solar  │
                              │  maps        │
                              │  (optional)  │
                              └──────────────┘
```

### Build order:
1. **bus.csv** first — everything else needs bus IDs and bus names.
2. **branch.csv** next — uses bus IDs for From/To mapping.
3. **gen.csv** next — uses bus IDs + EIA-860 enrichment.
4. **wind/solar maps** last — optional, uses gen UIDs.

### Suggested files to create:
- `config/fuel_prices.yaml` — fuel price and technology parameter lookup tables.
- `config/generator_defaults.yaml` — ramp rates, startup times, heat rates, O&M costs by technology.
- `core/sourcedata_builder.py` — pure functions that transform Dartboard data → SourceData format.
- `pipelines/9_build_ny_sourcedata.py` — orchestration: reads configs + CSVs, calls core functions, writes output.
- `pipelines/10_verify_sourcedata.py` — validation: check column counts, referential integrity (bus IDs in branch/gen match bus.csv), value ranges.

### Output directory:
```
vatic/data/grids/NY-Dartboard/
  NY_Data/
    SourceData/
      bus.csv       (724 rows × 26 cols)
      branch.csv    (~983 rows × 16 cols)
      gen.csv       (~200–500 rows × 54 cols)
    NY_NREL_wind_map.csv   (optional, ~39 rows)
    NY_NREL_solar_map.csv  (optional, ~50 rows)
```

---

## 5. Risks and Open Questions

1. **Zone assignment**: NYISO has 11 load zones (A–K), Texas-7k uses 8 numeric zones. Should we use real NYISO zones (more realistic) or match the 8-zone convention? NYISO zone boundaries are publicly available as shapefiles.

2. **Generator aggregation**: 1,449 EIA generators is many more than Texas-7k's 731 (for a much larger grid). Many NY generators are tiny DG/hydro (< 5 MW). Strategy: (a) keep all, (b) filter ≥ 1 MW, (c) aggregate small gens at same substation into equivalents. Recommend option (b) initially, revisit if vatic performance suffers.

3. **Cost curve accuracy**: Heat rate and fuel price defaults are reasonable but generic. For higher fidelity, scrape EIA-923 (generation and fuel consumption data) to get plant-specific heat rates. This is a future enhancement.

4. **Vatic loader compatibility**: Need to verify that a `T7kLoader`-style parser works for NY grid, or whether a new `NYLoader` subclass is needed. Check if the loader is parameterized by grid directory or hard-coded to Texas-7k paths.

5. **Transformer X values**: Our pipeline records `rating_mva` but not impedance. Default X = 0.001 pu is a placeholder. Could derive from kV ratio and typical transformer nameplate data.

6. **Multi-circuit lines**: Our pipeline's `circuits` column indicates parallel lines. Need to decide whether to emit separate rows per circuit (Texas-7k convention) or one row with combined rating.

7. **Grid voltage mismatch**: Our NY grid uses 345/115 kV, but Texas-7k also has 138/69/13.8/18 kV levels. The global.yaml conductor parameters use 138 kV as proxy for our 115 kV — verify this is acceptable.
