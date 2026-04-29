# MORA Matching Results (Passes 3.5 – 7)

## Before vs After

| Source | V1 Count | V2 Count | Change |
|---|---|---|---|
| eia860 | 241 | 241 | +0 |
| lz_centroid | 664 | 655 | -9 |
| mora_county_centroid | 0 | 5 | +5 |
| mora_eia860 | 0 | 178 | +178 |
| mora_ix_queue | 0 | 8 | +8 |
| mora_osm | 0 | 35 | +35 |
| osm | 1039 | 1039 | +0 |
| propagated | 3010 | 2793 | -217 |

**Total substations:** 4954 → 4954

## Pass 3.5 — County Validation

- Checked: **164** medium/high-confidence matches with MORA county data
- County-confirmed (within 100 km of MORA county centroid): **148**
- County-flagged (>100 km from MORA county centroid): **16**

### Flagged matches for review

| Substation | Source | Confidence | Score | Matched Name | MORA County | Dist (km) |
|---|---|---|---|---|---|---|
| AIRPRTRD | osm | medium | 87.8 | Airport Substation | MITCHELL | 247.8 |
| CALAVERS | osm | medium | 83.2 | Calvert Substation | BEXAR | 247.0 |
| CANYONWD | eia860 | medium | 88.5 | Canyon | SCURRY | 419.4 |
| COTTON | eia860 | medium | 85.7 | Cotton Plains Wind Farm | SAN PATRICIO | 764.7 |
| FORTMA | osm | medium | 84.7 | Formosa Substation | MASON | 345.2 |
| GARCENO | osm | high | 100 | Garceno Substation | MATAGORDA | 402.6 |
| HOUSEMTN | eia860 | medium | 83.6 | Houston Plant | BREWSTER | 792.4 |
| MARSFO | eia860 | medium | 84.0 | Mars Solar | TRAVIS | 340.9 |
| MESQUITE | eia860 | high | 92.0 | Mesquite Wind Power LLC | CAMERON | 741.3 |
| MONT | osm | high | 100 | Mont Substation | FOARD | 559.1 |
| MOORE | osm | high | 100 | Moore Substation | HIDALGO | 273.0 |
| PINEFRST | eia860 | medium | 85.6 | Pinecrest Energy Center | HOPKINS | 217.7 |
| RAYBURN | eia860 | medium | 91.2 | Rayburn Energy Station LLC | VICTORIA | 533.9 |
| SANDHSYD | osm | medium | 85.7 | Sandy Substation | TRAVIS | 188.7 |
| WAKEWE | eia860 | medium | 84.0 | Wake Wind Energy Center | DICKENS | 114.6 |
| WHTTAIL | eia860 | medium | 88.3 | Whitetail | COOKE | 700.0 |

## Passes 4, 6, 7 — New Direct Matches

- New direct lat/lon matches via MORA: **226**
  - Upgraded from lz_centroid: 9
  - Upgraded from propagated: 217

  - `mora_eia860`: 178
  - `mora_osm`: 35
  - `mora_ix_queue`: 8
  - `mora_county_centroid`: 5

### Sample new matches

| Substation | Source | Confidence | Score | Matched Name | MORA County |
|---|---|---|---|---|---|
| ABINDUST | mora_osm | high | 96.0 | Abilene Industrial Park Substation | TAYLOR |
| AE | mora_eia860 | medium | 90.5 | Angleton | BRAZORIA |
| AEEC | mora_osm | medium | 83.2 | Antelope Station Switchyard | HALE |
| AJAXWIND | mora_eia860 | medium | 83.7 | Western Trail Wind, LLC | WILBARGER |
| APPALOSA | mora_eia860 | high | 95.8 | Appaloosa Run Wind | UPTON |
| ATKINS | mora_osm | medium | 90.1 | Atkins Substation | BRAZOS |
| AUSTPL | mora_eia860 | medium | 87.0 | Austin | TRAVIS |
| BAIRDWND | mora_ix_queue | medium | 83.1 | Latimer Switchyard | CALLAHAN |
| BASTEN | mora_eia860 | medium | 91.2 | Bastrop Energy Center | BASTROP |
| BBREEZE | mora_eia860 | medium | 85.9 | Bruennings Breeze Wind Farm | WILLACY |
| BCATWIND | mora_eia860 | medium | 87.0 | Bobcat Bluff Wind Project LLC | ARCHER |
| BLACKJAK | mora_eia860 | high | 96.3 | Blackjack Creek Wind Farm | BEE |
| BLSUMIT3 | mora_eia860 | medium | 83.4 | Blue Summit Wind LLC | WILBARGER |
| BLUEJAY | mora_eia860 | high | 93.3 | Blue Jay Solar I, LLC | GRIMES |
| BR | mora_eia860 | medium | 88.8 | Bright Arrow Solar, LLC | HOPKINS |
| BRTSW | mora_eia860 | high | 100.0 | Barton Chapel Wind Farm | JACK |
| BTM | mora_eia860 | high | 92.9 | Brotman Power Station | BRAZORIA |
| BVE | mora_osm | high | 94.6 | Brazos Valley Substation | FORT BEND |
| BY | mora_osm | medium | 85.5 | Berry Substation | HARRIS |
| CAMWIND | mora_osm | medium | 87.0 | Cameron Wind Substation | CAMERON |
| CAPRIDG4 | mora_eia860 | high | 95.2 | Capricorn Ridge Wind LLC | STERLING |
| CAPRIDGE | mora_eia860 | high | 95.2 | Capricorn Ridge Wind LLC | STERLING |
| CARTWHL | mora_ix_queue | high | 94.2 | Sulphur Springs Switching Station | HOPKINS |
| CBEC | mora_eia860 | high | 94.6 | Colorado Bend Energy Center | WHARTON |
| CBECII | mora_eia860 | high | 95.5 | Colorado Bend II | WHARTON |
| CBY | mora_eia860 | high | 93.8 | Cedar Bayou | CHAMBERS |
| CBY4 | mora_eia860 | medium | 91.5 | Cedar Bayou | CHAMBERS |
| CFLATS | mora_eia860 | medium | 84.9 | Cactus Flats Wind Energy Project | CONCHO |
| CHIL | mora_ix_queue | high | 92.6 | Bell County Switching Station | BELL |
| CHISMGRD | mora_eia860 | medium | 85.8 | Chisholm Grid Energy Storage System | TARRANT |
| CISC | mora_eia860 | high | 100.0 | CISCO BESS | EASTLAND |
| CLO | mora_eia860 | high | 94.7 | Callisto I Energy Center | HARRIS |
| COTPLNS | mora_eia860 | high | 100.0 | Cotton Plains Wind Farm | FLOYD |
| COYOTSPR | mora_eia860 | medium | 87.5 | Coyote Springs (TX) | REEVES |
| CPSES | mora_eia860 | high | 95.8 | Comanche Peak | SOMERVELL |
| CR | mora_osm | medium | 90.5 | Crockett Substation | HARRIS |
| CS | mora_osm | medium | 88.4 | Crosby Substation | HARRIS |
| CSEC | mora_osm | high | 100.0 | Camp Springs Wind 2 Substation | SCURRY |
| CTW | mora_eia860 | high | 94.5 | Cottonwood Bayou Solar | BRAZORIA |
| DA | mora_osm | medium | 83.0 | Damon Substation | BRAZORIA |

## Pass 5 — County Centroid Upgrades

- Substations upgraded from lz_centroid → mora_county_centroid: **5**
  This replaces load-zone-level geographic fallback (~250,000 km²) with county-level (~2,600 km² average) anchoring.

## Confidence Summary

| Confidence | V1 | V2 | Change |
|---|---|---|---|
| high | 830 | 970 | +140 |
| medium | 450 | 531 | +81 |
| low | 3010 | 2798 | -212 |
| none | 664 | 655 | -9 |

