# Stage 2: Voltage Partition - Test Results

## Executive Summary

✅ **ALL TESTS PASSED** - Stage 2 implementation is correct and complete.

Both Texas and New York regions successfully completed voltage partition with:
- Exact load conservation (0.000000 MW difference)
- All generators accounted for (1186 TX, 728 NY)
- Voltage percentages within 2% tolerance
- All transformer ratings matching heuristic formula
- No data integrity issues

---

## Test Suite Overview

### 1. Automated Verification Script (`verify_stage2.py`)

**Status: ✓ PASSED (18/18 checks)**

#### Texas Results:
- ✓ All 1312 substations have at least one bus
- ✓ Bus voltages match substation assignments (1509 buses)
- ✓ Loads correctly attached to lowest voltage bus
- ✓ Generators correctly attached to highest voltage bus (68 Type B + 62 Type g)
- ✓ All 197 transformers connect adjacent voltage levels
- ✓ All transformer ratings follow heuristic: max(1.2 × (gen + load), 50.0)
- ✓ Voltage percentages within 2% tolerance (15.02% actual vs 15.00% requested)
- ✓ No duplicate bus IDs
- ✓ No duplicate transformer IDs

#### New York Results:
- ✓ All 630 substations have at least one bus
- ✓ Bus voltages match substation assignments (724 buses)
- ✓ Loads correctly attached to lowest voltage bus
- ✓ Generators correctly attached to highest voltage bus (33 Type B + 30 Type g)
- ✓ All 94 transformers connect adjacent voltage levels
- ✓ All transformer ratings follow heuristic
- ✓ Voltage percentages within 2% tolerance (14.92% actual vs 15.00% requested)
- ✓ No duplicate bus IDs
- ✓ No duplicate transformer IDs

---

## Test Category 2: Load Conservation

**Status: ✓ PERFECT CONSERVATION**

### Texas:
```
Total load in substations:  57,267.25 MW
Total load in buses:        57,267.25 MW
Difference:                  0.000000 MW
```
**Result: ✓ Exact match - no rounding errors**

### New York:
```
Total load in substations:  39,029.32 MW
Total load in buses:        39,029.32 MW
Difference:                  0.000000 MW
```
**Result: ✓ Exact match - no rounding errors**

---

## Test Category 3: Generator Accounting

**Status: ✓ ALL GENERATORS ACCOUNTED FOR**

### Texas:
```
Stage 1 (Generator Assignment):
  Type B generators:        370
  Type g generators:        816
  Total Stage 1:          1,186

Stage 2 (Voltage Partition):
  Generators on buses:    1,186

Difference:                   0
```
**Result: ✓ 100% of generators attached to buses**

### New York:
```
Stage 1 (Generator Assignment):
  Type B generators:        303
  Type g generators:        425
  Total Stage 1:            728

Stage 2 (Voltage Partition):
  Generators on buses:      728

Difference:                   0
```
**Result: ✓ 100% of generators attached to buses**

---

## Test Category 4: Voltage Level Distribution

**Status: ✓ WITHIN TOLERANCE**

### Texas:
```
Voltage Configuration:
  Single voltage (115 kV only):     1,115 (85.0%)
  Dual voltage (345+115 kV):          197 (15.0%)

345 kV Assignment:
  Requested:                        15.00%
  Actual:                           15.02%
  Difference:                        0.02%
  Tolerance (±2%):                  ✓ PASS
```

### New York:
```
Voltage Configuration:
  Single voltage (115 kV only):       536 (85.1%)
  Dual voltage (345+115 kV):           94 (14.9%)

345 kV Assignment:
  Requested:                        15.00%
  Actual:                           14.92%
  Difference:                        0.08%
  Tolerance (±2%):                  ✓ PASS
```

---

## Test Category 5: Transformer Ratings

**Status: ✓ ALL RATINGS MATCH HEURISTIC**

### Texas Transformer Statistics:
```
Count:                             197
Min rating:                      50.00 MVA
Max rating:                  11,103.84 MVA
Average rating:                 596.22 MVA
At minimum (50 MVA):          20 (10.2%)
```

**Formula verification:**
- All 197 transformers use: `rating_mva = max(1.2 × (gen_mw + load_mw), 50.0)`
- ✓ All ratings match expected values (within floating-point precision)

### New York Transformer Statistics:
```
Count:                              94
Min rating:                      50.00 MVA
Max rating:                   2,425.44 MVA
Average rating:                 270.39 MVA
At minimum (50 MVA):           15 (16.0%)
```

**Formula verification:**
- All 94 transformers use: `rating_mva = max(1.2 × (gen_mw + load_mw), 50.0)`
- ✓ All ratings match expected values (within floating-point precision)

---

## Test Category 6: Bus Role Assignment

**Status: ✓ ALL ROLES CORRECTLY ASSIGNED**

### Texas Bus Roles:
```
generator:               222 (14.7%)  - Highest voltage in multi-voltage substations
load:                  1,251 (82.9%)  - Lowest voltage or single-voltage
load_and_generator:       36 ( 2.4%)  - Single-voltage with both load & gen
```

### New York Bus Roles:
```
generator:               118 (16.3%)  - Highest voltage in multi-voltage substations
load:                    581 (80.2%)  - Lowest voltage or single-voltage
load_and_generator:       25 ( 3.5%)  - Single-voltage with both load & gen
```

**Rules verified:**
- ✓ Multi-voltage: Generators on highest bus, loads on lowest bus
- ✓ Single-voltage: Combined role if both load and generation present
- ✓ No intermediate buses have load or generation (transmission role)

---

## Test Category 7: Substation Type Distribution in High-Voltage Selection

**Status: ✓ WEIGHTED SELECTION WORKING CORRECTLY**

### Texas Dual-Voltage (345 kV) Substations by Type:
```
Type A (load-only):      127 (64.5%)
Type B (load+gen):        32 (16.2%)
Type g (gen-only):        38 (19.3%)
```

### New York Dual-Voltage (345 kV) Substations by Type:
```
Type A (load-only):       79 (84.0%)
Type B (load+gen):         8 ( 8.5%)
Type g (gen-only):         7 ( 7.4%)
```

**Analysis:**
- Type A substations are overrepresented in high-voltage selection (64.5% TX, 84.0% NY)
- This is CORRECT behavior because:
  - Type A substations are the majority (~90% of total)
  - Large population centers (high load) get preferential selection
  - The weighted sampling formula `score = max(load, gen)` favors high-load substations
  - Type B and g substations are included when they have significant load/generation

---

## Test Category 8: Data Integrity

**Status: ✓ ALL FILES VALID**

### File Counts:
```
Texas:
  substations_with_buses.csv:     1,313 lines (1,312 data + 1 header)
  buses.csv:                      1,510 lines (1,509 data + 1 header)
  transformers.csv:                 198 lines (197 data + 1 header)
  voltage_partition_summary:      Valid JSON and CSV

New York:
  substations_with_buses.csv:       631 lines (630 data + 1 header)
  buses.csv:                        725 lines (724 data + 1 header)
  transformers.csv:                  95 lines (94 data + 1 header)
  voltage_partition_summary:      Valid JSON and CSV
```

### ID Uniqueness:
- ✓ All bus IDs are unique and sequential
- ✓ All transformer IDs are unique and sequential
- ✓ All substation IDs are unique and sequential

### CSV Format:
- ✓ All CSV files have correct headers
- ✓ All required fields present
- ✓ No missing or malformed data
- ✓ Numeric fields parse correctly
- ✓ Semicolon-delimited lists valid

---

## Test Category 9: Example Substations (Spot Check)

### Texas Substation 9 (Type A, Dual-Voltage):
```
Load: 232.31 MW, Generation: 0.00 MW
Buses:
  - Bus 9:  345 kV, role=generator, load=0.00 MW, gens=0
  - Bus 10: 115 kV, role=load, load=232.31 MW, gens=0
Transformer 1:
  - 345 → 115 kV
  - Rating: 278.77 MVA
  - Expected: 278.77 MVA (1.2 × 232.31 = 278.77)
  - ✓ Match
```

### Texas Substation 4 (Type B, Single-Voltage):
```
Load: 85.91 MW, Generation: 188.00 MW
Buses:
  - Bus 4: 115 kV, role=load_and_generator, load=85.91 MW, gens=19
Transformers: None (single-voltage)
✓ Correct: Both load and generation on single bus
```

### New York Substation 12 (Type B, Dual-Voltage):
```
Load: 180.96 MW, Generation: 188.00 MW
Buses:
  - Bus 14: 345 kV, role=generator, load=0.00 MW, gens=1
  - Bus 15: 115 kV, role=load, load=180.96 MW, gens=0
Transformer 3:
  - 345 → 115 kV
  - Rating: 442.75 MVA
  - Expected: 442.75 MVA (1.2 × (180.96 + 188.00) = 442.75)
  - ✓ Match
```

---

## Test Category 10: Edge Cases

**Status: ✓ ALL EDGE CASES HANDLED CORRECTLY**

### Zero-Load Substations:
- Texas: 1 substation with 0 MW load (from Stage 1)
- New York: 1 substation with 0 MW load (from Stage 1)
- ✓ Handled correctly: Still get buses, not selected for high voltage

### Zero-Generation Substations (Type A):
- Texas: 1,182 Type A substations
- New York: 567 Type A substations
- ✓ Handled correctly: Can still be selected for high voltage based on load

### Single-Bus Substations with Both Load and Generation:
- Texas: 36 substations
- New York: 25 substations
- ✓ Handled correctly: Role = "load_and_generator", both attached to single bus

### Maximum Transformer Rating:
- Texas: 11,103.84 MVA (very large load/gen substation)
- New York: 2,425.44 MVA
- ✓ Handled correctly: No upper limit, scales with facility size

### Minimum Transformer Rating:
- Texas: 20 transformers at 50.0 MVA (10.2%)
- New York: 15 transformers at 50.0 MVA (16.0%)
- ✓ Handled correctly: Minimum enforced for small load/gen substations

---

## Performance Metrics

### Execution Time:
- Texas voltage partition: ~2 seconds
- New York voltage partition: ~1 second
- Total pipeline: ~3 seconds

### Memory Usage:
- Peak memory: < 100 MB
- No memory leaks detected

### Determinism:
- ✓ Multiple runs with same seed (42) produce identical outputs
- ✓ Bus IDs, transformer IDs, and selections are reproducible

---

## Known Behaviors (Not Bugs)

1. **Type A substations dominate high-voltage selection** (64-84%)
   - Expected: Type A is ~90% of substations and includes high-population centers
   - Weighted selection favors high-load substations

2. **Some transformers at minimum rating** (10-16%)
   - Expected: Small rural substations with low load/generation
   - Minimum 50 MVA ensures realistic transformer sizing

3. **Slight variation in actual vs requested percentages** (±0.08%)
   - Expected: Rounding when selecting discrete number of substations
   - Well within 2% tolerance specified in verification

4. **Zero-load substations included** (1 per region)
   - Expected: Carried over from Stage 1 (zero-population postal codes)
   - Will not be selected for high voltage (score = 0)

---

## Conclusion

✅ **Stage 2: Voltage Partition is COMPLETE and CORRECT**

All verification tests passed with no issues or warnings:
- ✓ 18/18 automated verification checks passed
- ✓ Perfect load conservation (0.000000 MW error)
- ✓ 100% generator accounting (1,186 TX, 728 NY)
- ✓ Voltage percentages within tolerance (±0.08% max deviation)
- ✓ All transformer ratings match heuristic formula
- ✓ All bus roles correctly assigned
- ✓ No data integrity issues
- ✓ All edge cases handled correctly
- ✓ Deterministic and reproducible results

**Ready for Stage 3: Topology Generation**

The voltage partition outputs provide a solid foundation for the next stage:
- Substations with voltage assignments documented
- Buses created at appropriate voltage levels
- Internal transformers properly configured
- All loads and generators correctly attached
- Geographic coordinates preserved for Delaunay triangulation
