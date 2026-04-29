# Transformer Branch Plan

## The Problem

`build_bus_table.py` produces 7,755 PSSE buses spanning voltage levels from 13.8 kV (generator terminals) up to 345 kV (HV transmission). Without transformer branches connecting these tiers, the DC-SCED network is a collection of electrically isolated voltage islands. Power cannot flow from a 345 kV generator bus to a 138 kV load bus. The PTDF matrix is computed separately per island. The model is topologically broken.

## What the Data Already Tells Us

The PSSE bus data (`Settlement_Points_*.csv`) already contains both sides of every transformer. Any substation that appears at multiple voltage levels has transformers connecting those levels. This is directly readable from the existing data:

```
942 substations appear at ≥2 voltage levels → need transformer branches
```

Voltage pair breakdown (most common):

| Pair | Count | Category |
|------|-------|----------|
| 34.5 / 345 kV | 237 | Generator step-up |
| 34.5 / 138 kV | 224 | Generator step-up |
| 69 / 138 kV | 196 | Sub-transmission |
| 138 / 345 kV | 157 | **HV-HV (most critical)** |
| ~14 / 138 kV | 79 | Generator step-up |
| 18 / 138–345 kV | ~46 | Generator step-up |

The 138/345 kV pair is the critical tier for network connectivity: it connects the two main HV transmission layers. The 69/138 kV and generator step-up pairs are important for completeness but less so for the West Texas Export constraint and other HV binding constraints.

## Algorithm

New script: `Realist/ERCOT/build_transformer_branches.py`

**Input:** `sced_inputs/bus.csv` (output of `build_bus_table.py`)

**Step 1 — Group buses by substation**

Group the bus table by `Sub Name`. For each group, collect all distinct `(Bus ID, BaseKV)` pairs. Any group with ≥2 distinct voltage levels needs transformer branches.

**Step 2 — Identify transformer pairs**

For substations with N voltage levels, connect consecutive levels in ascending order:
- If kV levels are [13.8, 138, 345] → add branches: 13.8↔138, 138↔345
- If kV levels are [138, 345] → add branch: 138↔345
- If kV levels are [13.8, 18, 345] → add branches: 13.8↔18 (generator internal, low priority), 18↔345

Do **not** add a branch between 13.8 kV and 345 kV directly at a three-voltage substation — real three-winding transformers connect via the intermediate winding. Connecting consecutive levels in order is the standard DC approximation.

**Step 3 — Assign reactance (p.u., 100 MVA base)**

Standard two-winding and autotransformer series reactance values. Tap ratio is ignored (DC approximation assumes all taps = 1.0 p.u.).

| From kV | To kV | X (p.u.) | Rationale |
|---------|-------|----------|-----------|
| ≤35 | 138 | 0.12 | Generator step-up, typical X=10-15% |
| ≤35 | 345 | 0.10 | Large GSU, lower leakage |
| 69 | 138 | 0.12 | Sub-transmission autotransformer |
| 138 | 345 | 0.08 | HV autotransformer, X=7-10% typical |
| any | any (default) | 0.12 | Conservative fallback |

Formula: `X_pu = X_pct / 100` on 100 MVA base. No additional normalization needed — `build_bus_table.py` does not do Vatic's internal division here.

**Step 4 — Assign thermal rating (MVA)**

Rating is limited by the lower-voltage winding. These are conservative fleet-average defaults; actual ratings vary by unit.

| Pair | Cont Rating (MVA) |
|------|-------------------|
| 138 / 345 kV | 600 |
| 69 / 138 kV | 300 |
| ≤35 / 138 kV | 200 |
| ≤35 / 345 kV | 400 |
| default | 200 |

For generator step-up transformers: if a generator bus (≤35 kV) is connected to exactly one generator in `gen.csv`, cap the rating at `PMax` of that generator rather than the fleet default. This prevents the transformer from being the binding constraint in a way that misrepresents reality.

**Step 5 — Branch UID**

Format: `XFMR_{Sub Name}_{from_kv:.0f}_{to_kv:.0f}` (e.g., `XFMR_COMANCHEPEAK_138_345`). Must be unique; append `_B` if a substation has two parallel transformer banks at the same voltage pair (check for duplicates after UID generation).

**Step 6 — Output**

Write `sced_inputs/transformers.csv` with the same columns as `branch.csv`:

```
UID, From Bus, To Bus, R, X, B, Cont Rating, LTE Rating, STE Rating, transformer
```

Set `R = 0`, `B = 0`, `transformer = True` (Vatic uses this flag). The branch-building step (`build_branch_table.py`) should load both `branches.csv` (OSM lines) and `transformers.csv` and concatenate them before passing to Vatic.

---

## Phased Scope

Run in three phases, validating after each:

**Phase 1 (critical):** 138/345 kV transformers only — 157 branches. This connects the two HV transmission tiers and is the minimum needed for meaningful DC-SCED results. Run SCED after this and check that power flows between 345 kV and 138 kV zones.

**Phase 2 (important):** Add 69/138 kV and ≤35/138 kV transformers — adds ~500 branches. This connects sub-transmission and generator buses to the 138 kV network.

**Phase 3 (completeness):** Add ≤35/345 kV generator step-up transformers — adds ~260 branches. These connect large direct-connected generators (e.g., nuclear, large wind plants) to the 345 kV backbone.

---

## Edge Cases

**Multiple transformer banks:** Some major 138/345 kV substations (e.g., Comanche Peak, Limestone) have 2–4 parallel transformer units. The PSSE data does not distinguish units — it shows one bus per voltage level per substation. Model each substation's voltage pair as a single transformer with aggregated rating (e.g., 2× 600 MVA → 1,200 MVA). This is acceptable for DC-SCED where per-unit transformer loading is not reported.

**Generator terminal buses (≤20 kV):** These only exist in the PSSE data because generators connect to them. They are not transmission buses. If a generator terminal bus (e.g., 13.8 kV) has no transformer to ≥69 kV at its substation, the generator is stranded. Log these and flag for manual inspection — they represent either a data gap or a unit that connects via a private step-up transformer not captured in the public SP data.

**Substations with buses at 3+ HV levels:** Rare but possible (e.g., 69/138/345 kV). Apply the consecutive-level rule: 69↔138, 138↔345. Do not add a 69↔345 branch.

**The 230 kV bus:** Only 1 bus appears at 230 kV in the dataset. Treat it as part of the 138–345 kV tier, using the 138/345 kV reactance/rating.

---

## What This Enables for Validation

After Phase 1 (138/345 kV transformers), the following checks become meaningful:

1. **Cross-voltage power flow**: In any SCED solution, confirm that buses on the 345 kV tier supply load on the 138 kV tier through transformer flows. If transformer flows are zero, the topology is still broken.

2. **West Texas Export constraint**: This constraint involves 345 kV generation → 345/138 kV autotransformers → 138 kV export corridors. It will only bind in the model if the 138/345 kV transformers are present. The published ERCOT shadow price on this constraint (from `ERCOT_SCED_Shadowprices.csv`) is the primary validation target.

3. **Nodal LMP spread**: Without transformers, 345 kV buses and 138 kV buses have completely independent prices. After adding transformers, prices should converge within each zone except when transformer limits bind.

---

## Integration with `build_bus_table.py`

`build_bus_table.py` already preserves `Sub Name` and `BaseKV` in the output bus table — these are exactly the join keys needed. The transformer builder can run independently after `build_bus_table.py` with no changes to the upstream script.

Suggested run order:
```
1. build_bus_table.py          → sced_inputs/bus.csv
2. build_branch_table.py       → sced_inputs/branches_osm.csv  (OSM lines)
3. build_transformer_branches.py → sced_inputs/transformers.csv
4. cat branches_osm.csv transformers.csv > sced_inputs/branch.csv
5. build_gen_table.py          → sced_inputs/gen.csv
6. run_sced.py                 → results/
```
