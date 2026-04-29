# Core Topology Generation Algorithm

**Full Specification with Penalties & Heuristics**

---

## Overview

Build transmission topologies per nominal voltage level to ensure:

- Each level is connected
- **m/n ≈ target_mn_ratio** (default 1.22)
- Proportions of edges match Delaunay quotas
- Line intersections are low
- DC-flow incentives guide placement toward corridors that connect generation and load
- **Deterministic** given random_seed

---

## Inputs (Per Region)

### Data Files
- **`data/processed/<region>_substations.csv`**  
  Substation nodes with: `sub_id`, `lat`, `lon`, `mw_load`, `total_gen_mw`, `voltage_levels[]`

### Configuration
- **`config/<region>.yaml`** containing:
  - `voltage_levels` (list)
  - `target_mn_ratio` per voltage
  - `delaunay_category_quotas` (mst, delaunay, neighbor_2, neighbor_3)
  - `overhead_line_params` per voltage:
    - `reactance_per_km` (Ω/km)
    - `MVA_limit_per_circuit` (MVA)
    - `V_base_kV`
    - `S_base_MVA`
  - `max_line_intersection_rate` (default 0.05)
  - `underground_line` thresholds
  - `K_per_iteration` (default 5)
  - Scoring weights (optional — defaults provided below)
  - `random_seed`

---

## Outputs

- **`data/processed/<region>_lines.csv`**  
  Fields: `from_sub`, `to_sub`, `voltage_kv`, `length_km`, `category`, `circuits`, `R`, `X`, `B` (per branch), `MVAmax`, `intersects_flag`

- **`data/processed/<region>_topology_summary.csv`**  
  Quotas, m/n, intersection rate, warnings

---

## Candidate Generation & Pruning (Per Voltage)

### Process

1. **Node set** = substations with that voltage bus
2. **Compute Delaunay triangulation**; derive neighbor distances (2-neighbors, 3-neighbors)
3. **Compute Euclidean MST**
4. **Candidate set** = MST ∪ Delaunay ∪ Delaunay-2 ∪ Delaunay-3 (deduplicate)

### For Each Candidate (u,v)

- Compute **haversine `length_km`**
- Label **category** (mst, delaunay, neighbor_2, neighbor_3)
- Compute **initial electrical params** from `overhead_line_params`:
  - `X_ohm = reactance_per_km × length_km / circuits` (circuits default 1)
  - `X_pu = X_ohm × (S_base_MVA) / (V_base_kV²)`
  - `b_pu = 1 / X_pu`
  - `MVAmax = MVA_limit_per_circuit × circuits`
- **Prune** if `length_km > hard_max_length_km` (optional config)

---

## Scoring Function

**Higher is better**

For a candidate edge **e** between nodes **i** and **j**:

```
score(e) = - distance_penalty(e)
           + dc_bonus(e)
           + connectivity_bonus_single_voltage(e)
           + connectivity_bonus_overall(e)
           - category_penalty(e)
           - intersection_penalty(e)
```

### Components

#### 1. Distance Penalty
```
distance_penalty(e) = w_dist × length_km
```
- **Default**: `w_dist = 1.242` per km  
  *(Paper: +2 per mile → converted to metric: 2 / 1.60934 ≈ 1.242)*

#### 2. DC Bonus
```
dc_bonus(e) = w_dc × Pest_MW
```
- **Pest_MW** = estimated DC-flow magnitude on e (MW) via DC linear model (see DC section)
- **Default**: `w_dc = 0.5`  
  *(Paper: −0.5×Pest as penalty; converted to positive bonus)*

#### 3. Connectivity Bonus (Single Voltage)
```
connectivity_bonus_single_voltage(e) = w_conn_v (if applicable)
```
- Applied if **e** contributes to single-voltage connectivity (connects two disconnected components or connects to a radial node)
- **Default**: `w_conn_v = +300`

#### 4. Connectivity Bonus (Overall System)
```
connectivity_bonus_overall(e) = w_conn_overall (if applicable)
```
- Applied if **e** contributes to full-system connectivity under single-node removal (improves multi-voltage resilience / removes articulation vulnerability)
- **Default**: `w_conn_overall = +1000`

#### 5. Category Penalty
```
category_penalty(e) = w_cat (if quota exceeded)
```
- **Implementation**: Keep counters of category usage
- If `current_count(category) / total_added > quota_category + tolerance`:  
  `category_penalty = w_cat`, else `0`
- **Default**: `w_cat = +200`

#### 6. Intersection Penalty
```
intersection_penalty(e) = w_intersect (if intersects)
```
- Applied if **e** intersects any existing same-voltage line
- **Default**: `w_intersect = +500`

### Notes
- **Penalties** are positive and subtract from score
- **Connectivity terms** are positive bonuses added to score
- Default values mirror Table V of Birchfield (converted to km units and sign-flipped to bonus-or-penalty convention)

---

## DC-Flow Estimation (Exact Procedure)

For scoring `dc_bonus(e)`:

### Steps

1. **Build per-voltage network B matrix** in per-unit using currently added edges + candidate **e** included (use `X_pu` from candidate estimate)

2. **Handle disconnected graphs**: If graph is disconnected, add temporary MST links with low conductance initially, then raise their impedances over successive iterations (see MST-temporary section) so **B** is invertible

3. **Define power injection**:  
   ```
   P_inj_i (pu) = (gen_dispatch_i − load_i) / S_base_MVA
   ```
   - **Default dispatch**: Use assigned generation at node, scaled so total generation matches total load  
     *(Per paper: generators given initial dispatch proportional to load)*

4. **Solve θ** (remove slack)

5. **Calculate edge flow**:  
   ```
   Pest_pu on edge = (θ_i − θ_j) / X_pu
   Pest_MW = |Pest_pu| × S_base_MVA
   ```

6. **Use Pest_MW** as dc_bonus contribution:  
   ```
   dc_bonus = w_dc × Pest_MW
   ```

**Important**: Use the same `overhead_line_params` `reactance_per_km` for X calculations

---

## MST-Temporary Impedances

**Purpose**: Keep DC solvable early in the algorithm

### Process

1. **Add temporary edges** along Euclidean MST between nodes with temporary reactance `X_temp_pu`

2. **Initialization**:  
   ```
   X_temp_pu_init = c_init × median(X_pu)
   ```
   - Where `c_init ∈ (0.01, 0.1)` to make temporary links relatively strong (ensures solvability)

3. **Each outer iteration**: Multiply `X_temp_pu` by factor `f_increase > 1` (e.g., 1.2) to progressively weaken temporary links as real lines are added

4. **Remove temporary links** once the actual graph becomes connected (no dependence on them)

---

## Iteration Loop

### Setup
```
target_edge_count_V = round(target_mn_ratio_V × n_V)
```

### Main Loop
While `added_edges_V < target_edge_count_V` (for any V):

1. **For each candidate not yet added**, compute `score(e)`

2. **Select top K candidates** globally (across voltages) or per-voltage, per config  
   - **Default**: `K = 5` (paper used 5)

3. **Add selected candidates** to graph:
   - Update edges
   - Update category counts

4. **Recompute DC flows** and `Pest` only after the batch of K is added (to reduce solver calls)

5. **Update temporary MST impedances** scaling

6. **Recompute intersection flags** for remaining candidates

7. **Stop early** if candidate pool exhausted

---

## Conductor Selection & Circuit Upgrades

**Post-placement optimization**

### Process

1. **Run DC flow** and compute:  
   ```
   loading_fraction = |flow_MW| / MVAmax
   ```
   for assumed circuits

2. **If loading > upgrade_threshold** (e.g., 0.85), consider:
   - Upgrading conductor (increase `MVAmax`), or
   - Adding parallel circuit(s) (increment `circuits`)

3. **Upgrade selection heuristic**:  
   Upgrade edges by descending loading until target max loading ≤ 0.85 or budget/limits reached

4. **Set final R/X/B and MVAmax** per chosen conductor/circuits and write to output

---

## Underground Decision

**If** `length_km ≤ config.underground_line.max_length_km` **and** both endpoints' loads ≥ `config.underground_line.load_percentile_threshold`:

- Mark as **underground**
- Use underground params (if available)

*Note: Underground can be skipped — then ignore*

---

## Intersection Control & Quota Enforcement

### Intersection Control
```
intersection_rate = (#intersecting_edges) / (#edges at that voltage)
```

- **If** `intersection_rate` exceeds `config.max_line_intersection_rate`:
  - Temporarily increase `w_intersect` until rate drops back within limit

### Quota Enforcement
- Apply `category_penalty` when quota exceeded
- If quotas never reached due to connectivity constraints, relax penalties gradually

---

## Deterministic Tie-Breaking

When multiple candidates have equal score, break ties deterministically by:

1. **Smaller combined `length_km`**
2. **Smaller combined category priority**:  
   `mst < delaunay < neighbor_2 < neighbor_3`
3. **Smaller lexicographic** `(min(node_i_id, node_j_id), max(...))`
4. RNG seed **not used** for tie-break unless all else equal

---

## Stopping Conditions

Stop when:

- **All voltage levels** reach their target edge counts (±1 tolerance), **OR**
- **Candidate set exhausted** (emit diagnostic), **OR**
- **Maximum number of iterations** reached (configurable safety cap)

---

## Final Validations (Must Pass)

1. ✓ Each per-voltage graph is **connected**

2. ✓ Combined multi-voltage graph remains **connected under single-node removal** (no articulation points)  
   - If not feasible, list articulation nodes and warn

3. ✓ **m/n per voltage** within ±5% of target

4. ✓ **Intersection rate** ≤ `config.max_line_intersection_rate` (or warning)

5. ✓ **DC flows solvable**; no lines > 100% MVA (ideally <85%)  
   - If >100% exist, report and recommend conductor upgrades

6. ✓ All assigned **generators attach** to a bus at their substation

---

## Output Format

### `lines.csv`
Rows with:
- `from_sub`, `to_sub`, `voltage_kv`, `length_km`, `category`, `circuits`
- `R_ohm`, `X_ohm`, `B_S`, `MVAmax`, `intersects_flag`

### `topology_summary.csv`
Per-voltage:
- `n`, `m`, `m/n`
- Quota proportions
- `intersection_rate`
- `total_added`
- Warnings

---

## Default Numeric Weights

**Paper-derived / Metric**

*(These are defaults — tune in config)*

| Parameter | Value | Notes |
|-----------|-------|-------|
| `w_dist` | 1.242 per km | Paper: +2 per mile |
| `w_dc` | 0.5 | Paper: −0.5 × Pest as penalty; converted to positive bonus |
| `w_cat` | 200 | Category quota penalty |
| `w_conn_v` | 300 | Single-voltage connectivity bonus |
| `w_conn_overall` | 1000 | Overall system connectivity bonus |
| `w_intersect` | 500 | Intersection penalty |
| `K_per_iteration` | 5 | Batch size for edge additions |

---

## Performance & Implementation Notes

### Optimization Strategies

- **Precompute** candidate list, `length_km`, and categories
- **Maintain min-heap** or partial-sorted structure for scores
- **Recompute scores** only for candidates affected by recent additions (those intersecting/new connectivity)
- **Run DC solver** after batches of K additions
- **Use sparse linear algebra** for B matrix (n up to thousands)
- **Log per-iteration diagnostics** for debugging