# Dartboard — Phase 1: Birchfield Synthetic Grid (Archival)

This file documents the first phase of Dartboard. It is archival — the methodology is complete and validated. Active development is in the Realist phase; see [`README.md`](README.md).

---

## What This Phase Built

A full Python implementation of the Birchfield et al. synthetic grid methodology for **Texas** and **New York**, producing topologically realistic transmission networks from public Census and EIA-860 data. Results were calibrated against the Texas-7k and Texas-2k reference networks from Texas A&M.

The pipeline runs in three stages:

1. **Stage 1 — Load Clustering**: Census Gazetteer population centers are clustered into load nodes using the Birchfield agglomeration procedure. Each cluster becomes a bus in the synthetic grid.

2. **Stage 2 — Generator Assignment**: EIA-860 generator records are matched to synthetic buses by proximity and voltage-tier rules. Generators carry fuel type, capacity, and geographic coordinates.

3. **Stage 3 — Topology Synthesis**: A spanning-tree backbone is generated over load nodes, then augmented with meshing links using the Birchfield betweenness-weighted attachment procedure to match the observed degree distribution and circuit redundancy of real transmission grids.

---

## Running the Pipeline

### Prerequisites

- Python 3.11+ (conda env in `.conda/`)
- EIA-860 2023 Excel files in `Birchfield/data/eia8602023/`

```bash
# Stage 1: load clustering
python3 Birchfield/pipelines/stage1_cluster.py --config Birchfield/config/texas.yaml

# Stage 2: generator assignment
python3 Birchfield/pipelines/stage2_generators.py --config Birchfield/config/texas.yaml

# Stage 3: topology synthesis
python3 Birchfield/pipelines/stage3_topology.py --config Birchfield/config/texas.yaml

# Visualization
python3 Birchfield/viz/plot_grid.py
```

Substitute `new_york.yaml` for the New York case.

---

## Calibration

Texas results were calibrated against Texas-7k and Texas-2k reference cases from the Texas A&M Power Systems Test Case Archive. Calibration metrics and results are in `Birchfield/Calibration/`.

---

## Data Sources

| Source | Use |
|---|---|
| U.S. Census Gazetteer | Population-weighted load nodes (Stage 1) |
| EIA-860 (2023) | Generator locations, capacity, fuel type (Stage 2) |
| Texas-7k reference case | Calibration of Texas topology |
| Texas-2k reference case | Secondary calibration benchmark |

---

## Repository Layout (Birchfield phase)

```
Birchfield/
├── core/                # Pipeline modules: graph_types, clustering, topology
├── pipelines/           # Stage 1–3 scripts
├── ingest/              # Census + EIA-860 data loaders
├── viz/                 # Visualization scripts
├── config/              # texas.yaml, new_york.yaml, global.yaml
├── data/                # Raw/processed/synthetic (mostly gitignored)
├── Calibration/         # Texas-7k / Texas-2k calibration experiments
├── vatic/               # Texas A&M Vatic power flow library (adapted)
├── version1/            # Earlier pipeline attempt (reference only)
├── 2k/                  # Texas-2k reference case data
└── plans/               # Birchfield implementation specs
```

---

## Why We Moved On

The synthetic grid is topologically plausible but not validated against real ERCOT operating data. Bus positions are at Census population centroids, not real substation locations. Generator assignments are probabilistic, not actual. The Realist phase replaces this with a model grounded in real public geography (OpenStreetMap), real generator records (MORA/EIA-860), and real market prices (ERCOT public data).
