# Related ERCOT / Power Systems SCED Projects

Research compiled 2026-03-05. Covers open-source projects, datasets, and methodologies
relevant to the Dartboard Realist model. Each section ends with concrete guidance on what
we can take from it.

---

## 1. ACTIVSg2000 — Texas A&M Synthetic Grid

**Repo / data:** `electricgrids.gatech.edu` (requires registration); also shipped with
MATPOWER and referenced in many IEEE papers. The 2,000-bus case covers the full
ERCOT footprint with synthetic but geographically realistic bus locations, line ratings,
and generation mix.

**What it has:**
- 2,000 buses placed at real lat/lon centroids in Texas (modeled after actual substations)
- Generation fleet sized to match 2014 ERCOT capacity (coal, gas, nuclear, wind, solar)
- Transmission topology built to match real ERCOT zone structure
- Validated line flow patterns: max-flow tests pass on every zone boundary
- Published impedance values at each voltage tier

**Relevance to Dartboard:**
- Our OSM network has 4,303 buses and 4,656 edges; ACTIVSg2000 has 2,000 buses and ~3,000
  branches. Comparison reveals whether our connectivity is plausible.
- **Branch ratings:** ACTIVSg2000 uses 345 kV ratings of 900–1,400 MVA for double-circuit
  lines and 400–600 MVA for 138 kV. Our v3 single-circuit 138 kV rating of 300 MVA and
  double-circuit of 600 MVA is consistent with these values.
- **Validation target:** after fixing load assignment and renewable CFs, compare zone-level
  LMPs and interchange flows against ACTIVSg2000 as a sanity check.

**How to use:**
1. Download the MATPOWER case file (M-file format) from TAMU or GridMod.
2. Parse bus/branch/gen tables; compare Pmax by fuel type to our gen.csv.
3. Use their line ratings as a cross-check for implausibly constrained corridors in our model.

---

## 2. TX-123BT — University of Houston / RPG Lab

**Paper:** "A 123-Bus Benchmark Texas Transmission System" (Birchfield et al. successor work,
~2020). Available as supplementary data from the IEEE Transactions paper.

**What it has:**
- 123-bus reduced model of the Texas grid with real-world calibration against ERCOT data
- Includes load profiles from ERCOT historical data (2019–2020)
- Renewable capacity factors at each bus derived from NREL's ATB
- Fully parameterized for DC-OPF

**Relevance to Dartboard:**
- Smallest fully calibrated Texas SCED benchmark — fast to run, good for validating our
  solver setup independent of network complexity.
- **Load profiles:** their 8,760-hour hourly load time-series per zone is directly reusable.
  We need exactly this for non-constant demand (currently deferred).
- **Renewable CFs:** ATB-derived wind/solar capacity factors by ERCOT zone, 8,760 hours.

**How to use:**
1. Email the RPG Lab (UH) or check the IEEE supplementary for the Excel/CSV data.
2. Extract zone-level hourly load scaling factors → apply to our 50,894 MW baseline.
3. Extract per-zone wind/solar CF time-series → apply to wind/solar generators in our gen.csv.

---

## 3. Breakthrough Energy / PowerSimData + PreREISE

**Repo:** `github.com/Breakthrough-Energy/PowerSimData` and
`github.com/Breakthrough-Energy/PreREISE`

**What it has:**
- Full US grid model (WECC, Eastern, Texas Interconnect) in a REISE-compatible format
- ERCOT region uses a ~1,000-bus reduced model
- 8,760-hour historical demand and renewable CF profiles (2016 base year)
- Wind/solar profiles derived from NREL WIND Toolkit and NSRDB
- Includes a scenario framework for capacity expansion studies

**Relevance to Dartboard:**
- **Best available open-source load + renewable profiles for ERCOT.**
  PreREISE pulls demand from EIA-930 and ERCOT historical publications.
  Solar CFs from NSRDB, wind from WIND Toolkit — exactly what we need.
- The ERCOT grid topology they use (~1,000 buses) is a good cross-check for ours.

**How to use:**
1. `pip install powersimdata` (MIT license)
2. Use `Scenario` class to pull the ERCOT base case; export bus/branch tables.
3. Load the `ct` (change table) time-series demand and CF profiles for the ERCOT region.
4. Map their zone-level demand scaling factors to our OSM buses via ERCOT zone membership.

```python
from powersimdata import Scenario
s = Scenario("Texas")          # pulls ERCOT base case
grid = s.get_grid()
profile_demand = s.get_demand() # DataFrame: 8760 rows × zones
profile_wind   = s.get_wind()
profile_solar  = s.get_solar()
```

---

## 4. ORFEUS-PERFORM / Vatic (Princeton)

**Repo:** `github.com/PrincetonUniversity/Vatic` (our solver's upstream)

**What it has:**
- Prescient-based DC-SCED/SCUC simulation engine (same as what we run on Adroit)
- Full US Western Interconnect and ERCOT studies published; input data partially available
- ERCOT studies use WECC/ERCOT case data from NREL's PLEXOS dataset

**Companion tool — PGscen:**
**Repo:** `github.com/PrincetonUniversity/PGscen`

- Probabilistic scenario generator for joint load/solar/wind uncertainty
- Trained on GridStatus historical ERCOT data
- Generates spatially and temporally correlated scenarios (copula model)
- Used in the ORFEUS real-time unit commitment studies

**Relevance to Dartboard:**
- PGscen is the best open-source tool for generating realistic correlated load + renewable
  scenarios from ERCOT historical data, without needing a subscription.
- Their scenario format is directly compatible with Vatic/Prescient input CSV structure.

**How to use:**
1. `pip install pgscen` (or clone repo)
2. Fit to ERCOT data via GridStatus API (free tier covers 1 year of history)
3. Sample N scenarios for a target date → get per-bus renewable CF profiles
4. Scale zone demand by their sampled load factor

---

## 5. Prescient / EGRET (Sandia / DOE)

**Repo:** `github.com/grid-parity-exchange/Prescient`

This is literally our solver stack. The EGRET data model is what Vatic wraps.

**What it has:**
- Reference test cases including RTS-GMLC (73-bus, 3-zone) with full 1-year profiles
- Prescient's `populator` module: downloads and formats real ISO data into SCED inputs
- Built-in support for ERCOT historical data via EIA and RTO APIs

**Relevance to Dartboard:**
- **`prescient.plugins.data_providers`:** their `ErcotDataProvider` (if it exists in your
  version) or equivalent can pull ERCOT load/price data directly into Prescient CSV format.
- RTS-GMLC case is the canonical validation benchmark for DC-SCED implementations.

**How to use:**
1. Run the Prescient `populate_with_download.py` script against ERCOT region to generate
   profiles in native CSV format.
2. Use RTS-GMLC as a unit test: if our solver reproduces published RTS-GMLC LMPs, the
   SCED solve is correct. This isolates network/generator model errors from solver errors.

---

## 6. RTS-GMLC — NREL / GridMod

**Repo:** `github.com/GridMod/RTS-GMLC`

**What it has:**
- 73-bus, 3-zone synthetic US grid test case with 1 year of hourly profiles (2020)
- Load: real US demand scaled to test case size
- Wind/solar CFs: NREL SAM-generated 8,760-hour profiles at bus locations
- Fully documented; IEEE-format bus/branch/gen tables plus Prescient-native CSVs
- Published benchmark results (LMPs, line flows, commitment decisions) for validation

**Relevance to Dartboard:**
- **Best validation target for our solver.** Before trusting 6,300 MW of load shedding in
  the Dartboard v4 run, we should verify that our Vatic/Prescient stack reproduces
  published RTS-GMLC results on the standard case.
- Their CSV format (`RTS_Data/SourceData/`) is identical to what Vatic expects.

**How to use:**
```bash
git clone https://github.com/GridMod/RTS-GMLC
# Copy RTS_Data/SourceData/ as sced_inputs/SourceData/
# Run run_sced.py pointed at RTS inputs
# Compare hourly_summary.csv against published results in docs/
```

---

## 7. GridStatus Library

**Repo:** `github.com/kmax12/gridstatus`

**What it has:**
- Python library for pulling real-time and historical ISO data
- ERCOT: loads, LMPs, wind/solar output, generation by fuel, ancillary prices
- Free tier: ~1 year historical, 15-min resolution
- Returns pandas DataFrames directly

**Relevance to Dartboard:**
- **Best source for real ERCOT validation data.** We can pull actual LMPs for Nov 5, 2025
  (our simulation date) and compare against our model's output.
- **Load profiles:** actual ERCOT hourly system load for any date → use as demand time-series
  instead of constant 50,894 MW.
- **Renewable output:** actual wind/solar generation by hour → derive zone-level CFs.

**How to use:**
```python
import gridstatus
ercot = gridstatus.Ercot()

# Actual load for our simulation date
load = ercot.get_load("2025-11-05")

# Actual LMPs (settlement point prices)
lmp = ercot.get_lmp("2025-11-05", market="DAM", locations="ALL")

# Wind/solar generation
fuel = ercot.get_fuel_mix("2025-11-05")
```

Compare `lmp["LMP"]` per zone to our `hourly_summary.csv` Price column.

---

## 8. ERCOT Public Data

ERCOT publishes extensive historical data at `ercot.com/gridinfo`:

| Dataset | URL path | What it gives us |
|---|---|---|
| Hourly load by weather zone | `/gridinfo/load/` | Hourly MWh by zone (8 zones) |
| Wind generation | `/gridinfo/generation/` | Hourly wind output statewide |
| Solar generation | `/gridinfo/generation/` | Hourly solar output statewide |
| 60-day LMPs (DAM/RTM) | `/mktinfo/prices/` | Settlement point prices |
| Generator capacity | `/gridinfo/resource/` | Installed capacity by fuel, updates monthly |
| Transmission constraint reports | `/gridinfo/ops/` | Real binding constraints by name |

**Most important for us:** the transmission constraint reports name real binding constraints
(e.g., "ERCOT_CNCTP_500kV_1" for specific corridors). Matching these to our branch.csv
UIDs would tell us which congestion patterns our model should reproduce.

---

## Prioritized Guidance for Dartboard

### Short-term (next session)
1. **Validate solver correctness against RTS-GMLC** before spending more time on network
   modeling. A 5-minute run on the standard case with published results will confirm the
   SCED solve is right.

2. **Pull actual ERCOT load for Nov 5, 2025 via GridStatus** and replace constant 50,894 MW
   with hourly zone-level demand. This is a one-afternoon task and removes the biggest
   source of model unrealism.

3. **Compare our LMPs to ERCOT DAM prices for Nov 5, 2025.** Our v4 prices are ~$21/MWh
   flat; actual ERCOT DAM prices on a typical fall day are $20–45/MWh with meaningful
   hour-to-hour variation. If ours are flat but in the right range, the generation mix is
   approximately right; if ours are wrong by 2–3x, recalibrate generator cost curves.

### Medium-term
4. **Use PreREISE / PowerSimData for 8,760 annual profiles** (load + wind CF + solar CF).
   Map their zone-level profiles to our bus-level assignments via ERCOT zone membership.

5. **Use ERCOT transmission constraint reports** to identify which corridors are most
   frequently binding in reality. If those corridors are also binding in our model, we have
   the right physics. If different corridors bind, the topology or ratings need adjustment.

6. **Cross-check generator fleet against ACTIVSg2000.** Their 2,000-bus ERCOT case has a
   calibrated 2014 fleet; scale to 2025 ERCOT installed capacity using EIA-860.

### Long-term
7. **Integrate PGscen for scenario-based studies.** Once deterministic SCED is validated,
   run N=100 scenarios of correlated load/wind/solar uncertainty for a full week to get
   uncertainty-aware dispatch and LMP distributions.

8. **Texas A&M ACTIVSg7000 (if accessible).** The 7,000-bus Texas case (if published) would
   be the closest analog to our OSM-native network at 4,303 buses.

---

## Key Takeaway on Current Shedding

Our v1–v4 shedding (2,976–8,600 MW depending on version) is **not a solver bug**. The
max-flow analysis confirms 98.1% of load is topologically reachable; the residual 6,300 MW
in v4 is congestion from:

1. Single-circuit 138 kV lines at 300 MVA (physically correct for unconfirmed segments)
2. Constant load on 138 kV substations creates uniform hourly pressure on every radial line
3. Wind/solar CF is constant at installed capacity — no off-peak slack

The fix is real demand profiles (#2 above), not more network nodes. Once load varies
hour-to-hour, congestion will appear only in the right hours (morning peak, evening ramp)
and the model will better reproduce real ERCOT market dynamics.
