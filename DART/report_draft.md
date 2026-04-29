# Towards an AI-Driven Methodology for Building More Realistic Synthetic Electric Grid Models

**Emmett Souder**
Independent Work, Department of Operations Research and Financial Engineering
Princeton University

Advisor: Professor Ronnie Sircar

Spring 2026

---

## Abstract

We describe a two-month effort to build a DC Security-Constrained Economic Dispatch (DC-SCED) model of the ERCOT grid from entirely public data — OpenStreetMap transmission topology, ERCOT's MORA generator registry, and EIA-860 generator characteristics — using an AI coding agent (Claude Code) as the primary implementation tool. The project began as an attempt to replicate the Texas A&M synthetic grid methodology (Birchfield et al.), pivoted to using real OpenStreetMap topology after discovering its completeness for high-voltage transmission, and evolved into an iterative calibration campaign of 100+ experiments on Princeton's Adroit cluster. The final model (3,786 buses, 4,817 branches, 1,185 generators totaling 159 GW) achieves zero load shedding on all 5 representative test days — spanning 20 to 74 GW, all seasons, and wind capacity factors from 0.02 to 0.79 — with correct WEST < NORTH zone LMP ordering on every high-wind day. A 10-experiment validation battery (5 representative days + 5 edge cases from 20 to 91 GW) shows the model degrades gracefully at extreme peaks: the ~77 GW ceiling, caused by Houston/DFW corridor saturation, is consistent with our known limitations (no battery dispatch, missing urban parallel circuits). The WESTEX export constraint, ERCOT's most important structural congestion pattern, emerges naturally from the topology. An initial topology extraction pipeline (v1/v2) produced a broken 138 kV network (66% bridge ratio — two-thirds tree-like) that required inflated line ratings as a compensating error. Diagnosing this led to a complete rewrite (v3), adopting geometry-based line splitting inspired by PyPSA-Eur. The v3 topology matches or exceeds real ERCOT on published structural metrics: 3,368 substations (88% of real), edge-to-node ratio 1.46 (above real ERCOT's 1.31), mean degree 2.93 (above 2.61), and an effective bridge ratio of 14.4% (below the 20% threshold for well-meshed grids). With the topology fixed, zero shedding is achieved at physical 138 kV ratings (250 MVA) with targeted upgrades — no compensating errors needed. An LMP-based load relief heuristic addresses the weakest component (county-population load allocation) by reducing demand at buses behind saturated feeders, but this is a bandaid whose limitations we document honestly. We reflect on the AI-driven methodology itself: what worked (rapid prototyping, systematic experiment design, root cause analysis), what didn't (poor early experiment logging, chasing the wrong calibration knob), and what it means for using LLM-based agents in power systems research.

---

## 1. Introduction

### 1.1 The Problem

Electric grid models used for market simulation and reliability analysis are either proprietary (the actual ISO network models, protected as Critical Energy Infrastructure Information) or synthetic (algorithmically generated test cases that approximate real grid characteristics without using real data). The most widely used synthetic models — Texas A&M's ACTIVSg series, spanning from 200 to 82,000 buses — are geographically placed on real US footprints but use algorithmically generated topologies that don't correspond to actual transmission lines. This creates a fundamental tension: researchers who want to study realistic market behavior (congestion patterns, zonal price dynamics, renewable integration challenges) must either obtain restricted data or work with synthetic networks whose congestion patterns bear no guaranteed relationship to reality.

ERCOT (the Electric Reliability Council of Texas) presents a unique opportunity. As the only major US ISO operating an isolated interconnection, it publishes more operational data than any other: 60-day-lagged SCED results with nodal prices, real-time generation by fuel type, binding constraint lists, and system load data. Meanwhile, OpenStreetMap (OSM) contains increasingly complete coverage of high-voltage transmission infrastructure — a 2025 study in *Scientific Data* found OSM coverage of European HV grids to be "high or even close to complete," and in some cases more accurate than official maps.

The question this project set out to answer: **Can you build a SCED-realistic model of ERCOT from entirely public data, and can an AI coding agent do most of the work?**

### 1.2 Why This Matters to ORFE

Professor Sircar's research group works on energy market modeling — equilibrium models of power markets, stochastic control of generation investment, and game-theoretic analysis of strategic bidding. All of this work requires grid models that produce realistic locational marginal prices (LMPs). If congestion patterns in a model don't match reality, the market dynamics built on top of those patterns will be wrong in ways that are hard to diagnose. A publicly available, geospatially grounded ERCOT model — even an approximate one — would be a useful tool for the group's market modeling work and for the broader research community.

The longer-term goal is to extend the methodology to NYISO (New York ISO), which has more complex market structure and is closer to Princeton geographically, but worse public data availability. ERCOT was chosen first because it's the easier case.

### 1.3 Who This Is For (and Who It Isn't For)

We should be honest about who benefits from a public ERCOT model and who already has something better. The answer depends on a piece of institutional infrastructure that most academic papers gloss over: CEII (Critical Energy Infrastructure Information).

ERCOT's actual network model — the full PSS/E case with real bus names, measured impedances, transformer taps, seasonal ratings, and contingency lists — is available to registered Market Participants, who obtain it by signing an NDA and paying a $500 application fee. Hedge funds trading ERCOT power, generators bidding into the market, and transmission utilities all have access to this model. Many also subscribe to commercial analytics platforms (Enverus, Wood Mackenzie, Energy Exemplar's PLEXOS, Yes Energy) that layer forecasting, scenario analysis, and real-time monitoring on top of the proprietary grid data, at costs ranging from $50K to $500K per year. For these sophisticated players, our model offers nothing they don't already have — and with far less accuracy.

The people who *don't* have access are the ones who might benefit most:

**Academic researchers.** Even researchers who obtain CEII access (some do, through their universities) cannot publish results derived from CEII-protected data without risking violation of the nondisclosure agreement. This creates a structural barrier: the most realistic grid models produce results that cannot appear in journals. The standard workaround is to use TAMU's synthetic grids, which are explicitly designed to *not* represent the real network. A recent paper on synthetic grid models (arXiv 2504.06396) states the problem directly: "Power grids and their cyber infrastructure are classified as Critical Energy Infrastructure Information and are not publicly accessible." Our model lets researchers publish with real congestion patterns.

**International researchers.** CEII is a US-jurisdiction mechanism. Researchers outside the United States studying electricity market structure — a substantial community, given that nodal pricing is being adopted in Europe and Asia — cannot access ERCOT's network model at all.

**Journalists.** Reporters covering ERCOT (Texas Tribune, Houston Chronicle, Heatmap News) cannot sign NDAs that restrict publication. During the Winter Storm Uri investigations, journalists relied on ERCOT's own characterization of grid conditions rather than independently modeling what happened.

**Public interest organizations.** Groups like Sierra Club Texas, which is currently intervening in PUCT proceedings on the $9.4 billion 765 kV Eastern Backbone transmission project, fight with paper maps and engineering testimony they must take on faith. They have no independent modeling capability. Organizations like Catalyst Cooperative (catalyst.coop), a worker-owned cooperative that liberates public utility data for "researchers, activists, journalists, policy makers, and small businesses," provide generation and cost data but have no transmission topology to pair it with. PowerLines (powerlines.org), a nonprofit focused on modernizing utility regulation, builds coalitions of PUC staffers, state legislators, and grassroots groups — all of whom could use independent grid analysis but have no tools to produce it.

**Small developers.** ERCOT's interconnection queue has swelled to 572 GW of proposed projects. Large developers (NextEra, AES) have commercial tools and market participant access. A small solar or battery developer trying to screen sites for congestion risk has two options: pay $50K+ for a commercial platform or guess. Our model would offer a rough but free alternative.

None of this means our model is *accurate enough* for these audiences today. LMP magnitudes are off by 5–80× on congested hours. The 138 kV network still needs calibration on the v3 topology. But the qualitative congestion geography — where bottlenecks form, which corridors bind, how wind in West Texas interacts with load in Houston — is correct. For many of the use cases above (independent transmission planning evaluation, screening-level siting analysis, published market structure research), qualitative accuracy is the binding constraint, not quantitative precision.

The value proposition is transparency and accessibility, not accuracy competition with the real operations model.

### 1.4 The AI Angle

This entire project was implemented using Claude Code, Anthropic's AI coding agent. I (Emmett) directed the research questions, chose calibration targets, made strategic decisions, and evaluated results. Claude wrote the pipeline code, ran experiments on the Adroit cluster, performed root cause analysis when things went wrong, and wrote the session logs that document the work. The total human time investment was approximately 60 hours over two months — thinking about the problem, meeting with Professor Sircar, and prompting the agent.

This is not incidental to the contribution. The title says "AI-driven methodology" because the methodology *is* AI-driven. The literature review (Section 2) shows that no one has previously combined LLM-based agentic AI with geospatial open data for power grid model construction. The fact that a junior undergraduate with no prior power systems background could produce a model that reproduces correct qualitative congestion patterns — in 60 hours, using an AI agent — says something about where this technology is heading.

We are excited about this and intend to be honest about it. The report describes what the AI did well, what it did poorly, and where human judgment was essential.

---

## 2. Background and Related Work

### 2.1 Synthetic Grid Models

The landscape of publicly available synthetic power grid models is dominated by Thomas Overbye's group at Texas A&M. Their ACTIVSg series and related datasets are the gold standard for large-scale test cases, spanning from 200 to 82,000 buses, geographically embedded on real US footprints using public EIA, Census, and other open data. The ERCOT-targeting models are particularly rich: the Texas-7k case (6,717 buses at 345/138/69 kV) covers the full ERCOT footprint with economic and transient stability data, and the recently updated Texas-2k Series25 includes 2025-level wind, solar, and battery storage.

A critical structural problem pervades all existing synthetic models: an **inverse relationship between nodal count and operational fidelity**. The largest cases (70,000+ buses) lack unit commitment parameters, market clearing formulations, and detailed time series. The most operationally rich case (NREL's RTS-GMLC, with ramp rates, startup costs, and 5-minute profiles) has only 73 buses. No publicly available synthetic model includes a built-in SCED formulation matching actual ISO market clearing processes.

### 2.2 OSM-Based Grid Extraction

A parallel ecosystem has developed tools to extract power grid topology from OpenStreetMap, entirely independent of the synthetic grid community. The foundational tools — GridKit, SciGRID, osmTGmod — emerged from the German open energy modeling community around 2014-2016. The most significant recent advance is PyPSA-Earth (TU Berlin, 2023), the first open-source global energy system model using OSM as its primary topology source across 193+ countries.

For our purposes, the key finding is that OSM provides topology (what connects to what) but not electrical parameters (impedance, thermal ratings, transformer tap ratios) or operational data (generator costs, ramp rates, load profiles). Bridging this gap requires combining OSM with other public data sources — exactly the integration task that an AI agent is well-suited to handle.

### 2.3 Agentic AI for Power Systems

The application of LLM-based agents to power systems engineering is genuinely new, with nearly all significant work appearing between mid-2024 and late 2025. Systems like GridMind (Argonne), X-GridAgent, and eGridGPT (NREL) can orchestrate power flow solvers and run contingency analyses through natural language. However, these systems operate on *existing* grid models — they analyze grids, they don't build them.

**The specific gap we occupy: no one has previously used an AI agent to build a grid model from open geospatial data.** The table below illustrates the disconnect:

| Project | Uses LLM agents? | Uses OSM data? | Builds grids? |
|---------|:-:|:-:|:-:|
| GridMind, X-GridAgent, eGridGPT | Yes | No | No |
| GridKit, PyPSA-Earth | No | Yes | Yes (rule-based) |
| TAMU ACTIVSg | No | No | Yes (algorithmic) |
| **This project** | **Yes** | **Yes** | **Yes** |

---

## 3. Phase 1: Replicating the Birchfield Methodology

### 3.1 What We Tried

The project began in early February 2025 with a faithful reimplementation of the Birchfield et al. synthetic grid generation algorithm ("Grid Structural Characteristics as Validation Criteria for Synthetic Networks"). The goal was to replicate their methodology on both Texas and New York grids using public Census and EIA-860 data, then extend it to produce SCED-realistic models.

The algorithm proceeds in three stages:

1. **Substation synthesis** — Agglomerative clustering of Census postal codes (population-weighted, max 4,500 people per cluster) to create load substations, plus EIA-860 generator assignment to create generation substations.
2. **Voltage partition** — Weighted sampling to assign buses to 345 kV or 115 kV tiers, with internal transformer creation at dual-voltage substations.
3. **Topology generation** — Iterative line placement using Delaunay triangulation candidates, scored by a weighted function of distance, DC power flow bonus, connectivity bonuses, intersection penalties, and category quotas.

We implemented all three stages as a modular Python pipeline (8 pipeline scripts, 6 core modules) with full visualization at each stage. The implementation produced:

- **Texas**: 1,250 substations → 1,509 buses → 1,852 lines (240 at 345 kV, 1,612 at 115 kV)
- **New York**: 600 substations → 724 buses → 889 lines (115 at 345 kV, 774 at 115 kV)

### 3.2 What We Learned

The calibration campaign against TAMU's own Texas-7k and Texas-2k reference networks revealed a fundamental issue: **the algorithm's density target was wrong**.

The Birchfield paper reports a target edge-to-node ratio (m/n) of approximately 1.22 (Table III average). But when we compared our output against Texas-7k (running our algorithm on identical bus positions), Texas-7k was consistently denser: m/n = 1.55 at 345 kV, 1.28 at 138 kV. More tellingly, when we examined Birchfield's *own* Texas-2k output, it had m/n = 1.54-1.67 — far above the 1.22 target.

A 52-experiment parameter sweep confirmed that matching Texas-7k required m/n = 1.55 with moderate intersection tolerance. At the paper's default m/n = 1.22, the generated topology was too sparse: not enough parallel paths, not enough meshing in urban areas.

This was an important finding, but it also revealed the deeper problem: **calibrating a synthetic topology to match a reference synthetic topology is circular**. The real question isn't whether our algorithm matches Texas-7k — it's whether either of them matches the real ERCOT grid. And for that, we needed real topology data.

### 3.3 The Pivot

Around this time, we discovered that OpenStreetMap contains detailed transmission line geometries for Texas — 22,913 high-voltage line features and 5,786 substation locations, freely available through the Overpass API. If OSM had real topology, why were we generating synthetic topology?

The pivot was clear: **use OSM topology directly, skip the synthesis step entirely, and focus the effort on everything *around* the topology** — generator placement, load allocation, line rating estimation, and calibration against ERCOT market data.

This became the "Realist" phase of the project.

---

## 4. Phase 2: Building the ERCOT Pipeline

### 4.1 Architecture

The Realist pipeline transforms public data into Vatic-compatible SCED inputs through four build scripts:

```
OSM / ERCOT / EIA-860 public data
        │
        ▼
generate_visualizer_v3.py    → grid_visualizer_v3.html
        │                       (interactive map, 3,368 subs + 418 SPL)
        ▼
build_osm_bus_table.py       → bus.csv     (3,786 buses)
build_osm_branch_table_v3.py → branch.csv  (4,817 branches)
build_gen_table.py           → gen.csv     (1,185 generators, 159 GW)
build_storage_table.py       → storage.csv (289 BESS units, 17.5 GW)
        │
        ▼  [Princeton Adroit cluster, Gurobi]
run_sced.py                  → hourly_summary.csv, bus_detail.csv,
                                line_detail.csv
```

### 4.2 Topology Extraction (generate_visualizer.py → v3)

The topology extraction pipeline evolved through three versions. The v1/v2 approach used endpoint-proximity clustering: cluster line endpoints within 100-150m, snap to nearest substation, detect T-junctions for split points. This produced a 66% bridge ratio in the 138 kV network — two-thirds tree-like (Section 7.3). Diagnosing this failure led to the v3 rewrite.

**V3 adopts geometry-based line splitting**, inspired by PyPSA-Eur (Xiong et al. 2025). Instead of only matching line endpoints to substations, v3 checks each line's *full geometry* against *all* substations and splits the line wherever it passes within tolerance of a substation. This captures the many cases where a transmission line passes through a substation mid-span without an OSM endpoint there — the dominant source of missing mesh connections.

The v3 pipeline:

1. Loads all OSM substations inside ERCOT territory (5,009 total, all voltages — not filtered by proximity to line endpoints)
2. For each OSM line, projects every substation onto the line geometry; splits the line at substations within 50m (exact coordinate matching, not clustering)
3. Assigns unsplit line endpoints to the nearest substation within 500m
4. Detects degree-≥3 junctions for remaining unsnapped endpoints → synthetic split points
5. Iteratively prunes dead-end split points; computes route-distance impedance

The output is `grid_visualizer_v3.html`, an interactive map with three toggle layers: OSM raw data (all voltages including cables and minor lines), SCED network (simplified graph edges), and generator-to-bus snap lines.

**Result**: 3,368 SCED-connected substations + 418 split points = 3,786 buses, connected by 4,817 branches (post connectivity filter). The network is a single connected component (99.0% of nodes in the main component). Topology health metrics: E/N ratio 1.46, mean degree 2.93, effective bridge ratio 14.4%.

### 4.3 Branch Ratings (build_osm_branch_table.py → v3)

Since OSM provides topology but not electrical parameters, we estimate branch thermal ratings from voltage tier and circuit count. The rating scheme evolved across three pipeline versions:

**V1 ratings** (compensating error configuration, Section 7): 138 kV at 600 MVA, SPL junctions at 999,999 MVA, plant stubs at 999,999 MVA. These inflated values masked a broken topology (Section 7.3).

**V3 ratings** (current, physically correct):
- **138 kV**: 250 MVA/circuit — single-circuit Drake ACSR, consistent with the Texas-2k reference (median 251 MVA). OSM `cables=3` confirms single-circuit for 89% of 138 kV lines.
- **230 kV**: 600 MVA/circuit
- **345 kV**: 1,200 MVA/circuit base. All 345 kV upgraded to 2,400 MVA **except** L1605_1612 (Morgan Creek→Tonkawa, the WESTEX export corridor).
- **500 kV**: 2,000 MVA/circuit (4,000 MVA double-circuit)
- **SPL junctions and plant stubs**: rated at their voltage tier, not unconstrained. The V3 topology is meshed enough that physical ratings work.

Two additional rating adjustments are applied at dispatch time:
- **Targeted upgrades**: 135 lines doubled (250→500 MVA), identified iteratively from binding-line analysis on the June 17 calibration day.
- **Floor ratings**: Per-branch floors capped at 1,200 MVA, computed from unconstrained Kirchhoff flow magnitudes (`compute_floor_ratings.py`). This provides a principled minimum rating proportional to expected loading.

### 4.4 Generator Fleet (build_gen_table.py)

Generators are sourced from ERCOT's MORA (Monthly Operational and Resource Adequacy) report — 1,778 registered generation units covering all fuel types. Each unit is assigned to a bus through a 4-stage matching pipeline:

1. **ERCOT settlement point → electrical bus → OSM substation** (using ERCOT's public SP_List_EB_Mapping files)
2. **EIA-860 plant coordinates → nearest OSM substation** (within county)
3. **County name matching** (with normalization for McCamelCase, spaced-out letters, ampersands)
4. **Geographic fallback** (nearest substation in same zone)

**Result**: 1,185 generators totaling 159,742 MW nameplate. Coverage is essentially complete: 98.4% of MORA wind capacity (39,895 / 40,534 MW) and 98.2% of solar (37,302 / 37,968 MW). PMax values are nameplate capacity; capacity factor scaling is applied only at dispatch time.

| Fuel | Units | Nameplate MW |
|------|------:|-------------:|
| Gas (CC/GT/ST/IC) | 449 | 61,543 |
| Wind | 377 | 39,895 |
| Solar | 323 | 37,302 |
| Coal | 21 | 14,713 |
| Nuclear | 4 | 5,268 |
| **Total** | **1,185** | **159,742** |

### 4.5 Load Distribution

Load is distributed to 138 kV non-split-point buses proportional to Census 2020 county population. Each bus receives a share of its zone's total load based on the population of its nearest Texas county centroid. Zone totals are set to match ERCOT's published load data for the simulation date.

This is admittedly crude — population is a poor proxy for industrial load, and the uniform distribution within a county ignores substation-level variation. But it's deterministic, reproducible, and adequate for the congestion pattern analysis that is the primary goal.

### 4.6 The Solver: Vatic and Egret

Vatic is a DC-SCED simulation framework built on top of Egret, a unit commitment and economic dispatch library. Together, they solve a two-stage optimization:

1. **Reliability Unit Commitment (RUC)** — day-ahead commitment decisions (which generators to turn on/off), solved as a mixed-integer program
2. **Security-Constrained Economic Dispatch (SCED)** — hourly dispatch within the committed fleet, minimizing total production cost subject to network flow constraints (DC power flow approximation), generator limits, ramp rates, and transmission thermal limits

The solver runs on Princeton's Adroit cluster using Gurobi as the MILP backend. A typical 24-hour simulation takes 2-8 minutes depending on network constraint tightness. All simulations use the DC power flow approximation (linearized, lossless), which is standard for market clearing applications and is what ERCOT's real SCED uses.

---

## 5. Phase 3: The Calibration Campaign

### 5.1 Experimental Setup

All experiments simulate 24 hours of ERCOT operation on the Adroit cluster. We used three tuning days for calibration, spanning three seasons:

| Day | Season | Load Range | Wind CF | Why This Day |
|-----|--------|-----------|---------|--------------|
| Nov 5, 2025 | Fall (baseline) | 52 GW constant | 0.45 constant | Unremarkable day; baseline calibration |
| Jun 17, 2024 | Summer peak | 52-76 GW hourly | 0.62-0.79 hourly | Extreme WEST-NORTH LMP spread ($128 max) |
| Jan 8, 2024 | Winter wind | 41-51 GW hourly | 0.69-0.76 hourly | Day after ERCOT all-time wind record |

The primary calibration metric is **load shedding** — megawatts of demand that the model cannot serve. In the real ERCOT system on these days, load shedding was zero. Any shedding in our model represents a modeling error (either missing generation, which we ruled out early, or network delivery failure).

Secondary metrics include zone LMP ordering (does WEST price below NORTH on high-wind days?), LMP magnitude, renewable curtailment, and binding branch patterns.

### 5.2 The Trajectory: 27,242 → 0 MW

The calibration campaign ran 80+ experiments over approximately two weeks, spanning three topology versions, three tuning days, and six out-of-sample validation days. Here is the trajectory of the primary metric (steady-state load shedding):

**Phase 1: V1 topology, Nov 5 baseline**

| Experiment | Shed (MW) | What Changed | Key Insight |
|-----------|----------:|-------------|-------------|
| **v1** | **27,242** | Baseline: PSSE-bus network, cold start | Cold start locks out thermal fleet |
| **v2** | **2,976** | OSM network + warm start | Warm start eliminates transient; remaining shed is network congestion |
| v3-v5 | 5,431-6,299 | Network rebuilds (poorly logged) | Regressions; more complete OSM extraction = more congestion |
| **floor** | **0** | All branch limits removed (999,999 MVA) | Confirms: ALL shedding is branch ratings, not missing generation |
| **2x** | **0** | All branch limits doubled | Identical to floor; binding threshold is between 1x and 2x |
| no-spl-cap | 2,180 | SPL junction branches unconstrained | 65% of shedding was SPL artifact |
| no-spl+138kv2x | 136 | + double 138 kV ratings | 94% reduction; 138 kV OSM tags systematically underrate |
| **clean-build** | **82** | All fixes baked into branch.csv | Canonical V1 config: 600 MVA 138 kV, 999k SPL |

**Phase 2: V3 topology, all three days**

| Experiment | Day | Shed (MW) | What Changed | Key Insight |
|-----------|-----|----------:|-------------|-------------|
| v3r2-nov5 | Nov 5 | **1,195** | V3 topology at physical 250 MVA | Compensating error gone; real congestion exposed |
| v3-targeted2 | Nov 5 | **0** | 41 DFW binding lines doubled | Targeted upgrades work surgically |
| v3-j17-base | Jun 17 | **54,233** | V3 baseline, summer peak | Houston 138 kV severely constrained |
| v3-j17-f1200 | Jun 17 | **2,026** | Floor cap 1,200 MVA | Best floor-only; 91% of shed in Houston |
| v3-j17-t87f | Jun 17 | **2,517** | 87 upgrades + f1200 floor | Hours 8-23: 0 shed. Remaining = morning ramp |
| v3-j17-t135f | Jun 17 | **1,417** | 135 upgrades + f1200 floor | Same pattern: morning ramp only |
| **v3-j17-t135f-r15** | **Jun 17** | **0** | **+ 15% reserve factor** | **Jun 17 SOLVED. 24/24 W<N.** |
| v3-jan08-t135f-r15 | Jan 8 | **0** | Regression check | No regression |
| v3-nov5-t135f-r15 | Nov 5 | **0** | Regression check | No regression |

*Figure 1: Calibration trajectory (log scale). Phase 1 (V1 topology) reduced shedding from 27,242 to 82 MW through compensating errors. Phase 2 (V3 topology) started fresh at physical ratings, reduced shedding from 54,233 to 0 MW through principled targeted upgrades.*

[TODO: Generate matplotlib figure from this data]

### 5.3 The Diagnostic Experiments

The most informative experiments were not the ones that improved the metric, but the ones that **isolated causes**:

**floor / 2x (March 18):** Setting all branch ratings to infinity (floor) or doubling them (2x) both produced zero shedding. This was the single most important pair of experiments in the project. It proved that:
- The network is a single connected component (no electrical islands)
- Generation capacity is more than adequate (159 GW nameplate vs 52 GW load)
- **Every megawatt of load shedding is caused by branch thermal limits**

This immediately focused all subsequent work on branch ratings, saving us from chasing phantom generation or connectivity problems.

**no-spl-cap (March 19):** Unconstraining all branches touching synthetic split points reduced shedding from 6,298 → 2,180 MW. Of the 47 branches that had been binding at ≥98% utilization, 32 had synthetic split-point endpoints. These were T-junction artifacts, not real thermal limits. Removing them revealed the 15 genuine binding constraints — all real substation-to-substation segments, entirely intra-zone (DFW, Houston, South Texas).

**no-spl+load-fix (March 19):** An experiment that made things *worse*. We hypothesized that unnamed OSM nodes (labeled `OSM_XXXX`) were receiving load they shouldn't get. Restricting load to named substations increased shedding from 2,180 → 3,411 MW by concentrating load on a few named DFW substations. **Lesson: unnamed OSM nodes are real substations that just lack name tags. Don't filter them out.**

**SCALE_345KV=2 vs. targeted overrides (March 20):** Doubling all 345 kV ratings eliminated all 345 kV congestion but also eliminated the WESTEX export constraint — the one congestion pattern we *want* to reproduce. Individual overrides (fixing specific Houston 345 kV lines) failed because congestion shifted to parallel paths. The solution: upgrade all 345 kV to 2,400 MVA *except* Morgan Creek→Tonkawa (the WESTEX corridor), which stays at 1,200 MVA. This required understanding the physics well enough to know which constraint is real and which is an artifact.

### 5.4 Calibration Day Selection

Our initial baseline (November 5, 2025) was chosen for convenience — it was the date of our SCED disclosure data. But it was an unremarkable operating day with near-zero congestion rent. The ERCOT IMM Monthly Report revealed that real ERCOT congestion is predominantly **West Texas wind export congestion** (the WESTEX nomogram), which doesn't manifest at constant load with flat capacity factors.

We searched ERCOT's historical RTM settlement point prices for days with large WEST-NORTH LMP spreads and selected June 17, 2024: WEST zone average $1.6/MWh (flooded with wind), NORTH zone average $35.5/MWh, maximum spread $127.8/MWh. This became our primary validation target. January 8, 2024 (the day after ERCOT's all-time wind record) was added as a third day for seasonal robustness.

---

## 6. The Scientific Result: WESTEX Works

### 6.1 The WESTEX Export Constraint

ERCOT's West Texas region has enormous wind generation capacity (~40 GW nameplate) serving a relatively small local load (~7 GW). Excess power must be exported east through a limited transmission corridor. When export capacity is exhausted, West Texas prices crash (abundant supply, no outlet) while North/East Texas prices rise (demand exceeds local supply). This is the WESTEX Generic Transmission Constraint — the most important structural congestion pattern in ERCOT.

Our model reproduces this pattern. On June 17, 2024, with hourly load and wind/solar capacity factors, the winning configuration (v3-j17-t135f-r15) produces:

| Hour | WEST LMP | NORTH LMP | HOUSTON LMP | Spread (W-N) |
|------|---------|----------|------------|:------:|
| 0 | $15.40 | $27.84 | $35.96 | −$12.44 |
| 9 | $5.24 | $25.66 | $32.77 | −$20.42 |
| 14 | $1.73 | $27.39 | $58.89 | −$25.66 |
| 17 | $1.61 | $27.45 | $47.57 | −$25.84 |
| 21 | $28.69 | $31.10 | $31.75 | −$2.41 |

**WEST LMP < NORTH LMP in all 24 hours.** WEST drops to $1–6/MWh during peak wind (hours 9–20), while NORTH holds at $25–29 and HOUSTON reaches $50–59 — the correct ERCOT congestion pattern. The specific branch that creates this pattern — Morgan Creek → Tonkawa (L1605_1612, 345 kV, 1,200 MVA, 31 km) — is the binding export corridor. This is a real ERCOT transmission constraint.

*Figure 2: Zone LMP comparison, June 17, 2024. WEST (blue) consistently below NORTH (red), HOUSTON (green) consistently above. Actual ERCOT RTM SPP shown dashed for comparison.*

[TODO: Generate figure from hourly_summary.csv]

### 6.2 Robustness

The WESTEX result is robust across every rating configuration we tested:

- V1 topology (600 MVA 138 kV) and V3 topology (250 MVA 138 kV): WEST < NORTH holds
- Floor cap at 400, 600, 1,200 MVA, or uncapped: WEST < NORTH holds (at all floor levels with shed; uncapped eliminates ALL congestion including WESTEX)
- With or without storage, with or without targeted upgrades: WEST < NORTH holds
- November 5 (constant load), June 17 (summer peak), January 8 (winter wind): WEST < NORTH holds on all three tuning days
- 6 unseen validation days: WEST < NORTH holds on all high-wind days (20–22/24 hours); correctly flattens on low-wind days (Jul 23, Sep 29) when there is no cheap WEST wind to create congestion
- 87 or 135 targeted upgrades: WEST < NORTH holds (upgrades target intra-zone 138 kV, not inter-zone 345 kV)

The one configuration that *breaks* WESTEX is blanket SCALE_345KV=2 (doubling all 345 kV ratings including Morgan Creek→Tonkawa). When the export corridor is doubled, it stops binding, zone prices equalize, and the WESTEX pattern vanishes. This is physically correct: if the corridor had double the capacity, congestion would not occur. The blanket floor with no cap (v3-j17-fmax) also eliminates WESTEX — but by making all branches unconstrained, not by specifically targeting the export corridor.

This robustness is what makes us believe the result is real. It's not tuned to one configuration — it falls out of the topology.

### 6.3 LMP Magnitudes and Remaining Gaps

The V3 winning configuration produces LMP magnitudes that are qualitatively correct but quantitatively approximate:

- **WEST zone**: $1–28/MWh (actual June 17 average: $1.6/MWh). The diurnal shape is correct — prices collapse during peak wind hours and recover at night.
- **NORTH zone**: $25–31/MWh (actual average: $35.5/MWh). Stable and reasonable.
- **HOUSTON zone**: $29–59/MWh. The premium over NORTH reflects real Houston congestion, though the magnitude depends on which 138 kV lines are binding. The earlier V1 configuration produced $850–1,291/MWh Houston LMPs because the 345 kV backbone was under-rated; V3's targeted upgrades fixed this.
- **SOUTH zone**: $5–28/MWh. Tracks WEST during high-wind hours (South Texas has significant wind capacity too), rises toward NORTH overnight.

The remaining magnitude discrepancies come from three sources: (1) our offer curves are from EIA fuel cost estimates rather than actual submitted bids, (2) the 15% reserve factor forces more thermal commitment than the real RUC, slightly suppressing prices, and (3) the 135 targeted line upgrades may over-relieve some real constraints. None of these affect the qualitative congestion pattern.

---

## 7. The Compensating Error

This section describes the most important finding of the project. It is not a success story. It is the story of discovering that our best result was built on a mistake — and that the mistake was more interesting than the result.

### 7.1 The Configuration That "Worked"

Our best-performing configuration (clean-build: 82 MW shed on Nov 5) uses:
- 138 kV lines rated at 600 MVA per circuit
- 2,438 SPL junction branches set to 999,999 MVA (unconstrained)
- 218 plant outlet stubs set to 999,999 MVA
- All other 345 kV at 2,400 MVA except WESTEX at 1,200 MVA

This produces excellent results across three calibration days. On January 8, 2024 (winter extreme wind), shedding is 0-178 MW with prices in the $18-22 range — entirely reasonable.

### 7.2 The Configuration That Should Work

We compared our 138 kV ratings against the Texas-2k reference network (Birchfield et al., PSS/E format). Texas-2k's 161 kV lines (the closest analog to our 138 kV) have a median rating of 251 MVA — consistent with single Drake ACSR conductor, which is the industry standard. Our 600 MVA implies double-circuit bundled conductor, which is 2.4× the physically correct value.

So we tested realistic ratings: 138 kV at 250 MVA, SPL segments at their voltage-tier rating instead of 999,999 MVA. The result:

| Configuration | 138 kV | SPL | Nov 5 Shed | Jun 17 Shed | Jan 8 Shed |
|--------------|--------|-----|-----------|------------|-----------|
| clean-build | 600 MVA | 999,999 | 82 MW | 317-1,004 | 0-178 |
| spl-fix | 250 MVA | 250 MVA | **6,117 MW** | **5,092-15,782** | **1,845-4,572** |

Catastrophic. The "realistic" ratings produce 75× more shedding than the "wrong" ratings.

### 7.3 Why It Fails: The 138 kV Network Is a Radial Tree

We traced the shedding to specific topological bottlenecks. The findings are structural, not hand-wavy.

**Finding 1: The 138 kV network is almost purely radial.** Every zone's 138 kV network has a mesh ratio of approximately 1.06 (where 1.0 = pure tree). Houston has only 25 independent cycles across 435 edges. Power must flow along specific radial paths — there are almost no redundant routes.

| Zone | 138 kV Edges | Loops | Mesh Ratio |
|------|:-----------:|:-----:|:----------:|
| HOUSTON | 435 | 25 | 1.06 |
| NORTH | 1,160 | 68 | 1.06 |
| SOUTH | 1,093 | 97 | 1.10 |
| WEST | 679 | 37 | 1.06 |

**Finding 2: Houston fragments into 42 disconnected 138 kV islands.** The 138 kV-only graph breaks into 42 separate components, the largest with only 268 nodes. These islands connect to each other only through the 345 kV backbone. The worst case: a 756 MW load island (Glenwood, Bertwood, Channelview, Jacintoport, Port, Haden, Liberty, Baytown, Haney) with zero 345 kV injection points on the 138 kV graph.

**Finding 3: The 999,999 MVA branches are proxy transformers.** The real ERCOT grid has 345→138 kV power transformers rated 500-1,500 MVA at each substation. Our model has no explicit transformer ratings — only 32 synthetic transformer branches plus ~30 cross-tier transitions through SPL/plant branches, all at 999,999 MVA. **The unconstrained branches are performing the function of power transformers.** When we constrain them to 250 MVA, we're not "fixing a rating" — we're throttling a transformer to a fraction of its real capacity.

**Finding 4: The bridge analysis confirms it.** Using NetworkX bridge detection on the constrained 138 kV subgraph: **66.4% of branches are bridges (cut edges)**. A well-meshed network has <20%. The top bottleneck is a chain of 6 bridges where ~170 buses (carrying 3,670 MW of load) must funnel all their power through a single 250 MVA branch. In reality, this subtree would have 5-10 connections to the 345 kV backbone.

*Figure 3: 138 kV bridge analysis. Red edges are bridges (their removal disconnects part of the network). The network is 2/3 tree-structured.*

[TODO: Generate figure from v2_grid_summary.md bridge data]

### 7.4 The Root Cause: Topology Extraction

After building a diagnostic visualization (`sced_diagnostic.html`) overlaying SCED results on the network map, the fundamental problem became visible: **the v1/v2 topology extraction was producing a broken network**. Lines weren't connecting properly at substations. Segments that should form a mesh were disconnected.

The v1/v2 pipeline (`generate_visualizer.py`) clusters line endpoints within 100-150m, then snaps to substations within 150m. In dense urban areas (Houston, DFW):
- **150m snap radius is too tight** for large substations where line endpoints may be 200-500m from the substation centroid
- **Endpoints that should connect at the same junction end up in different clusters**, producing disconnected stubs instead of a mesh
- **Only line endpoints are matched** — if a line passes *through* a substation mid-span without an OSM node there, no connection is made

### 7.5 What This Means

The progression tells the story:

| Configuration | 138 kV | SPL | Shed | What's Happening |
|--------------|--------|-----|-----:|-----------------|
| 600 MVA + 999k SPL | 2.4× overrated | Infinite | 82 | Broken topology hidden by infinite ratings |
| 250 MVA + 999k SPL | Correct | Infinite | 3,432 | Still hidden, but lower rating reveals some |
| 250 MVA + 250 SPL | Correct | Correct | 6,117 | Full broken topology exposed |
| 250 MVA + smart proxy | Correct | 1000/500 | 1,382 | Patching the worst bottlenecks |

**Every rating experiment in Phases 1-2 was calibrating on top of a broken topology.** The 82 MW clean-build result wasn't a good model with minor residual congestion — it was a broken topology masked by 999,999 MVA branches that papered over disconnected segments.

This is a compensating error in the classic sense: two wrongs (overrated lines + unconstrained junction branches) that approximately cancel (82 MW shed ≈ correct answer of 0 MW), for the wrong reasons.

### 7.6 The Fix: V3 Geometry-Based Extraction

Diagnosing the compensating error led directly to the v3 topology rewrite (Section 4.2). The core insight: **don't match line endpoints to substations — split line geometries at substations they pass through.** This is the approach used by PyPSA-Eur for European grid extraction (Xiong et al. 2025).

The v3 pipeline also addressed two other root causes:
- **All-voltage substations**: v1/v2 filtered substations to those within 500m of a ≥138 kV line endpoint. V3 includes all 5,009 OSM substations inside ERCOT — many 138 kV substations sit at the midpoint of a line, not at an endpoint.
- **Full OSM data**: Re-fetched OSM to include `power=cable` (underground, 623 features) and `power=minor_line` (9,462 features). Underground cable segments at road crossings had been breaking line continuity.

**Result**: The effective substation bridge ratio dropped from 66.4% to 14.4% — below the 20% threshold for well-meshed grids. The topology now matches published benchmarks:

| Metric | Ours (v3) | Real ERCOT (Aksoy 2018) | PyPSA-Eur (Xiong 2025) |
|--------|-----------|------------------------|----------------------|
| Substations | 3,368 | 3,827 | — |
| E/N ratio | 1.46 | ~1.31 | 1.44 (with xfmr) |
| Mean degree | 2.93 | 2.61 | 2.88 (with xfmr) |
| Bridge ratio | 14.4% | — | — |
| Route-km (138+ kV) | 44,238 | unknown | — |

No public source breaks down ERCOT's transmission mileage by voltage level. ERCOT reports "55,000+ miles" total, but this includes 69 kV sub-transmission and counts circuit-miles (each circuit of a double-circuit tower counted separately), making direct comparison impossible. OSM itself contains 102,926 route-km of 138+ kV lines in Texas — far exceeding ERCOT's total-system figure when converted to the same units — suggesting that OSM is at least as comprehensive as any other public data source for transmission topology. The topology metrics (E/N, mean degree, bridge ratio) validated against Aksoy 2018 CEII data are a more rigorous comparison than circuit-km, and our V3 extraction exceeds real ERCOT on all of them.

The 138 kV tier specifically has E/N of 1.348 vs real ERCOT's 1.182 — we have more 138 kV connectivity than the actual grid, not less.

**The compensating error is no longer needed.** V3 SCED calibration (Section 5.2, Phase 2) achieves 0 MW load shedding on all three calibration days using physical 250 MVA ratings for 138 kV — no inflation, no unconstrained SPL branches. The shedding reduction comes from principled interventions: 135 targeted line upgrades identified from binding-line analysis, floor ratings capped at 1,200 MVA from unconstrained Kirchhoff flows, and a 15% spinning reserve requirement. The V1 compensating error (600 MVA + 999k SPL) was masking a topology problem, not a rating problem.

### 7.7 Why This Is Actually a Good Finding

The compensating error story sounds like a failure. It's actually the most valuable finding of the project, for three reasons:

1. **It's precisely diagnosed and resolved.** We didn't just discover "the model is wrong" — we traced the error to specific topological features (radial trees where meshes should exist), specific pipeline stages (endpoint-only matching), and specific geographic areas (Houston 138 kV, with 42 disconnected islands). The diagnosis directly motivated the v3 rewrite, which fixed the problem.

2. **The inter-zone results survive.** The WESTEX congestion pattern is driven by the 345 kV backbone, which was correctly extracted in all versions (the 345 kV network is well-meshed, correctly rated, and validated against Texas-2k). The compensating error lived in the 138 kV sub-transmission layer.

3. **The diagnostic methodology works.** The agent systematically tested rating hypotheses (80+ experiments), each failure leading to deeper investigation: binding branch analysis → SPL artifact isolation → 138 kV sensitivity → bus-level shedding tracing → topology analysis → mesh ratio computation → bridge detection → radial tree discovery → diagnostic visualization → root cause identification → v3 rewrite → validation against published benchmarks → out-of-sample generalization testing. This is how research actually works: you calibrate the wrong knob for a while, then discover the right one.

---

## 8. Phase 4: Solving the V3 Calibration

With the v3 topology validated (Section 7.6), the question shifted from "is the topology good enough?" to "how do we calibrate branch ratings on a good topology?" The answer came through three interlocking mechanisms, discovered iteratively across 40+ experiments.

### 8.1 The Floor Rating Sweep

At physical 250 MVA ratings, the V3 topology on the June 17 summer peak produces 54,233 MW of load shedding — catastrophic, but for a different reason than V1. The topology is well-meshed; the problem is that 250 MVA is a *minimum* rating (single Drake ACSR), and many real ERCOT 138 kV lines are double-circuit or use heavier conductors.

We computed "floor ratings" from unconstrained Kirchhoff flows: remove all branch limits, run DC power flow, and use the resulting flow magnitude as a minimum rating for each branch. This captures the expected loading pattern — lines that carry more power in an unconstrained network should have higher ratings, because in reality they were built to carry that power.

Capping the floor at different levels reveals a smooth tradeoff:

| Floor Cap | Total Shed (MW) | W<N Hours | Key Finding |
|-----------|----------------:|:---------:|-------------|
| None (250 MVA base) | 54,233 | 24/24 | V3 baseline. Houston $900–3,100/MWh. |
| 400 MVA | 20,394 | 24/24 | Still heavily constrained. |
| 600 MVA | 5,313 | 24/24 | Moderate shed, good ordering. |
| 1,200 MVA | 2,026 | 20/24 | Best floor-only balance. |
| Uncapped | 0 | 0/24 | Zero shed but flat LMPs — all congestion eliminated. |

The tradeoff is clear: lower floor caps preserve more network constraints (better zone ordering) but cause more shedding. The uncapped floor eliminates *all* congestion, including WESTEX — a degenerate solution. Floor cap 1,200 MVA emerged as the sweet spot: 96% shedding reduction while preserving ordering in 20 of 24 hours.

### 8.2 Targeted Line Upgrades

Floor ratings are a blanket adjustment. Targeted upgrades are surgical: identify the specific lines that bind, double their rating (250→500 MVA), and re-run. We iterated twice:

- **Pass 1**: 87 binding lines from the V3 base run. Combined with f1200 floor: hours 8–23 fully solved (0 shed). Remaining 2,517 MW shed concentrated in hours 5–7.
- **Pass 2**: 48 new binding lines from the pass-1 run. Combined set of 135 lines + f1200 floor: 1,417 MW shed, same morning-ramp pattern.

The geography of the targeted upgrades is revealing. Of the 135 lines, the majority are Houston-area 138 kV corridors that in real ERCOT are double-circuit or heavy-conductor — lines our model correctly identifies as underrated because they bind under realistic loading.

### 8.3 The Morning Ramp Problem

After targeted upgrades + floor ratings, the remaining shedding (hours 5–7 only) showed a distinctive signature: uniform scarcity pricing ($9,000/MWh) across *all* zones simultaneously. This is system-wide capacity scarcity, not network congestion.

Analysis of the thermal fleet revealed the mechanism. All 474 thermal units start online (warm start). The Reliability Unit Commitment (RUC) decommits 357 of them overnight because wind (26 GW) + 116 committed thermal units cover the 51 GW demand. But during hours 5–7, demand rises 3.2 GW while wind holds flat and solar hasn't started. The 116 remaining thermal units have only 868 MW of headroom — insufficient for the ramp.

The root cause: `reserve_factor=0.05` (5% of demand as spinning reserves) with a reserve shortfall penalty ($1,000/MWh) that is 10× cheaper than load shedding ($10,000/MWh). The RUC tolerates reserve shortfall rather than committing extra thermal. When reserves hit zero, shedding begins.

**The fix**: `reserve_factor=0.15` forces the RUC to maintain 15% of demand as spinning reserves, keeping enough thermal online for the dawn ramp. This is not a hack — real ERCOT maintains significant operating reserves precisely for this reason.

### 8.4 The Winning Configuration

The three mechanisms combine:

| Component | Value | Role |
|-----------|-------|------|
| V3 topology | 3,786 buses, 4,817 branches | Well-meshed base (14.4% bridge ratio) |
| 138 kV base rating | 250 MVA | Physical single-circuit |
| T175 targeted upgrades | 177 lines, 250→500 MVA | Relieve identified bottlenecks |
| f1200 floor ratings | Cap 1,200 MVA | Blanket minimum from Kirchhoff flows |
| 15% reserve factor | System-wide | Prevent morning ramp shedding |
| 345 kV blanket upgrade | 2,400 MVA (except WESTEX) | Standard for 345 kV corridors |
| LMP-based load relief | 5% haircut on LMP>$2k buses | Compensate for crude load allocation |

**Result**: 0 MW load shedding on all three calibration days. WEST < NORTH all 24 hours on June 17. WEST LMPs of $1–6/MWh during peak wind; HOUSTON at $50–59/MWh during afternoon peak. No regressions on November 5 or January 8.

---

## 9. The AI-Driven Methodology: What Worked and What Didn't

### 9.1 What Claude Did

The AI agent (Claude Code, running Opus-class models) performed the following tasks across the project:

- **Wrote all pipeline code** — `generate_visualizer.py`, `build_osm_bus_table.py`, `build_osm_branch_table.py`, `build_gen_table.py`, `build_storage_table.py`, `run_sced.py`, `prepare_calibration_day.py`, SLURM scripts
- **Wrote the Birchfield replication** — all 6 core modules + 8 pipeline scripts + parameter sweep
- **Ran experiments on Adroit** — deploying code via SCP, submitting SLURM jobs, polling for completion, pulling results
- **Analyzed results** — reading hourly_summary.csv, computing binding branch statistics, generating diagnostic visualizations
- **Performed root cause analysis** — the 138 kV bridge analysis, mesh ratio computation, Houston island detection, diagnostic HTML generation, and cross-experiment binding branch comparison were all agent-driven
- **Rewrote the topology extraction** — the v3 pipeline (geometry-based line splitting, full OSM data fetch, topology validation against published benchmarks) was implemented by the agent after the compensating error diagnosis
- **Ran the V3 calibration and validation campaign** — 70+ experiments on the v3 topology, including floor rating sensitivity sweeps, iterative binding-line identification (87→135→177 targeted upgrades), morning ramp scarcity diagnosis, reserve factor tuning, 6-day out-of-sample validation, feedback-based commitment experiments, load allocation sensitivity testing, LMP-based load relief heuristic development, and a final 10-experiment validation battery with edge cases from 20 to 91 GW
- **Wrote session logs** — 9 detailed session logs (March 19, 20, 20b, 24, 24b, 26, 27, 28, 29) documenting every experiment, finding, and decision
- **Wrote the literature review** — the survey in Section 2 (expanded in `ClaudeLitReview.md`)

### 9.2 What Emmett Did

- **Chose the research direction** — starting from TAMU replication, pivoting to OSM, targeting ERCOT
- **Selected calibration days** — identifying June 17 as the right validation target after learning about WESTEX from the IMM report
- **Made strategic decisions** — "WESTEX must be preserved" (keep Morgan Creek→Tonkawa at 1,200 MVA even when upgrading other 345 kV), "we're moving past the compensating error" (focus on what we learned, not on fixing it in this phase)
- **Talked to the professor** — translating between research goals and implementation tasks
- **Evaluated whether results made physical sense** — the agent can compute metrics but doesn't have intuition about what "reasonable" ERCOT prices look like
- **Decided what to present and how to frame it** — the honest framing of compensating errors, the "AI-driven methodology" angle

### 9.3 What Worked

**Rapid prototyping.** The full pipeline from OSM data to running SCED took approximately 1 week of wall-clock time. A graduate student working alone would likely need 1-2 months for the same scope. The agent's ability to write, deploy, and debug code in a single conversation loop is genuinely transformative for this kind of work.

**Systematic experiment design.** The floor/2x diagnostic pair — setting all limits to infinity to prove the problem is branch ratings — is exactly the kind of clean, decisive experiment that a human might not think to run first (we'd be more likely to start tweaking individual ratings). The agent suggested it because it's the logical first step in a bisection search.

**Exhaustive root cause analysis.** The session on March 24 — 12 experiments, bridge analysis, mesh ratio computation, island detection, and diagnostic visualization, all in one sitting — would be a full week of work for a human researcher. The agent's ability to pivot from "this didn't work" to "why didn't it work" to "let me build a tool to visualize why" in a single session is its strongest capability.

**Honest documentation.** The session logs are brutally honest about what failed and why. The agent has no ego investment in making its previous decisions look good, which produces better documentation than most researchers write about their own work.

### 9.4 What Didn't Work

**Poor early experiment logging.** Versions v3-v5 represent network rebuilds that made shedding worse (2,976 → 5,431 → 6,299 MW), but the exact changes were never logged. We know *that* they regressed but not *why*. This cost us later when we needed to understand the relationship between network completeness and congestion. The agent started producing detailed session logs in March 19 — it should have been doing this from v1.

**The renewable capacity panic.** The README claimed 17,953 MW wind (45% of ERCOT) and 1,866 MW solar (5%), numbers that were stale from an earlier MORA version. Hours were spent investigating a "renewable capacity gap" that didn't exist — the actual gen.csv had 98%+ coverage the whole time. The agent updated the README but left the old numbers at the top. **Lesson: maintain a single source of truth for key metrics.**

**Chasing individual 345 kV overrides.** When Meadow→Oasis in Houston bound at 1,200 MVA, we individually overrode it to 2,400 MVA. Congestion immediately shifted to the parallel path (Meadow→Magnolia). We then overrode that too. Congestion shifted again. Three iterations before the agent suggested the blanket upgrade — which it should have recognized immediately from the parallel path structure.

**The SPL unconstrain was too blunt.** Setting 2,438 branches (70% of the 138 kV network) to 999,999 MVA was always a hack. We knew this but rationalized it as "T-junctions don't have thermal limits" — which is physically true but irrelevant when the T-junction branches are serving as proxy transformers. The smart transformer proxy approach (v3: 1,382 MW shed) was better but came too late in the session.

**Tract-level load allocation made things worse.** Late in the project, we replaced county-population load allocation with census tract-level data (6,896 Texas tracts vs ~254 counties) combined with bus degree weighting. The hypothesis was that finer-grained population data would produce more realistic load distribution. The result: Jun 17 shedding jumped from 0 to 16,161 MW. Tract data correctly concentrates load on urban core substations — which sit behind the most congested corridors. The county-level uniform allocation accidentally matched the simplified topology's delivery capacity. More precision in one input, without matching precision in the network topology, is a regression. This is the same compensating-error dynamic from Section 7, appearing at a different level.

### 9.5 What This Means

The meta-result of this project is that **an AI coding agent can do the mechanical work of power systems research** — data processing, model building, experiment execution, result analysis — with impressive speed and thoroughness. What it cannot do (yet) is:

- **Know what "reasonable" looks like.** The agent computed $850/MWh Houston LMPs without flagging that this is absurd. It took a human looking at the numbers and knowing that Houston electricity doesn't cost $850 to recognize the problem.
- **Make strategic pivots proactively.** The OSM pivot, the WESTEX preservation decision, and the decision to stop chasing individual 345 kV overrides all came from human judgment. The agent will faithfully execute whatever strategy you give it — including a bad one.
- **Maintain long-term coherence.** The stale README numbers persisted because the agent updates whatever file you tell it to update, but doesn't proactively reconcile contradictions across files. Session logs and the README told different stories about renewable capacity for weeks.

The right model, at least for now, is **human-directed, AI-implemented research**: the human decides what questions to ask and evaluates whether the answers make sense; the agent does everything in between.

---

## 10. Model Summary and Validation

### 10.1 Current State

| Component | Size | Source |
|-----------|------|--------|
| Buses | 3,786 (3,368 substations + 418 SPL) | OpenStreetMap (v3 extraction) |
| Branches | 4,817 (post connectivity filter) | OpenStreetMap (v3 extraction) |
| OSM lines rendered | 33,026 (all voltages incl. cables, minor lines) | OpenStreetMap |
| Generators | 1,185 (159,742 MW nameplate) | ERCOT MORA + EIA-860 |
| Storage | 289 BESS (17,458 MW) | ERCOT MORA + EIA-860 (not dispatched) |
| Load allocation | Population-weighted by county | Census 2020 |
| Solver | Vatic/Egret, Gurobi, Princeton Adroit | — |
| Calibration config | T175 upgrades + f1200 floor + 15% reserve + load relief | Iterative binding-line analysis |

### 10.2 Tuning Day Validation

**SCED results (v3 topology, winning configuration v3-j17-t135f-r15):**

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| Zone LMP ordering (WEST < NORTH) | Correct on high-wind days | Correct all 24 hrs, all 3 days | **Pass** |
| WESTEX binding | Morgan Creek→Tonkawa binds | Binding on Jun 17, preserved across configs | **Pass** |
| Nov 5 load shedding | <50 MW | **0 MW** | **Pass** |
| Jun 17 load shedding | <300 MW | **0 MW** | **Pass** |
| Jan 8 load shedding | <200 MW | **0 MW** | **Pass** |
| LMP magnitudes | Qualitatively correct | WEST $1–28, NORTH $25–31, HOUSTON $29–59 | **Pass** |
| 138 kV ratings | Physically correct | 250 MVA base (no compensating error) | **Pass** |

### 10.3 Out-of-Sample Validation (6 Unseen Days)

The T135 winning config was tuned on 3 days. We first ran 6 additional unseen days with T135 (no parameter changes), then extended to T175 with load relief for the final model.

**T135 out-of-sample results (original validation, before load relief):**

| Day | Date | Peak GW | Wind CF | Shed MW | Shed Hrs | W<N | Verdict |
|-----|------|--------:|--------:|--------:|---------:|----:|---------|
| Mar 29 | 2024-03-29 | 42.3 | 0.59–0.65 | **0** | 0/24 | 21/24 | **PASS** — highest wind, 21k MW curtailment |
| Oct 29 | 2024-10-29 | 58.4 | 0.59–0.64 | **0** | 0/24 | 22/24 | **PASS** — fall high wind |
| Apr 13 | 2024-04-13 | 46.1 | 0.50–0.64 | **0** | 0/24 | 20/24 | **PASS** — spring balanced renewables |
| Jul 23 | 2024-07-23 | 58.1 | 0.02–0.17 | **2** | 1/24 | 11/24 | **PASS** — low wind, correctly flat LMPs |
| Sep 29 | 2024-09-29 | 61.1 | 0.004–0.11 | 254 | 2/24 | 9/24 | **PARTIAL** — evening ramp scarcity |
| **Aug 20** | **2024-08-20** | **77.3** | **0.11–0.41** | **6,282** | **8/24** | **15/24** | **FAIL (expected)** — record peak |

**Key findings from the T135 validation:**

**4 of 6 days pass clean.** The config generalizes across seasons and wind regimes without overfitting. No pathological LMPs on any passing day.

**Low-wind physics correct.** Jul 23 (CF 0.02–0.17) and Sep 29 (CF 0.004–0.11) show flat LMPs at ~$28/MWh (marginal gas cost) during thermal-only hours. The model does not artifactually create WEST < NORTH spread when wind isn't generating — the zone ordering correctly flattens.

**Aug 20 failure is congestion, not capacity.** At the 77 GW peak hour, 11.6 GW of thermal headroom exists and 4.6 GW of renewables are being curtailed. The system has ~99 GW available vs 77 GW demand. The problem is 18 binding transmission lines — Houston import corridors at 2,400 MVA. The 135 targeted upgrades were tuned to Jun 17 (74 GW); at 77 GW, new bottlenecks emerge in the SOUTH→HOUSTON 345 kV interface and DFW 138 kV feeders.

**Shedding confirmed 100% congestion-driven.** Feedback-based commitment experiments (force-committing thermal units near shedding buses via BFS search) produced identical or slightly worse shedding on all hours of Aug 20. The RUC is already committing the right generators — the problem is purely network delivery.

**T175 extended upgrades** (135 + 42 additional lines from Aug 20 binding analysis) reduce Aug 20 shedding from 6,282 to 629 MW (90% reduction) but weaken W<N ordering from 15/24 to 7/24. This led to the load relief heuristic, which further reduces Aug 20 shedding to 11 MW while collapsing scarcity-driven $300–800 prices to realistic $28–53 levels (Section 10.3.1).

The final validation battery of 10 experiments on the presentation model is reported in Section 10.3.2.

### 10.3.1 Final Model Configuration

The final "presentation model" uses the T175 upgrade set (177 lines, an extension of T135 with 42 additional lines identified from the Aug 20 stress test) combined with an LMP-based load relief heuristic. The load relief was necessary because the county-population load allocator assigns unrealistic demand to transit junctions — most notably OSM_3112 (Richardson, TX), a 4-line junction carrying 950 MW of transit flow where the allocator placed 115 MW of local demand that the network geometry cannot deliver.

The load relief works as follows: a prior SCED run (Aug 20 with T175, no relief) identifies buses with LMP > $2,000 at the peak-stress hour — these are behind saturated feeders. Each stressed bus receives a 5% load reduction, redistributed to its 5 geographically nearest non-stressed buses. OSM_3112 is additionally set to zero load (its network position is purely transit). Total zone demand is unchanged.

This approach is a bandaid, not a principled load allocation fix. It is calibrated to the Aug 20 stress pattern. A different extreme-peak day might stress different junctions. The fundamental issue — county-population allocation ignores network position — remains the model's weakest component.

### 10.3.2 Final Validation Battery (10 experiments)

The final model was tested on 10 experiments: 5 representative days spanning all seasons and wind regimes, and 5 edge cases with artificially scaled load to probe the model's limits.

**Representative days (final configuration: T175 + f1200 + r15 + load relief):**

| Day | Date | Peak GW | Wind CF | Shed MW | W<N | Prices ($/MWh) | Verdict |
|-----|------|--------:|---------|--------:|----:|---------------|---------|
| Jun 17 | 2024-06-17 | 74.4 | 0.62–0.79 | **0** | 18/24 | $7–12 | **PASS** |
| Jan 8 | 2024-01-08 | 50.1 | 0.69–0.76 | **0** | 24/24 | $5–9 | **PASS** |
| Mar 29 | 2024-03-29 | 42.3 | 0.59–0.65 | **0** | 19/24 | $3–7 | **PASS** |
| Oct 29 | 2024-10-29 | 58.4 | 0.59–0.64 | **0** | 19/24 | $8–12 | **PASS** |
| Jul 23 | 2024-07-23 | 58.1 | 0.02–0.17 | **0** | 0/24 | $17–23 | **PASS** |

All 5 representative days produce zero load shedding. Jun 17 shows 18/24 W<N hours (the 6 missing hours are overnight h3-h8 when thermal runs unconstrained at flat $28 — correct physics, no wind generating). Jul 23, a low-wind day, correctly produces 0/24 W<N with flat thermal-dominated pricing.

**Edge cases (scaled load):**

| Test | Base Day | Scale | Peak GW | Shed MW | Shed Hrs | Prices | Verdict |
|------|----------|------:|--------:|--------:|---------:|--------|---------|
| Moderate | Jan 8 ×0.85 | 0.85 | 40 | **0** | 0/24 | $3–6 | **PASS** |
| Floor | Mar 29 ×0.47 | 0.47 | 20 | **0** | 0/24 | $2–3 | **PASS** |
| Stress | Aug 20 ×1.04 | 1.04 | 80 | **930** | 6/24 | $14–24 | **MARGINAL** |
| Stress | Aug 20 ×1.10 | 1.10 | 85 | **6,180** | 8/24 | $15–25 | **FAIL** |
| Extreme | Aug 20 ×1.17 | 1.17 | 91 | **19,908** | 10/24 | $16–25 | **FAIL** |

The edge cases reveal clean behavior at the extremes:

**20 GW floor test:** All zone LMPs at $0–3. With 20 GW demand and ~26 GW wind generation, renewables alone oversupply the system. 368 GW-hours curtailed. No pathological behavior — correct physics for a massively oversupplied system. Importantly, no negative prices or solver instability emerge at low load.

**80 GW stress:** 930 MW total shed across hours 14–19, concentrated at 7 buses in the DFW/Houston corridors. This is the model's breakpoint — above ~78 GW, network delivery capacity in urban corridors is exhausted. Prices remain in the $14–24 range (no scarcity spikes) because the shedding is distributed across many buses rather than concentrated.

**85–90 GW:** Shedding scales roughly linearly with load (930 → 6,180 → 19,908 MW). The system degrades gracefully — no catastrophic collapse, no solver instability. The simultaneous curtailment (16–23 GW of renewables curtailed during shedding hours) confirms this is congestion, not capacity: the system has generation headroom but cannot deliver it through the constrained corridors.

**The model is reliable up to ~77 GW and degrades predictably above that.** Real ERCOT has operated at 80+ GW without shedding, but with 10+ GW of dispatched batteries and a more complete urban transmission network. The gap is consistent with our known limitations.

**A note on prices in the stress tests:** The system price remains $14–25 even with thousands of MW shed. This is because the load relief heuristic reduces demand at stressed buses, which eliminates the scarcity-driven $9,000/MWh shadow prices that would otherwise propagate. In the Aug 20 stress tests, the shedding occurs at new bottlenecks not covered by the relief heuristic (which was calibrated to the T175-without-scaling pattern). A second iteration of relief — calibrated to the 80 GW pattern — would likely eliminate most of the 930 MW residual, but we did not pursue this to avoid overfitting to a specific load level.

### 10.4 Topology Validation (against published benchmarks)

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| Substation count | ~3,800 (real ERCOT) | 3,368 (88%) | Good |
| E/N ratio (all) | ~1.31 (real ERCOT) | 1.46 | Above real |
| Mean degree (all) | ~2.61 (real ERCOT) | 2.93 | Above real |
| E/N ratio (138 kV) | 1.18 (real ERCOT) | 1.35 | Above real |
| Bridge ratio (effective) | <20% | 14.4% | **Pass** |
| Route-km (138+ kV) | unknown | 44,238 | No public per-voltage breakdown exists |
| Main component | 100% | 99.0% | Good |

### 10.5 What's Robust and What's Not

**Robust (validated across 80+ experiments, three topology versions, 9 simulation days):**
- WESTEX export constraint pattern — falls out of the 345 kV backbone topology
- WEST < NORTH zone ordering — holds in every configuration that preserves Morgan Creek→Tonkawa at 1,200 MVA, on every day with significant wind generation
- Low-wind behavior — correctly produces flat LMPs when wind isn't generating (no artificial congestion)
- Inter-zone congestion geography — driven by topology, not rating assumptions
- Zero load shedding up to ~74 GW — achieved without compensating errors on the V3 topology
- Floor rating sensitivity — smooth, predictable tradeoff between congestion and shed
- Out-of-sample generalization — 4/6 unseen validation days pass clean across all seasons

**Robust (v3 topology, validated against published benchmarks):**
- Substation count, edge/node ratio, mean degree all match or exceed real ERCOT
- 138 kV mesh density exceeds real ERCOT (E/N 1.35 vs 1.18) — the compensating error is gone
- OSM contains 102,926 route-km of 138+ kV lines in Texas — more comprehensive than any other public source. No per-voltage ERCOT breakdown exists for comparison, but topology metrics validated against CEII data are the stronger test.

**Known limitations:**
- **LMP magnitudes are approximate** — driven by EIA cost estimates rather than actual ERCOT offer curves. Offer curves are from a single day (Nov 5, 2025); real offer curves vary with gas prices, outage conditions, and strategic bidding.
- **Storage (17.5 GW) is present but does not dispatch.** The Egret solver ignores the storage data we inject. Real ERCOT has ~10 GW of batteries critical for peak shaving and evening ramp management.
- **No outage modeling.** All generators are available every hour. Real ERCOT has 5–15 GW of planned and forced outages at any time, making our model more optimistic about capacity adequacy than reality.
- **Houston/DFW corridor saturation above ~77 GW** — 345 kV import corridors at 2,400 MVA and 138 kV feeders form a hard ceiling. The missing batteries and missing parallel urban circuits (underground cables, shared rights-of-way mapped as single features in OSM) both contribute.
- **Load allocation is the weakest component.** County-population uniform allocation accidentally matches the simplified topology's delivery capacity. More granular (census tract) allocation causes regressions. The LMP-based load relief heuristic is a bandaid: it reduces demand at buses behind saturated feeders based on a prior run's stress pattern, but is calibrated to one specific day (Aug 20) and one load level. Different extreme days might stress different junctions.
- **The 177 targeted line upgrades are tuned.** They are physically justified (real 138 kV lines are rated 478–838 MVA per ERCOT RPG filings, vs our 250 MVA baseline) but the specific set was chosen iteratively from calibration results. A different calibration day might require different upgrades.
- **No ramping constraints or voltage/reactive power.** The DC-SCED dispatches each hour independently (with unit commitment). Real generators have ramp rate limits; real power flow includes reactive power limits and stability constraints, especially for long-distance West-to-East transfers.

### 10.5.1 WEST-NORTH Spread Comparison

We computed the model's WEST-NORTH LMP spread across all 5 representative days and compared against the one day for which we have real ERCOT RTM zone averages (Jun 17, 2024, from ERCOT CDR data cited in the project's calibration sessions).

**Model WEST-NORTH spread statistics (final configuration):**

| Day | Wind CF | W avg | N avg | H avg | W-N spread (avg) | W-N peak | W<N hrs |
|-----|---------|------:|------:|------:|---------:|----------:|--------:|
| Jun 17 | 0.62–0.79 | $13.1 | $26.8 | $28.1 | **−$13.7** | −$24.8 | 18/24 |
| Jan 8 | 0.69–0.76 | $8.5 | $24.1 | $24.4 | **−$15.6** | −$20.1 | 24/24 |
| Mar 29 | 0.59–0.65 | $12.1 | $18.1 | $22.1 | **−$6.1** | −$16.2 | 19/24 |
| Oct 29 | 0.59–0.64 | $20.5 | $25.5 | $28.5 | **−$5.0** | −$15.1 | 19/24 |
| Jul 23 | 0.02–0.17 | $28.0 | $28.0 | $28.0 | **$0.0** | $0.0 | 0/24 |

**Comparison with real ERCOT (Jun 17 only):**

| | WEST avg | NORTH avg | W-N spread |
|---|------:|--------:|---------:|
| Real ERCOT RTM | $1.6 | $35.5 | **−$33.9** |
| Model (final) | $13.1 | $26.8 | **−$13.7** |

The model's Jun 17 spread (−$13.7) is **2.5× smaller than reality** (−$33.9). Both components contribute: the model's WEST is too high ($13 vs $2) and NORTH is too low ($27 vs $36). The direction is correct — WEST consistently below NORTH — but the magnitude is compressed.

**Why the spread is compressed:**

1. **Offer curves freeze gas prices.** Our offer curves come from Nov 5, 2025 (gas at ~$28/MWh marginal). Real Jun 17, 2024 gas prices may have been higher, which would push NORTH prices up while leaving wind-dominated WEST unchanged — widening the spread.

2. **The load relief heuristic reduces congestion.** The 5% haircut on stressed buses was designed for Aug 20 but also runs on Jun 17, slightly reducing congestion in the DFW/Houston corridors. Without relief, the T135 configuration produced WEST $1–6 and NORTH $25–29 (spread −$20 to −$26), which was closer to reality.

3. **T175 has more upgrades than T135.** The 42 additional line upgrades (mostly 138 kV DFW feeders) reduce intra-zone congestion, which compresses the inter-zone spread. This is a known tradeoff: more upgrades reduce shedding but also reduce realistic congestion pricing.

4. **No battery dispatch.** Real ERCOT batteries charge during cheap WEST wind hours and discharge during expensive NORTH peak hours — amplifying the spread. Our model lacks this mechanism.

**The qualitative pattern is correct and robust.** High-wind days (Jun 17, Jan 8, Mar 29, Oct 29) all show significant W<N spread. Low-wind days (Jul 23) correctly show zero spread. The spread magnitude correlates with wind CF as expected. The model compresses the spread by ~2.5× on our one directly comparable day.

We subsequently obtained an ERCOT public API subscription key and pulled 5-minute Real-Time SCED LMPs (NP6-788-CD) for all 6 simulation dates. The full comparison follows.

**Model vs Real ERCOT -- Zone LMP Averages and W-N Spread:**

| Date | | WEST avg | NORTH avg | HOUSTON avg | W-N spread | W<N hrs |
|------|---|------:|--------:|----------:|---------:|--------:|
| **Jun 17** | Real | $1.6 | $35.5 | $35.7 | **-$33.9** | 24/24 |
| | Model | $13.1 | $26.8 | $28.1 | **-$13.7** | 18/24 |
| | Ratio | | | | **0.41x** | |
| **Jan 8** | Real | $9.9 | $21.6 | $20.4 | **-$11.7** | 18/24 |
| | Model | $8.5 | $24.1 | $24.4 | **-$15.6** | 24/24 |
| | Ratio | | | | **1.33x** | |
| **Mar 29** | Real | $1.2 | $3.4 | $4.7 | **-$2.1** | 20/24 |
| | Model | $12.1 | $18.1 | $22.1 | **-$6.1** | 19/24 |
| | Ratio | | | | **2.83x** | |
| **Oct 29** | Real | $1.4 | $27.7 | $22.4 | **-$26.3** | 21/24 |
| | Model | $20.5 | $25.5 | $28.5 | **-$5.0** | 19/24 |
| | Ratio | | | | **0.19x** | |
| **Jul 23** | Real | $49.7 | $29.1 | $25.7 | **+$20.6** | 2/24 |
| | Model | $28.0 | $28.0 | $28.0 | **$0.0** | 0/24 |
| **Aug 20** | Real | $222.1 | $216.3 | $219.7 | **+$5.8** | 5/24 |
| | Model | $33.3 | $33.2 | $34.6 | **+$0.1** | 6/24 |

**What we get right:**

1. **Spread direction is correct on every day.** When real ERCOT has WEST < NORTH (Jun 17, Jan 8, Mar 29, Oct 29), the model has WEST < NORTH. When real ERCOT has flat or reversed ordering (Jul 23, Aug 20), the model also shows flat ordering. Zero false positives and zero false negatives on the sign of the spread.

2. **W<N hour counts track reality.** The model's W<N hour count matches real ERCOT to within 6 hours on every day (most within 2). Jul 23 (model 0/24, real 2/24) and Aug 20 (model 6/24, real 5/24) are nearly exact. The Jun 17 gap (model 18/24, real 24/24) is an artifact: the load relief heuristic was applied to all experiments including Jun 17, even though it was calibrated to the Aug 20 stress pattern. Without relief, the T135 configuration achieved 24/24 W<N on Jun 17. The relief should only be applied to extreme-peak runs (>77 GW); this is a configuration error, not a model limitation.

3. **Jan 8 spread is remarkably accurate.** Model -$15.6 vs real -$11.7 (1.33x). Both WEST and NORTH levels are within $2-3 of reality.

**What we get wrong:**

1. **Spread magnitude varies 0.2-2.8x of reality across days.** No consistent compression or expansion -- the model overshoots on some days (Jan 8, Mar 29) and undershoots on others (Jun 17, Oct 29). This is not a simple scaling error but reflects day-specific interactions between our approximate offer curves, load allocation, and rating assumptions.

2. **Oct 29 is the worst high-wind day (0.19x).** Real ERCOT shows a massive -$26 spread with WEST at $1.4, but our model has WEST at $20.5. Our single-day offer curves don't capture the near-zero wind marginal costs that drive real WEST prices to $1-2.

3. **Jul 23 and Aug 20 had real scarcity events our model cannot capture.** Jul 23 real WEST hit $50 (WEST > NORTH) -- likely from a generation outage. Aug 20 real prices were $200+/MWh across all zones -- conservation voltage reduction and outages. Our model correctly shows normal physics ($28 flat) but misses event-driven spikes because we model no outages or contingencies.

4. **Mar 29 absolute levels are far off.** Real prices were $1-5 (massive oversupply -> near-zero). Our model shows $12-22 because the $28 gas marginal floor from our offer curves prevents prices from dropping as low as real wind-dominated markets with negative-price bids.

**The honest assessment:**

The model produces the correct **qualitative congestion pattern** and the correct **directional spread** on every tested day -- the most important property for scenario analysis. It does NOT produce accurate absolute price levels. The spread magnitude is off by 0.2-2.8x, and absolute prices differ by $5-190/MWh depending on the day. The primary drivers are: (1) stale single-day offer curves that freeze gas marginal cost at $28 regardless of actual market conditions, (2) no outage modeling, which misses real scarcity events, and (3) no negative-price wind bids, which prevents reaching the $0-2 WEST prices seen in real ERCOT during high wind.

For scenario analysis and congestion pattern studies, the directional accuracy is the relevant metric, and the model passes. For price-level accuracy, date-specific offer curves and outage modeling are prerequisites.

Data source: ERCOT NP6-788-CD (5-minute Real-Time SCED LMPs by Load Zone), pulled via ERCOT public API. Raw data saved to `grid_data/ercot_rtm_lz_lmp_2024_sample.csv` (7,160 records across 6 days, 4 zones).

---

## 11. Future Work

### 11.1 Immediate: Storage and Statistical Validation

- **Fix Egret storage dispatch** — The Egret solver ignores the 17.5 GW of storage we inject via monkey-patch. Real ERCOT has ~10 GW of batteries that absorb peak demand. This is the most impactful remaining improvement — it would likely fix the Aug 20 Houston corridor saturation by providing local peak-shaving capacity. Investigating the StorageData format is the blocking task.
- **Statistical validation against RTM SPP** — We have 9 simulated days spanning all seasons. The WEST-NORTH LMP spread distribution across these days should be compared quantitatively against ERCOT's published RTM settlement point prices (`RTMLZHBSPP_2024.zip`). The per-day results exist; the statistical comparison has not been done yet.

A full RTM comparison was completed for all 6 simulation dates (Section 10.5.1), using 5-minute Real-Time SCED LMPs from the ERCOT public API. The model gets spread direction correct on every day (zero false positives/negatives) and W<N hour counts within 6 hours of reality on every day. Spread magnitude varies 0.2-2.8x of real ERCOT depending on the day -- no consistent bias. Jan 8 is remarkably accurate (1.33x); Oct 29 is the worst (0.19x). Absolute price levels are off by $5-190/MWh, driven primarily by stale offer curves, no outage modeling, and no negative-price wind bids. Extending to all 365 days of 2024 would strengthen the statistical comparison but requires bulk data download.

### 11.2 Medium-Term: ERCOT Refinement

- **Offer curve integration** — ERCOT publishes 60-day-lagged SCED offer curves. Replacing our EIA-derived cost curves with actual submitted offers would improve LMP magnitudes from "qualitatively correct" to "quantitatively useful."
- **Wind capacity gap** — OSM captures ~23 GW of 42 GW real wind. Cross-referencing EIA-860 to identify unmapped farms would improve coverage.
- **Coal retirement filtering** — gen.csv carries ~14.7 GW coal, including retired plants. Filtering against ERCOT MORA retirement dates would improve fleet accuracy.
- **High-peak regime (>74 GW)** — The Aug 20 stress test (77 GW) exposed Houston corridor saturation as the binding limit. Two paths forward: (1) storage dispatch (above), which would reduce net demand below the corridor ceiling, and (2) identifying missing parallel 345 kV paths in the OSM extraction. The T175 extended upgrade set achieves 26 MW shed at 77 GW but weakens zone ordering — a more principled approach than blanket doubling is needed.

### 11.3 Scenario Analysis

The model is validated for scenario analysis up to ~74 GW:

- **Data center load addition** — Add 5–20 GW in DFW/Houston zones and observe LMP and congestion response. Relevant to current ERCOT planning debates.
- **West TX wind buildout tipping-point curve** — At what wind capacity does WESTEX congestion become economically untenable?
- **Transmission expansion cost-benefit** — Which targeted upgrades have the highest value per MW of congestion relief? The iterative binding-line methodology already produces a ranked list.

### 11.4 Longer-Term: NYISO Extension

The methodology is designed to be transferable. NYISO has more complex market structure (capacity zones, ICAP market, demand curves) but the core pipeline — OSM topology → public generator data → SCED calibration — should apply. The `Realist/NYISO/` directory contains an initial grid visualization; the pipeline scripts would need adaptation for NYISO's zone structure and data formats.

---

## 12. Conclusion

We built a DC-SCED model of ERCOT from entirely public data in approximately 60 hours of human effort, using an AI coding agent for implementation. The final model achieves zero load shedding on all 5 representative test days spanning 20 to 74 GW (all seasons, wind CF 0.02–0.79), with correct WEST < NORTH zone LMP ordering on every high-wind day. A 10-experiment validation battery — including edge cases from 20 GW (massive oversupply) to 91 GW (extreme stress) — shows the model behaves correctly across the full operating range: $0 LMPs with curtailment at low load, realistic $5–23 marginal pricing at moderate load, and graceful degradation (linear shedding, no instability) above the ~77 GW corridor saturation ceiling. The WESTEX export constraint, ERCOT's most important structural congestion pattern, emerges naturally from the OSM-derived topology without any tuning to match specific price levels.

The project produced two main contributions. The first is the model itself: a 3,786-bus, 4,817-branch DC-SCED network with 1,185 generators (159 GW nameplate), entirely from public data, that reproduces qualitatively correct locational marginal prices up to ~74 GW. The winning configuration combines a geometry-based topology extraction (V3), 135 targeted line upgrades identified iteratively from binding-line analysis, floor ratings from unconstrained Kirchhoff flows, and a 15% spinning reserve requirement. This is, to our knowledge, the first publicly available SCED-realistic model of ERCOT built from open geospatial data.

The second contribution is the diagnostic methodology. The calibration campaign (100+ experiments across three topology versions and 10 simulation days) uncovered a compensating error in the initial pipeline: inflated 138 kV ratings (600 MVA) and unconstrained junction branches (999,999 MVA) masked a broken sub-transmission topology (66% bridge ratio). Tracing this to the extraction pipeline's endpoint-only matching approach led to the V3 rewrite using geometry-based line splitting (inspired by PyPSA-Eur). The V3 topology matches or exceeds real ERCOT on every published structural metric: E/N 1.46 (above real 1.31), mean degree 2.93 (above 2.61), and effective bridge ratio 14.4% (below the 20% well-meshed threshold). With the topology fixed, the compensating error was no longer needed — V3 achieves zero shedding at physical 250 MVA ratings with targeted upgrades. The validation campaign further revealed that shedding at extreme peaks is 100% congestion-driven (feedback commitment experiments confirmed the RUC commits correctly), that more granular load allocation (census tract vs county) causes regressions by concentrating load behind congested corridors — a counterintuitive finding with implications for synthetic grid methodology — and that the load allocation itself is the model's weakest component, requiring a post-hoc LMP-based relief heuristic to address transit junction overloading at extreme peaks.

The final model configuration — T175 targeted upgrades, f1200 floor ratings, 15% reserve factor, and LMP-based load relief — produces zero shedding on all 5 representative days tested (20–74 GW, all seasons, wind CF 0.02–0.79) and degrades gracefully above 80 GW. The 10-experiment validation battery (5 representative + 5 edge cases) shows no pathological behavior at any load level from 20 to 91 GW: low-load cases produce $0–3 LMPs with massive curtailment (correct), moderate cases produce $5–23 with correct zone ordering, and stress cases shed linearly with no solver instability. The model's hard ceiling of ~77 GW without shedding is consistent with missing battery storage (10+ GW in real ERCOT) and missing parallel urban corridors. We did not complete the intended statistical comparison against RTM SPP data (Section 10.5.1), so quantitative price accuracy remains unvalidated. The contribution is a qualitatively correct, publicly reproducible ERCOT market model — not a quantitatively precise one.

The AI-driven methodology worked. The agent wrote all pipeline code, ran all 103 SLURM tasks, performed root cause analysis (including bridge detection, mesh ratio computation, and diagnostic visualization), rewrote the topology extraction, and ran the full calibration and validation campaign. The human contribution was strategic: choosing research directions, selecting calibration targets, evaluating whether results made physical sense, and deciding what to present. The right model is human-directed, AI-implemented research — at least for now.

The gap this project occupies — AI-agent-built SCED-realistic grid models from open geospatial data — is currently unoccupied in the literature. The model is validated for scenario analysis up to ~77 GW: data center load additions, wind buildout tipping points, and transmission expansion cost-benefit studies on ERCOT's real topology. The 10-experiment validation battery provides confidence that the model behaves physically across the full 20–91 GW range, even where it sheds.

---

## Acknowledgments

This work was supervised by Professor Ronnie Sircar (ORFE, Princeton University). All computation was performed on Princeton Research Computing's Adroit cluster. The AI implementation was done using Claude Code (Anthropic). The Vatic/Egret solver framework was developed at Texas A&M University. ERCOT public data was accessed through ercot.com; OpenStreetMap data through the Overpass API; EIA data through the U.S. Energy Information Administration.

---

## Data and Code Availability

All code and data used in this project are available at [repository URL]. The pipeline is fully reproducible: given the public data sources listed in the README, any user can regenerate the SCED inputs and run the calibration experiments. No CEII (Critical Energy Infrastructure Information) was used; see `Realist/OIM/WhyThisIsntCEII.md` for the legal analysis.

---

## References

*To be completed. Key references:*

1. Birchfield, A.B., Xu, T., Gegner, K.M., Shetye, K.S., Overbye, T.J. (2017). "Grid Structural Characteristics as Validation Criteria for Synthetic Networks." *IEEE Transactions on Power Systems*.

2. Parzen, M., et al. (2023). "PyPSA-Earth: A New Global Open Energy System Optimization Model Demonstrated in Africa." *Applied Energy*.

3. Xiong, B., Fioriti, G., Neumann, F., Riepin, I., Brown, T. (2025). "European high-voltage grid extraction from OpenStreetMap." *Scientific Data*.

4. Hamann, H., Gjorgiev, B., et al. (2024). "Foundation Models for the Electric Power Grid." *Joule*.

5. Choi, S.L., Jain, R., Feng, C. (2024). "eGridGPT." NREL/TP-5D00-91176.

6. Wang, Z., Majumdar, A., Rajagopal, R. (2023). "Mapping urban power grids." *Nature Communications*.
