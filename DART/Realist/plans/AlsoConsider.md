# Also Consider — Gaps and Blind Spots in the DC-SCED Plan

This document is a constructive critique of `buildToSCEDPlan.md`. The plan is solid on data sourcing and pipeline architecture. The gaps below are not objections to the approach — they are decisions that need to be made consciously, because each one has a specific effect on what the model can and cannot reproduce.

Issues are grouped by severity: things that break the model structurally, things that materially bias results, and things worth acknowledging as limitations.

---

## Critical — Structural Issues

### 1. Transformers are missing entirely

The plan builds a branch table from OSM HV lines only. OSM HV lines are single-voltage features — they do not represent the transformers that connect the 345 kV, 138 kV, and 69 kV networks to each other.

Without transformer branches, the three voltage tiers in your model are **electrically disconnected**. Power cannot flow from a West Texas 345 kV wind plant through a 345/138 kV autotransformer to a 138 kV load bus. The PTDF matrix for each voltage island is computed in isolation. This is not a DC approximation — it is a topological error.

The Overbye group found that DC power flow missed nearly 50% of binding constraints identified by AC power flow on a 12,965-bus Midwest model. Incorrect transformer representation is a primary driver of that gap. The West Texas Export constraint — responsible for 22% of all ERCOT curtailment — involves multiple 345/138 kV autotransformers.

**No public dataset provides ERCOT transformer parameters.** Workarounds used in academic models:
- Assign synthetic transformer branches at every substation where ≥2 voltage levels appear in OSM within 500 m of each other
- Use standard autotransformer reactances: X ≈ 0.10–0.15 p.u. (series), tap = voltage ratio
- This is imprecise but far better than disconnected voltage islands

ERCOT's Modeling Guidelines (v0.06, 2009) describe the required data fields; the parameters themselves are not public.

---

### 2. Wind and solar are not fixed injections in SCED — and treating them as such prevents the model from producing its most interesting output

The plan sets `PMax = installed_mw` and `PMin = 0` for wind/solar and treats them as non-dispatchable. ERCOT's actual SCED does not work this way.

ERCOT classifies wind and solar as Intermittent Renewable Resources (IRRs) and dispatches them with a Base Point every 5 minutes. IRRs can be curtailed — instructed below their available output — by either economic offer or transmission constraint. In 2024, ERCOT curtailed **over 8 TWh** of renewable generation, averaging **1.2 GW continuously throughout the year**. 74% of that curtailment was transmission-driven, with West Texas alone accounting for 5.3 TWh.

A model that treats renewables as fixed injections **cannot reproduce curtailment, cannot produce negative LMPs, and systematically misrepresents West Texas node prices** in any hour with significant wind generation. It also means you cannot use the ERCOT 60-Day SCED Disclosure Reports (NP3-965-ER) — which publish High Dispatch Limit (HDL) and Base Point (BP) for every resource — as a validation target, because your model has no concept of the HDL–BP gap that those reports measure.

**The fix:** Treat wind and solar as dispatchable with `PMin = 0`, `PMax = actual_available_output_for_that_hour` (sourced from ERCOT's real-time wind/solar generation data, NP4-126-M). For a single-period run, replace `installed_mw` with the actual generation at your chosen timestamp. ERCOT publishes hourly aggregated wind and solar output publicly.

Typical capacity factors to expect:
- Wind (system-wide annual average): ~34%; range by plant: 20–54%
- Solar (system-wide annual average): ~23%; range by plant: 22–31%
- Diurnal and seasonal variability is large: a West Texas wind farm at 3 AM in spring runs at 2–3× its summer afternoon output

---

### 3. Single-period SCED for storage is not a storage model

The plan dispatches BESS as a generator with 0 marginal cost in each 5-minute interval. Single-period optimization has no awareness of future prices and no state-of-charge tracking across intervals. The consequences:

- The battery discharges at the first available positive-price window regardless of whether higher prices are coming later
- It cannot "save" capacity for the 6 PM peak if it discharged at 5 PM
- It reaches full or empty state prematurely and sits idle during economically significant windows
- The model is indistinguishable from a peaker with a 0 fuel cost — it tells you nothing about storage's actual dispatch pattern

CAISO implements a 65-minute look-ahead (13 intervals) in its 5-minute SCED specifically because, as CAISO states, "given that storage resources are energy limited, the multi-interval optimization is essential to ensuring that inter-temporal conditions are factored into battery schedules." A recent IEEE paper (Zheng et al., 2022, arXiv:2207.07221) found that existing single-period bidding models understate storage profit by 10–56% versus SoC-aware dispatch.

The minimum look-ahead needed to capture BESS arbitrage on a 2-hour battery against a daily peak cycle is **4–8 hours**. A 24-hour horizon is needed to fully co-optimize arbitrage with ancillary service provision.

**The question to answer before proceeding:** is the goal to model BESS behavior accurately, or to include BESS as a placeholder that contributes the right MW capacity to the network? If the latter, acknowledge it explicitly and flag that BESS dispatch results are not meaningful.

---

## Significant — Materially Biases Results

### 4. BESS duration assumption is too high, not conservative

The plan assumes 2-hour duration as a "conservative" default. The actual ERCOT fleet average as of early 2026 is **1.65 hours**, because a large portion of pre-2024 systems were built at 1-hour duration specifically for Non-Spin and ancillary service revenue where energy capacity doesn't matter.

Composition of the operational fleet (~13.9 GW / 22.9 GWh entering 2026):
- ~65% 1-hour systems (older fleet)
- ~30% 2-hour systems (2024–2025 builds)
- ~5% longer (4-hour outliers: Alamo City 120 MW, Ferdinand 200 MW in Bexar County)

The 2-hour default overstates fleet energy capacity by roughly 21% relative to the actual 1.65-hour average. If you want to be conservative about BESS energy availability, 1.5 hours is closer to reality than 2.

---

### 5. DC ties are missing — 1.1 GW energy imbalance

ERCOT has five DC interconnections that are treated as fixed schedule injections in operational SCED. Omitting them leaves ~1.1 GW of net power unaccounted for in the energy balance:

| Tie | Location | Capacity |
|-----|----------|----------|
| DC_N | Oklaunion, TX (SPP) | 220 MW |
| DC_E | Monticello, TX (SPP/SWEPCO) | 600 MW |
| Eagle Pass | Eagle Pass, TX (CFE) | 36 MW |
| McAllen | Near McAllen, TX (CFE) | 150 MW |
| Laredo VFT | Near Laredo, TX (CFE) | 100 MW |

In DC-SCED models, these are modeled as fixed MW injections/withdrawals at specific buses — not subject to SCED dispatch. ERCOT publishes real-time DC tie flows publicly. The DC_E tie at 600 MW is large enough that its omission produces visible LMP errors in Northeast Texas.

---

### 6. Uniform intra-zone load distribution produces wrong spatial LMP gradients

The plan acknowledges this gap but understates its consequence. Distributing zonal load equally across all buses within a zone means:
- Dallas/Fort Worth, Houston, and Austin — which account for the majority of Texas load — get the same load per bus as sparsely populated West Texas buses
- The model produces no load-driven east–west LMP gradient
- Congestion rents on the West Texas Export constraint are driven entirely by generation-side injection, with no load-side pull

The published academic standard (Overbye/Texas A&M group, Birchfield et al.) is population-weighted allocation using Census zip-code data. ERCOT itself publishes Load Distribution Factors (LDFs, NP4-159-CD) that allocate zonal load to individual electrical buses based on historical metered consumption — these are the exact data product for this purpose and they are available through the ERCOT market portal.

---

### 7. OSM topology is incomplete for recent Permian Basin build-out

The plan uses OSM HV lines as the sole source of network topology. OSM transmission coverage for Texas is better than most U.S. regions but has known gaps:
- No quantitative completeness study exists at the circuit-mile level for Texas specifically
- ERCOT's ~46,500 circuit miles of transmission include a significant 2022–2025 Permian Basin expansion (Project DE-RACE and related 345 kV builds) that is unlikely to be in OSM
- Short spur lines to generation points — exactly the lines that determine whether a generator can reach a named bus in your topology — are systematically under-represented
- Subtransmission (69 kV) is largely absent

The EIA HIFLD "U.S. Electric Power Transmission Lines" dataset (public, ArcGIS Hub) provides a cross-check. Comparing OSM against HIFLD for Texas would reveal which major corridors are missing before you build the branch table. Missing lines suppress binding constraints, which in turn suppresses congestion LMP components and curtailment events.

---

## Worth Acknowledging — Model Boundary Conditions

### 8. The reference bus choice affects every nodal LMP

DC power flow requires a slack bus. The plan designates "the highest-degree bus, or HB_BUSAVG's Bus ID." The choice of reference bus shifts the congestion component of every nodal LMP — even when total system energy is correct. ERCOT uses a specific reference bus in its real SCED. If your reference bus differs, your nodal LMP distributions will be offset relative to published ERCOT values even if your total energy price matches.

For validation purposes, this matters: you can correct for reference bus mismatch analytically by re-referencing published ERCOT LMPs to your chosen slack bus, but you need to be aware this is what's needed.

### 9. Operating Reserve Demand Curve (ORDC) adder is absent

ERCOT adds a real-time scarcity adder to all energy prices via the ORDC, based on the probability of load shed given current reserves. In scarcity conditions this adder has exceeded $3,000/MWh. During the summer of 2023, real-time LMPs were "significantly higher than previous years even when reserves were not scarce," partly driven by ORDC behavior. A DC-SCED without ORDC cannot reproduce price spikes or near-scarcity pricing. Flag this as a scope limitation.

### 10. Demand response (CLR) capacity is small but location-specific

ERCOT had approximately 940 MW of registered Controllable Load Resources (CLRs) as of spring 2023, concentrated in industrial loads in the Houston area (refineries, petrochemicals). Omitting them modestly overestimates peak Houston-zone LMPs. This is not a critical gap, but worth noting if the goal is to compare model outputs against published zonal prices.

---

## Validation Strategy — What to Compare Against

The plan mentions comparing shadow prices against `ERCOT_SCED_Shadowprices.csv`. A more complete validation ladder, in increasing specificity:

1. **Zonal LMP spreads** — compare model's West, North, South, Houston zone prices against ERCOT's published 15-min SPPs (NP6-788-CD, already in this repo's pipeline). The West–North spread is the best single diagnostic: it is driven primarily by the West Texas Export constraint and should be positive in spring/fall high-wind hours.

2. **Nodal LMP distribution** — model's nodal prices should show a bimodal distribution (cheap West Texas generation nodes, expensive load center nodes) matching the general shape of ERCOT's published nodal LMPs.

3. **Binding constraint shadow prices** — ERCOT publishes real-time constraint shadow prices. The West Texas Export constraint (sometimes called the "Competitive Renewable Energy Zone export limit") should bind in your model in any hour you model with high West Texas wind and high system load. If it doesn't bind, your PTDF for that constraint is wrong.

4. **Renewable curtailment check** — if you implement dispatchable renewables, compare your curtailed MW at West Texas nodes against the NP3-965-ER 60-Day SCED Disclosure (HDL − BP = curtailment). This is the most demanding validation and requires the full renewable dispatch implementation.

---

## Summary

| Gap | Severity | Effect |
|-----|----------|--------|
| No transformers | Critical | Voltage levels electrically disconnected; wrong PTDF everywhere |
| Renewables as fixed injection | Critical | No curtailment, no negative LMPs, wrong West Texas prices |
| Single-period BESS dispatch | Critical | Not a storage model; results are meaningless for BESS analysis |
| BESS duration 2 hr (should be ~1.65 hr) | Significant | Overstates fleet energy by ~21% |
| DC ties missing | Significant | ~1.1 GW energy imbalance; LMP errors in NE and South Texas |
| Uniform load distribution | Significant | Wrong spatial LMP gradient; underestimates congestion rents |
| OSM topology gaps | Significant | Missing lines → missing constraints → suppressed congestion |
| Reference bus mismatch | Moderate | Shifts all nodal LMPs relative to ERCOT published values |
| No ORDC adder | Moderate | Cannot reproduce scarcity pricing or near-scarcity spikes |
| No CLR/demand response | Minor | Modestly overestimates peak LMPs in Houston zone |
