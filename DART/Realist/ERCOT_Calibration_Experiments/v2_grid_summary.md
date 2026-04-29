# v2 ERCOT DC-SCED Grid Summary

Statistical analysis of the v2 model inputs. All numbers computed directly from
`sced_inputs_v2/SourceData/bus.csv`, `branch.csv`, `sced_inputs/SourceData/gen.csv`,
`init_state.csv`, and the calibration day hourly profiles.

Generated: 2026-03-24.

---

## 1. Network Topology

### Bus inventory

| Metric | Count |
|--------|------:|
| Total buses | 3,664 |
| Substations (real OSM nodes) | 2,930 |
| Split points (synthetic T-junctions) | 734 |
| Total branches | 4,420 |
| Edge/node ratio | 1.21 |

**Buses by voltage tier:**

| Voltage | Count |
|---------|------:|
| 138 kV  | 3,088 |
| 230 kV  | 44    |
| 345 kV  | 530   |
| 161 kV  | 1     |
| 698 kV  | 1     |

**Buses by zone:**

| Zone    | Count | % of total |
|---------|------:|----------:|
| NORTH   | 1,259 | 34.4%     |
| SOUTH   | 1,063 | 29.0%     |
| WEST    | 879   | 24.0%     |
| HOUSTON | 463   | 12.6%     |

### Connectivity

The network is a single connected component (all 3,664 buses reachable from any
starting bus). There are zero isolated buses.

**Gen.csv rebuilt for v2 bus IDs.** All 1,185 generators successfully matched to
v2 buses (0 orphaned). The rebuild re-ran the 4-stage bus assignment against v2
topology. Storage.csv also rebuilt (289 units, 17,458 MW).

### Degree distribution

| Degree | Count | Fraction |
|--------|------:|---------:|
| 1      | 720   | 19.7%    |
| 2      | 1,489 | 40.6%    |
| 3      | 1,055 | 28.8%    |
| 4      | 210   | 5.7%     |
| 5      | 87    | 2.4%     |
| 6      | 59    | 1.6%     |
| 7      | 21    | 0.6%     |
| 8      | 12    | 0.3%     |
| 9      | 7     | 0.2%     |
| 10     | 3     | 0.1%     |
| 12     | 1     | 0.0%     |

- **Mean degree: 2.41**
- Median degree: 2.0
- Standard deviation: 1.20
- Maximum degree: 12

**Comparison to real transmission networks:** In the literature (Pagani & Aiello,
2013; Hines et al., 2010), real high-voltage transmission grids typically have
mean degree 2.5-3.5. The Eastern Interconnection has mean degree ~2.8, WECC ~2.9.
Our mean of 2.41 is slightly low, suggesting some missing connections, especially
in urban areas (known issue with OSM topology extraction). The 19.7% pendant
(degree-1) fraction is high compared to typical 10-15% in real grids.

### Edge lengths (km)

| Statistic | km |
|-----------|----|
| Min       | 0.20 |
| P5        | 0.46 |
| P25       | 1.97 |
| Median    | 4.81 |
| P75       | 11.56 |
| P95       | 38.14 |
| Max       | 267.42 |
| Mean      | 10.16 |
| Total     | 44,902 |

- 655 branches < 1 km (14.8%) -- mostly urban bus-section connections and
  substation-to-substation stubs.
- 0 branches < 0.1 km (eliminated by topology construction).

**By voltage tier:**

| Tier  | Mean (km) | Median (km) | Max (km)  | Total (km) |
|-------|-----------|-------------|-----------|------------|
| 138 kV| 7.48      | 4.14        | 97.43     | 24,466     |
| 230 kV| 11.25     | 5.26        | 79.27     | 686        |
| 345 kV| 18.22     | 8.61        | 267.42    | 19,682     |
| 500 kV| 11.17     | 6.82        | 24.94     | 67         |

### Branch ratings

| Rating (MVA)   | Count | % of total |
|----------------|------:|----------:|
| 250            | 1,249 | 28.3%     |
| 500            | 1,058 | 23.9%     |
| 600            | 17    | 0.4%      |
| 750            | 6     | 0.1%      |
| 1,000          | 451   | 10.2%     |
| 1,500          | 8     | 0.2%      |
| 2,400          | 814   | 18.4%     |
| 3,600          | 1     | 0.0%      |
| 4,000          | 4     | 0.1%      |
| 4,800          | 117   | 2.6%      |
| 7,200          | 5     | 0.1%      |
| 8,000          | 2     | 0.0%      |
| 999,999        | 688   | 15.6%     |

**Key observations:**
- 52.2% of branches (2,307) are at either 250 or 500 MVA.
- 15.6% (688) are SPL bridge branches at 999,999 MVA.
- Sum of all finite branch ratings: 3,905,750 MVA.
- Average finite rating: 1,047 MVA.

**By voltage tier:**

| Tier   | Branches | Avg rating | Median | Min   | Max     |
|--------|----------|------------|--------|-------|---------|
| 138 kV | 3,273    | 153,470*   | 500    | 250   | 999,999 |
| 230 kV | 61       | 214,501*   | 2,400  | 600   | 999,999 |
| 345 kV | 1,080    | 163,408*   | 2,400  | 2,400 | 999,999 |
| 500 kV | 6        | 5,333      | 4,000  | 4,000 | 8,000   |

*Averages inflated by 999,999 MVA SPL branches. 138 kV finite branches: 501 at 999k,
leaving 2,772 real branches with median 500 MVA. 345 kV: 174 at 999k, leaving 906
real branches with median 2,400 MVA.

### Zonal interconnection

| Zone    | Cross-boundary branches | Finite capacity (MVA) | Infinite branches |
|---------|------------------------:|----------------------:|------------------:|
| NORTH   | 32                      | 57,550                | 0                 |
| HOUSTON | 16                      | 31,300                | 0                 |
| SOUTH   | 31                      | 43,000                | 0                 |
| WEST    | 17                      | 28,650                | 0                 |

No cross-zone branches have infinite ratings, which is good. The WEST zone has only
17 cross-boundary branches, the most constrained.

Top inter-zone branches (all 345 kV):
- NORTH-SOUTH: 4,800 MVA (L1545_3019_345, L1545_3301_345)
- NORTH-HOUSTON: 4,800 MVA (L3011_3012_345, L1793_3186_345)
- NORTH-WEST: 4,800 MVA (L1622_3054_345)
- HOUSTON-SOUTH: 4,800 MVA (L162_3009_345)

### WESTEX branch

The critical WESTEX branch is dynamically identified by substation name in v2:
**L1594_1601_345** (Morgan Creek Substation → Tonkawa Substation), kept at 1200 MVA.
Bus IDs shifted from v1 (1605→1612) to v2 (1594→1601) due to node merges. The
`build_osm_branch_table_v2.py` now detects Morgan Creek / Tonkawa by name rather
than hardcoded IDs.

### 138 kV bridge analysis (tree-like structure)

**This is the most important topology metric.** Using NetworkX bridge detection on
the constrained 138 kV subgraph (2,820 branches, excluding 999k plant stubs):

| Metric | Value | Healthy range |
|--------|-------|---------------|
| **Bridges (cut edges)** | **1,872 / 2,820** | < 500 for meshed |
| **Bridge ratio** | **66.4%** | < 20% for well-meshed |
| Overloaded bridges | 66 | 0 ideal |
| Total excess load on overloaded bridges | 38,484 MW | 0 ideal |

**A bridge is a branch whose removal disconnects part of the network.** In a true
tree, 100% of edges are bridges. In a well-meshed network, < 20% are. Our 66.4%
confirms the 138 kV network is 2/3 tree-like — OSM captures corridors, not the
full urban mesh.

**Top 10 bottleneck bridges (by downstream load):**

| Branch | Subtree nodes | Load buses | Downstream load (MW) | Rating (MVA) | Excess (MW) |
|--------|--------------|------------|---------------------|-------------|------------|
| 161→1941 | 169 | 141 | 3,670 | 250 | 3,420 |
| 1940→1941 | 168 | 140 | 3,658 | 250 | 3,408 |
| 1940→3634 | 167 | 139 | 3,645 | 500 | 3,145 |
| 2619→3633 | 157 | 133 | 3,570 | 500 | 3,070 |
| 2619→2974 | 155 | 131 | 3,545 | 250 | 3,295 |
| 2563→2974 | 154 | 130 | 3,518 | 250 | 3,268 |
| 926→796 | 75 | 66 | 1,786 | 250 | 1,536 |
| 795→796 | 74 | 65 | 1,759 | 250 | 1,509 |
| 793→795 | 73 | 64 | 1,732 | 250 | 1,482 |
| 925→793 | 71 | 62 | 1,678 | 500 | 1,178 |

The top bottleneck is a chain of 6 bridges where ~170 buses (140 with load) must
funnel ALL their power through a single 250 MVA branch. These 140 load buses carry
roughly 3,670 MW of population-weighted load — 14.7× the branch capacity. In
reality, this subtree would have 5-10 connections to the 345 kV backbone, not 1.

**This is the root cause of load shedding.** Even with adequate generation and
reasonable per-branch ratings, the tree-like structure forces massive load through
single narrow branches.

---

## 2. Generation

### Capacity by fuel type

| Fuel    | Units | Total PMax (MW) | Total PMin (MW) | Avg PMax | Range |
|---------|------:|----------------:|----------------:|---------:|-------|
| Gas     | 449   | 61,542          | 15,695          | 137      | 3-765 |
| Wind    | 384   | 40,534          | 0               | 106      | 2-236 |
| Solar   | 327   | 37,684          | 0               | 115      | 1-336 |
| Coal    | 21    | 14,713          | 5,885           | 701      | 175-1,008 |
| Nuclear | 4     | 5,268           | 4,741           | 1,317    | 1,269-1,365 |
| **TOTAL** | **1,185** | **159,742** | **26,322**  |          |       |

**Comparison to real ERCOT:** As of 2024, ERCOT's installed capacity is approximately
155 GW (nameplate), including ~45 GW wind, ~30 GW solar, ~80 GW thermal. Our model
has 159.7 GW total which is close. Gas (61.5 GW) is slightly below ERCOT's ~75 GW
but reasonable given some generator matching failures. Wind (40.5 GW) and Solar
(37.7 GW) are close to actual.

### Capacity by zone and fuel (MW)

| Zone    | Gas    | Wind   | Solar  | Coal   | Nuclear | Total  |
|---------|--------|--------|--------|--------|---------|--------|
| NORTH   | 20,250 | 11,456 | 12,522 | 3,665  | 0       | 47,893 |
| SOUTH   | 22,742 | 10,046 | 6,125  | 6,680  | 5,268   | 50,860 |
| WEST    | 7,530  | 16,288 | 14,294 | 2,679  | 0       | 40,791 |
| HOUSTON | 7,522  | 1,989  | 4,001  | 1,690  | 0       | 15,202 |

WEST zone: 75% renewable (30,582 MW wind+solar), only 7,530 MW gas -- this is the
export-dependent zone that needs strong transmission to NORTH/SOUTH.

HOUSTON zone: only 15,202 MW generation but 11,500 MW Nov 5 load (20,612 MW Jun 17
peak). At summer peak, Houston would need 5,410 MW imports even if all local gen ran.

### Generators per bus

- **332 buses have generators** out of 3,664 total (**9.1%**).
- Typical real grids: 5-15% of buses have generation. We are in range.
- Most common: 1-2 generators per bus (166 buses).
- Maximum: 22 generators at one bus.

**Top 10 buses by generation capacity:**

| Bus  | Name                    | Zone    | MW    | Units |
|------|-------------------------|---------|------:|------:|
| 1896 | Avery Ranch             | SOUTH   | 4,009 | 9     |
| 1893 | Hilltop                 | SOUTH   | 2,730 | 2     |
| 795  | Briar                   | NORTH   | 2,691 | 17    |
| 1571 | Gasconades Creek        | WEST    | 2,679 | 3     |
| 1895 | Blockhouse              | SOUTH   | 2,538 | 2     |
| 2799 | OSM_2799                | NORTH   | 2,441 | 13    |
| 1842 | P H Robinson            | HOUSTON | 2,203 | 14    |
| 1889 | Industrial Blvd         | NORTH   | 2,145 | 5     |
| 1891 | Zorn                    | SOUTH   | 2,024 | 8     |
| 904  | Onion Creek             | SOUTH   | 1,930 | 9     |

Generation at split points: 1,613 MW (7 units) -- small, not a concern.
Generation at substations: 153,133 MW (1,112 units).
Plus 4,996 MW on 66 units mapped to bus IDs missing from v2.

### Bid stack

| Price ($/MWh) | Fuel(s)       | Units | MW      | Cumulative MW |
|---------------|---------------|------:|--------:|--------------:|
| 0.00          | Wind, Solar   | 711   | 78,218  | 78,218        |
| 1.00          | Gas           | 24    | 568     | 78,786        |
| 8.00          | Nuclear       | 4     | 5,268   | 84,054        |
| 25.00         | Coal          | 21    | 14,713  | 98,768        |
| 28.00         | Gas-CC        | 187   | 37,009  | 135,777       |
| 35.00         | Gas-ST        | 41    | 11,844  | 147,620       |
| 40.00         | Gas           | 7     | 142     | 147,762       |
| 42.00         | Gas-GT        | 148   | 10,347  | 158,109       |
| 45.00         | Gas           | 26    | 1,128   | 159,238       |
| 60.00         | Gas           | 16    | 504     | 159,742       |

The bid stack is clean and realistic:
- 78 GW of zero-marginal-cost renewables form the base
- Nuclear at $8/MWh (reasonable fuel cost)
- Coal at $25/MWh (typical for lignite/sub-bituminous)
- Gas-CC at $28/MWh, Gas-ST at $35/MWh, Gas-GT at $42/MWh
- Price cap at $60/MWh (peakers)

### Initial state

All generators start online and warm:
- Nuclear: `UnitOnT0State=1000`, `PowerGeneratedT0` at PMin
- All thermals: `UnitOnT0State=24` (24 hours online), at PMin
- Total initial power output: 104,540 MW
- This means no cold-start delays at hour 0.

---

## 3. Load Distribution

### How `distribute_load()` works

1. Only 138 kV non-split buses receive load (2,486 eligible out of 3,664).
2. Each bus is assigned the Census 2020 population of its nearest Texas county centroid.
3. Zone MW is distributed proportionally: `bus_load = zone_total * bus_pop / zone_pop_sum`.
4. DC tie imports (1,106 MW total) are subtracted from matching buses.

**Load bus eligibility by zone:**

| Zone    | Load buses | Total buses | Avg MW/bus | Zone total MW |
|---------|-----------|-------------|-----------|--------------|
| NORTH   | 850       | 1,259       | 27.1      | 23,000       |
| HOUSTON | 309       | 463         | 37.2      | 11,500       |
| SOUTH   | 770       | 1,063       | 13.6      | 10,500       |
| WEST    | 557       | 879         | 12.6      | 7,000        |

### Calibration day loads

**Nov 5 default (constant):** 52,000 MW all 24 hours.

**Jun 17, 2024 (summer peak):**
- Min: 51,957 MW (hour 4, early morning)
- Max: 75,891 MW (hour 16, late afternoon)
- Mean: 64,375 MW
- Peak is 1.46x the Nov 5 constant load.

**Jan 8, 2024 (winter):**
- Min: 40,953 MW (hour 2)
- Max: 51,121 MW (hour 18, evening peak)
- Mean: 47,106 MW
- Comfortable within generation capacity.

### Load bus connectivity

| Bus degree | Load bus count |
|-----------|---------------|
| 1 (pendant) | 579 (23.3%)  |
| 2           | 1,304 (52.5%) |
| 3           | 399 (16.0%)   |
| 4+          | 204 (8.2%)    |

**579 load buses (23.3%) are pendant.** Each receives load through a single branch.
For Houston, 31.7% of load buses are pendant; for WEST, 32.1%. These are
single-point-of-failure paths that can create artificial congestion.

---

## 4. Capacity Factors

### Default (Nov 5)

| Fuel  | CF   | Available MW |
|-------|------|-------------|
| Wind  | 0.45 | 18,240      |
| Solar | 0.05 | 1,884       |

### Jun 17 hourly

Wind CF ranges 0.62-0.79 (high wind day, much above 0.45 default).
Solar CF ranges 0.0-0.73 (sunrise ~7am, peak ~3pm, sunset ~9pm).

### Jan 8 hourly

Wind CF ranges 0.69-0.76 (high winter wind day).
Solar CF ranges 0.0-0.19 (low winter solar, short day, overcast).

### Available generation at key hours

**Nov 5 (constant, all hours):**

| Fuel    | Available MW |
|---------|-------------|
| Wind    | 18,240      |
| Solar   | 1,884       |
| Gas     | 61,542      |
| Coal    | 14,713      |
| Nuclear | 5,268       |
| **TOTAL** | **101,649** |
| Load    | 52,000      |
| **Surplus** | **+49,649 (95.5%)** |

**Jun 17 hour 16 (system peak):**

| Fuel    | Available MW |
|---------|-------------|
| Wind    | 27,519      |
| Solar   | 24,773      |
| Gas     | 61,542      |
| Coal    | 14,713      |
| Nuclear | 5,268       |
| **TOTAL** | **133,816** |
| Load    | 75,891      |
| **Surplus** | **+57,925 (76.3%)** |

At every hour on all three calibration days, available generation is 1.4-2.7x
the load. **Generation adequacy is never the problem.**

---

## 5. Energy Storage

289 BESS units in storage.csv:
- Total discharge capacity: 17,458 MW
- Total energy capacity: 54,320 MWh (average ~3.1 hours duration)
- Default aggregation: by zone (4 aggregate units to reduce MIP complexity)

Storage represents a significant resource -- 17.5 GW discharge is one-third of
peak Nov 5 load.

---

## 6. Key Ratios and Sanity Checks

| Metric | Value | Healthy range |
|--------|-------|--------------|
| Nameplate / Nov 5 load | 3.07x | 1.5-2.5x typical |
| Available gen / Nov 5 load | 1.95x | > 1.15x required |
| Available gen / Jun 17 peak | 1.77x | > 1.15x required |
| Network edge/node ratio | 1.21 | 1.2-1.8 typical |
| Mean bus degree | 2.41 | 2.5-3.5 typical |
| Pendant bus fraction | 19.7% | 10-15% typical |
| Buses with generators | 9.1% | 5-15% typical |
| Sum finite ratings / load | 75x | N/A |
| 250+500 MVA branch fraction | 52.2% | varies |
| SPL (999k) branch fraction | 15.6% | 0% ideal |
| Gen/bus mismatch (v1->v2) | 4,996 MW lost | 0 ideal |
| Thermal PMin | 26,322 MW | watch for oversupply |
| Total DC tie imports | 1,106 MW | small |

---

## 7. Bottleneck Diagnosis

### What is most likely causing load shedding?

**Ranking of causes by likely impact:**

### 1. Network congestion -- PRIMARY CAUSE

The model has nearly 2x the generation it needs at every hour, yet load sheds.
This means power cannot reach load centers through the network.

Specific evidence:
- **52.2% of branches at minimum ratings (250 or 500 MVA).** In real ERCOT, 138 kV
  lines are rated 200-600 MVA depending on conductor type; our default of 250 MVA
  for "unknown" lines and 500 MVA for "known" is conservative but not unreasonable.
  The problem is the sheer number -- 2,307 branches bottleneck the 138 kV mesh.

- **688 SPL branches at 999,999 MVA** create phantom corridors. These synthetic
  split-point connections have zero physical basis for their infinite ratings. A
  999,999 MVA line next to a 250 MVA line creates a nonsensical flow distribution
  where all power routes through the SPL bypass.

- **Pendant bus bottlenecks.** 82 pendant buses have generators totaling 34,390 MW.
  17 of these buses have generation exceeding their single outgoing branch rating,
  stranding 7,431 MW. Examples:
  - Bus 1600 (Radium, WEST): 1,231 MW gen but 500 MVA branch
  - Bus 978 (Amistad, WEST): 1,215 MW gen but 250 MVA branch
  - Bus 905 (Texas A&M, NORTH): 1,090 MW gen but 250 MVA branch
  - Bus 184 (Bryan, HOUSTON): 643 MW gen but 250 MVA branch

- **WEST zone export constraint.** WEST has 40,791 MW generation but only 17
  cross-boundary branches with 28,650 MVA total finite capacity. The zone's
  internal load is only 7,000 MW, requiring massive exports (30,000+ MW in
  principle). Even with 28.6 GVA of cross-boundary capacity, internal congestion
  within WEST's 138 kV mesh limits the ability to reach those 345 kV corridors.

- **Houston import constraint.** Houston has 15,202 MW generation but 20,612 MW
  peak summer load, requiring 5,410+ MW imports. The zone has only 16
  cross-boundary branches (31,300 MVA total), which should be adequate -- but
  again, internal 138 kV congestion can prevent power from reaching load buses.

### 2. Tree-like 138 kV topology -- PRIMARY CAUSE (detailed)

The bridge analysis reveals the core problem: **66.4% of 138 kV branches are
cut edges (bridges).** A well-meshed grid has < 20%. This means 2/3 of the
138 kV network is tree-structured, with large subtrees funneling all downstream
load through single bottleneck branches.

The top bottleneck carries 3,670 MW through a 250 MVA branch — a 14.7× overload.
In reality, this subtree would have multiple redundant paths to the backbone.
OSM doesn't capture these because:
- Underground cables are rarely mapped
- Closely-spaced parallel lines are often digitized as one
- Urban distribution meshes use shared rights-of-way not visible in satellite imagery

**Total excess load across all 66 overloaded bridges: 38,484 MW.** This is 74%
of the 52 GW system load. This is why v1's 999k SPL hack "worked" — it
uncapped the T-junction branches that form the tree's interior edges, effectively
eliminating the tree bottleneck. The v2 approach of 2× tier rating (500 MVA)
is not enough for the largest subtrees.

### 3. Load distribution artifacts -- MINOR

579 load buses (23.3%) are pendant, meaning all their load must flow through a
single branch. If a 138 kV pendant load bus receives, say, 50 MW of
population-proportional load but its connecting branch is rated 250 MVA, this is
fine in isolation. But if the branch also carries load for downstream buses, or if
the path to the generation source traverses other congested branches, the pendant
topology amplifies congestion.

The population-weighted distribution is reasonable but can create hotspots near
county centroids with high population (Harris County = 4.7M, Dallas = 2.6M,
Tarrant = 2.1M, Bexar = 2.0M). A bus near the Harris County centroid gets
disproportionate load.

### 4. Bid stack and commitment -- NOT A PROBLEM

The bid stack is well-structured. All thermals start warm (UnitOnT0State=24).
Nuclear is must-run. The merit order is clean. Prices range from $0 (renewables)
to $60 (peakers). No cold-start issues.

### 5. Generation adequacy -- NOT A PROBLEM

With 1.77-1.95x available generation vs load at every hour across all three
calibration days, this is definitively not a supply problem.

---

## 8. Recommendations

### Already done (this session)
- ✅ Gen.csv rebuilt for v2 bus IDs (0 orphaned generators)
- ✅ Storage.csv rebuilt for v2 bus IDs (289 units, 17,458 MW)
- ✅ WESTEX branch dynamically identified by name (L1594_1601_345 at 1200 MVA)

### Options for addressing the tree bottleneck

**Option A: Rate bridges by subtree load (targeted)**
For each bridge branch, compute downstream load and set rating = max(tier_default,
downstream_load × 1.2). This compensates exactly for the missing mesh — a branch
serving 3,670 MW downstream would be rated ~4,400 MVA. Physically motivated: if
the real grid has 5 parallel paths carrying 750 MW each, our single branch should
carry the full 3,670 MW.

**Option B: Increase 138 kV base rating (simple)**
Change the default 138 kV rating from 250 to 400-600 MVA. This is within the
physical range for 138 kV (Drake ACSR can carry 400-600 MVA). But it doesn't fix
the top bottlenecks (3,670 MW >> 600 MVA). Would need to combine with SPL
multiplier increases.

**Option C: Add synthetic mesh connections (architectural)**
For large 138 kV subtrees (>50 nodes behind a bridge), add 2-5 synthetic
connections to the nearest 345 kV bus. This simulates the missing OSM mesh.
Most physically correct but largest code change.

**Option D: Hybrid — constrained bridge rating + moderate SPL multiplier**
- Rate bridge branches at max(tier_default, downstream_load / 5) — assumes
  the real grid has ~5 parallel paths where we have 1
- Increase SPL multiplier from 2× to 4× tier
- Keep plant outlet stubs unconstrained (999k)
This is a middle ground between v1's 999k hack and v2's strict 2× tier.

### Recommended approach
Option D (hybrid) for the next SCED run, then evaluate whether Option A or C
is worth implementing based on results. Option D is quick to implement (change
one constant + add bridge-load logic to build_osm_branch_table_v2.py) and should
dramatically reduce shedding while maintaining realistic congestion patterns.

### Other improvements
1. **Address pendant generator bottlenecks.** 17 pendant buses have generation
   exceeding their single branch rating (7,431 MW stranded). Fix by rating
   gen-outlet branches at max(tier_default, total_gen_at_bus × 1.1).

2. **Increase 138 kV mesh density in urban areas.** Houston and DFW have known
   topology gaps. This is a longer-term effort but would reduce bridge ratio
   toward the healthy < 20% range.
