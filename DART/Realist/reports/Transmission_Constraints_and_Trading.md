# ERCOT Transmission Constraints and Trading Implications

**Generated:** 2026-02-26
**Data window:** 2026-01-27 → 2026-02-26 (720 hourly SCED snapshots)
**Nodes analyzed:** 455 direct-matched substations (high/medium confidence only)

---

## Overview

ERCOT's nodal pricing reveals which transmission corridors are binding by creating persistent
price wedges between geographically proximate nodes. This report synthesizes 30 days of LMP
history to identify the most active constraints, map them to specific corridors in the physical
network, and draw implications for point-to-point (FTR/CRR) and day-ahead/real-time (DART)
trading strategies.

The mean system-wide LMP spread (max − min across all resource nodes per hour) was
**$174.44/MWh** over this period. Zone-to-zone spreads are much smaller (mean $17.38/hr),
confirming that the most severe constraints are **intra-zonal** — binding within LZ_SOUTH
and LZ_WEST rather than across the historical four-zone seams.

---

## Identified Constrained Corridors

### 1. Del Rio / Eagle Pass Import Pocket (SW Texas 345 kV)

**Evidence:** AMISTAD, HAMILTON, ZIER_SLR, PUEBLO, FTDUNCAN, ESCONDID, ECLIPSE, ANACACHO —
all clustered between lon −100° and −101°, lat 29°–30°, all in LZ_SOUTH with congestion
premiums of **+$14 to +$25** above their load zone average.

| Node | Mean LMP | Zone Premium | Std Dev |
|------|----------|-------------|---------|
| AMISTAD | $53.49 | +$24.96 | $102.59 |
| HAMILTON | $53.49 | +$24.96 | $102.59 |
| ZIER_SLR | $43.76 | +$15.23 | $89.70 |
| PUEBLO | $43.53 | +$15.01 | $102.34 |
| FTDUNCAN | $42.98 | +$14.46 | $100.62 |
| ESCONDID | $42.40 | +$13.87 | $98.91 |
| ANACACHO | $42.33 | +$13.80 | $90.70 |

The AMISTAD→JUNCTION differential is −$18.88 on average with the Junction end cheaper 76%
of the time — load is pulling northward but the lines can't deliver enough. The geographic
cluster resolves to the **345 kV backbone feeding Eagle Pass and Del Rio**: the Uvalde–
Braunig and Laredo–Lobo corridors that serve a load pocket with limited local generation.
The pocket's only significant local resources are hydro at Amistad Dam (modest capacity)
and a few peakers — demand pulls from San Antonio and Laredo, which have to push over
constrained 345 kV lines.

**The high standard deviation ($90–$103) at these nodes is the tell.** This constraint binds
hardest during summer afternoons and winter morning ramps, when border-area load peaks and
the lines are already at thermal limit from serving Laredo's load.

---

### 2. Permian Basin / Pecos Isolation (West Texas Intra-Zonal)

**Evidence:** RUSSEKST (Rusk East, lon −101.46, lat 31.18) is the single most import-
constrained node in the dataset: mean **$65.22**, congestion proxy **+$30.45**, and a
standard deviation of **$140.29** — the highest in the network. APPALOSA and INDNNWP nearby
show similar but smaller premiums. Simultaneously, COYANOSA (Pecos Basin, lon −102.96)
is export-constrained at **$24.89** (−$9.88 below LZ_WEST average), and the
Rusk–Coyanosa differential averages **−$35.78** (Rusk is $35.78 more expensive), with
divergence exceeding $20 in 17% of hours.

This is the **Permian Basin bottleneck**: the transmission path connecting Pecos Basin
wind and gas generation to the Midland–Odessa load center is thermally limited.
COYANOSA sits at the export (generation) side; RUSSEKST sits at the import (load) side.
When the constraint binds, Permian Basin wind/gas gets stranded at Coyanosa-area prices
while Rusk-area industrial and oilfield load pays a large premium. The $140 standard
deviation at RUSSEKST reflects a constraint that swings violently — inactive during
shoulder hours, extremely active during morning industrial ramps in the Permian.

---

### 3. Rio Grande Valley Export Constraint (South Texas Wind/Solar Trap)

**Evidence:** BBREEZE, ELSAUZ, NEBULA, LAURELES, CEDROHIL, SANROMAN, CORAZON, WFTANK —
a dense cluster of nodes in the lower Rio Grande Valley (lat 26°–27°, lon −97° to −99°)
all showing:

- Mean LMP **$19–20** (−$8 to −$9 below LZ_SOUTH average of $28.52)
- **30–36% of hours with negative prices**
- Low standard deviation ($66–67) relative to their negative proxy — the constraint is
  **persistent**, not intermittent

The Breezeport→Formosa corridor (RGV to the Corpus Christi coast) shows a +$15.32 mean
differential with Formosa more expensive **69% of the time**. This is the signature of
wind and solar generation in the Valley that is stranded behind a northbound 345 kV
constraint. The RGV has substantial wind capacity (South Texas wind belt) and growing
solar, but the lines heading north toward San Antonio (through the Edinburg/McAllen area)
are consistently full, particularly during daytime solar hours and overnight wind peaks.

The 36% negative-price frequency at BBREEZE/ELSAUZ is the clearest trading signal in
this dataset.

---

### 4. DFW West / Decatur Wind Export (North Texas Intra-Zonal)

**Evidence:** SPNCER (Spencer substation, lat 33.20, lon −97.11) is the most export-
constrained node in LZ_NORTH: mean $20.69, proxy **−$12.57**, std $88.68. DEC (Decatur)
is adjacent with proxy −$9.18. The Spencer–LK differential averages **+$15.53** with LK
more expensive 47% of the time and divergences exceeding $20 in 16% of hours.

Spencer and Decatur sit west-northwest of Fort Worth, in a dense wind corridor. The
constraint is on the lines carrying wind generation southeast toward the DFW load center.
This is a well-known ERCOT bottleneck: the Denton–Graham–Jacksboro area has abundant
West Texas and North Texas wind reaching its export limits into the metroplex. The high
standard deviation ($88) reflects that this constraint binds primarily at night
(high wind, low load) and releases during peak afternoon demand.

---

### 5. Panhandle Wind Export (HB_PAN Structural Underpricing)

**Evidence:** HB_PAN is the cheapest hub in the dataset at **$27.72** mean. The Panhandle→
North differential averages **+$5.53** with North more expensive 54% of the time and
differentials exceeding $10 in 24% of hours. This is modest relative to the intra-zonal
constraints above, but it is directionally consistent.

The Panhandle is chronically long on wind capacity relative to its local load. The constraint
is on the PNEC (Panhandle North-East Connector) and associated 345 kV lines heading south.
During high-wind periods, Panhandle generation spills over into HB_WEST, compressing the
West–North differential and occasionally driving negative prices in the far northwest.

---

## Temporal Patterns

LZ_WEST by hour of day reveals the two-regime pattern typical of solar-heavy West Texas:

| Period | LZ_WEST Mean | Interpretation |
|--------|-------------|----------------|
| 09:00–16:00 | **$7–12** | Solar saturation; Permian Basin generation exceeds local export capacity |
| 07:00 | **$80.79** (std $244) | Morning ramp; most volatile hour in the data |
| 18:00–21:00 | **$50–62** | Evening peak; solar gone, wind not yet sufficient |
| 00:00–05:00 | **$43–47** | Overnight baseload; moderate West Texas prices |

The 07:00 spike with std=$244 is extreme. It captures the morning ramp window when West Texas
industrial load turns on faster than generation can respond — the constraint briefly inverts
before solar output rises. This is the single most rewarding window for short-duration DART
trades at West Texas import nodes.

---

## Trading Implications

### Point-to-Point / FTR Positions

FTRs (or CRRs in ERCOT terminology) are financial instruments that pay the LMP differential
between a source and sink node, collected over the auction settlement period.

**High-conviction directional positions:**

| Source (sell) | Sink (buy) | Mean $/MWh spread | Binding frequency | Risk |
|--------------|-----------|-------------------|-------------------|------|
| COYANOSA | RUSSEKST | +$35.78 | 61% of hours | Very high std ($125) — spike risk |
| BBREEZE / ELSAUZ | FORMOSA | +$15.32 | 69% of hours | Moderate — persistent, stable pattern |
| SPNCER | LK | +$15.53 | 47% of hours | Moderate — intermittent, wind-dependent |
| AMISTAD | JUNCTION | +$18.88 | 76% of hours | Moderate — persistent during peak demand |
| HB_PAN | HB_NORTH | +$5.53 | 54% of hours | Low magnitude but directionally reliable |

**The RGV→coast corridor (BBREEZE→FORMOSA) is the cleanest trade.** It binds 69% of hours
with a consistent $15 average spread and moderate standard deviation — meaning the constraint
is structural rather than event-driven. A long FTR source=RGV, sink=Corpus area captures
the bottleneck on northbound export capacity from the Valley wind belt.

**The COYANOSA→RUSSEKST position has the highest expected value but also the highest variance.**
The $125 standard deviation means this spread regularly goes negative (Coyanosa more expensive
than Rusk during off-peak solar hours when the Pecos Basin constraint relaxes). This is a
position for participants with the balance-sheet tolerance for mark-to-market swings.

**The Eagle Pass import pocket (AMISTAD→interior)** is attractive but carries political risk:
if ERCOT builds additional 345 kV capacity into the Del Rio/Eagle Pass area (proposals exist),
the congestion premium collapses. FTRs here are a bet that planned transmission is delayed.

### DART (Day-Ahead vs. Real-Time) Trades

DART arbitrage exploits the difference between day-ahead LMPs (which reflect the DA market
clearing) and real-time LMPs (which respond to actual dispatch and constraint binding).

**1. RGV negative-price hours (BBREEZE, ELSAUZ, ELSAUZ area nodes)**

With 36% of real-time hours at negative prices and a mean LMP of +$19, the day-ahead
typically prices these nodes positive. A systematic **buy real-time / sell day-ahead** at
BBREEZE and ELSAUZ — triggered by high wind forecasts or high solar production in the
Valley — captures the RT negative spike relative to a positive DA clearing. The trade is
essentially: the DA market underestimates curtailment frequency; the RT market delivers
negative prices that the DA cleared away.

Execution caveat: this trade is directionally profitable but requires predicting which hours
will clear negative. The 36% frequency suggests the DA market knows curtailment happens — the
arb is in the hours where the DA cleared at +$5 and RT hits −$30.

**2. West Texas morning ramp (07:00 RUSSEKST, APPALOSA)**

The 07:00 hour in LZ_WEST has a mean of $80.79 with std=$244 — by far the highest expected
value single hour. When the morning ramp constraint binds at Rusk East, RT prices spike far
above what DA typically clears. A **long RT / short DA** at RUSSEKST during mornings with
high industrial activity (weekday) and low Permian wind captures this. The risk is that when
the morning ramp doesn't bind (wind carries the load), the position is flat or slightly short.

**3. Daytime solar suppression in West Texas (09:00–16:00)**

LZ_WEST averages only $7–12 during solar hours. If DA clears at $15–20 (reflecting expected
solar but not curtailment), a **buy DA / sell RT** at West Texas generation nodes during
daytime is profitable when solar oversupply drives RT below DA. This is the flip side of the
morning ramp trade: same nodes, opposite time-of-day, opposite direction.

**4. DFW wind constraint overnight (SPNCER)**

Spencer trades at −$12.57 below its zone average, and the constraint is wind-driven (peaks
overnight and during high-wind periods). When ERCOT's wind forecast for North Texas is high,
DA may not fully price in the Spencer constraint. A **sell DA / buy RT** at Spencer on
high-wind nights — paired with a **buy DA / sell RT** at a southeast load sink — approximates
a synthetic FTR that the RT constraint will deliver.

---

## Structural Observations

**The dominant narrative in this 30-day window is renewable curtailment**, not load-driven
congestion. The export-constrained nodes (RGV, Panhandle, Pecos Basin, DFW West) are all
generation-heavy renewable areas. The import-constrained nodes (Eagle Pass pocket, Rusk East)
are either load pockets with limited local supply or areas where the grid simply cannot
import enough to match local demand.

**Zone-to-zone constraints are mild relative to intra-zonal constraints.** The mean hourly
zone spread is only $17.38, and the North–Houston and West–North hubs trade within $5 of
each other most of the time. The big money in ERCOT right now is in nodal FTRs that capture
intra-zonal pockets, not in legacy four-hub trades.

**Network topology note:** The corridors identified here are consistent with known ERCOT
transmission planning priorities. Projects in the queue (Oak Hill–Lobo, additional Laredo
area 345 kV, Panhandle expansion) would specifically address the Eagle Pass pocket and
Panhandle export constraints. Participants holding long FTRs on these corridors face step-
change downside risk when new lines enter service.

---

## Caveats

- **30-day window (Jan–Feb 2026)** covers winter load patterns and seasonal wind but misses
  summer peak demand, when the Eagle Pass and Houston-area constraints are likely more severe.
- **455 direct-matched nodes** out of ~5,000 ERCOT settlement points — the most active
  constraints may be on substations not captured in this dataset.
- **Node coordinates** are from OSM/EIA-860 matching (high/medium confidence only); the
  geographic corridor inference is approximate.
- FTR values depend on the auction-clearing price, not just the historical LMP spread.
  Spreads shown here are indicative of constraint rent but not directly bankable without
  accounting for FTR auction premiums.

---

## Data Provenance

- LMP source: ERCOT Public API, report NP6-788-CD, one SCED interval per hour
- Substation coordinates: `grid_data/matching_results/texas_matched_substations_v6.csv`
  (filtered to `confidence ∈ {high, medium}`, `match_source` direct only — 455 nodes)
- Resource-node → substation mapping: `SP_List_EB_Mapping/Resource_Node_to_Unit_01292026_104938.csv`
- Supporting figures: `Realist/reports/figures/` (see `ERCOT_Congestion_Analysis.md`)
- Analysis code: `Realist/reports/congestion_analysis.py`, `Realist/ERCOT/pull_lmp_ercot.py`
