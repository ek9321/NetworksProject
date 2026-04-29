# Diagnosing Resilience in the ERCOT Transmission Network

Network science analysis of the ERCOT (Electric Reliability Council of Texas) transmission grid.
See `DART/report.tex` for the full paper.

---

## How to read this repo (start here)

The repo root looks busy because the analysis scripts hard-code paths like `nodes.csv`
and `figures/01_*.png`, so we left every original file in place. To navigate the
project the way the paper is structured, **ignore the root file list and use the
index instead**:

### Step 1 — open the paper-section index

**[`PAPER_INDEX.md`](PAPER_INDEX.md)** is the entry point. It has one link per paper
section and per appendix.

### Step 2 — pick the section you want

The "clean" view that mirrors the paper is exactly these folders:

```
PAPER_INDEX.md                            ← start here
visualization/                            ← grid map (Fig. used in §3)
analysis/
├── 3_network_construction/               ← §3
├── 4_structural_diagnosis/               ← §4 (overview)
│   ├── 4.1_articulation_points/          ← §4.1
│   ├── 4.2_attack_curves/                ← §4.2
│   ├── 4.3_link_prediction/              ← §4.3
│   └── 4.4_spectral_bisection/           ← §4.4
├── 5_n1_contingency/                     ← §5
└── 6_topology_optimal/                   ← §6
appendix/                                 ← full inventory of scripts/data/figures
```

Every folder above contains a `README.md` with: a short summary of that section,
relative links to the relevant figure(s) in `figures/`, the script(s) that produced
them, and pointers to related sections.

### Step 3 — ignore everything else at the root *for navigation purposes*

The following root entries are the *machinery* that the indexed READMEs link back
to. You don't need to browse them directly; the indexed READMEs will pull up the
right file when you click through:

| Root entry | What it is | Used by |
|---|---|---|
| `build_network.py` | builds the graph | §3 |
| `analyze_network.py` | runs all diagnostics | §4, §5 |
| `nodes.csv`, `edges.csv` | graph data | every section |
| `figures/` | all generated PNGs | linked from each section README |
| `notebooks/` | Jupyter notebooks | §4.3 |
| `output.png` | debug output of `build_network.py` | — |
| `DART/` | precursor sub-project (Dartboard) | acknowledgments |
| `CLAUDE.md`, `.gitignore`, `*.code-workspace` | tooling | — |

### TL;DR

> **Click [`PAPER_INDEX.md`](PAPER_INDEX.md). Click the section you want. Each
> section's README links to its figures and code. Don't browse the root.**

---

## Original repo notes (machinery reference)


## The Network (V3 pipeline)

| | |
|---|---|
| **Nodes** | 3,786 (3,000 real substations + 786 synthetic T-junctions) |
| **Edges** | 4,817 transmission lines |
| **Zones** | NORTH (1,319), SOUTH (1,081), WEST (909), HOUSTON (477) |
| **Generation** | 159 GW nameplate, 1,185 units (MORA April 2026) |
| **Connectivity** | Single connected component (100%), bridge ratio 14.4% |

## Data Pipeline

```
OpenStreetMap (OSM)   ──► build_osm_bus_table.py        ─┐
ERCOT MORA April 2026 ──► extract_mora.py                ─┼─► sced_inputs_v3/
Census 2020 pop.      ──► (inline in network_analysis.py) ─┘
                                    │
                         build_osm_branch_table_v3.py
                         (V3: 50 m proximity snap + T-junctions)
                                    │
                         network_analysis.py   ──► figures/, network_analysis_results.json
                         optimal_grid.py       ──► figures/real_vs_optimal_attack_curves.png
```

Source data lives in `DART/Realist/grid_data/sced_inputs_v3/SourceData/`.

## Analyses

| Script | Output | Section in paper |
|---|---|---|
| `network_analysis.py` | `figures/attack_curves.png` | §4 Attack curves |
| `network_analysis.py` | `figures/spectral_analysis.png` | §4 Spectral bisection |
| `network_analysis.py` | `figures/n1_stress.png` | §5 N–1 contingency |
| `optimal_grid.py` | `figures/real_vs_optimal_attack_curves.png` | §6 Topology-optimal grid |
| `notebooks/graph_simulations.ipynb` | `sim.png` | §4 Link prediction simulation |

## Requirements

```
pip install networkx matplotlib numpy scipy pandas geopandas shapely
```

## File Manifest

```
DART/report.tex                                  — paper source
DART/Realist/ERCOT/
  network_analysis.py                            — attack curves, spectral, N–1, null model
  optimal_grid.py                                — greedy λ₂-optimal grid + attack-curve comparison
  build_osm_bus_table.py                         — OSM substation extraction
  build_osm_branch_table_v3.py                   — V3 line extraction (50 m proximity snap)
  extract_mora.py                                — MORA generation unit ingestion
  figures/                                       — output plots
  network_analysis_results.json                  — numerical results
  optimal_grid_results.json
  n1_stress_results.csv
DART/Realist/grid_data/
  sced_inputs_v3/SourceData/{bus,branch,gen}.csv — V3 grid inputs
  MORA_April2026_unit_capacities.csv             — generation nameplate
  texas_tract_pop_2020.csv                       — Census 2020 load allocation
  ercot_zones.geojson                            — ERCOT zone boundaries
notebooks/graph_simulations.ipynb                — link prediction simulation
```
