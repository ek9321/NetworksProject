# Agentic AI meets synthetic power grids: a wide-open gap

**No one has yet combined LLM-based agentic AI with geospatial open data to build SCED-realistic synthetic power grid models — despite rapid 2024–2025 advances on both sides of this intersection.** Agentic AI systems like GridMind, X-GridAgent, and eGridGPT can now orchestrate power flow solvers and run contingency analyses through natural language, while publicly available synthetic grids from Texas A&M reach 82,000 buses and OSM-derived tools like PyPSA-Earth cover entire continents. Yet these two domains remain disconnected. The specific opportunity — using an AI coding agent (like Claude Code) to ingest OpenStreetMap transmission infrastructure, EIA generator data, and FERC flow statistics, then automatically assemble and validate an SCED-realistic synthetic grid — represents a clear, unoccupied niche in power systems research.

## Agentic AI for power systems exploded in 2025

The application of LLM-based agents to power systems engineering is a **genuinely new field**, with nearly all significant work appearing between mid-2024 and late 2025. The trajectory moved from initial proof-of-concept papers to multi-agent architectures operating on realistic test cases in roughly 18 months.

The foundational conceptual paper is **"Foundation Models for the Electric Power Grid"** by Hendrik Hamann (IBM Research), Blazhe Gjorgiev (ETH Zurich), and 25 co-authors from NREL, Argonne, Hydro-Québec, and Imperial College London, published as a cover article in *Joule* in December 2024. It proposes Grid Foundation Models (GridFMs) based on graph neural networks pre-trained on over 300,000 solved OPF problems, arguing that such models could deliver **3–4 orders of magnitude speedup** for grid computations. An open-source GridFM release through the Linux Foundation for Energy was projected for mid-2025.

The most operationally mature system is **eGridGPT**, developed at NREL by Seong Lok Choi, Rishabh Jain, and Cong Feng, documented in a November 2024 technical report (NREL/TP-5D00-91176). eGridGPT demonstrates an AI orchestrator that writes Python code to run transient analysis, power flow studies, and generation redispatch through natural language — with input from CAISO, ERCOT, SPP, and NERC. It follows a three-step training pipeline: general power engineering knowledge, control room procedures, then utility-specific fine-tuning for on-premise deployment compliant with NERC CIP cybersecurity standards.

Three multi-agent LLM systems emerged in 2025 with progressively more sophisticated architectures:

- **GridMind** (Argonne National Laboratory, SC'25 Workshops) coordinates specialized agents for AC Optimal Power Flow and N-1 contingency analysis using PandaPower as the solver backend, achieving **100% success rates** on IEEE 14, 30, 118, and 300-bus systems across multiple LLMs including GPT-5 and Claude 4 Sonnet.
- **X-GridAgent** (arXiv, December 2025) introduces a three-layer hierarchical architecture with eight modular MCP-based tool servers, integrating RAG for dataset retrieval and scaling to the **Texas 2,000-bus system** — the largest grid on which an agentic AI system has been demonstrated.
- **Grid-Agent** (arXiv, August 2025) deploys five specialized agents (Topology, Planner, Executor, Validator, Summarizer) with sandboxed execution and rollback mechanisms, handling up to 29 concurrent grid violations.

A key enabler for this wave was Anthropic's **Model Context Protocol (MCP)**, introduced in 2025, which standardized LLM-tool communication and allowed agents to interface with heterogeneous power system software including PSS®E, PowerWorld, and PandaPower through a single protocol. The ETH Zurich group (Mengshuo Jia and Gabriela Hug) demonstrated that their multi-agent framework achieves **93–97% success rates** on simulation coding tasks across MATPOWER and DALINE toolboxes at roughly $1.68 per 120 tasks — establishing economic viability for research acceleration.

Other notable contributions include GAIA (the first LLM fine-tuned specifically for power dispatch, published in *Scientific Reports* 2025), PowerGraph-LLM (University of Luxembourg, first LLM framework for solving OPF), and PowerAgent (Harvard SEAS open-source community building LLM tools for power systems). A comprehensive survey paper ("Agentic AI Systems in Electrical Power Systems Engineering," arXiv, November 2025) documents the field's rapid formation.

## Synthetic grid models have matured but plateau on operational fidelity

The landscape of publicly available synthetic power grid models is dominated by **Thomas Overbye's group at Texas A&M**, whose ACTIVSg series and related datasets remain the gold standard for large-scale synthetic test cases. These models, funded primarily by DOE ARPA-E's GRID DATA and PERFORM programs, span from 200 to **82,000 buses** and are geographically embedded on real US footprints using public EIA, Census, and other open data.

The ERCOT-targeting models are particularly rich. The **Texas 7k** case (6,717 buses at 345/138/69 kV) covers the full ERCOT footprint with economic and transient stability data, plus extensions coupling distribution networks (~200,000+ circuit nodes) and natural gas pipelines (2,459 gas nodes). The **EPIGRIDS Texas** case from the University of Wisconsin-Madison offers 7,336 buses with annual hourly load time series. The recently updated **Texas2k Series25** includes 2025-level wind, solar, and battery storage with improved inverter-based resource dynamics. A smaller but operationally rich **TX-123BT** system provides five years (2017–2021) of hourly weather-correlated profiles for wind, solar, dynamic line ratings, and load.

Beyond TAMU, the key publicly available models include:

- **RTS-GMLC** (NREL, 73 buses): Small but operationally detailed with unit commitment parameters (ramp rates, min up/down times, startup costs), hourly and 5-minute load profiles, and modern generation mix including wind, solar, and storage
- **PGLib-OPF** (IEEE PES Task Force): Curated, validated benchmark collection ensuring all cases have reasonable generation limits, cost functions, and thermal limits
- **PEGASE European cases** (French TSO RTE): Up to 13,659 buses from real European transmission snapshots
- **Polish system cases**: Real-world snapshots of 2,383–3,375 buses contributed by Roman Korab
- **Columbia University synthetic grids** (Gil Zussman's group): Learning-based topology generation with geographic coordinates

A critical structural problem pervades all existing synthetic models: **an inverse relationship between nodal count and operational fidelity**. The largest cases (70,000–82,000 buses) lack unit commitment parameters, market clearing formulations, and detailed time series. The operationally richest case (RTS-GMLC with ramp rates, startup costs, and 5-minute profiles) has only 73 buses. No publicly available synthetic model includes a built-in SCED/SCUC formulation matching actual ISO market clearing processes, virtual bidding, ancillary service co-optimization, or transmission congestion revenue rights. This gap is the most frequently cited limitation across the literature.

## OSM-based grid extraction works — but without AI

A parallel ecosystem has developed tools to extract power grid topology from OpenStreetMap, entirely independent of both the agentic AI and synthetic grid communities. Three foundational tools emerged from the German open energy modeling community around 2014–2016:

**GridKit** (NEXT ENERGY/EWE Research Centre) uses PostgreSQL with PostGIS to transform OSM power objects into topological network models. **SciGRID** (University of Oldenburg) applies route-based analysis to produce European transmission models. **osmTGmod** (Wuppertal Institut) generates load-flow-ready models separated by voltage level. A 2019 comparison study (AutoGridComp) found GridKit and osmTGmod have the highest topological completeness.

The most significant recent advance is **PyPSA-Earth** (TU Berlin, Parzen et al., *Applied Energy* 2023), the first open-source global energy system model with high spatial and temporal resolution, using OSM as its primary grid topology source across 193+ countries. A 2025 paper in *Scientific Data* (Xiong, Fioriti, Neumann, Riepin & Brown) rigorously benchmarked European high-voltage grid extraction from OSM against ENTSO-E statistics and found that **OSM coverage of the European HV grid is "high or even close to complete"** — and in Spain, OSM topology was actually more accurate than the ENTSO-E map.

For the United States, OSM power infrastructure data is generally less systematically mapped than in Europe, though major transmission lines and substations are well-represented. The critical limitation is that OSM provides topology (what connects to what) but not electrical parameters (impedance, thermal ratings, transformer tap ratios) or operational data (generator costs, ramp rates, load profiles). Bridging this gap requires combining OSM with EIA Form 860 (generator characteristics), EIA Form 923 (fuel consumption), FERC Form 714 (hourly load), and EPA CEMS (emissions/generation) data.

Stanford's Ram Rajagopal group has pushed geospatial grid mapping further with ML — Wang, Majumdar & Rajagopal (2023, *Nature Communications*) demonstrated a framework combining street view images, road networks, and building locations to map both overhead and underground distribution grids with over 80% precision. Other geospatial efforts include the World Bank's GridFinder (Arderne et al., 2020, *Scientific Data*), which uses nighttime lights and OSM to predict MV/LV grid locations globally, and Development Seed's satellite-based HV tower detection.

## The specific gap: no one is using AI agents to build grids from open data

The most striking finding from this research is the **complete absence of any project combining LLM-based agentic AI with geospatial open data for power grid model construction**. The summary table below illustrates the disconnect:

| Project | Uses LLM/AI agents? | Uses OSM/geospatial data? |
|---|---|---|
| GridMind, X-GridAgent, Grid-Agent | Yes | No |
| eGridGPT (NREL) | Yes | No |
| GAIA, PowerGraph-LLM | Yes | No |
| GridKit, SciGRID, osmTGmod | No | Yes |
| PyPSA-Earth/Eur | No | Yes |
| TAMU ACTIVSg synthetic grids | No | Geographically placed only |
| Wang et al. (Stanford, satellite ML) | ML (CNN), not LLM-agentic | Yes |

The closest work is **Deng, Zhou, Zeng, Wang & Guo (2025), "Power Grid Model Generation Based on the Tool-Augmented Large Language Model,"** published in *IEEE Transactions on Power Systems*. This paper frames grid model generation as structured text generation, allowing users to specify topologies and power flow properties in natural language. However, it generates models from scratch based on user specifications — it does **not** ingest real-world geospatial data. It demonstrates that LLMs can produce valid power grid models, but leaves the data integration problem unsolved.

Five specific gaps define the opportunity space at this intersection:

**Gap 1: No AI-agent pipeline from OSM to SCED-ready model.** An agentic system could orchestrate the full workflow — extract OSM topology, match EIA generators to substations, estimate line parameters from conductor types and lengths, assign load profiles from FERC Form 714, calibrate against publicly available ERCOT market data, and validate power flow convergence — all through autonomous tool use and reasoning.

**Gap 2: No AI-assisted data quality improvement for OSM power data.** OSM power infrastructure has known issues (missing transformers, incorrect voltage tags, disconnected segments) that an agent could identify and correct by cross-referencing multiple data sources and applying electrical engineering constraints (e.g., Kirchhoff's laws, voltage level consistency).

**Gap 3: No automated parameter estimation from combined open sources.** While topology extraction from OSM is solved, estimating electrical parameters requires combining information across EIA, FERC, EPA, and engineering standards — a task well-suited to agentic AI's ability to reason across heterogeneous data sources.

**Gap 4: No end-to-end geospatially grounded synthetic grid generation with AI.** TAMU's synthetic grids are algorithmically generated but don't use real OSM topology; PyPSA uses real OSM topology but without AI augmentation. The hybrid approach — real topology where OSM data exists, AI-generated topology for gaps, validated against aggregate statistics — doesn't exist.

**Gap 5: No ERCOT-specific SCED-realistic model built from open data with AI assistance.** Despite multiple ERCOT-footprint synthetic models (Texas 7k at 6,717 buses, EPIGRIDS Texas at 7,336 buses), none includes SCED/SCUC market clearing formulations. ERCOT publishes extensive public data (60-day SCED disclosure, fuel mix reports, outage schedules) that could constrain and validate a synthetic model — but no automated pipeline exists to exploit this.

## What an AI-agent-built ERCOT model could look like

The value proposition of using an AI coding agent to build an SCED-realistic synthetic ERCOT model is compelling because ERCOT is uniquely data-rich among US ISOs. ERCOT publishes **60-day-lagged SCED results** with nodal prices, real-time generation by fuel type, transmission constraint shadow prices, and system-wide load data. Combined with EIA Form 860 (all 700+ ERCOT generators with capacity, fuel type, location, and heat rates), EPA CEMS (hourly generation and emissions from fossil plants), FERC Form 714 (hourly load by utility), and OSM transmission infrastructure, an agentic AI system would have access to sufficient open data to construct a model with genuine operational fidelity.

The agent workflow would likely proceed in phases: topology extraction from OSM (substations and transmission lines at 345/138/69 kV), generator placement using EIA coordinates, load allocation based on Census population and FERC profiles, line parameter estimation from OSM conductor metadata and standard engineering tables, and iterative calibration where the agent runs SCED simulations and compares outputs against ERCOT's published market data — adjusting parameters until aggregate statistics (total generation by fuel type, major constraint patterns, zonal price differentials) align with historical data. This calibration loop is precisely the kind of iterative, tool-augmented reasoning task at which modern agentic AI systems excel.

The existing TAMU Texas 7k model provides a useful benchmark: **6,717 buses at 345/138/69 kV** with economic and dynamic data, covering the ERCOT footprint. An AI-agent-built model could potentially exceed this in SCED realism by incorporating actual ERCOT market features — offer curves derived from EIA heat rates and fuel prices, transmission constraints calibrated to published binding constraint lists, and time-varying renewable generation profiles matched to ERCOT's published wind and solar output data.

## Key researchers and institutions shaping this intersection

The researchers most likely to bridge this gap span three communities. In **agentic AI for power systems**: Mengshuo Jia and Gabriela Hug (ETH Zurich) lead on multi-agent simulation frameworks; NREL's team (Choi, Jain, Feng) built eGridGPT with explicit ISO engagement; the Argonne GridMind team demonstrated scaling to real test cases; and the Harvard SEAS PowerAgent community is building open-source infrastructure.

In **synthetic grid models**: Thomas Overbye and Adam Birchfield (Texas A&M) remain the definitive group, with 15+ years of work on the ACTIVSg series and active development of updated cases with modern generation mixes. Line Roald (Wisconsin) contributes to optimization-focused benchmarking.

In **OSM-based and open-data grid modeling**: Tom Brown's group at TU Berlin (PyPSA-Earth/Eur) has built the most complete open-data grid modeling ecosystem; Ram Rajagopal's group at Stanford leads on ML-based geospatial grid mapping; and Priya Donti (MIT) bridges ML methodology with power systems applications, including synthetic data benchmarks like PF∆.

The **DOE national laboratories** are particularly well-positioned to catalyze this intersection. NREL (eGridGPT + Smart-DS synthetic distribution models), PNNL (ChatGrid + ExaGO), and Argonne (GridMind + GridFM collaboration) each have pieces of the puzzle. The DOE ARPA-E program, which funded both the original TAMU synthetic grids (GRID DATA program) and subsequent PERFORM cases, is the natural funding vehicle for a project combining agentic AI with open-data grid construction.

## Conclusion

The convergence of three independently maturing capabilities — agentic AI systems that can orchestrate power system solvers through natural language, large-scale synthetic grid models that provide structural templates, and OSM-based tools that extract real transmission topology — creates a clear and currently unoccupied research opportunity. The **specific gap of using AI agents to build SCED-realistic synthetic grid models from open data** is not merely an incremental improvement; it would fundamentally change how the power systems research community generates test cases, by enabling rapid, reproducible, and geospatially grounded model construction that can be calibrated against publicly available market data.

The technical feasibility is high. LLM agents have already demonstrated the ability to write and execute power flow code (93–97% accuracy at ETH Zurich), OSM coverage of high-voltage transmission is near-complete in many regions, and ERCOT publishes more operational data than any other US ISO. What's missing is not capability but integration — a research effort that connects the agentic AI, synthetic grid, and open-data communities into a single pipeline. The first group to publish a credible AI-agent-built SCED-realistic grid model, validated against real ISO market data, will define a new subfield at this intersection.