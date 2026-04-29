# Why This Project Is Not CEII

## Background: What Is CEII?

Critical Energy Infrastructure Information (CEII) is a protective designation established by FERC under **18 CFR § 388.113** (originally created after the 2003 Northeast blackout and expanded by Order Nos. 630, 649, 683, and 833). The standard was further codified under the **Fixing America's Surface Transportation (FAST) Act of 2015**, which added 16 U.S.C. § 824o-1 to the Federal Power Act, giving FERC explicit authority to protect "critical electric infrastructure information."

CEII covers **specific engineering, vulnerability, or detailed design information** about proposed or existing critical infrastructure that:

1. Relates details about the physical or operational characteristics of a system
2. Could be **useful to a person planning an attack** on critical infrastructure
3. Is exempt from mandatory disclosure under FOIA (5 U.S.C. § 552(b)(3))
4. Goes beyond merely giving the **general location** of the infrastructure

FERC has been explicit that CEII is not a general confidentiality tool. The Commission regularly requires submitters to segregate public information from CEII, and rejects overbroad CEII designations that cover information that does not pose a genuine security risk.

---

## The "Mosaic Theory" Question

The mosaic theory holds that combining individually innocuous pieces of public information could, in aggregate, constitute protected CEII by revealing operationally sensitive details not apparent from any single source.

FERC has acknowledged this risk in principle — but has applied it narrowly and has never issued a blanket ruling that aggregating public datasets creates CEII. The relevant test is always **functional**: does the combined dataset reveal specific engineering vulnerabilities, precise operational parameters, or attack-useful specificity beyond what is already publicly accessible?

This project does not meet that test. Here is why, source by source.

---

## Data Sources and Why Each Is Public

### 1. EIA Form 860

**Why it's public:** EIA-860 is a federally mandated survey under the **Federal Energy Administration Act of 1974 (Public Law 93-275)**. The Energy Information Administration is legally required to collect and publish this data as part of the national energy information program. There is no discretion to withhold it — it is a statutory transparency obligation.

**What it contains:** Generator nameplate capacity, fuel type, plant name, utility ownership, and **plant-level latitude/longitude**. These are *plant* coordinates (i.e., the approximate center of the generating facility's property), not substation schematics, control system architecture, or interconnection parameters.

**What it does not contain:** Transformer impedances, protection relay settings, SCADA system layouts, fault current contributions, breaker configurations, or any information that would enable an adversary to selectively disable infrastructure or predict cascade failure paths.

The plant coordinates in EIA-860 are publicly visible from satellite imagery and county property records. FERC has never attempted to CEII-designate EIA-860 data.

### 2. OpenStreetMap (OSM) Overpass API

**Why it's public:** OSM is crowdsourced geographic data contributed by volunteers observing publicly visible physical infrastructure. High-voltage transmission lines are visible from aerial and satellite imagery and are not concealed from public view. OSM substation data reflects what mappers can observe from public vantage points.

**What it contains:** Line geometries (as OSM ways), voltage tags where recorded by contributors, and substation node locations at a coarse geographic level.

**What it does not contain:** Electrical parameters of any kind. OSM has no impedance data, no protection settings, no SCADA topology, and no knowledge of which substations are electrically coupled. The voltage tags in OSM are often incomplete, inconsistent, or wrong — OSM is a geographic dataset, not an electrical engineering dataset.

### 3. ERCOT Settlement Point / LMP Data

**Why it's public:** ERCOT is required by the **Texas Public Utility Commission** (16 TAC Chapter 25) and by ERCOT's own Nodal Protocols to publish real-time and historical locational marginal prices. Settlement Point Prices (SPPs) are published every 5 minutes on ERCOT's public website and via its public data API. This is a market transparency requirement — electricity markets cannot function without public price signals.

**What it contains:** Prices ($/MWh) at named Settlement Points (Resource Nodes, Load Zones, and Hubs) at 5-minute intervals.

**What it does not contain:** The actual network model used to compute those prices. The ERCOT Network Operations Model (NOM) — which contains the real impedances, bus topology, contingency definitions, and protection schemes — **is** CEII-protected and is posted only to ERCOT's CEII-restricted MIS Certified Area for qualified market participants.

The distinction is critical: **prices** are public; the **network model** that generates them is not.

### 4. U.S. Census Gazetteer

Population counts and ZIP Code Tabulation Area (ZCTA) centroids are public census data, entirely unrelated to infrastructure security.

---

## Why Combining These Sources Does Not Create CEII

### The Output Is Explicitly Synthetic

The Birchfield methodology — which this project implements — was specifically designed for ARPA-E's **GRID DATA program** (Generating Realistic Information for the Development of Distribution and Transmission Algorithms) to produce open, non-CEII power system models. The program's explicit goal was to create grid models that *statistically resemble* real grids without disclosing any actual grid data.

The project description of ACTIVSg2000 (the Texas 2000-bus reference case this project calibrates against) states directly:

> *"It is entirely synthetic, built from public information and a statistical analysis of real power systems. It bears no relation to the actual grid in this location, except that generation and load profiles are similar."*

Dartboard's synthetic grid inherits this property. The topology it generates is a plausible graph that satisfies graph-theoretic properties of real grids — not a reconstruction of the actual ERCOT network. The algorithm has no access to, and does not attempt to recover, the actual transmission line routes, bus configurations, or impedance parameters of ERCOT.

### The OIM Matching Is Geographic Approximation, Not Operational Topology

The `match_nodes.py` fuzzy matching produces approximate geographic coordinates for ERCOT settlement points by correlating settlement point names against EIA-860 plant names and OSM substation names. The result is a set of **approximate lat/lon pairs** for named trading nodes — not an electrical network topology.

Knowing that "BRAUNFELS_UNIT1" is located approximately near New Braunfels, Texas, is not CEII. This information is derivable from the plant name alone and is consistent with what a market participant already knows from the settlement point name and published unit data.

Critically, the matching process does not produce:
- Electrical connections between nodes
- Impedance or admittance values
- Transformer configurations
- Substation single-line diagrams
- Any information useful for targeting physical or cyber attacks

### The Mosaic Test Fails on Specificity

For mosaic theory to apply, the combination must produce **attack-useful specificity** — information that allows an adversary to identify a high-value target, understand its vulnerability, and exploit it. This project produces:

- Statistical distributions of node degrees and line lengths
- Approximate plant locations (already public from EIA-860)
- Market price time series (already public from ERCOT)
- A synthetic graph with Birchfield-calibrated structural properties

None of this reveals protection system vulnerabilities, control system interfaces, or failure propagation paths in the real grid. The information that matters for attack planning — which specific buses are N-1 critical, which substations have cyber-accessible SCADA, what the relay coordination settings are — is entirely absent.

---

## What IS CEII-Protected (That This Project Does Not Touch)

For contrast, here is the category of information that genuinely qualifies as CEII:

| Category | Example |
|---|---|
| Actual network model | ERCOT NOM with real bus/branch impedances |
| Protection relay settings | Time-overcurrent pickup values, coordination margins |
| SCADA architecture | Which RTUs communicate with which EMS, protocol details |
| Fault current calculations | Short-circuit contributions by substation |
| N-1 / N-2 contingency lists | Which contingencies are binding in ERCOT's security analysis |
| Substation single-line diagrams | Actual breaker configurations and bus arrangements |
| Cybersecurity vulnerability assessments | Penetration test results, patch status |
| CRR auction network model | The specific PTDF matrix used in CRR auctions |

This project has access to none of the above.

---

## What the Work Is Good For

Despite being entirely public-data-based and CEII-free, this project has genuine research and analytical value:

**Academic and methodological validation.** Reproducing the Birchfield pipeline demonstrates that synthetic grid generation can be automated end-to-end from open sources, supporting reproducibility in power systems research.

**Algorithm development and benchmarking.** The synthetic topology provides a CEII-free testbed for optimal power flow solvers, contingency analysis tools, and planning algorithms. This is precisely what the ARPA-E GRID DATA program was designed to enable.

**Market structure analysis.** The OIM/GridStatus pipeline — pairing approximate substation geolocations with real ERCOT LMP time series — supports spatial analysis of market price patterns, congestion zone identification, and basis risk between settlement points. This is commercially useful for energy traders studying geographic price spreads without needing access to CEII.

**Load zone and hub basis visualization.** The LMP heatmaps and congestion maps in `OIM/GridStatus/` are directly useful for understanding which geographic regions carry persistent price discounts or premiums relative to the system hub — a standard input to power trading strategies.

---

## What Would Still Need to Happen for Power Trading and Consulting Use

The gap between this project and production-grade power market analytics is real. Here is what is missing:

### 1. Actual Impedance Data (CEII or Derived)

Transmission constraint modeling requires the real PTDF (Power Transfer Distribution Factor) matrix, which depends on actual line impedances. PTDFs determine how power flows when a generator dispatches, and therefore determine which settlement points are exposed to binding constraints.

Without real impedances, this project cannot compute binding constraint shadow prices, congestion revenue rights (CRR) values, or counterflow relationships. These are the core inputs to transmission-aware trading strategies.

*Path to fill this gap:* ERCOT publishes a CRR network model periodically, which qualified market participants can access. Some consultancies use this model under CEII agreements.

### 2. Real-Time Outage and Constraint Data

ERCOT publishes Transmission Constraint and Default Constraint (TCDC) data and Real-Time Binding Constraint reports. Integrating these with the geographic framework built here would allow constraint-aware price prediction. This data is publicly available but requires automated ingestion pipelines not yet implemented.

### 3. Unit Commitment and Offer Data

ERCOT publishes 60-day-lagged unit-level offer curves. Incorporating these into a locational analysis would allow modeling of dispatch-weighted average LMPs by fuel type and geographic cluster — a standard tool for power PPA structuring and hedging analysis.

### 4. Historical Validated Node Matching

The current match rate is ~26% of settlement points matched with high confidence. For trading applications, comprehensive node-level price history coverage is necessary. Closing the remaining 74% requires either manual review of ambiguous matches, TSP interconnection data, or access to ERCOT's own settlement point geographic reference (which is not publicly available).

### 5. Congestion Revenue Right (CRR) Path Modeling

CRR auctions clear on a network model. To value CRR paths — buying the right to collect congestion rents between two settlement points — requires knowing the effective PTDF between those points in ERCOT's auction model. This is the single most commercially valuable missing piece and is definitionally CEII-adjacent (it requires the actual network model or a licensed approximation).

### 6. Validation Against Real Dispatch

The synthetic grid calibrates against structural graph statistics (degree distributions, m/n ratios, line length distributions). It has not been validated against actual ERCOT power flow outcomes — i.e., it is not known whether the synthetic grid produces accurate PTDF estimates for any specific real constraint. Such validation would require comparison against CEII-protected ERCOT data.

---

## Summary

This project occupies a well-defined and legitimate position: it is an open, synthetic, research-grade tool built entirely from public data. Each source is public for independent statutory or market-transparency reasons. Their combination does not produce CEII because it does not yield the attack-useful engineering specificity that CEII is designed to protect.

The genuine gap is not a legal one — it is a modeling one. The project lacks actual network impedances, real constraint data, and validated dispatch modeling. Filling those gaps is what separates this kind of open research infrastructure from the CEII-adjacent data that power market participants license, under appropriate agreements, for production trading and consulting work.

---

## Sources

- [18 CFR § 388.113 — Critical Energy/Electric Infrastructure Information](https://www.law.cornell.edu/cfr/text/18/388.113)
- [FERC CEII Overview](https://www.ferc.gov/ceii)
- [FERC CEII Filing Guide](https://www.ferc.gov/ceii-filing-guide)
- [Federal Register: Critical Energy Infrastructure Information (2002)](https://www.federalregister.gov/documents/2002/09/13/02-23302/critical-energy-infrastructure-information)
- [EIA Form 860 — Annual Electric Generator Report](https://www.eia.gov/electricity/data/eia860/)
- [ARPA-E GRID DATA Program](https://arpa-e.energy.gov/?q=arpa-e-programs%2Fgrid-data)
- [ACTIVSg2000 — Texas 2000-Bus Synthetic Grid](https://electricgrids.engr.tamu.edu/electric-grid-test-cases/activsg2000/)
- [Texas2k Series 2025](https://electricgrids.engr.tamu.edu/texas2k-series25/)
- [ERCOT Market Prices](https://www.ercot.com/mktinfo/prices)
- [ERCOT Real-Time Settlement Point Prices](https://www.ercot.com/content/cdr/html/real_time_spp.html)
- [ERCOT Public Data Portal](https://www.ercot.com/services/mdt/data-portal)
- [ERCOT Modeling Guidelines](https://www.ercot.com/files/docs/2009/05/20/modelingguidelines_v06.pdf)
- [CUI Category: Critical Energy Infrastructure Information — National Archives](https://www.archives.gov/cui/registry/category-detail/critical-energy-infrastructure-information)
- [State Protection of CEII — NGA](https://www.nga.org/wp-content/uploads/2019/05/CEII-Paper-June-2019-Revised.pdf)
