# Plan: Degree-Weighted + Census-Tract Load Allocation

## Problem

The current `pop` load allocation in `run_sced.py` uses county-level population (254 Texas counties) to distribute zone load across buses. In Houston, all 122 load buses map to Harris County (pop 4.7M), giving them identical 162 MW allocations regardless of their network position. 72% of those buses are degree ≤ 2 (spur lines), putting 14.3 GW behind single 138 kV corridors. This causes artificial congestion at 77+ GW demand.

Real substations on spur lines serve much less load than well-connected substations in the transmission mesh — distribution networks provide multiple feed paths to meshed nodes but only one path to spur endpoints.

## Fix: Two-Factor Weighting

Replace `weight = county_pop` with `weight = tract_pop × degree_factor`.

### Factor 1: Census tract population (sub-county granularity)

**Source:** Two public datasets, no API key required:
- Census 2020 Decennial PL file (population per tract): `https://api.census.gov/data/2020/dec/pl?get=P1_001N&for=tract:*&in=state:48` → 6,896 Texas tracts
- TIGER 2020 shapefile (tract centroids): `https://www2.census.gov/geo/tiger/TIGER2020/TRACT/tl_2020_48_tract.zip` → INTPTLAT/INTPTLON columns

**What this fixes:** In Harris County, tracts range from ~1,500 people (industrial Ship Channel area) to ~12,000 (dense midtown). A substation in midtown gets 8× the weight of one near the refineries. Currently they both get 4.7M (the county total).

**Typical tract sizes:** 0.2–0.5 sq miles in dense urban Houston, 1–5 sq miles in suburbs, hundreds of sq miles in rural West Texas. There are ~800 tracts in Harris County alone vs 1 county entry now.

### Factor 2: Bus degree (network connectivity)

**Rationale:** A degree-1 bus (leaf node) is fed by a single transmission line. In reality, load at such a point is small — it's a tap off a main line, serving a small area. A degree-4+ bus sits at a transmission junction where multiple lines converge, typically a major substation serving a large area via a distribution network beneath it.

**Formula:**
```
degree_factor = min(degree, cap) / normalization
```

Options for the degree function (to be tested):
- **Linear:** `degree_factor = degree` — degree-4 bus gets 4× a leaf
- **Sqrt:** `degree_factor = sqrt(degree)` — gentler; degree-4 gets 2× a leaf
- **Capped linear:** `degree_factor = min(degree, 6)` — prevent outlier high-degree buses from dominating

### Combined weight

```
weight(bus) = tract_pop(bus) × degree_factor(bus)
```

Then same normalization as current code: `bus_load = zone_total_mw × weight / zone_weight_sum`.

## Implementation

### Step 1: Fetch and cache tract population + centroid data

Add a function `_load_tract_data()` to `run_sced.py` (or a separate `census_tracts.py`):
1. Check for cached CSV at `grid_data/texas_tract_pop_2020.csv`
2. If missing, fetch from Census API + TIGER shapefile, merge on GEOID, save CSV
3. Return DataFrame: `tract_id, lat, lng, population`

~6,900 rows. One-time download, cached forever.

### Step 2: Replace `_nearest_county_pop()` with `_nearest_tract_pop()`

Same haversine nearest-neighbor logic, but against ~6,900 tract centroids instead of 254 county centroids. Slightly slower (27× more points) but still fast for 4,227 buses (< 1 second with vectorized haversine).

Optimization: use a KD-tree (`scipy.spatial.cKDTree`) for O(n log n) instead of O(n×m) brute force. But brute force over 6,900 × 4,227 ≈ 29M distance calculations is still fine in practice.

### Step 3: Add degree-factor computation

After loading bus.csv and branch.csv, compute the degree of each bus from the branch table. Weight = `tract_pop × degree ** alpha` where alpha is configurable (default 1.0).

### Step 4: New LOAD_ALLOC method: `"tract_degree"`

Add a new case to the `distribute_load()` function:
```python
elif load_alloc == "tract_degree":
    alpha = float(os.environ.get("DEGREE_ALPHA", "1.0"))
    bus["_weight"] = bus["_tract_pop"] * bus["_degree"].apply(lambda d: max(d, 1) ** alpha)
```

Keep existing `"pop"` method as default for backwards compatibility. The new method is opt-in via `LOAD_ALLOC=tract_degree`.

### Step 5: Env vars

| Var | Default | Purpose |
|---|---|---|
| `LOAD_ALLOC` | `pop` | Set to `tract_degree` to use new method |
| `DEGREE_ALPHA` | `1.0` | Exponent on degree factor. 0.5 = sqrt, 1.0 = linear |

## Experiments

### Experiment design

Run the winning config (t135 + f1200 + reserve=0.15) with different load allocations on Jun 17 (known solution) and Aug 20 (known failure):

| Task | Tag | LOAD_ALLOC | DEGREE_ALPHA | Date | Purpose |
|---|---|---|---|---|---|
| 79 | alloc-j17-td1 | tract_degree | 1.0 | Jun 17 | Regression check — does Jun 17 still solve? |
| 80 | alloc-aug20-td1 | tract_degree | 1.0 | Aug 20 | Main test — does tract+degree fix Aug 20? |
| 81 | alloc-aug20-td05 | tract_degree | 0.5 | Aug 20 | Sensitivity: sqrt(degree) weighting |
| 82 | alloc-j17-tract | tract (no degree) | — | Jun 17 | Ablation: is tract alone sufficient? |
| 83 | alloc-aug20-tract | tract (no degree) | — | Aug 20 | Ablation: tract alone on stress test |

### Success criteria

1. **Jun 17 regression:** Must remain 0 MW shed, 24/24 W<N
2. **Aug 20 improvement:** Shed should drop substantially from 6,282 MW. Target: < 1,000 MW
3. **Zone ordering preserved:** W<N should hold during high-wind hours on both days
4. **No new pathologies:** No zone with median LMP > $1,000 (indicates starved region)

### Diagnostic checks

Before running SCED, validate the new allocation:
- Print Houston load distribution: min/max/median/p90 per bus
- Print correlation between bus degree and assigned MW
- Confirm zone totals are unchanged (just redistribution within zones)

## Risk / What Could Go Wrong

1. **Overcorrection:** If degree weighting is too aggressive, leaf buses get near-zero load and the mesh interior gets too much — could create new congestion at mesh junctions. Mitigate: test alpha = 0.5 as well.

2. **Tract assignment noise:** Some substations may be near a tract boundary and get assigned to a low-pop industrial tract when they actually serve a high-pop residential area. Less likely than the county problem (tracts are much smaller) but possible. Mitigate: visual spot-check Houston allocations on a map.

3. **Jun 17 regression:** The floor ratings and targeted upgrades were tuned to the current load distribution. Changing it could shift congestion patterns. Mitigate: run Jun 17 first.

## Files to modify

- `Realist/ERCOT/run_sced.py` — add `_load_tract_data()`, `_nearest_tract_pop()`, degree computation, new `LOAD_ALLOC` case
- `Realist/ERCOT/run_sced_array.slurm` — add tasks 79–83
- No changes to branch.csv, gen.csv, or other pipeline scripts
