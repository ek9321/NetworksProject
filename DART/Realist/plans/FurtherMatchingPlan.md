# Further Matching Plan: Using MORA to Improve ERCOT Settlement Point Geolocation

## What We Have and What We're Trying to Do

The current `OIM/match_nodes.py` pipeline geolocates 4,954 unique ERCOT settlement point substations using three sources: EIA-860 plant coordinates, OSM substation names, and topology propagation. Only 1,280 (26%) are matched at medium-to-high confidence. The remaining 3,674 fall back to propagation from sibling nodes or a load zone centroid — which is geographically near-useless.

The MORA April 2026 report (`MORA_April2026_unit_capacities.csv`) introduces a new naming layer. The question is where it overlaps with and complements what we already have.

---

## Naming System Rosetta Stone

Understanding how these systems encode the same physical asset is the foundation of any improvement.

### ERCOT Settlement Point systems

| Field | Where | Example | Encodes |
|---|---|---|---|
| `SUBSTATION` | SP list | `WAP` | Abbreviated substation name — the primary key for the matching problem |
| `PSSE_BUS_NAME` | SP list | `WAP_WAP_G5` | PSS/E bus name: usually `SUB_SUBUNITID` |
| `RESOURCE_NODE` | SP list / RNU table | `WAP_WAP_G5_RN` | Market resource node: usually `PSSE_BUS_NAME + _RN` |
| `NODE_NAME` | SP list | `0001` | Electrical node group (used for topology propagation) |
| `ELECTRICAL_BUS` | SP list | `0001VICTOR` | Unique settlement bus identifier |

### MORA fields

| Field | Example | Encodes |
|---|---|---|
| `unit_name` | `W A PARISH U5` | Human-readable plant unit name |
| `unit_code` | `WAP_WAP_G5` | Almost always identical to `PSSE_BUS_NAME` |
| `inr` | `21INR0210` | ERCOT interconnection request number (planned/recent resources only) |
| `county` | `FORT BEND` | Texas county — geographic anchor |
| `zone` | `HOUSTON` | ERCOT load zone (NORTH/SOUTH/HOUSTON/WEST/COASTAL/PANHANDLE) |
| `fuel` | `COAL` | Fuel type — useful for validation |
| `in_service` | `1977` | In-service year |

### The key structural finding

**MORA `unit_code` == ERCOT `PSSE_BUS_NAME` in the majority of cases.**

From the analysis:
- 295 MORA `unit_code` values are direct exact matches to `PSSE_BUS_NAME` in the SP table
- 1,139 MORA `unit_code` values have a first segment (before the first `_`) that is an ERCOT `SUBSTATION` name
- Only 341 MORA entries have unit_codes where neither pattern applies — these use multi-word abbreviations like `B_DAVIS` (Barney Davis), `FRONT_EC` (Frontera Energy Center), `LEON_CRK` (Leon Creek), `NUECES_B` (Nueces Bay)

This means MORA is effectively a lookup table that maps PSSE bus names to county, zone, fuel, and in-service year for the entire ERCOT generation fleet.

---

## What MORA Can and Cannot Fix

### What it can fix

**Generation-side substations with bad matches.** MORA covers all operational generators. Any ERCOT substation that hosts generation should appear in MORA. If that substation is currently matched at medium confidence or propagated, the MORA county field is a free geographic validation. If the OSM-matched location is in the wrong county, that's a flag for manual review or rejection.

**Upgrading propagated matches to county-level geographic anchoring.** Currently, 3,010 substations are "propagated" — they inherit coordinates from a sibling node. If the substation is a generator substation, MORA tells us the county, which is a much tighter constraint than the LZ centroid but doesn't give lat/lon directly.

**Validating existing medium-confidence matches.** For all 450 medium-confidence matches (EIA-860 + OSM), the MORA county is a cross-check. If the current matched lat/lon falls in the wrong Texas county, that match should be flagged for review.

**Fuel-type disambiguation.** Some ERCOT substation names are ambiguous (multiple OSM candidates). MORA's fuel type can break ties — a substation marked `GAS-CC` shouldn't match an OSM solar farm.

### What it cannot fix

**Load substations.** The majority of unmatched substations are pure load nodes — no generation, so absent from MORA. MORA is a generation-only registry. The 74% problem is largely a load substation problem. MORA helps with the generator-hosting subset of that 74%.

**Novel naming structures.** The 341 MORA entries where the unit_code first segment isn't an ERCOT substation (e.g. `B_DAVIS`, `PANDA_S`) likely correspond to substations whose ERCOT abbreviated name was derived from a different word in the plant name. These require the unit_name route instead.

---

## Proposed New Passes

### Pass 3.5: MORA County Validation of Existing Matches

**Where it fits:** Between the existing match output and any downstream use.

**Algorithm:**
1. For each medium-confidence OSM or EIA-860 match in `texas_matched_substations.csv`, look up whether the substation name appears as the first segment of any MORA `unit_code`
2. If it does, resolve the county (MORA `county`) to an approximate centroid using the Census Gazetteer county centroids (already loaded in `ingest/census.py`)
3. Compute distance between the current matched lat/lon and the county centroid
4. Flag matches where the distance exceeds 80 km (roughly the diameter of a Texas county) as `county_mismatch`

**Expected output:** A flagged subset of current medium-confidence matches to review. Some fraction will turn out to be false positives that should be dropped or downgraded.

### Pass 4: MORA Unit Name → OSM Matching

**Where it fits:** Run after Pass 2 (OSM matching), on substations that are still unmatched.

**The problem with Pass 2:** It matches the ERCOT abbreviated substation name (`FRONT_EC`) against OSM names. The OSM name might be `Frontera Energy Center Substation`. The abbreviation and the full name don't fuzzy-match well.

**Algorithm:**
1. For MORA entries whose `unit_code` first segment did NOT match an ERCOT substation (the 341 "miss" cases), use the MORA `unit_name` as an additional candidate name
2. MORA `unit_name` → canonicalize → fuzzy match against OSM substation names (same ensemble scorer as Pass 2)
3. Apply county geographic constraint: only accept OSM matches that fall in the same Texas county as MORA records
4. If match found, link back to ERCOT substation via the SP table's `PSSE_BUS_NAME` → `SUBSTATION` join (using the MORA `unit_code` as the PSSE bridge)

**Key advantage:** The county constraint from MORA dramatically reduces false positives. Instead of searching all of Texas, we search only OSM substations in Nueces County for `NUECES BAY CTG 8`.

**Expected yield:** The 341 misses span real substations. A reasonable fraction will have an OSM entry with a name close to the MORA unit_name. Rough estimate: 50–150 new matches.

### Pass 5: MORA Unit Code → PSSE Bridge → Substation Coordinates

**Where it fits:** Parallel to Pass 4 — a structural join, not fuzzy matching.

**Algorithm:**
1. Join MORA `unit_code` → SP table `PSSE_BUS_NAME` (exact match — 295 hits confirmed)
2. For each hit, resolve `PSSE_BUS_NAME` → `SUBSTATION` via the SP table
3. Now we have: `MORA unit_code` → `SUBSTATION`, plus MORA `county`, `zone`, `fuel`, `unit_name`
4. For any substation currently at `lz_centroid` confidence that appears in this join, use the county centroid as the geographic anchor — a major improvement over the LZ centroid

**Note:** This doesn't give a precise lat/lon — it gives a county. The county centroid lookup (using Census Gazetteer data) is much better than an LZ centroid. Counties in Texas average ~2,600 sq km vs load zones of ~250,000 sq km.

**Expected yield:** Substations currently at `lz_centroid` that host generation — some portion of the 9 already identified, potentially more via the 295-entry exact join set.

### Pass 6: MORA Unit Name → EIA-860 Name (Enhanced Pass 1)

**Where it fits:** Supplementary to the existing Pass 1.

**Observation:** The existing Pass 1 matches ERCOT abbreviated substation names against EIA-860 plant names. The abbreviated names (e.g. `FRONT_EC`) don't fuzzy-match `Frontera Energy Center` well. But the MORA `unit_name` (`FRONTERA ENERGY CENTER CTG 1`) is much closer to EIA-860's `Frontera Energy Center`.

**Algorithm:**
1. For each MORA entry, canonicalize `unit_name` using the same `canonicalize()` function
2. Match against the EIA-860 plant name index (same `ensemble_score()` as Pass 1)
3. Apply the MORA county as a geographic constraint — EIA-860 has plant-level lat/lon, reject matches outside the expected county
4. If matched, link: MORA `unit_code` → EIA-860 plant → lat/lon → ERCOT `SUBSTATION` via SP table

**Key advantage over current Pass 1:** The MORA unit_name removes the abbreviation problem. "FRONTERA ENERGY CENTER CTG 1" vs "Frontera Energy Center" scores far higher than "FRONT_EC" vs "Frontera Energy Center".

**Expected yield:** Most significant for the 341 MORA entries with multi-word-abbreviated unit_codes. Some fraction will match EIA-860, and from there give lat/lon for the substation.

### Pass 7: INR → ERCOT Interconnection Queue Data

**Where it fits:** Specifically for the 491 MORA entries with INR numbers (planned and recently-commissioned resources).

**Background:** ERCOT publishes the Generator Interconnection Status Report, which lists interconnection requests by INR number with county, TSP (transmission service provider), and sometimes substation name. This is public data, updated monthly.

**Algorithm:**
1. Fetch/scrape the current ERCOT Generator Interconnection Status Report
2. Join on INR number → county, substation name, TSP
3. For MORA entries with INR numbers, use the interconnection report's substation name as an additional candidate for OSM and EIA-860 matching
4. County + substation name from the interconnection report, matched against OSM, gives lat/lon with geographic validation built in

**Expected yield:** Planned resources are the hardest to geolocate because they may not exist yet in OSM or EIA-860. But the interconnection report gives the proposed substation, which may already exist and be in OSM.

---

## Validation Strategy

### Price correlation check (internal consistency)

After any new matching pass, run the correlation test described in the README:

1. Pull 30 days of 5-minute SCED prices for all settlement points
2. Compute pairwise price correlation for all matched substation pairs
3. Plot correlation vs geographic distance for the new matches
4. Expect: high correlation for nearby substations, low for distant ones
5. Outliers (high correlation but far apart, or low correlation but close) are likely matching errors

### County cross-check (external validation)

For all matches at medium-or-better confidence where MORA provides a county:
- If matched lat/lon is not in the MORA county, flag as `suspect`
- These are candidates for manual review

### Fuel-type plausibility check

For OSM-matched substations, OSM sometimes records the `power` tag or `voltage` tag but not fuel. For the subset where MORA gives fuel:
- A substation matched to an OSM `substation=converter` node but classified as `GAS-CC` in MORA is suspicious
- These edge cases are rare but worth checking

---

## Implementation Order

1. **Pass 3.5** — county validation of existing matches (pure analysis, no new code paths needed, reuses existing data)
2. **Pass 5** — MORA `unit_code` → PSSE bridge → county centroid upgrade (structural join, highest confidence output)
3. **Pass 6** — MORA `unit_name` → EIA-860 enhanced matching (builds on existing Pass 1 infrastructure)
4. **Pass 4** — MORA `unit_name` → OSM matching with county constraint (builds on existing Pass 2 infrastructure)
5. **Pass 7** — INR → interconnection queue (requires fetching new data source)

Passes 3.5 through 6 all use data we already have in the repo. Pass 7 requires a new data fetch but is the most powerful for planned resources.

---

## File Dependencies

| Input | Source |
|---|---|
| `ERCOT/MORA_April2026_unit_capacities.csv` | Extracted in this session |
| `SP_List_EB_Mapping/Settlement_Points_01292026_104938.csv` | Existing |
| `SP_List_EB_Mapping/Resource_Node_to_Unit_01292026_104938.csv` | Existing |
| `OIM/FirstPass/texas_matched_substations.csv` | Output of current `match_nodes.py` |
| `OIM/data/texas_substations.geojson` | Existing (OSM) |
| `data/eia8602023/2___Plant_Y2023.xlsx` | Existing (EIA-860) |
| Census county centroids | Derivable from `data/raw/` Census Gazetteer or hardcoded |
| ERCOT GIS interconnection queue | Fetch from ERCOT public portal (Pass 7 only) |

---

## Realistic Expectations

The 74% unmatched problem is primarily a load substation problem. MORA does not cover load substations. The most it can do for generator-adjacent substations is:

- Validate or correct existing medium-confidence matches
- Provide county-level geographic anchoring where lat/lon is currently unknown
- Bridge the multi-word abbreviation problem for names like `B_DAVIS` and `FRONT_EC`

A realistic outcome from Passes 3.5–6 is upgrading perhaps 200–400 substations from `lz_centroid` or `propagated` to `county_centroid` confidence, and potentially recovering 50–150 new direct lat/lon matches via the enhanced EIA-860 and OSM passes. The remaining ~2,500 load substations require either:
- A different data source entirely (ERCOT's own geographic reference, not public)
- Utility-specific GIS data from Oncor, CenterPoint, AEP, etc. (mixed availability)
- Manual geocoding of the highest-volume substations
