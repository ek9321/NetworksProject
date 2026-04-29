# Adroit Cluster Run Notes

## Environment

```bash
conda activate vatic-test
# Solver: gurobi (licensed on Adroit)
# Python: 3.11
# Vatic: ~/Vatic/vatic/  (js0735 install, shared)
```

## Files to Upload (flat layout)

```
SourceData/
    bus.csv           ← 3,878 buses (largest connected component)
    branch.csv        ← 4,501 branches
    gen.csv           ← 1,174 generators
    init_state.csv    ← initial commitment state
run_realist_sced.ipynb
```

Rebuild locally if needed (in order):
1. `python Realist/ERCOT/build_osm_bus_table.py`
2. `python Realist/ERCOT/build_osm_branch_table.py`  ← also filters to largest connected component
3. `python Realist/ERCOT/build_gen_table.py`

---

## Deprecation Warnings (harmless)

These appear on every Vatic run in this environment. They are Pyomo/Egret API
deprecation notices, not errors. Do not investigate them.

```
WARNING: DEPRECATED: The quicksum(linear=...) argument is deprecated and ignored.
  (deprecated in 6.6.0) → will be removed in Pyomo 7.0
  source: egret/model_library/unit_commitment/uc_utils.py:100

WARNING: DEPRECATED: Using __getitem__ to return a set value from its (ordered)
position is deprecated. Please use at()
  (deprecated in 6.1, will be removed in 7.0)
  sources: power_vars.py, startup_costs.py

Warning for adding constraints: zero or small (< 1e-13) coefficients, ignored
  → Gurobi filtering near-zero LP matrix entries. Normal for large sparse models.
```

The reference precept_testfile notebook produces identical warnings.

---

## First Successful Run (2026-03-04)

**Status: RUNNING but severe load shedding**

Output confirmed:
- PTDF Matrix Factorization succeeded → network is connected (1 component)
- RUC MILP solved → Fixed costs $8,004,575 / Variable costs $13,696,342
- SCED intervals solving sequentially with LMPs

### Load Shedding Problem

```
Load shedding at t=1:  27,241.86 MW   (52% of 52 GW total load)
Load shedding at t=2:  20,473.79 MW
Over-generation at t=1: 1,611.78 MW
Reserve shortfall at t=1: 2,017.90 MW
Renewables curtailment at t=1: 550.28 MW
Quick start capacity at t=1: 0.00 MW
```

Shedding decreases interval-to-interval, indicating the RUC is committing more
thermal over time. Root cause is likely one or more of:

1. **RUC commits too little thermal in the first pass** — constant 48-hour
   timeseries with all renewables at PMax and flat load gives the optimizer no
   reason to ramp up expensive thermal early. Most thermal has min-up/down time
   constraints so once behind, the system can't catch up for several hours.

2. **Total installed capacity vs load** — our gen.csv uses MORA nameplate
   capacities. Total dispatchable capacity should exceed 52 GW, but the RUC
   may be leaving most of it offline.

3. **Network congestion** — even with sufficient aggregate capacity, DC PTDF
   constraints may prevent delivery from West Texas (heavy wind/solar) to
   load centers.

### Next Debugging Steps

- Check total PMax in gen.csv vs 52 GW load: `gen['PMax MW'].sum()`
- Check how many thermal generators are committed in init_state.csv
- Try `prescient_sced_forecasts=False` → `True` with a ramping load profile
  instead of flat constant timeseries
- Consider setting `init_ruc_file` to pre-commit all thermal at startup
- Check if load distribution is correct: zone totals should be
  NORTH 23,000 + HOUSTON 11,500 + SOUTH 10,500 + WEST 7,000 = 52,000 MW
