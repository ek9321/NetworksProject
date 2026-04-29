# Research Directions for the Dartboard ERCOT Model

*Compiled March 26, 2026. Based on deep web research into academic literature, industry tools, policy landscape, and potential users.*

---

## Honest Framing: What This Model Is and Isn't

### What it is
- The only **publishable, reproducible, geographically grounded** DC-SCED model of ERCOT
- Built entirely from public data (OSM topology, ERCOT MORA, EIA-860, Vatic solver)
- Reproduces correct qualitative WESTEX congestion pattern (WEST < NORTH LMP ordering)
- 4,268 buses, 5,331 branches, 1,185 generators (160 GW), 289 BESS (17.5 GW)
- V3 topology validated: E/N 1.46 (above real ERCOT 1.31), 81% circuit-km coverage, 13.4% bridge ratio

### What it isn't
- **Not a competitor to commercial tools.** Enverus, Wood Mackenzie, PLEXOS, MarketNSight, Yes Energy all produce more accurate LMP forecasts. They cost $50K–$500K/yr.
- **Not a replacement for CEII.** Market participants (hedge funds, generators, utilities) get ERCOT's actual network model by registering as an IMRE ($500 + NDA) or Market Participant. Some academics get it too.
- **Not accurate on LMP magnitudes.** Our model is 5–80x off on congested hours. Houston LMPs reach $850–$1,291/MWh (actual: ~$20–50). Any hour with shedding triggers $10,000/MWh penalty prices.
- **Not an operations model.** No AC power flow, no transformer modeling, no contingency analysis (N-1/N-2), no real-time topology switching, no sub-hourly dispatch.

### The actual value proposition
**Transparency and accessibility, not accuracy.** This is the only ERCOT grid model that is:
1. Fully open and publishable (no CEII NDA restrictions)
2. Geographically grounded (real OSM coordinates, not generic "Sub_047" IDs)
3. Reproducible (anyone can re-run the pipeline from public data)
4. Capable of producing qualitatively correct congestion patterns

---

## Who Actually Needs This? (Realistic Assessment)

### The CEII access landscape

| Access Level | Who Gets It | What They Get |
|---|---|---|
| Full unredacted model (PSS/E with real names, impedances, transformer taps) | Transmission Service Providers only | Everything |
| Redacted model (generic bus IDs like "Sub_047") | Registered Market Participants, IMREs ($500 + NDA) | Topology but not geography |
| Nothing | Everyone else | Nothing |

**Key insight:** Even Market Participants who have the redacted model **cannot publish analyses derived from it** without risking CEII violations. And the redacted model has generic bus names — mapping congestion to real geography requires additional work. Our model is inherently geographic.

### Tier 1: Genuine unmet need (no better alternative exists)

**Academic researchers publishing ERCOT market papers**
- Cannot use CEII-derived results in publications
- Currently use TAMU synthetic grids (ACTIVSg2000/Texas-7k), which are explicitly "not the real grid" and have no SCED formulation
- ArXiv 2504.06396 explicitly states: "Power grids are classified as CEII and are not publicly accessible" as motivation for synthetic grid work
- Our model lets them publish with real congestion patterns

**International researchers**
- CEII is US-jurisdiction only — requires NDA, security verification, US-based affiliation
- Researchers outside the US studying electricity markets cannot access ERCOT's network model at all
- Significant demand from developing countries (Nigeria, Kenya, Ghana, Ethiopia, ASEAN) for grid modeling methodology

**Journalists investigating grid reliability**
- Cannot sign CEII NDAs that restrict publication
- During Winter Storm Uri investigations, reporters relied on ERCOT's own characterization of grid conditions rather than independent modeling
- Texas Tribune, Houston Chronicle energy desks would benefit

### Tier 2: Useful but have workarounds

**Environmental/consumer advocacy groups**
- **Sierra Club Texas** — Active PUCT intervener on 765 kV transmission proposals. Currently fighting with paper maps while utilities have full PSS/E models. "Hundreds of Texans are already taking the step to formally intervene" on new transmission cases.
- **Energy Justice Network** (energyjustice.net) — Maps pollution sources, needs grid context for siting fights
- **Texas Solar Energy Society** (txses.org) — Covers transmission constraints and CREZ
- Currently use **no model at all** — even a rough one is better than nothing

**PowerLines** (powerlines.org)
- Nonprofit founded by Charles Hua (former Harvard researcher, DOE advisor), launched September 2024
- Mission: modernize utility regulatory system, lower consumer bills, reform PUCs
- Three pillars: smarter planning, better incentives, greater consumer protection
- Coalition: PUC staffers, state legislators, clean energy providers, academics, grassroots groups
- **Honest assessment:** More policy/advocacy than technical. Would use model *outputs* (e.g., independent congestion analysis) rather than running the model. A distribution channel for insights, not a direct user.

**Catalyst Cooperative / PUDL Project** (catalyst.coop)
- Worker-owned cooperative that liberates public utility data for "researchers, activists, journalists, policy makers, and small businesses that might not otherwise be able to afford access"
- Already integrated with PyPSA-USA
- PUDL handles generation/cost data but **has no transmission topology** — our model fills that gap
- Most directly aligned organization for data partnership

**Small developers screening interconnection sites**
- ERCOT queue has 355+ GW of projects waiting
- Small solar/battery developers need grid models to estimate interconnection costs
- LandGate now sells "unmasked CEII" as a commercial product — confirming this is a real market need
- Our model offers a free alternative for rough screening (not detailed studies)

### Tier 3: Would not switch from current tools

- **Hedge funds and generators** — Have CEII + Enverus/WoodMac. Our model offers nothing they don't already have with better accuracy.
- **National labs** — Have CEII access + their own models (ReEDS, etc.).
- **Large utilities** — Are TSPs. Have the full unredacted model.

---

## Research Directions (Ranked by Realism)

### 1. Testbed for Market Design Theory — BEST FIT FOR SIRCAR

**Why it matters:** Sircar's group works on mean field games for energy markets. His July 2025 paper (Hubert, Lolas, Sircar) models renewable capacity expansion via MFG on stylized networks. The EPEC literature on strategic bidding in nodal markets (Hu & Ralph, Operations Research 2007) uses small test cases because realistic grids are proprietary.

**What our model uniquely enables:** Embed Sircar's MFG framework in a SCED with realistic congestion. Instead of a single price, producers in WEST face congested export paths to NORTH/HOUSTON. The mean field equilibrium changes qualitatively when transmission constraints create local market power.

**Concrete paper:** "Mean Field Games on Congested Networks: How Transmission Constraints Shape Renewable Investment Equilibria"

**Key data asset:** ERCOT publishes 60-day lagged SCED offer curves for every generator. You can empirically estimate strategic markup as a function of congestion, then compare to theoretical equilibrium predictions.

**Honest limitation:** Our LMP magnitudes are off, so the game-theoretic analysis would be qualitative (correct congestion geography, approximate price levels) rather than quantitative calibration.

**Feasibility:** HIGH. SCED model exists. MFG layer is Sircar's existing framework. Offer curve data is public.

**Relevant Sircar papers:**
- "A Mean Field Game for Capacity Expansion Modeling" (Hubert, Lolas, Sircar, July 2025)
- "Mean Field Models to Regulate Carbon Emissions in Electricity Production" (Dynamic Games, 2021)
- "Fracking, Renewables & Mean Field Games" (SIAM Review, 2017)

---

### 2. Open Data Descriptor Paper — HIGHEST PUBLICATION PROBABILITY

**Why it matters:** Xiong et al. published "European high-voltage grid extraction from OpenStreetMap" in Nature Scientific Data in 2025. Yang et al. published Alberta grid recovery from OSM (arXiv, April 2025). There is no equivalent for ERCOT or any US ISO.

**What we'd publish:** The pipeline (OSM → bus.csv → branch.csv → gen.csv → SCED), the dataset, validation against ERCOT public statistics (line-miles, generation capacity, zone load), and SCED output samples.

**Honest limitation:** Our model is less mature than PyPSA-Eur's European extraction. V3 topology is validated but V3 SCED hasn't been run yet. We'd need to demonstrate that the v3 topology produces reasonable SCED results at physical ratings before this paper is credible.

**Target venues:**
- Nature Scientific Data (direct precedent: Xiong et al. 2025)
- Applied Energy (PyPSA-Earth published here)

**Feasibility:** MEDIUM-HIGH. Requires V3 SCED validation first.

---

### 3. Public Grid Impact Analysis for Large Loads (Data Centers)

**Why it matters:** ERCOT's large load queue jumped 300% in 2024, reaching 572 GW. Texas SB6 (2025) creates new interconnection rules for data centers. EIA warns data center demand could raise ERCOT prices 79%. Only 17% of substations near viable data center land have positive withdrawal headroom.

**What our model can do:** Place 500 MW–2 GW loads at specific 345 kV buses, re-run SCED, produce a public "headroom map." No public tool does this.

**Who would use it:**
- Sierra Club Texas (intervening on data center transmission cases)
- Journalists covering ERCOT load growth
- Small communities evaluating economic impact of proposed data centers
- City/county planning departments

**Honest limitation:** Our model can identify *which corridors bind* when you add load, but the precise MW threshold will be off because our ratings are approximate. Qualitative screening ("this bus is deeply congested, that one has headroom"), not engineering studies.

**Feasibility:** HIGH. Literally adding load to a bus and re-running.

---

### 4. Transmission Expansion Independent Analysis

**Why it matters:** ERCOT approved $9.4B 765 kV Eastern Backbone (Dec 2025). Full STEP plan is $33B for 2,468 miles. ERCOT claims $172M/yr congestion savings. Sierra Club and hundreds of Texas landowners are intervening. No intervener has an independent grid model.

**What our model enables:** Add proposed 765 kV corridors, re-run SCED, measure congestion rent change. Provide independent (if approximate) verification of ERCOT's cost-benefit claims.

**Who would use it:**
- PUCT interveners (landowners, environmental groups)
- Sierra Club Texas (already fighting these cases)
- State legislators evaluating the $33B investment
- Journalists (Texas Tribune has covered STEP extensively)

**Honest limitation:** Our model can't replicate ERCOT's full planning analysis (AC contingency, dynamic stability, seasonal ratings). We can only assess DC congestion reduction — one component of the cost-benefit case. Still more than what interveners currently have (nothing).

**Feasibility:** MEDIUM. Adding branches is straightforward; 765 kV substations may not exist in OSM yet.

---

### 5. Network Science Publication

**Why it matters:** The complex systems community has never had empirical bridge-ratio data from a real full-scale grid. Everyone uses IEEE test cases or TAMU synthetic networks.

**Key findings to publish:**
- 138 kV network has 66% bridge ratio (tree-like) in v1/v2 → 13.4% in v3
- Voltage-class heterogeneity: 345 kV well-meshed, 138 kV radial
- Houston fragments into 42 disconnected 138 kV islands (connected only through 345 kV backbone)
- Bridge structure predicts SCED binding constraints

**Target venues:** Physical Review E, Network Science (Cambridge), PLOS ONE

**Honest limitation:** This is descriptive/empirical, not a new method. Strong for a short letter-style paper, not a full research article.

**Feasibility:** HIGH. The analysis is already done (v2_grid_summary.md, diagnostic_analysis.md).

---

### 6. AI-for-Science Methodology Paper

**Why it matters:** GridMind, eGridGPT, X-GridAgent all use LLMs to *analyze* existing models. Nobody has used an AI agent to *build* a model from raw data.

**What makes it novel:** The diagnostic loop (floor/2x experiment → SPL isolation → bridge analysis → v3 rewrite) is a case study in AI-assisted research. 60 hours human time vs. estimated months for a postdoc.

**Target venues:** NeurIPS AI4Science workshop, AAAI, interdisciplinary journals

**Honest limitation:** Hard to evaluate scientifically. "I used Claude and it was fast" is an anecdote, not a controlled experiment. Need to frame carefully as a case study with specific metrics (lines of code, experiments run, diagnostic steps, human vs. agent decision points).

**Feasibility:** MEDIUM. Requires careful methodology section. Session logs are the raw material.

---

### 7. CRR/FTR Valuation

**Why it matters:** ERCOT's CRR market has 867 nodes, 375K source-sink combinations. One paper found systematic abnormal returns ("Seeking Alpha in ERCOT's CRR Market," 2023). The iHedge FTR simulator is the main commercial tool — not public.

**What our model could do:** Price top CRR paths under Monte Carlo wind/solar scenarios. Compare to actual auction clearing prices (public ERCOT data).

**Sircar connection:** Optimal CRR portfolio selection under congestion uncertainty is a stochastic optimization/control problem.

**Honest limitation:** CRR valuation requires accurate LMP *differentials*, not just correct ordering. Our magnitudes are 5–80x off. This direction requires significant model improvement first.

**Feasibility:** LOW-MEDIUM. Requires Monte Carlo SCED runs + bus numbering matching + LMP magnitude improvements.

---

### 8. Methodology Transfer to Other ISOs/Countries

**Why it matters:** PyPSA-Earth covers Europe and Africa. No one has demonstrated OSM-to-SCED for a US ISO. The methodology (geometry-based line splitting, generator matching, rating estimation, calibration against market data) is transferable.

**Concrete next step:** NYISO extension (already scoped in `Realist/NYISO/`). NYISO has more complex market structure but worse public data availability.

**International audience:** Researchers in developing countries building grid models. Proving OSM is accurate enough for DC-SCED congestion analysis has global implications.

**Feasibility:** MEDIUM. Requires adapting pipeline to different data formats and zone structures.

---

## Specific Organizations to Contact

| Organization | Contact Point | What They'd Get | Likelihood of Interest |
|---|---|---|---|
| **Catalyst Cooperative** (catalyst.coop) | Greg Schivley, Zane Selvans (founders) | Transmission topology complement to PUDL generation data | HIGH — directly aligned mission |
| **PowerLines** (powerlines.org) | Charles Hua (founder) | Independent congestion analysis for PUC advocacy | MEDIUM — policy-focused, not technical users |
| **Sierra Club Texas** | Clean energy team | Independent model for 765 kV transmission case interventions | MEDIUM-HIGH — active PUCT interveners |
| **Open Energy Transition** (GitHub) | "Awesome Electrical Grid Mapping" list maintainers | Add project to curated open grid tools list | HIGH — visibility, not usage |
| **PyPSA-USA** (pypsa-usa.readthedocs.io) | Existing PUDL/Catalyst partnership | ERCOT bus-level topology for their zonal model | MEDIUM — different modeling framework |
| **Texas Tribune** energy desk | Mitchell Ferman, Erin Douglas | Publishable grid analysis for investigative reporting | MEDIUM — need newsworthy findings |
| **DOE OEDI** (data.openei.org) | Open Energy Data Initiative | Dataset contribution (2.28 PB of energy data, but no transmission topology) | MEDIUM — bureaucratic process |

---

## Publication Venues (Ranked by Fit)

### Best fit
1. **Applied Energy** (IF ~11) — Full pipeline + SCED + WESTEX paper. PyPSA-Earth published here. No page limit.
2. **Nature Scientific Data** — Data descriptor. European HV grid OSM paper published here 2025. Direct precedent.
3. **IEEE TPWRS** (IF ~7) — Core power systems contribution. 12-page format.

### Conference deadlines
4. **PSCC 2026** (Limassol, Cyprus, June 8–12) — Submissions open September 2025.
5. **IEEE PESGM 2026** (Montreal, July 19–23) — Submissions due November 17, 2025. 5-page papers.

### Niche angles
6. **Physical Review E** / **Network Science** — Complex network topology paper.
7. **NeurIPS AI4Science** — AI methodology case study. Deadline ~May 2026.
8. **Energy Informatics** (Springer) — Lower bar, fast turnaround.

---

## Key Academic Citations

| Paper | Venue | Year | Relevance |
|---|---|---|---|
| Xiong et al., "European HV grid from OSM" | Nature Scientific Data | 2025 | Methodological twin (Europe, no SCED) |
| Yang et al., "Alberta Power Network from OSM" | arXiv 2504.07870 | 2025 | Closest parallel (OSM grid recovery, no SCED) |
| Parzen et al., "PyPSA-Earth" | Applied Energy | 2023 | OSM-based grid for Africa, no SCED |
| Birchfield et al., "Texas-7k Synthetic Grid" | IEEE TPWRS | 2017–2024 | TAMU synthetic, comparison target |
| Li et al., "RT-SCED Benchmark" | GitHub/rpglab | 2023 | Open SCED on test cases only |
| Hu & Ralph, "EPECs for Bilevel Games" | Operations Research | 2007 | Strategic bidding on nodal markets |
| Hubert, Lolas, Sircar, "MFG for Capacity Expansion" | arXiv | 2025 | Direct Sircar alignment |
| Liu et al., "GridMind" | SC'25 Workshops | 2025 | LLM for grid analysis (not building) |
| Kruse et al., "eGridGPT" | NREL Technical Report | 2024 | LLM for control room support |
| Meyur et al., "Open Power System Datasets" | IEEE | 2025 | Survey identifying the data gap |

---

## Bottom Line

The honest pitch is not "we built a better ERCOT model" — sophisticated players already have better models. The pitch is:

**We built the only ERCOT model that is simultaneously (a) geographically grounded on real topology, (b) capable of SCED market clearing, and (c) fully publishable without CEII restrictions.**

The primary audiences are people who are currently locked out: academics who can't publish CEII-derived results, international researchers who can't access CEII at all, journalists who can't sign NDAs, and advocacy groups intervening in transmission cases with no independent modeling capability. The secondary audience is the open energy modeling community (Catalyst Cooperative, PyPSA-USA, Open Energy Transition) who want a US transmission topology dataset to complement their existing generation and load data.

The strongest near-term research direction is **embedding this in Sircar's MFG framework** — it's the only paper where the model's qualitative accuracy (correct congestion geography) matters more than quantitative accuracy (exact LMP magnitudes), and it directly extends ongoing work in the advisor's research group.

---

## Sustainable Energy Directions: Where This Model Has Real Leverage

*Added March 28, 2026. Assessment of which research directions matter most for clean energy transition, given what this model can and cannot do.*

### The Core Insight

ERCOT's decarbonization bottleneck is not generation — it's delivery. Texas has 42 GW of installed wind and 38 GW of solar, with 355+ GW in the interconnection queue. The binding constraint is the transmission network's ability to move clean power from where it's generated (West Texas, South Texas, Gulf Coast) to where it's consumed (DFW, Houston, San Antonio). Our model captures exactly this dynamic: the WESTEX corridor binds, WEST zone prices crash to $1-6/MWh while HOUSTON pays $50-59/MWh. That price spread represents real curtailed clean energy and real fossil generation that didn't need to run.

This means the model's sustainability value is concentrated in **transmission-constrained renewable integration** — questions where the geographic structure of congestion matters more than exact price levels.

### Direction A: Wind Buildout Tipping-Point Curve — HIGHEST IMPACT

**The question:** At what West Texas wind capacity does the WESTEX corridor become permanently congested, making further wind investment uneconomic without new transmission?

**Why it matters:** ERCOT's interconnection queue has ~200 GW of wind projects, mostly in West Texas. Developers need to know whether their project will face chronic curtailment. PUCT needs to know when to approve new transmission. Neither has a public model to test this.

**What we'd do:** Start from the winning config (0 MW shed, 24/24 W<N). Incrementally add wind capacity at West Texas buses (scale existing wind PMax by 1.1x, 1.2x, ... 2.0x). For each level, measure: hours of WESTEX binding, total wind curtailment (MWh), WEST zone average LMP, and the marginal value of the next MW of transmission capacity on the Morgan Creek-Tonkawa corridor. Plot the tipping-point curve.

**The deliverable:** A public "renewable absorption capacity" curve for West Texas — the first of its kind from a non-proprietary model. Directly useful for PUCT transmission planning proceedings and developer site selection.

**Feasibility:** HIGH. Literally scaling PMax and re-running. Could produce the full curve in a day of cluster time.

**Sustainable energy value:** VERY HIGH. This is the single most decision-relevant output the model can produce for clean energy deployment in Texas.

### Direction B: Transmission vs. Storage for Congestion Relief — LIVE POLICY DEBATE

**The question:** For relieving WESTEX congestion, is it cheaper to build new 345/765 kV lines or to site battery storage strategically?

**Why it matters:** The $33B STEP plan proposes 2,468 miles of new 765 kV transmission. Environmental groups and landowners are fighting it. The counter-argument is that distributed storage (already 17.5 GW in ERCOT's queue) could absorb West Texas wind locally and reduce the need for new wires. Nobody has modeled this tradeoff on realistic topology.

**What we'd do:** Two parallel experiment sets:
1. **Transmission scenarios**: Add proposed 765 kV Eastern Backbone corridors (public ERCOT STEP maps) as new branches. Measure congestion relief.
2. **Storage scenarios**: Once Egret storage dispatch is working, place 2-10 GW of 4-hour batteries at West Texas 345 kV buses. Measure congestion relief.
Compare $/MW of congestion reduction between the two approaches.

**Honest limitation:** Our model runs DC-SCED, not production cost modeling with 8,760-hour chronological dispatch. Storage value depends heavily on temporal arbitrage patterns that a 24-hour single-day simulation captures imperfectly. This analysis would be indicative, not definitive — but still more rigorous than anything currently in the public record.

**Feasibility:** MEDIUM. Requires fixing Egret storage dispatch (known issue) and digitizing STEP corridor coordinates. The transmission-only half is straightforward.

**Sustainable energy value:** HIGH. This is the central question in Texas energy policy right now. Even approximate public analysis has value when the alternative is "trust ERCOT's proprietary modeling."

### Direction C: Data Center Co-Location with Renewables — NOVEL AND TIMELY

**The question:** Can data centers be sited in West Texas to consume excess wind locally, reducing WESTEX congestion instead of adding to Houston/DFW load?

**Why it matters:** ERCOT's large load queue (572 GW, mostly data centers) is concentrated in DFW and Houston — the demand side of the WESTEX constraint. If even 5-10 GW of data center load moved to West Texas, it would consume locally generated wind that currently can't be exported, reducing both curtailment and the need for new transmission.

**What we'd do:** Run three scenarios on Jun 17:
1. **Baseline**: Winning config (0 shed, 24/24 W<N)
2. **DFW addition**: Add 5 GW load at DFW-area 345 kV buses
3. **West TX co-location**: Add 5 GW load at West Texas 345 kV buses near wind clusters

Compare: total wind curtailment, WESTEX binding hours, system-wide LMP, and load shedding. The hypothesis is that West TX co-location *reduces* system stress while DFW addition *increases* it — a counterintuitive result with direct policy implications.

**Who would care:** ERCOT planning staff, data center developers (Google, Microsoft, Meta all have Texas operations), PUCT commissioners evaluating SB6 interconnection rules, and environmental groups arguing that data centers should co-locate with renewables.

**Feasibility:** HIGH. Adding load to specific buses is trivial. The analysis is compelling because it uses the model's core strength (geographic congestion patterns).

**Sustainable energy value:** HIGH. Could shift the data center siting conversation from "where is land cheap?" to "where does load help the grid?"

### Direction D: Coal Retirement Sequencing — PRACTICAL AND NEEDED

**The question:** Which coal plant retirements reduce emissions without causing reliability problems, and which ones require replacement capacity or transmission upgrades first?

**Why it matters:** ERCOT has ~14.7 GW of coal in our gen.csv, but several plants have announced retirements. The policy question is sequencing: can you retire Plant X without causing local reliability issues? The answer depends on the transmission network around that plant — whether nearby gas or renewable capacity can backfill through existing lines.

**What we'd do:** For each major coal plant, zero out its PMax and re-run SCED on a winter peak day (Jan 8, when wind is high but solar is absent). Measure local load shedding and LMP spike. Plants whose retirement causes no local impact are "safe to retire." Plants whose retirement causes shedding need either replacement generation or transmission upgrades before retiring.

**Feasibility:** HIGH. Just zeroing out generators and re-running.

**Sustainable energy value:** MEDIUM-HIGH. Accelerating coal retirement within reliability constraints is a concrete decarbonization action. This analysis is simple but nobody has published it for ERCOT on a geographically grounded model.

### Direction E: Environmental Justice Overlay — IMPORTANT BUT HARDER

**The question:** Do low-income and minority communities in ERCOT face disproportionate exposure to grid reliability risk (load shedding, high LMPs)?

**Why it matters:** Winter Storm Uri killed 246 people, disproportionately in low-income communities of color. Load shedding in ERCOT is supposed to be rotating and equitable, but transmission constraints create geographic patterns: areas downstream of congested corridors shed first. Our model produces bus-level shedding patterns that can be mapped to Census demographics.

**What we'd do:** Overlay bus-level shedding from stress-test scenarios (85-90 GW peak, extreme cold with low wind) onto Census tract demographics (income, race, housing type). Identify whether shedding correlates with socioeconomic vulnerability.

**Honest limitation:** Our load allocation is population-proportional, which assumes equal per-capita consumption — it doesn't capture industrial vs. residential load patterns. This is a first-order analysis, not a definitive environmental justice assessment.

**Feasibility:** MEDIUM. Requires Census data integration and stress-test scenarios. The bus-level shedding data already exists from our calibration runs.

**Sustainable energy value:** MEDIUM. Important framing, but the analysis is limited by our crude load allocation. More valuable as a demonstration of what's possible with better load data.

### Ranking for Sustainable Energy Impact

| Direction | Impact | Feasibility | Novel? | Policy-Relevant? | Recommended Priority |
|-----------|--------|-------------|--------|------------------|---------------------|
| **A: Wind tipping point** | Very High | High | Yes | Yes — PUCT, developers | **1st** |
| **C: Data center co-location** | High | High | Yes | Yes — SB6, ERCOT planning | **2nd** |
| **B: Transmission vs. storage** | High | Medium | Somewhat | Yes — STEP, Sierra Club | **3rd** |
| **D: Coal retirement sequencing** | Medium-High | High | No | Yes — plant-level decisions | **4th** |
| **E: Environmental justice** | Medium | Medium | Somewhat | Yes — equity framing | **5th** |

### The Throughline

All five directions share a common structure: **use the model's geographic congestion patterns to answer a question that matters for clean energy deployment, where no public tool currently exists.** The model's limitation (approximate LMP magnitudes) matters less for these questions than for, say, CRR valuation or hedge fund trading. What matters is *which corridors bind, where curtailment happens, and how congestion shifts when you change the grid* — exactly what this model does well.

The strongest immediate package would be Directions A + C together: "West Texas Wind Integration: Tipping Points and the Case for Load Co-Location." This tells a complete story — the problem (WESTEX saturates), the conventional solution (build transmission), and the unconventional solution (move demand to the supply) — all on a public model that anyone can reproduce.
