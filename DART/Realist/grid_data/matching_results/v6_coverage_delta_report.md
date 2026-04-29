# V6 Coverage Delta Report

Generated: 2026-02-25 03:08:02 UTC

## Core Coverage Delta

| Metric | V5 | V6 | Delta |
|---|---|---|---|
| Total substations | 4954 | 4954 | +0 |
| Rows with OSM ID | 1144 | 1302 | +158 |
| Rows with OSM ID (%) | 23.09% | 26.28% | +3.19% |
| High/Medium rows | 2492 | 2492 | +0 |
| High/Medium rows with OSM ID | 1144 | 1302 | +158 |

## LMP Snapshot Coverage Delta

Latest SCED timestamp in `OIM/data/lmp_test.csv`: `2026-02-16 13:05:18-06:00`

| Metric | V5 | V6 | Delta |
|---|---|---|---|
| Unique substations represented in latest Resource Node LMP snapshot | 737 | 737 | +0 |
| Those substations with OSM ID | 131 | 262 | +131 |
| LMP substation OSM coverage (%) | 17.77% | 35.55% | +17.77% |

## Step Outputs

- Crosswalk rows written: **1002** -> `data/processed/ercot_crosswalk_v1.csv`
- Auto-accepted strict snaps: **158**
- Review queue rows (1-2 km): **28** -> `OIM/FirstPass/texas_matched_substations_v6_snap_review.csv`

## Auto-Accepted by Original Source

| Original Source | Count |
|---|---|
| eia860 | 76 |
| mora_eia860 | 82 |
