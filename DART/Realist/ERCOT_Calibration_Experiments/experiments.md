# ERCOT SCED Calibration Experiments

All runs use Vatic DC-SCED with Gurobi (Adroit cluster) or CBC (local). Nov 5 2025 runs use **~50,894 MW constant** load. Jun 17 2024 and Jan 8 2024 runs use **hourly** load profiles (52–76 GW and 41–51 GW respectively) with hourly wind/solar capacity factors from ERCOT public data.

---

## Quick Reference

| Tag | Date | Platform | h0 shed (MW) | SS shed (MW) | Curtail (MW) | Price ($/MWh) | What changed |
|---|---|---|---|---|---|---|---|
| v1 | 2025-11-05 | local | 27,242 | 8,622 | 13,543 | $19.66 | Baseline: PSSE-bus network, cold start |
| cluster_v1 | 2025-11-05 | adroit | 27,242 | 8,622 | 13,543 | $19.66 | Re-run of v1 on Adroit — identical outputs |
| v2 | ~2026-03 | adroit | 2,976 | 2,976 | 11,117 | $21.56 | OSM-native network; warm start thermal |
| v3 | ~2026-03 | adroit | 5,431 | 5,431 | 11,396 | $20.92 | OSM network rebuild — regression, details not logged |
| v4 | ~2026-03 | adroit | 6,299 | 6,299 | 13,009 | $20.96 | OSM network rebuild — regression, details not logged |
| v5 | ~2026-03 | adroit | 6,298 | 6,298 | 13,009 | $20.96 | Near-identical to v4 |
| floor | 2026-03-18 | adroit (job 3026476_0) | 0 | **0** | 0 | $13.86 | BRANCH_SCALE=0: all Cont Ratings set to 999,999 MVA |
| 2x | 2026-03-18 | adroit (job 3026476_1) | 0 | **0** | 0 | $13.86 | BRANCH_SCALE=2.0: all Cont Ratings doubled |
| no-spl-cap | 2026-03-19 | adroit (job 3030219_2) | 2,180 | **2,180** | 10,490 | $21.13 | NO_SPL_CAP=1: SPL junction branches set to 999,999 MVA; real branches at cables-based ratings |
| no-spl+load-fix | 2026-03-19 | adroit (job 3030392_3) | 3,411 | **3,411** | 11,593 | $20.47 | no-spl-cap + LOAD_NAMED_ONLY=1: exclude unnamed OSM nodes and _Plant substations from load |
| no-spl+hv2x | 2026-03-19 | adroit (job 3030392_4) | 2,033 | **2,033** | 11,618 | $21.91 | no-spl-cap + SCALE_345KV=2: double all 345 kV branch ratings |
| best-so-far | 2026-03-19 | adroit (job 3030502_6) | 87 | **87** | 8,174 | $20.85 | no-spl-cap + 138 kV 2x + NO_PLANT_CAP=1 (plant outlets and <0.5 km stubs unconstrained) |
| no-spl+138kv2x | 2026-03-19 | adroit (job 3030435_5) | 136 | **136** | 6,393 | $19.57 | no-spl-cap + SCALE_138KV=2: double all 138 kV branch ratings |
| clean-build | 2026-03-20 | adroit (job 3033672_7) | 81.7 | **81.7** | 9,048 | $21.31 | Rebuilt branch.csv: 600 MVA 138kV base + SPL+plant baked in (1 km stub threshold); no runtime env vars |
| jun17-hourly | 2026-03-20 | adroit (job 3033707_8) | — | **593–1923** | varies | $5–$2778 | June 17 2024 calibration day: hourly load (52–76 GW) + hourly wind/solar CFs (0.62–0.79 wind) |
| hv2400 | 2026-03-20 | adroit (job 3033709_9) | 24.1 | **24.1** | — | $18.69 | clean-build + SCALE_345KV=2: all 345 kV doubled to 2400 MVA |
| hv-default2 | 2026-03-20 | adroit (job 3033726_10) | 79.6 | **79.6** | 9,859 | $21.67 | New branch.csv with 345 kV default=2 circuits (only Hicks→WillowCreek upgraded vs clean-build) |
| jun17-hv2400 | 2026-03-20 | adroit (job 3033726_11) | — | **291–1101** | varies | $22–24 | June 17 2024 + SCALE_345KV=2; WESTEX eliminated (MC→Tonkawa max 1293 MVA vs 2400 MVA rating) |
| spl-fix | 2026-03-24 | adroit (job 3040750_18) | 6,113 | **6,117** | 8,200 | $17.4 | 138 kV at 250 MVA + SPL segments voltage-tier rated (not 999k). Proves compensating error is necessary. |
| jun17-spl-fix | 2026-03-24 | adroit (job 3040750_19) | — | **5,092–15,782** | 12k–31k | $13–17 | Jun 17 with 250 MVA 138 kV + constrained SPL. Catastrophic. |
| jan08-spl-fix | 2026-03-24 | adroit (job 3040750_20) | — | **1,845–4,572** | 15k–21k | $16–18 | Jan 8 2024 (extreme wind) with 250 MVA 138 kV + constrained SPL. |
| jan08-clean | 2026-03-24 | adroit (job 3040759_21) | — | **0–178** | 3,840–6,933 | $18.66–22.32 | Jan 8 2024 with clean-build config. Third calibration day validated. |
| v2-nov5-presplice | 2026-03-24 | adroit (job 3042500_31) | 5,254 | **5,254** | 7,300–7,660 | $18.13 | V2 topology (fixes 1-6, xvolt merge, 4× SPL, bridge comp). Bridge ratio 66.4% → tree bottleneck. |
| v2-nov5 | 2026-03-24 | adroit (job 3042790_31) | 4,306 | **4,306** | 6,971 | $19.05 | V2 + edge-splice (fix 8): bridge ratio 18.4%. All 33 binding lines are 138 kV at 250 MVA. |
| v2-600-nov5 | 2025-11-05 | adroit (job 3042837_34) | 0 | **0** | 0 | $14.11 | V2 topology + 600 MVA 138 kV base + SPL×4. Uncongested (matches floor). |
| v2-600-jun17 | 2024-06-17 | adroit (job 3042867_35) | — | **171–1,429** | 17–6,268 | $7.5–12.7 | V2 + 600 MVA + SPL×4. WESTEX only 33% util. Houston LMPs $590–$8,500. WEST<NORTH 20/24 hrs. |
| v2-600-jan08 | 2024-01-08 | adroit (job 3042867_36) | — | **0–57** | 0–600 | $3.6–8.4 | V2 + 600 MVA + SPL×4. WEST<NORTH 18/24 hrs. Houston LMPs ~$170. |
| v2-spl1-nov5 | 2025-11-05 | adroit (job 3042940_37) | 0 | **0** | 0 | $14.11 | V2 + 600 MVA + SPL×1. Same as SPL×4 on Nov 5. |
| v2-spl1-jun17 | 2024-06-17 | adroit (job 3042940_38) | — | **287–2,012** | 538–15,410 | $11.6–14.6 | V2 + 600 MVA + SPL×1. WESTEX 75% util (better). WEST<NORTH 24/24. Higher shed. |
| v2-spl1-jan08 | 2024-01-08 | adroit (job 3042940_39) | — | **0–110** | 0–513 | $3.7–8.4 | V2 + 600 MVA + SPL×1. WEST<NORTH 21/24 hrs. |
| v2-spl2-* | all 3 days | adroit (job 3042990_40-42) | — | **not pulled** | — | — | V2 + 600 MVA + SPL×2 (1200 MVA, matches WESTEX). Results on adroit, not yet retrieved. |
| v3r2-nov5 | 2025-11-05 | adroit (task 46) | — | **1,195** | 3,315 | $24.26 | V3 topology, 250 MVA 138 kV, pop-weighted load. Bridge ratio 24%. |
| v3-uniform | 2025-11-05 | adroit (task 47) | — | **695** | 4,678 | — | V3 + uniform load allocation. W-N spread -$18.5 (too large). |
| v3-sqrt | 2025-11-05 | adroit (task 48) | — | **361** | 1,756 | — | V3 + sqrt(pop) load allocation. W-N spread -$52.6 (unrealistic). |
| v3-cap75 | 2025-11-05 | adroit (task 49) | — | **895** | 2,185 | — | V3 + pop capped at 75 MW/bus. W-N spread +$0.4 (kills price signal). |
| v3-targeted | 2025-11-05 | adroit (task 50) | — | **88** | 513 | — | V3 + 28 binding lines doubled (250→500 MVA). W-N spread -$7.2. |
| v3-targeted2 | 2025-11-05 | adroit (task 51) | — | **0** | 59 | — | V3 + 41 lines doubled. **Network clean.** W-N spread -$0.5, zone medians $27-29. |
| v3-jun17-t2 | 2024-06-17 | adroit (task 52) | — | **244–2,012** | 0 | $6–12 | V3 + 41 DFW upgrades. 24/24 W<N but Houston $800–2,450. DFW fixes insufficient for summer. |
| v3-jan08-t2 | 2024-01-08 | adroit (task 53) | — | **0** | 0–600 | $3–8 | V3 + 41 DFW upgrades. **SOLVED.** 24/24 W<N, clean dispatch. |
| v3-j17-base | 2024-06-17 | adroit (task 57) | — | **290–4,874** | 110–8,462 | $8–13 | V3 baseline Jun 17 (250 MVA, pop). 54,233 MW total shed. 24/24 W<N. |
| v3-j17-f400 | 2024-06-17 | adroit (task 58) | — | **290–4,743** | varies | $4–13 | Floor cap 400 MVA. 20,394 MW total. 24/24 W<N. Too tight. |
| v3-j17-f600 | 2024-06-17 | adroit (task 59) | — | **varies** | varies | $5–13 | Floor cap 600 MVA. 5,313 MW total. 24/24 W<N. |
| v3-j17-f1200 | 2024-06-17 | adroit (task 60) | — | **52–398** | 110–8,462 | $8–13 | Floor cap 1200 MVA. 2,026 MW total. 20/24 W<N. Best balance. |
| v3-j17-fmax | 2024-06-17 | adroit (task 61) | — | **0** | 0 | $5–12 | Uncapped floor. **0 shed** but 0/24 W<N — flat LMPs, no congestion. |
| v3-j17-f8p8 | 2024-06-17 | adroit (task 62) | — | **0–568** | 70–8,905 | $9–14 | Floor ~800 + pop^0.8. 3,559 MW total. 23/24 W<N. pop^0.8 hurts. |
| v3-j17-best | 2024-06-17 | adroit (task 63) | — | **0–159** | 0–645 | $6–12 | Uncapped + pop^0.8. 160 MW total. 5/24 W<N. Mostly flat. |
| v3-j17-t87 | 2024-06-17 | adroit (task 64) | — | **0–934** | 5,600–8,500 | $0.5–12 | 87 binding lines doubled. 6,464 MW total. 24/24 W<N. Houston still $1,200–3,700. |
| v3-j17-t87f | 2024-06-17 | adroit (task 65) | — | **0–1,542** | 0–8,300 | $6–12 | 87 upgrades + f1200. 2,517 MW total. 21/24 W<N. Hours 8–23: 0 shed. |
| v3-j17-t135 | 2024-06-17 | adroit (task 66) | — | **0–780** | 1,800–8,200 | $2–13 | 135 lines doubled (iter 2). 4,085 MW total. 22/24 W<N. |
| v3-j17-t135f | 2024-06-17 | adroit (task 67) | — | **0–1,045** | 0–8,100 | $6–12 | 135 upgrades + f1200. 1,417 MW total. 21/24 W<N. Hours 8–20: 0 shed. |
| **v3-j17-t135f-r15** | **2024-06-17** | **adroit (task 68)** | — | **0** | 0 | $2–59 | **135 upgr + f1200 + reserve=0.15. 0 MW shed. 24/24 W<N. SOLVED.** |
| v3-j17-t135f-stor | 2024-06-17 | adroit (task 69) | — | **0–1,045** | 0–8,100 | $6–12 | 135 + f1200 + storage. 1,417 MW total. Storage NOT dispatching. |
| v3-j17-t135f-r15s | 2024-06-17 | adroit (task 70) | — | **0** | 0 | $2–59 | 135 + f1200 + r=0.15 + storage. 0 MW. Storage irrelevant. |
| v3-nov5-t135f-r15 | 2025-11-05 | adroit (task 71) | — | **0** | 0 | — | Regression check: 0 shed. Passed. |
| v3-jan08-t135f-r15 | 2024-01-08 | adroit (task 72) | — | **0** | 0 | — | Regression check: 0 shed. Passed. |
| val-aug20 | 2024-08-20 | adroit (task 73) | — | **0–1,099** | 27,205 | $14–25 | **Stress test.** 6,282 MW total shed (h13–20). Congestion (120 binding lines, 11.6 GW headroom). 15/24 W<N. |
| val-sep29 | 2024-09-29 | adroit (task 74) | — | **0–240** | 380 | $10–25 | Lowest wind. 254 MW shed (h19–20 evening ramp). Flat LMPs when no wind. 9/24 W<N. |
| val-mar29 | 2024-03-29 | adroit (task 75) | — | **0** | 21,301 | $4–7 | **PASS.** Highest wind. 0 shed, massive curtailment. WEST $3–10. 21/24 W<N. |
| val-oct29 | 2024-10-29 | adroit (task 76) | — | **0** | 4,909 | $8–13 | **PASS.** Fall high wind. 0 shed. WEST $7–11. 22/24 W<N. |
| val-apr13 | 2024-04-13 | adroit (task 77) | — | **0** | 6,939 | $4–9 | **PASS.** Spring balanced. 0 shed. 20/24 W<N. |
| val-jul23 | 2024-07-23 | adroit (task 78) | — | **~0** | 0 | $18–23 | **PASS.** Low wind → flat LMPs ($28). Correct physics. 11/24 W<N. |
| | | | | | | | |
| *Load-sweep battery (T135+f1200+r15 config, scaled load profiles):* | | | | | | | |
| final-j17 | 2024-06-17 | adroit | — | **0** | 0–5,959 | $7–13 | Winning config on Jun 17. 0 shed all 24h. Peak 74.4 GW. |
| final-jan08 | 2024-01-08 | adroit | — | **0** | 0–2,841 | $5–9 | Winning config on Jan 8. 0 shed. Peak 50.1 GW. |
| final-jul23 | 2024-07-23 | adroit | — | **0** | 0 | $18–23 | Low wind, 0 shed. Peak 58.1 GW. Flat LMPs ($18–23). |
| final-mar29 | 2024-03-29 | adroit | — | **0** | 0–2,729 | $3–7 | High wind, 0 shed. Peak 42.3 GW. |
| final-oct29 | 2024-10-29 | adroit | — | **0** | 0–985 | $8–12 | Fall high wind, 0 shed. Peak 58.4 GW. |
| floor-20gw | 2024-03-29 | adroit | — | **0** | 10,137–20,788 | $2–3 | Mar 29 load scaled to 20 GW peak. Massive curtailment. |
| moderate-40gw | 2024-01-08 | adroit | — | **0** | 1,054–5,271 | $3–6 | Jan 8 load scaled to 42 GW peak. 0 shed. |
| stress-80gw | 2024-08-20 | adroit | — | **0–239** | 0–4,038 | $14–24 | Aug 20 scaled to 80.5 GW. 930 MW total shed (6 hrs). |
| stress-85gw | 2024-08-20 | adroit | — | **0–1,156** | 0–5,007 | $15–25 | Aug 20 scaled to 85.2 GW. 6,180 MW total shed (8 hrs). |
| stress-90gw | 2024-08-20 | adroit | — | **0–3,008** | 0–4,400 | $16–25 | Aug 20 scaled to 90.7 GW. 19,908 MW total shed (10 hrs). |

SS shed = hours 9–23 average for Nov 5 runs; range shown for hourly runs. Renewable available = 19,818 MW in Nov 5 runs (v1 topology) / varies for v3.

---

## What the Experiments Tell Us

**Cold start vs. congestion:** The v1→v2 drop (27,242 → 2,976 MW at h0) confirms that
`UnitOnT0State = -1` was the dominant cause of the early-hour spike. All runs from v2 onward
use warm start (UnitOnT0State = 24 for thermal).

**Branch ratings are the binding constraint:** floor = 2x = 0 MW shed. With unlimited capacity,
the system clears completely. The 6,298 MW steady-state shed in v5 is entirely due to branch
rating constraints — not missing generation, not network islands.

**138 kV is the dominant control variable:** Doubling 138 kV ratings (300→600 MVA) reduces
shedding by 94% (no-spl+138kv2x: 136 MW). Clean-build (600 MVA baked in) achieves 81.7 MW.
V2 topology + 600 MVA eliminates congestion entirely on Nov 5 (v2-600-nov5: 0 MW).

**V3 topology at 250 MVA:** The geometry-based V3 pipeline (session_2026-03-26) achieves
1,195 MW shed at physical 250 MVA — down from 8,622 (v1) and 4,306 (v2) at the same rating.
Targeted doubling of 41 DFW binding lines (v3-targeted2) reaches 0 MW shed on Nov 5.

**Jun 17 summer peak (74 GW):** Requires 135 targeted line upgrades + f1200 floor ratings +
reserve_factor=0.15 to achieve 0 MW shed with 24/24 WEST < NORTH ordering. Floor ratings
alone trade congestion for shed along a smooth curve (f400: 20k shed/24 W<N → fmax: 0 shed/0 W<N).
Targeted upgrades are more surgical, preserving ordering while reducing shed. The morning-ramp
scarcity (hours 5–7) is a unit-commitment problem — reserve_factor=0.15 forces the RUC to
maintain 15% spinning reserves, keeping enough thermal online for the wind-to-solar transition.

**Storage monkey-patch non-functional.** Elements inject into Egret model dict (confirmed via
logging) but are not dispatched by the solver. Identical results with and without storage.csv.
Needs investigation into Egret's StorageData format requirements.

**v3–v5 regression explained:** The v3/v4/v5 naming here refers to early unnamed rebuilds
(not the V3 topology pipeline from Mar 26). Each rebuild captured more 138 kV branches from
OSM, increasing the number of binding constraints. The v2 result was a lower-resolution case.

---

## Current Inputs

### V1 topology (sced_inputs/) — clean-build baseline, as of 2026-03-20

| Script | Output | Key assumption |
|---|---|---|
| `build_osm_bus_table.py` | `osm_bus.csv` → `bus.csv` | OSM nodes from grid_visualizer.html |
| `build_osm_branch_table.py` | `branch.csv` | 138 kV: 600 MVA, 230 kV: 600 MVA, 345 kV: 1,200 MVA (2,400 double-circuit); SPL + plant outlet stubs at 999,999 MVA |
| `build_gen_table.py` | `gen.csv` | Thermal UnitOnT0State = 24; nuclear = 1000; renew = 1 |
| `run_sced.py` | results/ | ZONE_LOAD_MW constant (Nov 5) or hourly (Jun 17, Jan 8) |

Network: 3,878 buses, 4,501 branches, 474 thermal generators, 711 renewable generators.

### V2 topology (sced_inputs_v2/) — bridge-compensated, as of 2026-03-24

Built by `build_osm_branch_table_v2.py`. 3,714 buses, 4,626 branches. Bridge ratio reduced from ~36% to 18% via edge-splice. SPL branches at 4x tier rating (configurable via SPL_MULT). Bridge-load compensation for tree-like 138 kV.

### V3 topology (sced_inputs_v3/) — geometry-based splitting, as of 2026-03-26

Built by `build_osm_branch_table_v3.py` from `grid_visualizer_v3.html` (re-fetched OSM with 49,392 features). 3,786 buses, 4,817 branches. 250 MVA 138 kV baseline, no SPL multiplier, no bridge compensation. All 345 kV at 2,400 MVA except WESTEX (L1605_1612). Bridge ratio ~24%.

---

## Prioritized Next Experiments

All items from the original experiment plan (138kv-600, hourly-load, hourly-cf) have been completed. The 138 kV rating was validated at 600 MVA in clean-build. Hourly load/CF profiles are implemented via `HOURLY_LOAD_CSV` and `HOURLY_CF_CSV` env vars and used on Jun 17 and Jan 8 calibration days.

Current priorities (as of 2026-03-27):

**All three calibration days SOLVED** (0 MW shed, WEST < NORTH ordering).

Winning config: V3 topology + 135 targeted upgrades + f1200 floor + reserve_factor=0.15.

| Tag (proposed) | What to change | Expected outcome |
|---|---|---|
| stress-test-85gw | Scale Jun 17 hourly load × 1.15 | Test headroom above 74 GW peak |
| multi-day-sweep | Run 10–20 representative days | Statistical validation of W<N ordering |
| fix-storage | Investigate Egret StorageData format | Enable battery dispatch for realistic modeling |

Key findings from 3/27 session:
- Floor ratings trade congestion for shed smoothly (f400 → fmax sweep)
- Targeted upgrades preserve ordering while reducing shed (iterative binding-line identification)
- Morning ramp scarcity (hours 5-7) was a unit commitment issue — reserve_factor=0.15 forces adequate thermal commitment
- Storage monkey-patch injects into model dict but Egret does not dispatch — non-functional, needs investigation

---

## Detailed Entries

---

### v1 — Baseline (local, 2025-11-05)

**Platform:** Local, CBC solver
**Adroit job:** N/A
**sced_inputs basis:** PSSE-bus network (build_bus_table.py / build_branch_table.py)

**What changed from previous:** N/A — first run.

**Key metrics:**
- Hour 0 load shed: 27,242 MW
- Steady-state shed (h9–23): 8,622 MW
- Renewable curtailment: 13,543 MW
- System price: ~$19.66/MWh
- Demand: 50,894 MW constant

**Interpretation:** Cold start causes the h0 spike — all thermal units locked out by min-down-time
constraints. By h9, thermal capacity comes online but 108 branches are simultaneously at their
thermal limit. The simultaneous curtailment + shedding is the network delivery problem: West Texas
wind can't reach East Texas load because 138 kV intra-zone lines at 300 MVA flat are bottlenecks.

**Detailed analysis:** `Realist/reports/v1_sced_audit.md`

---

### cluster_v1 — v1 on Adroit (2025-11-05)

**Platform:** Princeton Adroit, Gurobi solver
**Adroit job:** (not logged)
**sced_inputs basis:** Same as v1

**What changed:** Nothing — first cluster run, confirming v1 is reproducible with Gurobi vs CBC.

**Key metrics:** Identical to v1 in every field.

**Interpretation:** Result is solver-independent. Gurobi and CBC produce the same dispatch.

---

### v2 — OSM-native network, warm start (~2026-03)

**Platform:** Adroit, Gurobi
**Adroit job:** not logged
**sced_inputs basis:** OSM-native network (build_osm_bus_table.py, build_osm_branch_table.py, build_gen_table.py)

**What changed from v1/cluster_v1:**
1. Network rebuilt on OSM nodes (grid_visualizer.html) instead of PSSE buses
2. Thermal UnitOnT0State changed from -1 to 24 (warm start)

**Key metrics:**
- Hour 0 load shed: 2,976 MW (flat all 24 hours — no cold-start transient)
- Steady-state shed: 2,976 MW
- Renewable curtailment: ~11,117 MW
- System price: $21.56/MWh

**Interpretation:** Warm start eliminated the h0 spike. The remaining 2,976 MW is pure network
congestion. Lower shedding than v3–v5 — may reflect a slightly different OSM network topology
(see version summary for caveat).

---

### v3 — OSM network rebuild (~2026-03)

**Platform:** Adroit, Gurobi
**Adroit job:** not logged
**sced_inputs basis:** OSM-native (rebuilt)

**What changed from v2:** Not logged. Network or gen table was rebuilt; shedding increased.

**Key metrics:**
- Hour 0 load shed: 5,431 MW (flat)
- Steady-state shed: 5,431 MW
- Renewable curtailment: ~11,396–11,553 MW
- System price: $20.92/MWh

**Interpretation:** Regression. Most likely cause: the rebuilt network has more 138 kV branches
(more complete OSM extraction) which increases the number of binding constraints. The v2 result
may have been the lower-resolution case. Details were not logged.

---

### v4 — OSM network rebuild (~2026-03)

**Platform:** Adroit, Gurobi
**Adroit job:** not logged
**sced_inputs basis:** OSM-native (rebuilt again)

**What changed from v3:** Not logged. Shedding and curtailment both increased.

**Key metrics:**
- Hour 0 load shed: 6,299 MW (flat)
- Steady-state shed: 6,299–6,304 MW
- Renewable curtailment: ~12,972–13,029 MW
- System price: $20.97/MWh
- Demand: 50,894.0015 MW (slightly different — bus.csv rebuilt)

**Interpretation:** Another regression. Renewables dispatched dropped from ~8,350 MW (v3)
to ~6,846 MW. Network is more congested. Demand change (50,893.99 → 50,894.00) confirms
bus.csv was rebuilt.

---

### v5 — Near-identical to v4 (~2026-03)

**Platform:** Adroit, Gurobi
**Adroit job:** not logged
**sced_inputs basis:** Same as v4

**What changed from v4:** Essentially nothing — results are bit-for-bit identical to v4.
May have been a re-run to confirm stability or test a minor change that had no effect.

**Key metrics:** Identical to v4 in every field.

**Interpretation:** v5 = v4. This is the current baseline before branch-limit sensitivity testing.

**Detailed summary:** `Realist/reports/sced_version_summary_2026-03-06.md`

---

### floor — No branch limits (2026-03-18)

**Platform:** Princeton Adroit, Gurobi
**Adroit job:** 3026476_0 (array task 0)
**sced_inputs basis:** v5 network, BRANCH_SCALE=0 applied at run time (all Cont Ratings → 999,999 MVA)
**SLURM script:** `Realist/ERCOT/run_sced_array.slurm`

**What changed from v5:**
- All branch Cont Ratings set to 999,999 MVA in run_sced.py (BRANCH_SCALE=0 env var)
- No changes to bus.csv, branch.csv, gen.csv, or load

**Key metrics:**
- Hour 0 load shed: 0 MW
- Steady-state shed: 0 MW
- Renewable curtailment: 0 MW
- Renewables dispatched: 19,818 MW (100% of available)
- System price: $13.858/MWh (flat all 24h — load and CFs still constant)
- Runtime: 131.2 seconds

**Interpretation:** Removing all branch limits eliminates load shedding entirely. The 6,298 MW
steady-state shed in v5 is 100% attributable to branch rating constraints, not missing generation
or network islands. All 19,818 MW of renewable available capacity is dispatched — there is
sufficient generation and thermal commitment to clear the system at flat load.

Price drops from ~$21/MWh (v5 with congestion) to $13.86/MWh (unconstrained). This is the
economic floor — the marginal unit cost with no network constraints.

---

### 2x — Branch ratings doubled (2026-03-18)

**Platform:** Princeton Adroit, Gurobi
**Adroit job:** 3026476_1 (array task 1)
**sced_inputs basis:** v5 network, BRANCH_SCALE=2.0 applied at run time
**SLURM script:** `Realist/ERCOT/run_sced_array.slurm`

**What changed from v5:**
- All branch Cont Ratings multiplied by 2.0 in run_sced.py (BRANCH_SCALE=2.0 env var)
- No changes to bus.csv, branch.csv, gen.csv, or load

**Key metrics:**
- Hour 0 load shed: 0 MW
- Steady-state shed: 0 MW
- Renewable curtailment: 0 MW
- Renewables dispatched: 19,818 MW (100%)
- System price: $13.858/MWh (flat)
- Runtime: 131.7 seconds

**Interpretation:** Identical to floor. Doubling ratings reaches the same unconstrained optimum
as removing all limits. This means the binding constraints in v5 are at most 2x underrated —
the threshold is between 1x (original) and 2x. The 138 kV → 600 MVA experiment will tell us
if the 138 kV tier alone is sufficient.

**Key finding:** floor = 2x. The next experiment should narrow the gap with `138kv-600`
(raise only 138 kV lines to 600 MVA, leave 345 kV at 1,200 MVA) and `1x` (run v5 at
nominal ratings as a formal baseline).

---

### no-spl-cap — Unconstrain SPL synthetic junction branches (2026-03-19)

**Platform:** Princeton Adroit, Gurobi
**Adroit job:** 3030219_2 (array task 2)
**sced_inputs basis:** v5 network; NO_SPL_CAP=1 applied at run time (SPL-connected branches → 999,999 MVA)
**SLURM script:** `Realist/ERCOT/run_sced_array.slurm`

**What changed from v5:**
- All branches where at least one endpoint is a synthetic split point (`is_split=True` in bus.csv) set to 999,999 MVA at run time via new `NO_SPL_CAP` env var in `run_sced.py`
- Real substation-to-substation branches remain at cables-based ratings (300/600/1200/2400 MVA)
- BRANCH_SCALE=1 (no uniform scaling)

**Key metrics:**
- Hour 0 load shed: 2,180 MW (flat — warm start, no transient)
- Steady-state shed (h9-23 avg): 2,180 MW
- Renewable curtailment: 10,490 MW
- Renewables dispatched: ~9,328 MW (47.1% of 19,818 MW available)
- System price: $21.13/MWh
- Runtime: 232 seconds

**Binding branches:** 34 branches ≥98% utilization. **0 SPL-connected** (the unconstrained SPL branches correctly drop out). All 34 are real substation-to-substation segments. Distribution:

| Zone | Count | Notable |
|---|---|---|
| NORTH | 22 | Hicks→Willow Creek (345 kV, 1,200 MVA); Hebron→OSM_2124 (345 kV, 1,200 MVA); Venus→OSM_2208 (345 kV, 1,200 MVA); many 138 kV urban DFW |
| HOUSTON | 8 | Meadow→Oasis (1,200 MVA); Cedar Bayou Plant→OSM_3019 (1,200 MVA); T.H. Wharton→North Belt (1,200 MVA); Strawberry Belt→Davson (600 MVA); Reading→Fort Bend (300 MVA) |
| SOUTH | 4 | Knob Creek→Panda Temple 2 (345 kV, 1,200 MVA); Azteca→SE Edinburg (300 MVA); Schertz→Parkway (300 MVA); Westover Hills→Anderson (300 MVA) |
| WEST | 0 | No WEST branches binding — Morgan Creek→Tonkawa did NOT bind |

**Key findings:**

1. **SPL artifact was real but not the whole story.** Removing SPL caps cuts shedding from 6,298 → 2,180 MW (65% reduction), but does not eliminate it. The remaining constraints are genuine.

2. **Morgan Creek→Tonkawa (WEST, 345 kV) does NOT bind** in no-spl-cap. The WEST zone is not congested at current load and renewable levels. Phase 2 experiments targeting WEST 345 kV are deprioritized.

3. **Hicks→Willow Creek (NORTH, 345 kV, 1,200 MVA) IS fully saturated** — as expected. This is the primary 345 kV bottleneck in NORTH.

4. **Multiple Houston 345 kV segments bind:** Meadow→Oasis, Cedar Bayou Plant→OSM_3019, T.H. Wharton→North Belt. The Houston 345 kV ring is the second major constraint zone.

5. **Knob Creek→Panda Temple 2 (SOUTH, 345 kV, 1,200 MVA) binds** — this is the path serving central Texas.

6. **Many OSM_XXXX endpoints** in the binding list are unnamed nodes that were NOT synthetic split points (is_split=False) but are simply OSM nodes that lacked a substation name in the source data. They represent real junctions where name lookup failed — the branches themselves are physically real.

7. **Next experiment:** `no-spl+hicks2x` — double only Hicks→Willow Creek to 2,400 MVA, test if NORTH congestion resolves. Simultaneously consider Houston 345 kV: Meadow→Oasis, Cedar Bayou, Wharton→North Belt may be double-circuit (check OSM cables tags).

---

### no-spl+load-fix — Load restricted to named non-plant substations (2026-03-19)

**Platform:** Princeton Adroit, Gurobi
**Adroit job:** 3030392_3 (array task 3)
**sced_inputs basis:** v5 network; NO_SPL_CAP=1 + LOAD_NAMED_ONLY=1
**SLURM script:** `Realist/ERCOT/run_sced_array.slurm`

**What changed from no-spl-cap:**
- `LOAD_NAMED_ONLY=1` env var: `distribute_load()` now excludes buses where `Bus Name` starts with `OSM_` (unnamed geographic waypoints) or contains `_Plant` (generation substations) from receiving MW load.
- All other settings identical to no-spl-cap.

**Key metrics:**
- Hour 0 load shed: 3,411 MW
- Steady-state shed (h9-23 avg): 3,411 MW
- Renewable curtailment: 11,593 MW
- Renewables dispatched: ~8,225 MW (41.5%)
- System price: $20.47/MWh
- Runtime: 224 seconds

**Binding branches:** 35 total — 6 at 345 kV (same as no-spl-cap), 29 at 138 kV (up from 27).
- 15 NEW 138 kV bindings in NORTH DFW (North Lake→Coppell, Shiloh→Marquis, Walnut→Apollo, Fairdale→Brand, Mesquite→Lawson Road, Mesquite→East Mesquite, Richardson Woodhaven→OSM, etc.) and WEST (Westover→Amoco South Foster).
- 12 RESOLVED 138 kV bindings (mostly OSM_→OSM_ segments in north DFW that previously received load).

**Interpretation: Load fix made things worse (2,180 → 3,411 MW shed).** Removing load from unnamed OSM nodes redistributed that MW to named substations. Named substations in NORTH are concentrated in specific DFW neighborhoods (Mesquite, Coppell, Richardson, Shiloh, North Lake) rather than spread across the grid. This concentrates load in areas that are already congested, adding 15 new binding 138 kV links in those neighborhoods while resolving 12 elsewhere.

**Key takeaway:** Many unnamed `OSM_XXXX` nodes are likely legitimate distribution substations that simply lack OSM name tags. Excluding them does not improve load realism — it worsens spatial coverage. The `LOAD_NAMED_ONLY` filter is not the right approach; the underlying issue is OSM data completeness, not the filtering logic.

---

### no-spl+hv2x — Double all 345 kV branch ratings (2026-03-19)

**Platform:** Princeton Adroit, Gurobi
**Adroit job:** 3030392_4 (array task 4)
**sced_inputs basis:** v5 network; NO_SPL_CAP=1 + SCALE_345KV=2
**SLURM script:** `Realist/ERCOT/run_sced_array.slurm`

**What changed from no-spl-cap:**
- `SCALE_345KV=2` env var: all branches with Cont Rating ≥ 1,000 MVA and < 999,000 MVA (i.e., 345 kV real-substation branches) doubled. 345 kV single-circuit (1,200 MVA) → 2,400 MVA; 345 kV double-circuit (2,400 MVA) → 4,800 MVA; 500 kV (2,000 MVA) → 4,000 MVA.
- SPL-connected branches still set to 999,999 MVA.

**Key metrics:**
- Hour 0 load shed: 2,033 MW
- Steady-state shed (h9-23 avg): 2,033 MW
- Renewable curtailment: 11,618 MW
- Renewables dispatched: ~8,200 MW (41.4%)
- System price: $21.91/MWh
- Runtime: 207 seconds

**Binding branches:** 31 total — **0 at 345 kV** (all cleared!), 31 at 138 kV (up from 27).
- 6 NEW 138 kV bindings vs no-spl-cap (OSM_2770→OSM_2771, OSM_2771→OSM_2772, OSM_2788→OSM_2790, OSM_2345→OSM_2790, OSM_2367→OSM_2371, Clodine→Roark).
- Only 1 RESOLVED 138 kV binding (L799_931, Center Point→Reno).

**Interpretation:** Doubling 345 kV ratings fully clears all 345 kV congestion. Load shed reduces only modestly (2,180 → 2,033 MW, -7%) because the bottleneck shifts entirely to the 138 kV network. In fact, freeing up the 345 kV backbone causes MORE power to flow into the 138 kV distribution network, binding 6 additional 138 kV lines that were previously not stressed. This is physically expected (relaxing upstream constraints can worsen downstream overloads).

**Key finding: The remaining ~2,000 MW of load shedding is driven entirely by the 138 kV urban DFW network.** Neither load redistribution nor 345 kV uprating resolves it. The 138 kV urban NORTH lines (OSM_2770→2771, OSM_2788→2789, etc. — mostly in the DFW urban core) are the true binding constraint. The next question is whether these 300 MVA 138 kV ratings are defensible or underrated (cables tag completeness for urban DFW lines).

---

### no-spl+138kv2x — Double all 138 kV branch ratings (2026-03-19)

**Platform:** Princeton Adroit, Gurobi
**Adroit job:** 3030435_5 (array task 5)
**sced_inputs basis:** v5 network; NO_SPL_CAP=1 + SCALE_138KV=2
**SLURM script:** `Realist/ERCOT/run_sced_array.slurm`

**What changed from no-spl-cap:**
- `SCALE_138KV=2` env var: all branches with Cont Rating in [100, 1000) MVA doubled. 138 kV single-circuit (300 MVA) → 600 MVA; 138 kV double-circuit (600 MVA) → 1,200 MVA.
- 345 kV branches unchanged (still at cables-based ratings).
- SPL-connected branches still 999,999 MVA.

**Key metrics:**
- Hour 0 load shed: 136 MW
- Steady-state shed (h9-23 avg): 136 MW
- Renewable curtailment: 6,393 MW
- Renewables dispatched: ~13,425 MW (67.7% of 19,818 MW available)
- System price: $19.57/MWh
- Runtime: 166 seconds

**Interpretation: Near-complete resolution. Doubling 138 kV ratings reduces load shed from 2,180 MW → 136 MW (94% reduction), effectively eliminating the intra-zone 138 kV congestion that was the primary bottleneck.**

Renewables utilization jumps from 47% → 68%: the freed-up 138 kV network can now deliver wind and solar to load, dramatically reducing curtailment (10,490 → 6,393 MW). The remaining 136 MW of shed is a residual — likely a handful of locally isolated substations or very short segments still binding.

Price drops from $21.13 to $19.57/MWh. Without 138 kV congestion, cheaper generation (wind + nuclear) displaces more expensive gas, lowering the marginal cost.

**Key finding: The 138 kV OSM cables tags are systematically underrated.** OSM defaults to single-circuit (cables=3 → 300 MVA) for most 138 kV lines, but the actual ERCOT urban network uses predominantly double-circuit conductors (or bundled conductors with higher ratings). The correct default for the 138 kV tier in urban Texas is likely 600 MVA, not 300 MVA. This should be propagated back to `build_osm_branch_table.py` as the new cables-based default.

**Next steps:**
1. Update `build_osm_branch_table.py` to use 600 MVA/circuit as the 138 kV base rating (instead of 300 MVA), regenerate `branch.csv`, push to adroit, and confirm results match `no-spl+138kv2x`.
2. Investigate the residual 136 MW — which lines are still binding, and are they also underrated?
3. Begin Phase 3: hourly load + real offer curves on this network configuration.

---

### clean-build — Baked-in fixes, rebuilt branch.csv (2026-03-20)

**Platform:** Princeton Adroit, Gurobi
**Adroit job:** 3033672_7 (array task 7)
**sced_inputs basis:** v5 bus/gen tables; branch.csv **rebuilt** from updated build_osm_branch_table.py
**SLURM script:** `Realist/ERCOT/run_sced_array.slurm`

**What changed from best-so-far:**
- `build_osm_branch_table.py` updated: VOLTAGE_TIERS now 138 kV = 600 MVA/circuit (was 300 MVA)
- SPL branch unconstrain (→999,999 MVA) now permanent post-processing in build script (was NO_SPL_CAP=1 runtime)
- Plant outlet + stub unconstrain now permanent with 1.0 km threshold (was NO_PLANT_CAP=1 at 0.5 km runtime)
- No runtime env var patches — all fixes baked into branch.csv at build time

**Build output:**
- 2,575 branches at 600 MVA (previously 300 MVA — 138 kV single-circuit correction)
- 2,438 SPL branches unconstrained; 218 plant outlet/stub branches unconstrained (35 _Plant, 824 < 1 km)
- Total 2,656 branches at 999,999 MVA

**Key metrics:**
- Hour 0 load shed: 81.7 MW
- Steady-state shed (h0-23 avg): 81.7 MW (flat — constant load/CFs)
- Renewable curtailment: 9,048 MW
- Renewables dispatched: 10,770 MW (54.3% of 19,818 MW available)
- System price: $21.31/MWh
- Runtime: 159 seconds

**Interpretation:**
Clean-build is equivalent to best-so-far (87 MW → 81.7 MW; within numerical tolerance).
The baked-in fixes work correctly. The small difference (5 MW improvement in shedding, 874 MW
increase in curtailment) is due to the 1.0 km vs 0.5 km stub threshold — more stubs unconstrained
in the baked-in version, shifting the optimizer's preferred routing slightly.

This is now the canonical baseline branch.csv. Runtime env vars NO_SPL_CAP and NO_PLANT_CAP are
no longer needed for baseline runs. SCALE_138KV env var is also obsolete.

---

## How to Add a New Experiment

1. Run the experiment on adroit. Note the job ID.
2. Pull results: `scp -r adroit:/scratch/network/js0735/dartboard/sced_inputs_<TAG>/results_<TAG>/ results/<TAG>/`
   - Must contain at minimum: `hourly_summary.csv`, `bus_detail.csv`, `line_detail.csv`
3. Add a row to the Quick Reference table above.
4. Add a Detailed Entry following the template below.
5. Use the diagnostic engine to inspect:
   ```bash
   # Quick terminal summary of new experiment vs existing
   python build_diagnostics.py compare --tags <TAG> v3-j17-t135f-r15

   # Load into the interactive visualizer (swap in for one of the 5 slots)
   python build_diagnostics.py build --tags <TAG> v3-j17-t135f-r15 v3-nov5-t135f-r15 val-aug20 val-apr13
   # → open diagnostics.html: Map tab for geographic view, Scorecard tab for comparison
   ```
6. (Optional) Run `python compare.py` to regenerate `comparison_summary.csv` (all experiments).

### Entry template

```
### <tag> — <one-line description> (<date>)

**Platform:** [local | adroit], [CBC | Gurobi]
**Adroit job:** <job ID or N/A>
**sced_inputs basis:** <which scripts/version generated bus.csv, branch.csv, gen.csv>
**SLURM script:** <path if applicable>

**What changed from <previous tag>:**
- <explicit change 1>
- <explicit change 2>

**Key metrics:**
- Hour 0 load shed: X MW
- Steady-state shed (h9-23 avg): X MW
- Renewable curtailment: X MW
- Renewables dispatched: X MW (X% of available)
- System price: $X/MWh
- Runtime: X seconds

**Interpretation:** <what did we learn>
```
