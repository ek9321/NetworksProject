# First Pass: ERCOT Node Matching Report

## Executive Summary

Attempted to geolocate **4954** unique ERCOT substations from the Settlement Point to Electrical Bus mapping.

- **241** matched via EIA-860 plant names (Pass 1)
- **1039** matched via OSM substation names (Pass 2)
- **3010** propagated from matched siblings (Pass 3)
- **664** assigned load zone centroid (fallback)

**Total geolocated: 4954/4954 (100.0%)**

**High-quality matches (EIA-860 + OSM, confidence ≥ medium): 1280** (25.8% of total substations)

## Confidence Breakdown

| Confidence | Count | % of Total |
|---|---|---|
| high | 830 | 16.8% |
| medium | 450 | 9.1% |
| low | 3010 | 60.8% |
| none | 664 | 13.4% |

## Match Source × Confidence

| Source | High | Medium | Low | None | Total |
|---|---|---|---|---|---|
| eia860 | 98 | 143 | 0 | 0 | 241 |
| osm | 732 | 307 | 0 | 0 | 1039 |
| propagated | 0 | 0 | 3010 | 0 | 3010 |
| lz_centroid | 0 | 0 | 0 | 664 | 664 |

## Matches by Load Zone

| Load Zone | EIA-860 | OSM | Propagated | Centroid | Total |
|---|---|---|---|---|---|
| LZ_HOUSTON | 11 | 30 | 488 | 24 | 553 |
| LZ_NORTH | 57 | 137 | 1184 | 295 | 1673 |
| LZ_SOUTH | 87 | 578 | 552 | 131 | 1348 |
| LZ_WEST | 86 | 294 | 786 | 214 | 1380 |

## Sample Matches

### EIA860 matches (top 20 by score)

| ERCOT Sub | Matched Name | Score | Confidence |
|---|---|---|---|
| ALVIN | Alvin | 100.0 | high |
| ANGLETON | Angleton | 100.0 | high |
| ASTRA | Astra Wind Farm | 100.0 | high |
| AUSTIN | Austin | 100.0 | high |
| AVIATOR | Aviator Wind | 100.0 | high |
| BAFFIN | Baffin Wind | 100.0 | high |
| BAKKE | Bakke | 100.0 | high |
| BRAZORIA | Brazoria | 100.0 | high |
| BRISCOE | Briscoe Wind Farm | 100.0 | high |
| CANYON | Canyon | 100.0 | high |
| CONIGLIO | Coniglio Solar | 100.0 | high |
| DANSBY | Dansby | 100.0 | high |
| DERMOTT | Dermott Wind | 100.0 | high |
| EDENS | Edens Solar | 100.0 | high |
| EL_CAMPO | El Campo Wind | 100.0 | high |
| FAULKNER | Faulkner | 100.0 | high |
| FLUVANNA | Fluvanna | 100.0 | high |
| FRONTERA | Frontera Energy Center | 100.0 | high |
| GALLOWAY | Galloway 1 Solar Farm | 100.0 | high |
| GANADO | Ganado Solar | 100.0 | high |

### OSM matches (top 20 by score)

| ERCOT Sub | Matched Name | Score | Confidence |
|---|---|---|---|
| ACACIA | Acacia Substation | 100 | high |
| ADERHOLD | Aderhold Substation | 100 | high |
| AFTON | Afton Substation | 100 | high |
| AIRLINE | Airline Substation | 100 | high |
| AIRPORT | Airport Substation | 100 | high |
| AJO | Ajo Switching Station | 100 | high |
| AJ_SWOPE | AJ Swope Substation | 100 | high |
| ALAZAN | Alazan Substation | 100 | high |
| ALBANY | Albany Substation | 100 | high |
| ALBERTA | Alberta Switching Station | 100 | high |
| ALCOA | Alcoa Substation | 100 | high |
| ALIBATES | Alibates Substation | 100 | high |
| ALICE | Alice Substation | 100.0 | high |
| ALLEN | Allen Switching Station | 100.0 | high |
| ALPINE | Alpine Substation | 100 | high |
| ALTAIR | Altair Substation | 100 | high |
| ALTUDA | Altuda Substation | 100 | high |
| AMOCO | Amoco Substation | 100 | high |
| ANDICE | Andice Substation | 100 | high |
| ANTLER | Antler Substation | 100 | high |

### Lowest-scoring accepted matches (for manual review)

| ERCOT Sub | Source | Matched Name | Score | Confidence |
|---|---|---|---|---|
| LILY | eia860 | Lily Solar Hybrid | 82.2 | medium |
| HILL_CO | eia860 | Hill County Generation Facility | 82.3 | medium |
| BELD | osm | Belding Substation | 82.3 | medium |
| CLEARCRO | osm | Clear Crossing Substation | 82.3 | medium |
| EOLATAP | osm | Eola Substation | 82.3 | medium |
| ESPU | osm | Espuela Substation | 82.3 | medium |
| KINGRNCH | osm | King Ranch Gas Plant Substation | 82.3 | medium |
| MERT | osm | Mertzon Substation | 82.3 | medium |
| PEAC | osm | Peacock Substation | 82.3 | medium |
| SHELTONS | osm | Shelton Street Substation | 82.3 | medium |
| SLAUGHTE | osm | Slaughter Lane Substation | 82.3 | medium |
| WEIN | osm | Weinert Substation | 82.3 | medium |
| WINT | osm | Winters Substation | 82.3 | medium |
| W_LD_138 | osm | West Uvalde Substation | 82.3 | medium |
| W_LD_345 | osm | West Uvalde Substation | 82.3 | medium |
| MIEL | osm | Milo Substation | 82.4 | medium |
| FOREST | eia860 | Forest Creek Wind Farm LLC | 82.6 | medium |
| MARIAH | eia860 | Mariah del Norte | 82.6 | medium |
| PISGAH | eia860 | Pisgah Ridge Solar, LLC | 82.6 | medium |
| TURKEY | eia860 | Turkey Track Wind Energy LLC | 82.6 | medium |

## Quality Assessment

### Changes from initial run

Three key filters were applied to clean the match set:

1. **Raised thresholds** — high ≥ 92 (was 90), medium ≥ 82 (was 75). This eliminated ~400 marginal matches.
2. **Structural validation** — reject matches where (a) ERCOT name ≤ 3 chars and score < 92, (b) first 2 characters don't match between canonical names, (c) large length-ratio mismatch (penalty). This killed garbage like KIMBRO → "East Blackland Solar".
3. **Resource node cross-check** — when a match comes through a resource-node alias (not the substation name directly), require the substation name's first character to match the plant name. This eliminated 31 false positives where ERCOT substations were incorrectly assigned to distant plants via shared resource node aliases (e.g., COBSW → "Shannon Wind", GRISSOM → "Cranell Wind Farm").

### Current quality

- **Bottom of the medium band looks reasonable.** Worst accepted matches: LILY → "Lily Solar Hybrid" (82.2), BELD → "Belding Substation" (82.3), EOLATAP → "Eola Substation" (82.3). These all have clear name correspondence.
- **No first-character mismatches remain** in EIA-860 matches (was 31).
- **Short-name (≤3 char) matches** — 14 survive, all either exact (AJO, DOW, ELY) or strong partial (FT → "Fort Bend"). A few borderline cases remain in medium (LK → "Lake Creek", PT → "Point Blank").

### What this gives us

**1,280 clean, directly geolocated ERCOT substations** (241 EIA-860 + 1,039 OSM) — roughly 26% of all 4,954. These span all four load zones and cover the major transmission substations across Texas.

### What's still missing

- **LZ_HOUSTON** has only 41 direct matches (7.4% of its 553 substations). Houston-area subs use highly abbreviated names that don't match OSM well.
- **LZ_NORTH** has the lowest direct match rate (198/1,673 = 11.8%). Many are rural co-op substations not in OSM.
- **3,674 substations (74%)** still rely on propagation or centroid fallback — these need a different approach (PSSE bus name parsing, utility-specific naming conventions, or manual geocoding of the top-volume substations).
