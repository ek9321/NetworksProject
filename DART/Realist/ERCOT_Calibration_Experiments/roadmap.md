# Dartboard Realist — Big Picture Roadmap
*Written 2026-03-20. Scope: where is this project, where is it going, what does one month look like?*

---

## Where We Are

The OSM-native Vatic DC-SCED pipeline is working. That's the hard part — it took roughly two months to get here from scratch. The network (4,303 buses, 4,501 branches) is topologically grounded in real ERCOT geography. The solver runs in ~3 minutes on Adroit. The experiment framework (SLURM array, env vars, session logs) is solid enough to iterate quickly.

The calibration trajectory tells the story:

| Milestone | Shed (MW) | What fixed it |
|---|---|---|
| v1 (PSSE buses, cold start) | 27,242 | — |
| v2 (OSM network, warm start) | 2,976 | Cold start was 90% of v1 shed |
| best-so-far | 87 | SPL junctions, 138 kV ratings, plant stubs |
| clean-build | 81.7 | Baked fixes into network builder |
| hv2400 (Nov 5) | 24.1 | 345 kV at double-circuit |
| **June 17 calibration day** | 593–1923 | Real summer load — now the true frontier |

On the **qualitative** side — the thing that matters for this project's scientific value — we've already achieved the key result: WEST LMP < NORTH LMP all 24 hours on a high-wind day. The WESTEX export corridor (Morgan Creek→Tonkawa) is the binding constraint in the model. That's not a toy result. That's the real physics of why West Texas wind is cheap and Dallas power is expensive.

The remaining work is about *magnitudes*. The model currently overshoots shedding by 50–100x on summer peak and LMP spread by 5–80x. Those gaps have known causes.

---

## The Remaining Work Layers

There are four separable layers, roughly in order of importance and tractability:

### Layer 1: Branch Ratings (1–2 sessions, mostly done)

**Status:** Close. The next session implements targeted 345 kV overrides — raising Meadow→Oasis and Wharton→Addicks from 1200 to 2400 MVA while keeping Morgan Creek→Tonkawa at 1200 MVA. This should preserve WESTEX physics while clearing the artificial Houston congestion that's driving $850+/MWh LMPs.

A handful of other binding lines need investigation: L2649_3019 (Houston stub that binds 24/24 — likely an artifact, not a real line), L1518_1691 (Boerne Cico→Talley, SOUTH, binds 17/24 hrs), Alief→Stafford (138 kV, possibly double-circuit). Each of these is a half-session lookup-and-fix.

**Expected outcome:** After targeted overrides + stub cleanup, June 17 shedding probably drops to 100–400 MW range, which is 2–5x actual (actual is 0 MW). The LMP spread structure should resemble ERCOT — WEST cheap, NORTH moderate, HOUSTON higher — even if magnitudes are off.

### Layer 2: Missing Renewable Capacity (2–4 sessions, hardest remaining)

**The gap:** The model has 17,953 MW wind and 1,866 MW solar. ERCOT has ~35 GW wind and ~18 GW solar. We're missing 54% of wind and 90% of solar. On a summer midday, ERCOT is running 20–25 GW solar. Our model runs 1.3 GW. The missing generation forces the dispatch onto expensive gas, inflating prices and causing shedding.

**Why it's hard:** The OSM-to-ERCOT generator matching in `build_gen_table.py` uses name fuzzy matching and geographic snapping. Many ERCOT wind farms are in rural West Texas with inconsistent naming. OSM coverage of generation assets is good for large nuclear/coal/gas plants but spotty for the hundreds of wind farms added in the last decade.

**The fix path:**
1. Audit which EIA-860 wind/solar plants in Texas are absent from our gen.csv
2. Try geographic snapping within 10–15 km (looser threshold than current 5 km)
3. Fall back to adding "ghost" generators at zonal buses to account for unresolvable plants — crude but better than zero

Recovering 10–15 GW of wind in the model is probably achievable. Getting close to full ERCOT capacity requires more careful EIA-860 / ERCOT CDR cross-referencing than we've done.

**Expected outcome if successful:** June 17 shedding could drop to under 100 MW. Curtailment in the WEST zone would increase (matching ERCOT's real curtailment pattern), and WEST LMPs might drop further toward actual values (~$1–5/MWh on high-wind days).

### Layer 3: Generator Offer Curves (2–3 sessions, medium effort)

**Status:** The model currently uses SCED disclosure data from 2025-11-05 for offer curves. We have this file (`sced_disclosure_20251105_gen_resource.csv`). It probably isn't terrible for Nov 5 runs, but for June 17 2024, the generator dispatch stack could be meaningfully different (different committed units, different marginal cost ordering due to gas price changes).

The SCED disclosure for June 17, 2024 is not on the public MIS API (rolled off). Getting it requires either an ERCOT market participant account or a formal data request. Without it, we're limited to using a representative offer curve from a different date.

The offer curve shape is what sets the *level* of LMPs once you fix the congestion pattern. If system marginal cost is $30/MWh in the model but actual was $20/MWh, the LMPs will be 1.5x off even if the network is perfect.

**Practical path:** Use the Nov 5 2025 disclosure curves for all calibration runs until/unless we get June 2024 data. Accept a baseline LMP offset and focus on getting the *spread pattern* right.

### Layer 4: Quantitative LMP Calibration (3–6 sessions, open-ended)

Getting LMPs within 2× of actual on any given day is a hard problem even for ERCOT's own real-time software, because it requires:
- Accurate transmission constraint limits (Hamilton GTC, STP nomogram, WESTEX nomogram — most are proprietary)
- Unit commitment state (which plants are actually committed in advance)
- Actual offer curves for that specific day
- Reserve requirements and ancillary service co-optimization (Vatic does support this)

The model will realistically never match LMPs to within 10–20% without proprietary data. The achievable target is:
- Zone price ordering correct (WEST < NORTH ≈ SOUTH < HOUSTON on high-wind days)
- Zone ratio within 2–3× of actual (WEST/NORTH ≈ 0.05–0.2 actual; we'd be happy with 0.05–0.5)
- Seasonal qualitative differences (summer Houston expensive, winter NORTH expensive in cold events)

---

## The Honest One-Month Forecast

At the current pace — roughly 1–2 meaningful sessions per week, each doing real work — here's what one month looks like:

**Sessions 1–2 (next 2 weeks):** Targeted 345 kV overrides implemented and validated. Stub artifacts removed. June 17 calibration shows WESTEX binding + Houston not pathological. Shedding maybe 150–400 MW. LMP spread present and qualitatively correct. This is a genuine milestone — the model becomes useful for studying congestion patterns even if magnitudes are off.

**Sessions 3–4 (weeks 3–4):** Missing renewables investigation begins. Audit of what wind/solar is in EIA-860 but absent from gen.csv. Maybe 5–10 GW of wind recovered, shedding drops further. A second calibration day (maybe a high-load winter day to contrast) could be added.

**End of month:** A model that:
- Reproduces zone LMP ordering correctly on representative days
- Has load shedding in the tens-of-MW range on Nov 5, maybe 50–200 MW on June 17
- Has WEST/NORTH spread present on high-wind days at 2–5× the actual magnitude (not 80×)
- Can be run for any historical day with `SCED_DATE` + hourly CSVs

That's a useful research artifact. It's not a commercial SCED tool, but it can answer questions like: "how much does the WESTEX export constraint affect West Texas wind economics" and "how does the Houston 345 kV network constrain imports from the north."

**What it won't be in one month:** A quantitatively accurate LMP forecasting tool. Getting LMP magnitudes within 2× of actual requires the offer curve and unit commitment state for specific days, which is either proprietary or buried in ERCOT MIS archives that require a market participant login.

---

## Key Risks

**Renewable capacity recovery might be harder than expected.** If EIA-860 geo-matching at 10–15 km still misses half the wind farms because they're filed under holding company names, we'd need manual curation of the largest missing plants. This could eat a whole session on data wrangling.

**OSM topology gaps.** The network is built from what's in OpenStreetMap, which has uneven coverage. Some real ERCOT transmission lines are simply not in OSM, or are mapped incorrectly. We'd find out when certain binding branches don't exist at the right location. The Nov 5 2024 SCED disclosure file we have is one anchor on what's actually in ERCOT's network — cross-referencing more systematically is future work.

**The WESTEX nomogram is more complex than one line.** The real WESTEX constraint is a nomogram involving multiple lines in the Permian Basin export corridor, not just Morgan Creek→Tonkawa. Our model binds one line, which is good, but the real constraint may involve different facilities under different generation dispatch scenarios. This could cause qualitative errors on days where the binding constraint is a different part of the nomogram.

**Solver degeneracy at low load.** Some early-morning hours on June 17 had suspiciously flat prices ($22/MWh constant). DC-SCED can degenerate when there's excess capacity and the binding constraint is slack — the nodal prices lose physical meaning. This is a modeling artifact, not a network error, but it could obscure valid signals in off-peak hours.

---

## What "Done" Means at Different Ambition Levels

| Level | Criterion | ETA |
|---|---|---|
| **Useful** | Zone LMP ordering correct on 2+ calibration days; shed < 200 MW on Nov 5 | 3–5 sessions |
| **Good** | WEST/NORTH spread within 3× of actual; shed < 50 MW all seasons; renewable capacity within 20% of ERCOT | 2–4 months |
| **Publication-quality** | LMP magnitudes within 2×; validated on 5+ days across seasons; documented assumptions | 4–8 months |
| **Commercial-grade** | Requires proprietary offer curves, actual unit commitment, nomogram data | Not achievable from public sources alone |

The project is currently tracking toward **Useful** within weeks and **Good** within 2–4 months. That's a respectable outcome for a fully open-source, publicly-sourced model of a system as complex as ERCOT.

---

## The Structural Bet

The deepest assumption in this project is that the OSM transmission skeleton — despite being incomplete, rating-approximate, and missing some real circuits — captures enough of the real ERCOT transmission topology that a DC power flow through it produces qualitatively correct congestion patterns. The evidence so far suggests this bet is paying off. The WESTEX result wasn't guaranteed; plenty of power grid models fail to reproduce regional congestion patterns even with more data. Getting it right from OSM data is the scientific contribution, if the model holds up to more calibration days.
