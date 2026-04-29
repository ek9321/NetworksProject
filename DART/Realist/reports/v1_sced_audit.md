# v.1 SCED Audit Report
**Date:** 2026-03-05
**Simulation:** Vatic DC-SCED, 2025-11-05, 24 hours
**Auditor:** Claude Code

---

## Executive Summary

The v.1 run completed successfully, but shows persistent load shedding (~8,600 MW in steady state) alongside ~13,500 MW of simultaneous renewable curtailment. This is not a generation capacity problem — we have 101,342 MW of modeled PMax against 50,894 MW of demand, and every zone has a substantial surplus. The problem is network delivery.

Three issues, in order of impact:

1. **108 transmission lines are binding at their thermal limit in every steady-state hour.** They are overwhelmingly 138 kV lines at the 300 MVA flat default. This creates a grid of narrow pipes that prevents renewable energy from reaching load buses. Whether 300 MVA is too conservative for ERCOT 138 kV is our deepest uncertainty — and the single most impactful assumption to test.

2. **Cold-start binding constraints cause hours 0–7 to be artificially bad.** All non-nuclear thermal units start with `UnitOnT0State = -1`, triggering minimum down-time lockouts. This is a one-line fix in `build_gen_table.py` and has no bearing on the steady-state problem.

3. **Generator matching is essentially complete** — contrary to the hypothesis in the v.1 diagnosis. 97–100% of all fuel types matched to OSM buses. This is not a contributing factor to load shedding.

The v.2 path is: fix cold-start (easy), then run a branch rating sensitivity study on the 138 kV flat limit before deciding whether to raise it. Details below.

---

## Section 1 — Generator Audit

### 1.1 Match Rate by Fuel

All major fuel types achieved near-complete matching against MORA. The unmatched-generator hypothesis from the v.1 diagnosis was wrong.

| MORA Fuel | MORA Units | MORA MW | gen.csv Group | gen.csv Units | Match % |
|---|---|---|---|---|---|
| SOLAR | 333 | 37,968 | Solar | 323 | 97% |
| GAS-CC | 187 | 37,009 | Gas-CC | 187 | 100% |
| WIND-O/C/P | 384 | 40,534 | Wind | 377 | ~98% |
| COAL | 21 | 14,713 | Coal | 21 | 100% |
| GAS-ST | 37 | 10,624 | Gas-ST | 37 | 100% |
| GAS-GT | 148 | 10,347 | Gas-GT | 148 | 100% |
| NUCLEAR | 4 | 5,268 | Nuclear | 4 | 100% |
| GAS-IC | 26 | 1,128 | Gas-IC | 26 | 100% |
| HYDRO/BIOMASS/DIESEL/OTHER | 51 | 2,434 | various | 51 | 100% |

**Total: 1,174 of ~1,191 non-storage units matched (99%).**

The 17-unit shortfall is entirely within Wind (~7 units) and Solar (~10 units). These are small and represent <1% of installed nameplate. They are not causing the shedding.

### 1.2 Capacity by Zone (gen.csv PMax vs modeled load)

| Zone | gen.csv PMax | Modeled Load | Surplus |
|---|---|---|---|
| NORTH | 35,390 MW | 23,000 MW | +12,390 MW |
| SOUTH | 31,780 MW | 10,500 MW | +21,280 MW |
| WEST | 18,083 MW | 7,000 MW | +11,083 MW |
| HOUSTON | 16,089 MW | 11,500 MW | +4,589 MW |

Every zone has a large surplus. Supply is not the problem.

### 1.3 Zone Composition of gen.csv PMax

| Zone | Coal | Gas | Nuclear | Solar | Wind |
|---|---|---|---|---|---|
| NORTH | 7,720 | 23,299 | 2,538 | 599 | 1,234 |
| SOUTH | 4,257 | 19,983 | 2,730 | 519 | 4,290 |
| WEST | 0 | 5,049 | 0 | 605 | 12,428 |
| HOUSTON | 2,737 | 13,211 | 0 | 142 | 0 |

WEST is almost entirely wind + gas. With 12,428 MW of wind PMax (after 0.45 CF applied) and only 7,000 MW of local load, WEST needs to export ~11,000 MW to be uncongested. Whether the network can carry that export is the central question.

**Note on MORA zone labels:** MORA uses weather zones (NORTH, SOUTH, WEST, HOUSTON, COASTAL, PANHANDLE) which differ from ERCOT pricing zones. COASTAL (14,237 MW) and PANHANDLE (7,535 MW) generators are being assigned to ERCOT pricing zones by the Stage 3/4 bus snap, which places them based on OSM substation proximity. Those 21,772 MW of COASTAL/PANHANDLE capacity appear in the table above, distributed across our four zones. There is no systematic loss of capacity here, but the geographic placement of individual units within those groups is less precise than for units matched via Stages 1–2.

---

## Section 2 — Branch Rating Audit

### 2.1 Network Composition

| Type | Count | % | Notes |
|---|---|---|---|
| Same-voltage lines | 4,063 | 90.3% | OSM transmission segments |
| Mixed-voltage (transformers) | 438 | 9.7% | Connect 345 kV to 138 kV backbone |

**Total: 4,501 branches** (4,656 in the visualizer; the difference is branches that connect to nodes outside the largest connected component and were dropped by `build_osm_branch_table.py`).

### 2.2 Lines by Voltage Tier

| kV | Count | Flat Rating | Avg Rating | Avg Implied Length |
|---|---|---|---|---|
| 345 kV (lines only) | 986 | 1,200 MVA | 1,200 MVA | 21 km (median) |
| 230 kV (lines only) | 58 | 600 MVA | 600 MVA | — |
| 138 kV (lines only) | 3,063 | 300 MVA | 300 MVA | 3.9 km (median) |

Implied lengths are computed from X (p.u.) using standard overhead resistivity: 0.000269 p.u./km at 345 kV, 0.001995 p.u./km at 138 kV. The 138 kV median of 3.9 km is short but plausible for urban/suburban sub-transmission in Texas.

### 2.3 Transformer Branches (438 total)

Branches where from_kv ≠ to_kv represent transformers. The model treats them as lines in the DC formulation.

| kV Pair | Count | Avg Rating | Total MVA |
|---|---|---|---|
| 345 → 138 | 252 | 379 MVA | 95,400 MVA |
| 138 → 345 | 147 | 514 MVA | 75,600 MVA |
| 138 → 230 | 18 | 300 MVA | 5,400 MVA |
| 230 → 345 | 2 | 600 MVA | 1,200 MVA |
| others | 19 | varies | — |

The 345→138 transformers have avg 379 MVA — lower than typical large ERCOT 345/138 kV power transformers (which are commonly 400–750 MVA per bank). These transformers are the gateways between the 345 kV backbone and the 138 kV distribution mesh where load buses sit. If they are systematically underrated, they constrain the delivery of bulk power to load buses even when 345 kV lines are not binding.

### 2.4 Inter-Zone Capacity

| Corridor | 345 kV | 138 kV | Total MVA |
|---|---|---|---|
| NORTH ↔ WEST | 8,400 MVA (7 lines) | 1,200 MVA (4 lines) | 9,600 MVA |
| NORTH ↔ SOUTH | 5,100 MVA (5 lines) | 3,000 MVA (10 lines) | 8,100 MVA |
| HOUSTON ↔ SOUTH | 4,800 MVA (4 lines) | 1,800 MVA (6 lines) | 6,600 MVA |
| HOUSTON ↔ NORTH | 4,200 MVA (4 lines) | 600 MVA (2 lines) | 4,800 MVA |
| SOUTH ↔ WEST | 3,600 MVA (3 lines) | 900 MVA (3 lines) | 4,500 MVA |

The inter-zone numbers look plausible at the headline level. NORTH↔WEST at 9,600 MVA can theoretically carry the ~11,000 MW WEST surplus. The problem is not here.

**However:** these inter-zone branches only count because we can identify zone boundary crossings from bus zone labels. Many OSM 345 kV lines that physically cross zone boundaries may have both endpoints snapping to buses on the same side of the boundary, making them appear intra-zone when they are inter-zone in reality. This is an invisible undercount that the inter-zone numbers cannot detect.

---

## Section 3 — Congestion Analysis

### 3.1 Binding Lines in v.1

| Hour | Binding Lines (≥95% loaded) |
|---|---|
| 0 | 39 |
| 1–3 | 56–78 |
| 4–8 | 106–110 |
| **9–23** | **108 (constant)** |

**108 branches are simultaneously at their thermal limit in every steady-state hour.** This is the source of the persistent 8,621 MW load shedding.

The binding lines in hour 0 (sample):

| Line | Flow (MW) | Rating (MVA) | kV | Zone |
|---|---|---|---|---|
| L53_684 | −300 | 300 | 138 | WEST |
| L1625_1919 | 1,200 | 1,200 | 345 | NORTH |
| L643_644 | −1,200 | 1,200 | 345 | SOUTH |
| L2547_4268 | −300 | 300 | 138 | NORTH |
| L3035_4078 | 300 | 300 | 138 | NORTH |
| L1628_4268 | 300 | 300 | 345 | NORTH |

The binding lines are overwhelmingly **138 kV intra-zone lines**, all hitting the 300 MVA flat limit. A handful of 345 kV lines also bind, but those appear to be the 345 kV lines with suspicious 300 MVA ratings that were identified in Section 2.3 as likely transformer connections.

### 3.2 The Simultaneous Curtailment + Shedding Pattern

In hours 9–23:
- **Renewable curtailment:** 13,543 MW
- **Load shedding:** 8,622 MW
- **OverGeneration:** 610 MW

This is physically coherent: wind generation in WEST and renewable-heavy sub-regions is hitting intra-zone 138 kV limits before it can reach the 345 kV export backbone. Load in other zones is simultaneously going unserved because the inter-zone flows are constrained by the same 138 kV bottlenecks on the receiving end.

The 13,543 MW curtailment is large relative to the 19,818 MW of total available renewable capacity (68%). This says the 138 kV network in renewable-heavy zones (particularly WEST, where 12,428 MW of wind PMax is co-located with only 7,000 MW of local load) is far too constrained for the generation density we are modeling.

### 3.3 Root Cause Attribution

| Cause | Hours affected | MW effect | Confidence |
|---|---|---|---|
| Cold-start thermal (UnitOnT0State = −1) | 0–7 | +5,000–18,600 MW incremental | High |
| 138 kV line ratings too conservative | 4–23 (persistent) | ~8,600 MW sustained shedding | Medium |
| 345 kV intra-zone lines with 300 MVA rating (should be 1,200 MVA) | 4–23 | contributes to binding set | Medium |
| Constant load / constant renewables | all | distorts optimal dispatch timing | High |

---

## Section 4 — Uncertainty Assessment

### 4.1 What We Know

- **Voltage:** OSM tags are reliable for major ERCOT transmission. 345/230/138 kV lines are correctly identified.
- **Topology:** Connectivity is well-captured for major substations. Junction detection at 150 m radius is validated against the HV layer.
- **Generator data:** MORA is ERCOT's public resource adequacy report. Nameplate MW is accurate.
- **Generator placement:** 97–100% match rate achieved; geographic precision varies by stage (Stage 1 exact, Stage 4 county centroid ±50 km).

### 4.2 What We Do Not Know

- **138 kV line thermal ratings:** This is the dominant uncertainty. ERCOT's actual ratings are non-public (CEII). The 300 MVA flat default is reasonable for a typical single-circuit ERCOT 138 kV line, but:
  - ERCOT double-circuit 138 kV lines are commonly rated 500–700 MVA.
  - OSM does not tag single vs double circuit.
  - A factor-of-2 error here directly produces a factor-of-2 error in 138 kV network throughput.

- **345 kV line circuit configuration:** Similarly, 1,200 MVA is conservative for a double-circuit ERCOT 345 kV line (real ratings can reach 1,800–2,000 MVA per circuit pair). But 345 kV is binding much less often than 138 kV in this run.

- **Transformer ratings:** 438 transformer branches have ratings assigned from voltage tier defaults, not from nameplate data. The 345→138 kV group at avg 379 MVA per transformer may be underrated by 50–100%.

- **OSM completeness for 138 kV:** OSM is known to be less complete for sub-transmission (138 kV) than for bulk transmission (345 kV). Missing parallel circuits create phantom bottlenecks. There is no easy way to quantify this without ERCOT's non-public network model.

### 4.3 Sensitivity Framework

The single most informative experiment is a branch rating sensitivity study on the 138 kV tier:

| Scenario | 138 kV Rating | Expected Shedding |
|---|---|---|
| v.1 (current) | 300 MVA | ~8,600 MW |
| v.2 test A | 600 MVA | unknown — test this |
| v.2 test B | unconstrained (remove limits) | floor case: shows how much shedding is cold-start vs congestion |

If test B (no branch limits) still shows shedding, the cold-start fix is needed first. If test B eliminates shedding, then the branch rating is the entire problem.

---

## Section 5 — Fix Priority and Effort Assessment

| Fix | File | Effort | Expected Impact |
|---|---|---|---|
| Warm-start thermal units | `build_gen_table.py` line ~725 | 5 min | Eliminates hours 0–7 shedding spike |
| Hourly load profile | `run_sced.py` `ZONE_LOAD_MW` dict | 1 hr | Reduces overnight overload, fixes dispatch timing |
| Hourly wind/solar profiles | `run_sced.py` `create_timeseries` | 2 hrs | Eliminates solar-at-night, fixes daily renewable pattern |
| 138 kV sensitivity test | `build_osm_branch_table.py` rating constant | 15 min | Directly reveals whether 300 MVA is the binding assumption |
| Fix 345 kV lines misrated at 300 MVA | `build_osm_branch_table.py` transformer logic | 1 hr | Removes false 345 kV constraints |
| Improve transformer rating assignment | `build_osm_branch_table.py` | 2 hrs | Marginal; 438 transformers, most not binding |
| OSM 138 kV completeness | fundamental data gap | weeks | Cannot fix without additional data sources |

### Recommended v.2 sequence

1. Apply warm-start fix (5 min).
2. Add hourly load + renewable profiles (3 hrs).
3. Re-run with 600 MVA for 138 kV lines as sensitivity test A.
4. Re-run with no branch limits as floor case test B.
5. Compare: if sensitivity A eliminates most shedding, 300 MVA is the dominant assumption and should be documented but kept as a conservative default with explicit sensitivity caveat. If floor case B still shows shedding after warm-start fix, something else is wrong (network islands, disconnected load buses, etc.) and needs investigation.

---

## Appendix: Key Numbers

| Metric | Value |
|---|---|
| Buses | 3,878 |
| Branches | 4,501 |
| Generators | 1,174 |
| Total gen PMax | 101,342 MW |
| System demand (constant v.1) | 50,894 MW |
| Demand/PMax ratio | 0.50 |
| Steady-state load shedding | 8,622 MW (17% of demand) |
| Steady-state curtailment | 13,543 MW (68% of renewable PMax) |
| Binding lines (steady state) | 108 / 4,501 (2.4%) |
| Lines at exactly 300 MW (138 kV flat limit) | dominant in binding set |
| 345 kV lines misrated at 300 MVA | 343 (actually transformer connections) |
| Inter-zone capacity NORTH↔WEST | 9,600 MVA |
| WEST generation surplus | 11,083 MW |
