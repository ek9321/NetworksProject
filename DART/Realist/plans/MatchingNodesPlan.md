# Matching ERCOT Settlement Nodes to Geographic Coordinates

## Objective

Geolocate ERCOT's ~4,954 unique substations (from `Settlement_Points`) by matching them against two coordinate-bearing datasets:
1. **OSM substations** — 5,786 substations inside Texas (3,802 transmission-tagged), fetched via Overpass API, each with lat/lon and an OSM name.
2. **EIA-860 plants** — Power plant locations with lat/lon, plant code, balancing authority, and grid voltage. Generators link back to plants via `plant_code`.

The settlement point data has **no coordinates** — only substation abbreviations (e.g., `PRSPERO2`, `LOOKOUT`, `DOWGEN`), PSS/E bus names (e.g., `L_BUCKRA8_1Y`), voltage levels, and load zone assignments. The matching problem is essentially: *given an abbreviated substation name, find its real-world location.*

---

## Data Inventory

| Dataset | Records | Has Coords | Key Fields |
|---|---|---|---|
| ERCOT Settlement_Points | 18,991 rows, 4,954 unique substations | No | SUBSTATION, PSSE_BUS_NAME, VOLTAGE_LEVEL, SETTLEMENT_LOAD_ZONE |
| ERCOT Resource_Node_to_Unit | 1,584 rows | No | RESOURCE_NODE, UNIT_SUBSTATION, UNIT_NAME |
| OSM Substations (Texas) | 5,786 (3,802 transmission) | Yes | name, voltage_kv, operator, lat, lon |
| EIA-860 Plants (Texas) | ~600 in TX with ERCOT BA | Yes | plant_code, lat, lon, grid_voltage_kv, balancing_authority |
| EIA-860 Generators (Texas) | ~2,000+ operational in TX | Yes (via plant) | plant_code, generator_id, nameplate_capacity_mw, technology |

---

## Matching Strategy

Three passes, each building on the previous:

### Pass 1: EIA-860 Generator → ERCOT Resource Nodes (High Confidence)

**Rationale:** ERCOT resource nodes often encode the plant name (e.g., `VICTORIA_CC1` → Victoria plant). EIA-860 generators have exact coordinates and plant names.

**Method:**
1. Load EIA-860 plants filtered to `balancing_authority == "ERCO"` (ERCOT's BA code).
2. Load `Resource_Node_to_Unit` — this maps resource nodes to unit substations.
3. Load `Settlement_Points` — this maps substations to electrical buses and has a `RESOURCE_NODE` column (populated for generator buses).
4. For each ERCOT resource node with a non-empty `RESOURCE_NODE` in Settlement_Points:
   - Extract the base name (strip suffixes like `_RN`, `_ALL`, `_CC1`, `_UNIT1`).
   - Fuzzy match against EIA-860 plant names (from the `2___Plant_Y2023.xlsx` "Plant Name" column — we'll need to read this directly since `PlantRecord` doesn't store the name).
   - Score using `rapidfuzz.fuzz.token_sort_ratio` or similar.
   - Accept matches above a threshold (e.g., 85).
5. For matched plants, assign the EIA-860 lat/lon to the ERCOT substation.

**Expected yield:** Most large generators (natural gas, nuclear, coal, large wind/solar) should match. Probably 300–500 substations geolocated.

### Pass 2: OSM Substation Name → ERCOT Substation Name (Medium Confidence)

**Rationale:** OSM substation names are often the full human-readable name (e.g., "Prospero Switching Station"), while ERCOT uses abbreviations (e.g., `PRSPERO2`). Fuzzy matching with spatial consistency checks can bridge this.

**Method:**
1. For each OSM substation with a non-empty `name`:
   - Normalize: uppercase, strip "Substation", "Switching Station", "SS", punctuation.
   - Generate candidate abbreviations (first N chars, consonant skeletons, etc.).
2. For each unmatched ERCOT substation:
   - Normalize the abbreviation similarly.
   - Compute fuzzy similarity against all OSM candidate names.
   - Use `VOLTAGE_LEVEL` as a secondary filter — OSM substations often have voltage tags that should be consistent.
   - Use `SETTLEMENT_LOAD_ZONE` as a geographic sanity check — e.g., LZ_HOUSTON substations should be near Houston.
3. Accept matches above threshold with voltage consistency.

**Refinements:**
- Define bounding boxes for each ERCOT load zone (LZ_HOUSTON, LZ_NORTH, LZ_SOUTH, LZ_WEST) to reject geographic outliers.
- For OSM substations without names but with `ref` tags, try matching against ERCOT bus names.

**Expected yield:** Potentially 1,000–2,000 additional substations, but with higher false-positive risk.

### Pass 3: Spatial Proximity Backfill (Lower Confidence)

**Rationale:** After Passes 1–2, some matched substations can anchor nearby unmatched ones.

**Method:**
1. For each unmatched ERCOT substation that shares a PSS/E bus number range or electrical bus prefix with a matched substation, infer approximate location.
2. Use ERCOT's topology: buses connected by the same `NODE_NAME` in Settlement_Points likely share a substation location. If one bus in the node is matched, propagate coordinates to siblings.
3. For remaining unmatched substations, use load zone centroids as a fallback (low precision, but ensures coverage).

**Expected yield:** Fill in most remaining gaps with varying precision.

---

## Implementation Plan

### File: `OIM/match_nodes.py`

```
Step 1: Load all datasets
  - ERCOT Settlement_Points CSV
  - ERCOT Resource_Node_to_Unit CSV
  - OSM substations GeoJSON (texas_substations.geojson)
  - EIA-860 plants (2___Plant_Y2023.xlsx, including Plant Name column)

Step 2: Pass 1 — EIA-860 generator matching
  - Filter EIA plants to BA == "ERCO"
  - Read Plant Name from Excel directly (not via existing PlantRecord which omits it)
  - Build ERCOT resource node → substation lookup
  - Fuzzy match resource node names to EIA plant names
  - Output: matched_substations dict {ercot_sub_name: (lat, lon, source, confidence)}

Step 3: Pass 2 — OSM name matching
  - Load named OSM substations (4,220 have names)
  - Normalize both OSM names and ERCOT substation names
  - Fuzzy match with voltage + load zone geographic constraints
  - Append new matches to matched_substations

Step 4: Pass 3 — Topology propagation
  - Group Settlement_Points by NODE_NAME
  - If any bus in a node group has a matched substation, propagate to siblings
  - Assign load zone centroids to any remaining unmatched

Step 5: Export results
  - Save OIM/data/texas_matched_substations.csv:
      columns: ercot_substation, lat, lon, match_source (eia860/osm/propagated/zone_centroid),
               confidence_score, osm_name, eia_plant_code, voltage_kv, load_zone
  - Save OIM/data/texas_matched_substations.geojson for plotting

Step 6: Summary statistics
  - Print match rates by pass and by load zone
  - Print confidence distribution
```

### File: `OIM/plot_matched_nodes.py`

```
- Load matched substations GeoJSON
- Plot on the existing Texas HV lines + boundary map
- Color-code by match source:
    Green  = EIA-860 match (Pass 1)
    Blue   = OSM match (Pass 2)
    Orange = Topology propagation (Pass 3)
    Gray   = Load zone centroid fallback
- Size points by voltage level
- Show match statistics in a text box on the plot
```

---

## Dependencies

- `rapidfuzz` — for fuzzy string matching (`pip install rapidfuzz`)
  - Alternative: `thefuzz` or stdlib `difflib.SequenceMatcher` (slower but zero-install)
- `pandas` — already available
- `openpyxl` — already available (for Excel reading)

---

## Known Challenges

| Challenge | Mitigation |
|---|---|
| ERCOT abbreviations are cryptic (e.g., `CNPOI`, `MRSDO`) | Use consonant skeleton matching + multiple strategies |
| OSM names vary in format ("XYZ Substation" vs "XYZ SS" vs just "XYZ") | Normalize aggressively before matching |
| Many ERCOT substations are distribution-level (13.8 kV) with no OSM equivalent | Accept that distribution subs may only match via topology propagation |
| EIA-860 has plants, not substations — a plant may connect to a substation with a different name | Use Resource_Node_to_Unit as the bridge; also try matching PSSE_BUS_NAME |
| Multiple ERCOT substations may map to the same physical location (different voltage buses) | Group by NODE_NAME first; one coordinate per physical site |
| OSM data quality varies — some substations mislocated or misnamed | Cross-validate with voltage consistency |

---

## Success Metrics

| Metric | Target |
|---|---|
| Pass 1 match rate (generator substations) | >70% of resource-node substations |
| Pass 2 match rate (OSM name match) | >30% of remaining substations |
| Overall geolocated substations | >50% of 4,954 unique substations |
| Geographic consistency (matched sub in correct load zone) | >95% |

---

## Output Files

```
OIM/
  match_nodes.py                           ← matching logic
  plot_matched_nodes.py                    ← visualization
  data/
    texas_matched_substations.csv          ← all matches with metadata
    texas_matched_substations.geojson      ← for plotting
    texas_match_report.txt                 ← summary statistics
  output/
    texas_matched_nodes.png                ← map visualization

    
```

### Immediate improvements 

Conservative thresholds + triage tiers

Use three acceptance bands: high (score ≥ 90) auto-accept, medium (75–90) accept but flag for sampling/manual review, low (<75) reject/hold. This prevents silent false positives.

Blocking to avoid O(N×M) blowup

Pre-block by: load zone, voltage bucket (±10kV), first 3 chars or consonant skeleton. Only run fuzzy on candidates in the same block.

Robust normalizer

Build one canonicalizer: uppercase, remove words (SUBSTATION, SWITCH, SS, STN, PLANT, GEN, punctuation), expand known abbreviations map (e.g., STN→STATION), collapse whitespace, strip digits-only suffixes (_2, A).

Multiple scorers and ensemble

Compute token_set_ratio, token_sort_ratio, and a normalized Jaro-Winkler / edit distance. Combine (e.g., mean or weighted) — this reduces edge cases where one scorer misleads.

Use PSSE bus names & Resource_Node_to_Unit as extra evidence

Treat matches on PSSE_BUS_NAME or UNIT_NAME as a strong signal (higher weight) even if plant-name fuzzy score is lower.