# Dartboard

Synthetic transmission grid generation + real-world ERCOT network analysis.

This repository implements the synthetic grid methodology of Birchfield et al. (*"Grid Structural Characteristics as Validation Criteria for Synthetic Networks"*) and supplements it with real-world data from ERCOT, OpenStreetMap, and EIA-860 to validate and visualize the results.

---

## Repository Structure

```
Dartboard/
│
├── config/                        # Region-specific and global parameters
│   ├── texas.yaml
│   ├── new_york.yaml
│   └── global.yaml                # Shared topology parameters (Stage 3+)
│
├── core/                          # Core algorithmic modules
│   ├── graph_types.py             # Data structures (Bus, Branch, Generator, etc.)
│   ├── load_nodes_clustering.py   # Stage 1a: Hierarchical clustering (Type A)
│   ├── generator_assignment.py    # Stage 1b: Generator assignment (Type B)
│   ├── remaining_generator_clustering.py  # Stage 1c: Gen-only clusters (Type g)
│   ├── voltage_partition.py       # Stage 2: Voltage levels & bus creation
│   └── topology_generation.py     # Stage 3: Birchfield iterative line placement
│
├── ingest/                        # Data loading and preprocessing
│   ├── census.py                  # Census Gazetteer + population data
│   ├── eia860.py                  # EIA-860 power plant data
│   └── boundary_filter.py         # Geographic boundary filtering
│
├── pipelines/                     # Pipeline scripts (numbered by execution order)
│   ├── 1_build_clustered_substations.py
│   ├── 2_assign_generators.py
│   ├── 3_cluster_remaining_generators.py
│   ├── 4_verify_stage1.py
│   ├── 5_partition_voltages.py
│   ├── 6_verify_stage2.py
│   ├── 7_generate_topology.py
│   └── 8_visualize_topology.py
│
├── viz/                           # Visualization scripts
│   ├── cluster_visualization.py
│   ├── generator_assignment_viz.py
│   ├── complete_substation_viz.py
│   ├── voltage_partition_viz.py
│   └── network_topology.py
│
├── Calibration/                   # Calibration against Texas-7k reference network
│   ├── compute_reference_targets.py
│   ├── run_topology_on_texas7k.py
│   ├── compare_texas7k_vs_dartboard.py
│   ├── run_alignment_experiments.py
│   ├── run_texas2k_experiments.py
│   ├── parameter_sweep.py
│   ├── network_stats.py
│   ├── network_io.py
│   ├── texas2k_io.py
│   ├── visualize_*.py
│   └── texas7k_calibration_results.md
│
├── OIM/                           # OpenInfraMap — real-world ERCOT network analysis
│   ├── fetch_hv_lines.py          # Pull HV transmission lines from OSM Overpass API
│   ├── fetch_substations.py       # Pull substations from OSM Overpass API
│   ├── plot_hv_lines.py           # Texas HV line + substation map
│   ├── match_nodes.py             # 3-pass fuzzy matching: ERCOT nodes → OSM/EIA-860
│   ├── data/                      # OSM GeoJSON, LMP snapshots, substation CSVs
│   ├── FirstPass/                 # Matching results, visualizations, report
│   ├── GridStatus/                # Real-time ERCOT LMP maps
│   └── plans/                     # Integration plans (OpenInfraMap, Matching, ERCOT API)
│
├── SP_List_EB_Mapping/            # ERCOT settlement point reference data
│
├── Texas2k_series2025/            # Texas-2k reference case data and comparisons
│
├── data/
│   ├── raw/                       # Census Gazetteer (gitignored)
│   ├── eia8602023/                # EIA-860 Form 2023 (gitignored)
│   ├── processed/                 # Intermediate CSVs from Stages 1–3
│   └── synthetic/                 # Final line CSVs and topology PNGs
│
├── vatic/                         # Power flow simulation library (Texas A&M)
├── plans/                         # Implementation specs for Stages 1–3
├── version1/                      # Earlier pipeline attempt (reference only)
├── old tests/                     # Archived stage test reports
│
├── CLAUDE.md                      # Agent instructions for Claude Code
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Required packages: `numpy`, `pandas`, `matplotlib`, `scipy`, `pyyaml`, `openpyxl`
- For OIM/GridStatus: Python 3.12 venv with `gridstatus`, `geopandas`, `rapidfuzz`, `shapely`

### Running the Synthetic Grid Pipeline

```bash
# Stage 1: Substation Synthesis
python3 pipelines/1_build_clustered_substations.py
python3 pipelines/2_assign_generators.py
python3 pipelines/3_cluster_remaining_generators.py
python3 pipelines/4_verify_stage1.py

# Stage 2: Voltage Partition
python3 pipelines/5_partition_voltages.py
python3 pipelines/6_verify_stage2.py

# Stage 3: Topology Generation
python3 pipelines/7_generate_topology.py
python3 pipelines/8_visualize_topology.py
```

### Running the OIM Pipeline (Real-World ERCOT Analysis)

```bash
# Fetch OSM data (one-time)
python3 OIM/fetch_hv_lines.py
python3 OIM/fetch_substations.py

# Match ERCOT settlement points to geographic coordinates
python3 OIM/match_nodes.py

# Plot matched substations
python3 OIM/FirstPass/plot_matched_nodes.py

# Pull real-time LMPs (requires Python 3.12 venv)
OIM/.venv312/bin/python3.12 OIM/GridStatus/pull_lmp.py

# Plot LMP maps
python3 OIM/GridStatus/plot_lmp_map.py
```

---

## Synthetic Grid Pipeline (Stages 1–3)

### Stage 1: Substation Synthesis

Clusters Census postal codes into load substations (Type A), assigns generators (Type B), and clusters remaining generators (Type g).

- Population-weighted Haversine distance with max population constraint (4500 people)
- Deterministic weighted sampling with fixed seed (42)
- Fuel homogeneity constraints for Type-g clustering

**Results:**
- **Texas**: 1,250 substations (1,182 A + 68 B + 62 g) from 1,934 postal codes
- **New York**: 600 substations (567 A + 33 B + 30 g) from 903 postal codes

### Stage 2: Voltage Partition

Assigns voltage levels and creates buses per substation.

- 15% of substations receive 345 kV buses; all get 115 kV base buses
- Internal transformers connect voltage levels

**Results:**
- **Texas**: 1,312 substations → 1,509 buses (1,312 @ 115 kV + 197 @ 345 kV)
- **New York**: 630 substations → 724 buses (630 @ 115 kV + 94 @ 345 kV)

### Stage 3: Topology Generation

Implements the Birchfield iterative line placement algorithm.

- Candidate generation: Delaunay triangulation + MST + 2-neighbor + 3-neighbor edges
- Category quotas (MST 50%, Delaunay 20%, 2-neighbor 25%, 3-neighbor 5%)
- DC power flow via susceptance matrix solved with `scipy.sparse.linalg.spsolve`
- Two-phase scoring: cheap pass on all candidates, expensive (intersections + DC flow) on top K
- Target m/n ratio: 1.22

**Results:**

| Network | Nodes | Lines | m/n | Intersection Rate | Time |
|---|---|---|---|---|---|
| NY 345 kV | 94 | 115 | 1.223 | 1.74% | 0.5s |
| NY 115 kV | 630 | 774 | 1.229 | 4.01% | 17s |
| TX 345 kV | 197 | 240 | 1.218 | 4.58% | 1.7s |
| TX 115 kV | 1,312 | 1,612 | 1.229 | 3.23% | 71s |

---

## Calibration

The `Calibration/` module validates the synthetic topology against the Texas-7k reference network (from `vatic/`). It runs Dartboard's topology generator on the same bus positions as Texas-7k for an apples-to-apples comparison.

Key findings (see `Calibration/texas7k_calibration_results.md`):
- Degree distribution shape matches Texas-7k (dominated by degree-2, tail to 10–13)
- Line lengths closely match at 138 kV (mean 9.8 km vs 13.1 km)
- Intersection rate is much lower than Texas-7k (1–3% vs 10–24%)
- Main structural gap: Texas-7k is denser (m/n = 1.55 at 345 kV) than Birchfield's 1.22 target

Also includes experiments against the Texas-2k reference case (`Texas2k_series2025/`).

---

## OIM: OpenInfraMap / ERCOT Real-World Analysis

The `OIM/` module pulls real-world transmission infrastructure from OpenStreetMap and connects it to ERCOT market data. This provides a ground-truth reference layer for validating the synthetic grid.

### Data Acquisition

- **HV transmission lines**: 28,504 lines (≥115 kV) fetched from OSM Overpass API, clipped to Texas boundary → 22,913 lines
- **Substations**: 8,212 substations fetched from OSM, clipped → 5,786

### ERCOT Settlement Point Matching

`match_nodes.py` uses 3-pass fuzzy matching to geolocate ERCOT's 4,954 settlement point substations:

1. **Pass 1 — EIA-860**: Match substation names to power plant names (241 matches)
2. **Pass 2 — OSM**: Match to OSM substation names (1,039 matches)
3. **Pass 3 — Propagation**: Inherit coordinates from matched siblings in the same electrical topology; remaining get load zone centroid fallback

**Result**: 1,280 high-quality direct matches (26% of 4,954), covering all four ERCOT load zones.

Matching uses rapidfuzz ensemble scoring (token_sort 0.3 + token_set 0.4 + Jaro-Winkler 0.3), consonant-skeleton blocking, and structural validation (prefix overlap, length ratio, short-name filters). See `OIM/FirstPass/report.md` for details.

### Real-Time LMP Visualization

`OIM/GridStatus/` pulls live ERCOT 5-minute SCED prices via the `gridstatus` library (no API key required) and maps them onto the transmission network:

- **LMP heatmap**: 737 substations colored by price on the HV line background (diverging RdYlBu colormap)
- **HQ-only map**: 201 high-confidence substations only
- **Congestion map**: Deviation from system mean LMP, highlighting transmission bottlenecks

Requires a Python 3.12 venv (`OIM/.venv312/`) since gridstatus needs Python 3.11+.

---

## Data Sources

| Source | Location | Usage |
|---|---|---|
| U.S. Census Gazetteer (2020) | `data/raw/` | Load node clustering (Stage 1a) |
| EIA-860 Form (2023) | `data/eia8602023/` | Generator assignment (Stages 1b, 1c) + OIM matching |
| OpenStreetMap (Overpass API) | `OIM/data/` | HV lines + substations for Texas |
| ERCOT SP/EB Mapping | `SP_List_EB_Mapping/` | Settlement point to substation/bus joins |
| ERCOT LMP (via gridstatus) | `OIM/data/lmp_test.csv` | Real-time locational marginal prices |
| Texas-7k reference grid | `vatic/` | Calibration reference network |
| Texas-2k reference case | `Texas2k_series2025/` | Calibration reference case |

---

## Configuration

### Region Configs (`config/texas.yaml`, `config/new_york.yaml`)

- Region metadata, data source paths, ZCTA prefixes
- Census parameters (load factor MW/person)
- Substation counts, generator capture radius
- Voltage levels: [345, 115] kV with 15% at high voltage
- Topology: target m/n ratio (1.22), random seed (42)

### Global Config (`config/global.yaml`)

- Delaunay category quotas
- Conductor parameters (R, X, B, MVA limits for 345 kV and 138 kV)
- Intersection rate limits, distance metrics

---

## Design Principles

- **Methodological fidelity** — replicate Birchfield et al., don't redesign
- **Explicit ambiguity resolution** — where the paper is unclear, document and configure
- **One responsibility per module**
- **Readable over clever**
- **Research artifact, not production system**
