# HV Matching Results (Passes 9A & 9B)

## Before vs After

| Source | V3 Count | V4 Count | Change |
|---|---|---|---|
| eia860 | 241 | 241 | +0 |
| gnis | 929 | 929 | +0 |
| hv_endpoint | 0 | 223 | +223 |
| hv_osm_345 | 0 | 27 | +27 |
| lz_centroid | 490 | 477 | -13 |
| mora_county_centroid | 5 | 5 | +0 |
| mora_eia860 | 178 | 178 | +0 |
| mora_ix_queue | 8 | 8 | +0 |
| mora_osm | 35 | 35 | +0 |
| osm | 1039 | 1039 | +0 |
| propagated | 2029 | 1792 | -237 |

**Total substations:** 4954 → 4954

## Confidence Summary

| Confidence | V3 | V4 | Change |
|---|---|---|---|
| high | 1546 | 1562 | +16 |
| medium | 884 | 895 | +11 |
| low | 2034 | 2020 | -14 |
| none | 490 | 477 | -13 |

## Pass 9A — PSSE Name → 345 kV OSM Matching

- Attempted: **319** unresolved 345 kV substations
- New matches: **27**
  - High confidence (≥90): 16
  - Medium confidence (80–89): 11

### All new 9A matches

| Substation | OSM Name | Score | Confidence |
|---|---|---|---|
| BOMSW | Bowman Substation | 100.0 | high |
| KG | King Substation | 100.0 | high |
| MARANA | Marana Switchyard | 100.0 | high |
| NUCOR | Nucor Substation | 100.0 | high |
| OAS | Oasis Substation | 100.0 | high |
| PC_NORTH | Panther Creek Wind 1 Substation | 100.0 | high |
| TNP_ONE | TNP One Substation | 100.0 | high |
| W_FD_345 | Faraday Substation | 100.0 | high |
| W_GT_345 | Grelton Substation | 100.0 | high |
| ZEN | Zenith Substation | 100.0 | high |
| BNDVS | Ben Davis Substation | 95.1 | high |
| TKWSW | Tonkawa Substation | 94.6 | high |
| PC_SOUTH | Panther Creek Wind 3 Substation | 94.5 | high |
| ADK | Addicks Substation | 93.5 | high |
| CTLSW | Corn Trail Switching Station | 91.0 | high |
| SHBSW | Shamburger Substation | 91.0 | high |
| LHORN_N | Longhorn Wind Substation | 86.0 | medium |
| GDLSW | Inadale Wind Farm Substation | 85.5 | medium |
| JN | Jeanetta Substation | 85.3 | medium |
| GIBCRK | Gibbons Creek Station | 85.1 | medium |
| RTW | Rothwood Substation | 84.8 | medium |
| WLFSW | Wolf Switching Station | 84.0 | medium |
| TOKSW | Twin Oaks Substation | 83.7 | medium |
| SUNVASLR | Valley Switching Station (345 kV) | 83.6 | medium |
| SNG | Singleton Substation | 83.0 | medium |
| PANDA_T1 | Panda Temple 1 Substation | 81.9 | medium |
| MDSSW | Midessa South Substation | 81.0 | medium |

## Pass 9B — 345 kV Line Endpoint Clustering

- Raw 345 kV+ endpoints extracted: **10,170**
- Endpoint clusters (≥2 converging lines): **1,349**
- New geographic anchors assigned: **223** (source: `hv_endpoint`, confidence: `low`)

  These substations remain unresolved by name but now have a geographic position
  anchored to the nearest cluster of 345 kV line endpoints within 75 km of the load zone.
  This replaces the propagated/lz_centroid fallback for 345 kV generation-side nodes.

**Still unresolved after both passes:** 2269
