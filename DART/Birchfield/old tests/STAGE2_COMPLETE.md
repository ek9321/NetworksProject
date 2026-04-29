# Stage 2: Voltage Partition - COMPLETE ✓

## Overview

Stage 2 assigns nominal voltage buses to each substation and creates internal transformers between voltage levels. This stage implements the voltage partitioning methodology from the Birchfield et al. paper.

## Implementation

### Core Module: `core/voltage_partition.py`

Implements the complete voltage partition algorithm:

1. **Load all substations** (Type A, B, and g together)
2. **Compute selection scores** = max(load MW, generation MW)
3. **Select substations for high-voltage buses** via weighted sampling
4. **Create buses** at appropriate voltage levels per substation
5. **Create internal transformers** connecting voltage levels
6. **Attach loads** to lowest voltage bus
7. **Attach generators** to highest voltage bus

**Key Functions:**
- `load_all_substations()` - Integrates all three substation types
- `select_high_voltage_substations()` - Weighted sampling for 345 kV assignment
- `create_buses_and_transformers()` - Bus and transformer generation
- `voltage_partition()` - Main orchestration function

### Pipeline: `pipelines/5_partition_voltages.py`

Orchestrates voltage partition for both Texas and New York regions.

**Functions:**
- `save_substations_with_buses_csv()` - Saves substation metadata with voltage assignments
- `save_buses_csv()` - Saves bus definitions
- `save_transformers_csv()` - Saves internal transformer definitions
- `save_summary_csv()` - Saves partition summary statistics
- `partition_region()` - Executes voltage partition for a single region
- `main()` - Runs both regions

### Verification: `pipelines/6_verify_stage2.py`

Comprehensive validation of Stage 2 outputs with 9 checks:

1. All substations have at least one bus
2. Bus voltages match substation assignments
3. Loads attached to lowest voltage bus
4. Generators attached to highest voltage bus
5. Transformers connect adjacent voltage levels
6. Transformer ratings follow heuristic
7. Voltage percentages match requested (within 2% tolerance)
8. No duplicate IDs
9. Expected transformer count matches

### Visualization: `viz/voltage_partition_viz.py`

Creates two-panel visualization showing:
- Left panel: Substations colored by voltage level (115 kV only vs. 345 kV + 115 kV)
- Right panel: Substations colored by type (A, B, g)

## Configuration

Voltage settings are defined per-region in `config/texas.yaml` and `config/new_york.yaml`:

```yaml
voltage:
  levels: [345, 115]  # kV, ordered high to low
  pct_substations_with_high_voltage:
    345: 0.15  # 15% of substations get 345 kV buses
    115: 1.0   # All substations get 115 kV buses
  selection_weight_metric: "max_load_or_generation"

topology:
  target_mn_ratio: 1.22
  random_seed: 42
```

## Algorithm Details

### High-Voltage Substation Selection

Uses **weighted sampling without replacement** where:
- **Weight** = max(load MW, generation MW)
- **Probability** = weight / sum(all weights)
- **Target count** = round(percentage × total substations)
- **Random seed**: 42 (deterministic)

### Bus Creation

For each substation with voltages [V1, V2, ..., Vn] (highest to lowest):
- **Highest voltage bus**: Role = 'generator', attached generators
- **Lowest voltage bus**: Role = 'load', attached load
- **Intermediate buses**: Role = 'transmission', no load/gen
- **Single-bus substations**: Role = 'load_and_generator' (if both present)

### Transformer Creation

For substations with multiple voltage levels:
- Creates transformers between **adjacent voltage levels**
- **Direction**: Higher voltage → Lower voltage
- **Rating heuristic**: max(1.2 × (generation + load), 50.0) MVA
- Ensures all voltage levels are internally connected

## Results

### Texas
- **Input**: 1312 substations (1182 Type A + 68 Type B + 62 Type g)
- **Output**:
  - 1509 buses (1312 @ 115 kV + 197 @ 345 kV)
  - 197 transformers
  - Actual 345 kV percentage: **15.02%** (requested 15%)

### New York
- **Input**: 630 substations (567 Type A + 33 Type B + 30 Type g)
- **Output**:
  - 724 buses (630 @ 115 kV + 94 @ 345 kV)
  - 94 transformers
  - Actual 345 kV percentage: **14.92%** (requested 15%)

## Verification Results

✓ **All checks passed** for both regions:
- All substations have buses
- Voltages correctly assigned
- Loads/generators correctly attached
- Transformers properly configured
- No duplicate IDs
- Percentages within 2% tolerance

## Outputs

### CSV Files (in `data/processed/`)

For each region (texas, new_york):

1. **`{region}_substations_with_buses.csv`**
   - One row per substation
   - Includes voltage assignments: `has_high_voltage_{V}kv` columns
   - Geographic location, load, generation, type

2. **`{region}_buses.csv`**
   - One row per bus
   - Fields: bus_id, substation_id, voltage_kv, role, connected_load_mw, connected_generator_ids

3. **`{region}_transformers.csv`**
   - One row per internal transformer
   - Fields: transformer_id, substation_id, from_bus_id, to_bus_id, from_kv, to_kv, rating_mva

4. **`{region}_voltage_partition_summary.csv` and `.json`**
   - Summary statistics: total substations/buses/transformers
   - Requested vs. actual percentages for each voltage level
   - Voltage level list

### Visualizations (in `viz/texas/` and `viz/new_york/`)

- **`voltage_partition.png`**: Two-panel map showing voltage levels and substation types

## Key Design Decisions

1. **Integration of all substation types**: Type A, B, and g substations are processed together in a single pipeline, not separately.

2. **Weighted selection**: High-voltage substations are selected based on max(load, generation), giving preference to larger facilities.

3. **Deterministic sampling**: Using fixed random seed (42) ensures reproducible results.

4. **Monotonic voltage assignment**: If a substation has voltage V, it also has all lower voltages.

5. **Transformer rating heuristic**: Simple formula based on connected power with safety margin, minimum 50 MVA.

6. **Role assignment**: Clear separation of responsibilities - generators on highest bus, loads on lowest bus.

## Next Steps: Stage 3 - Topology Generation

The voltage partition outputs are ready for Stage 3, which will:

1. Perform Delaunay triangulation per voltage level
2. Generate MST for initial connectivity
3. Create candidate lines with distance filtering
4. Score lines using heuristic penalties/rewards
5. Iteratively add lines until target m/n ratio (1.22) is achieved

Input files needed:
- `{region}_substations_with_buses.csv` - For coordinates and voltage flags
- `{region}_buses.csv` - For bus-level connectivity
- `{region}_transformers.csv` - For internal substation connections

## Files Modified/Created

### Core
- ✓ `core/voltage_partition.py` (new)

### Pipelines
- ✓ `pipelines/5_partition_voltages.py` (new)
- ✓ `pipelines/6_verify_stage2.py` (new)

### Visualization
- ✓ `viz/voltage_partition_viz.py` (new)

### Configuration
- ✓ `config/texas.yaml` (modified - added voltage section)
- ✓ `config/new_york.yaml` (modified - added voltage section)
- ✓ `config/global.yaml` (modified - clarified stage separation)

### Documentation
- ✓ `README.md` (updated with Stage 2 completion status)
- ✓ `STAGE2_COMPLETE.md` (this file)

## References

- Birchfield et al., "Grid Structural Characteristics as Validation Criteria for Synthetic Networks"
- `VoltagePartitionPlan.md` - Original implementation plan
- `BirchfieldGrid.pdf` - Reference methodology document
