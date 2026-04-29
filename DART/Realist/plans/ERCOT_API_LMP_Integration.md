# Plan: ERCOT API / LMP Integration with OSM Network

## Goal

Assess the feasibility of pulling real ERCOT Locational Marginal Prices (LMPs) and connecting them to the geolocated OSM transmission network — producing a map where each settlement point shows actual market prices on the physical grid.

---

## Part 1: Data Access — Two Paths

### Path A: gridstatus (open-source Python library)

**What it is:** [gridstatus](https://github.com/gridstatus/gridstatus) is an open-source Python library (`pip install gridstatus`) that wraps ERCOT's public data feeds. It provides a clean Pandas-based interface for pulling market data.

**Key methods:**
```python
import gridstatus
ercot = gridstatus.ERCOT()

# Real-time LMPs (5-min SCED) by settlement point
ercot.get_lmp(date="today", location_type="SETTLEMENT_POINT")
# Returns: Time, Market, Location, Location Name, Location Type, LMP, Energy, Congestion, Loss

# Day-ahead market settlement point prices
ercot.get_spp(date="2024-01-15")

# Real-time settlement point prices (15-min)
ercot.get_spp(date="today", market="REAL_TIME_15_MIN")
```

**Authentication:** The base `gridstatus.ERCOT()` class scrapes ERCOT's public report pages — **no API key required** for current/recent data. For the ERCOT Data API wrapper (`gridstatus.ErcotAPI()`), you need ERCOT credentials (see Path B).

**Limitations:**
- Public scraping may be rate-limited or fragile if ERCOT changes page formats
- Historical depth depends on what ERCOT keeps publicly posted (typically 2-3 days of 5-min LMPs)
- For deep historical data, the ERCOT API (Path B) or bulk CSV downloads are needed

**Feasibility: HIGH.** Can pull current LMPs in minutes with zero setup.

### Path B: ERCOT Public API (direct)

**What it is:** ERCOT's official REST API ([apiexplorer.ercot.com](https://apiexplorer.ercot.com/)) built on Azure API Management. OpenAPI-compliant, returns JSON/XML.

**Registration (free):**
1. Go to [apiexplorer.ercot.com](https://apiexplorer.ercot.com/)
2. Register with email verification
3. Subscribe to "Public API" product
4. Get a Subscription Key (Ocp-Apim-Subscription-Key header)
5. Generate an ID token via POST (valid 1 hour, re-requestable)

**Key endpoints:**
| Endpoint | Data | Granularity |
|---|---|---|
| `/np6-788-cd/lmp_node_zone_hub` | RT LMP by settlement point | 5-min (SCED) |
| `/np6-787-cd/lmp_electrical_bus` | RT LMP by electrical bus | 5-min (SCED) |
| `/np6-905-cd/spp_node_zone_hub` | RT settlement point prices | 15-min |
| `/np4-190-cd/dam_spp` | Day-ahead settlement point prices | Hourly |
| `/np6-785-er/hb_lz_spp` | Historical RTM hub/LZ prices | Yearly archives |
| `/np4-180-er/hb_lz_dam` | Historical DAM hub/LZ prices | Yearly archives |

**Feasibility: HIGH.** Free registration, well-documented API, extensive historical data.

### Path C: Bulk CSV Downloads (no auth)

ERCOT publishes CSV/ZIP files directly at [ercot.com/mktinfo/prices](https://www.ercot.com/mktinfo/prices):
- DAM settlement point prices (NP4-190-CD): all nodes, daily files
- RT settlement point prices (NP6-905-CD): all nodes, daily files
- Historical hub/LZ compilations by year

**Feasibility: HIGH.** Zero setup. Good for one-off historical analysis.

### Recommended approach

Start with **Path A (gridstatus)** for rapid prototyping — pull a snapshot of current LMPs with 3 lines of code. Then register for **Path B** if we need deeper historical data or bus-level granularity. Use **Path C** for bulk historical analysis.

---

## Part 2: Connecting LMPs to the OSM Network

### The join problem

LMP data is keyed by **settlement point name** (e.g., `LZ_HOUSTON`, `HB_NORTH`, `VICTORIA_RN`, `0001`). Our matched substations map provides the bridge:

```
ERCOT Settlement Point  →  ERCOT Substation  →  Matched (lat, lon)  →  OSM Network
       (LMP data)            (SP mapping)        (FirstPass results)    (lines + subs)
```

### Step-by-step integration

**Step 1: Pull an LMP snapshot**
```
- Use gridstatus to get current 5-min LMPs for all settlement points
- Output: DataFrame with ~19,000 rows (one per settlement point per interval)
- Columns: settlement_point_name, location_type, lmp, energy, congestion, loss
```

**Step 2: Aggregate to substation level**
```
- Join LMP data to Settlement_Points CSV via NODE_NAME or ELECTRICAL_BUS
- Multiple electrical buses per substation → take the max-voltage bus LMP
  (or mean across buses, since LMPs at the same substation are typically close)
- Output: one LMP per substation
```

**Step 3: Join to geolocated substations**
```
- Inner join on ercot_substation name with FirstPass matched_substations.csv
- For the 1,280 directly matched substations: exact coordinates
- For propagated substations: inherited coordinates (lower precision)
- Drop centroid-only substations from the visualization
```

**Step 4: Map LMPs onto the OSM network**
```
- Plot OSM HV lines as background (gray)
- Color each geolocated substation by its LMP value
  - Use a diverging colormap (blue = low, white = mean, red = high)
  - Or a sequential colormap if all LMPs are positive
- Size points by voltage level
- Add contour/heatmap interpolation between points (optional)
```

**Step 5: Identify congestion patterns**
```
- LMP = Energy + Congestion + Loss components
- Plot congestion component separately to show transmission bottlenecks
- Overlay on the HV line network to see which corridors are constrained
```

---

## Part 3: What This Unlocks

### Immediate outputs
1. **LMP heatmap on real topology** — settlement point prices overlaid on the physical transmission network, showing where electricity is expensive vs cheap
2. **Congestion visualization** — where transmission constraints create price separation
3. **Time-lapse capability** — pull LMPs at multiple timestamps to animate price propagation

### Validation use cases
4. **Synthetic grid calibration** — compare Dartboard's synthetic DC power flow results against real ERCOT LMP patterns to validate topology realism
5. **Load zone boundary validation** — verify that our matched substations' load zone assignments align with LMP clustering patterns

### Future extensions
6. **Real-time dashboard** — periodically pull LMPs and update the map
7. **Historical congestion analysis** — identify persistent bottlenecks using months of LMP data
8. **Price-topology correlation** — test whether synthetic grid topology produces similar congestion patterns to the real grid

---

## Part 4: Implementation Plan

### File: `OIM/pull_lmp.py`

```
1. pip install gridstatus
2. Pull current 5-min LMPs via gridstatus.ERCOT().get_lmp()
3. Also pull DAM prices for comparison
4. Save raw DataFrames to OIM/data/lmp_snapshot_{timestamp}.csv
5. Aggregate to substation level using SP_List_EB_Mapping join
6. Save OIM/data/lmp_by_substation_{timestamp}.csv
```

### File: `OIM/plot_lmp_map.py`

```
1. Load LMP-by-substation data
2. Join to FirstPass matched_substations.geojson
3. Plot on Texas boundary + HV lines background
4. Color-code substations by LMP (diverging colormap)
5. Separate plot for congestion component
6. Save to OIM/output/
```

### File: `OIM/explore_ercot_api.py` (feasibility probe)

```
1. Test gridstatus.ERCOT() — pull LMPs, verify column names, check coverage
2. Test gridstatus.ErcotAPI() — check if auth works (if registered)
3. Compare settlement point names in LMP data vs SP_List_EB_Mapping
4. Report: how many LMP settlement points can we geolocate?
5. Save OIM/FirstPass/api_feasibility_report.txt
```

---

## Part 5: Feasibility Assessment Checklist

| Question | Status | Notes |
|---|---|---|
| Can we pull LMPs without credentials? | Likely YES | gridstatus scrapes public pages |
| Do settlement point names in LMP data match our SP mapping? | TO TEST | Names should be NODE_NAME or ELECTRICAL_BUS |
| How many LMP points can we geolocate? | TO TEST | Depends on join between LMP names and our 1,280 matched subs |
| Is gridstatus stable enough for repeated use? | TO TEST | Library scrapes HTML; may break |
| Can we get bus-level LMPs (not just settlement points)? | YES (with API key) | `/np6-787-cd/lmp_electrical_bus` |
| Can we get historical LMPs for time-series analysis? | YES | Bulk CSVs at ercot.com or via API |
| Is ERCOT API registration actually free? | Likely YES | Public API product, no pricing mentioned |

---

## Part 6: Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| gridstatus breaks due to ERCOT page changes | Can't pull data | Fall back to direct API (Path B) or CSV downloads (Path C) |
| Settlement point names in LMP data don't match our SP mapping | Can't join data | The SP mapping file IS the canonical name list — names should match exactly |
| Low match rate limits map coverage | Sparse visualization | Focus on hub/load zone aggregate prices as a baseline; bus-level prices for matched subs |
| ERCOT rate-limits or blocks scraping | Intermittent access | Register for official API; cache aggressively |
| LMP data volume is large for historical analysis | Storage/processing | Aggregate to 15-min or hourly; filter to matched substations only |

---

## Suggested First Experiment

**Minimum viable test (30 minutes):**

```bash
pip install gridstatus
python -c "
import gridstatus
ercot = gridstatus.ERCOT()
lmp = ercot.get_lmp(date='today')
print(lmp.columns.tolist())
print(f'Rows: {len(lmp)}')
print(lmp.head(10))
print(f'Unique locations: {lmp[\"Location\"].nunique()}')
lmp.to_csv('OIM/data/lmp_test.csv', index=False)
"
```

If this works, we immediately know:
1. Whether gridstatus can pull ERCOT data without auth
2. What the settlement point names look like in LMP data
3. How many unique locations we get
4. Whether those names match our SP_List_EB_Mapping

---

## References

- [ERCOT Market Prices](https://www.ercot.com/mktinfo/prices) — official price data hub
- [ERCOT API Explorer](https://apiexplorer.ercot.com/) — registration and API docs
- [ERCOT Developer Portal](https://developer.ercot.com/applications/pubapi/user-guide/registration-and-authentication/) — auth guide
- [gridstatus docs](https://opensource.gridstatus.io/en/latest/) — open-source Python library
- [gridstatus GitHub](https://github.com/gridstatus/gridstatus) — source code
- [GridStatus.io ERCOT LMP dataset](https://www.gridstatus.io/datasets/ercot_lmp_by_settlement_point) — hosted data explorer
- [NP6-788-CD: LMP by Settlement Point](https://www.ercot.com/mp/data-products/data-product-details?id=NP6-788-CD) — ERCOT data product spec
- [NP4-190-CD: DAM Settlement Point Prices](https://www.ercot.com/mp/data-products/data-product-details?id=NP4-190-CD) — day-ahead prices
