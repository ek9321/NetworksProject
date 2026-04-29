# Dartboard Analysis

Synthetic power grid topology generator following the Birchfield methodology. Generates realistic grid topologies for NY and TX using Census data, EIA generator data, and graph algorithms.

## Features

- **Gold Book Extraction** - Parse NY ISO Gold Book PDF for generator data
- **Census Integration** - Create load nodes from ZCTA population data
- **Agglomerative Clustering** - Group ZCTAs into realistic substation locations
- **Delaunay Triangulation** - Generate initial mesh topology
- **RNG Pruning** - Prune to realistic line/node ratios using Relative Neighborhood Graph filtering
- **EIA Generator Integration** - Add real generator locations from EIA-860 data
- **Voltage Assignment** - Assign 115kV/345kV levels based on generation and load
- **RNG Filtering** - Alternative topology using Relative Neighborhood Graphs

## Project Structure

```
dartboard-project/
├── run_pipeline.py              # Master pipeline runner
├── pipeline/                    # Modular pipeline phases
│   ├── __init__.py
│   ├── config.py                # Shared configuration & paths
│   ├── utils.py                 # Utility functions (haversine, graph I/O)
│   ├── phase1_goldbook.py       # Gold Book PDF extraction
│   ├── phase2_census.py         # Census data / load nodes
│   ├── phase3_clustering.py     # Substation clustering
│   ├── phase4_topology.py       # Delaunay triangulation
│   ├── phase5_pruning.py        # RNG-based pruning
│   ├── phase6_generation.py     # EIA generator integration
│   ├── phase7_voltage.py        # Voltage assignment
│   └── phase8_rng.py            # RNG alternative topology
├── requirements.txt             # Python dependencies
├── GoldBook.pdf                 # NY ISO Gold Book (input)
├── 2020_Gaz_zcta_national*.txt  # Census Gazetteer file (input)
├── eia8602023/                  # EIA-860 data directory (input)
└── output/                      # Generated outputs
    ├── intermediate/            # CSV & pickle files between phases
    └── visualizations/          # PNG visualization files
```

## Installation

### Prerequisites
- Python 3.10+ (tested with 3.12)
- Conda or pip

### Using the existing conda environment
```bash
cd /path/to/project
source .conda/bin/activate  # or: conda activate ./.conda
```

### Or create a new environment
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### Run the full pipeline
```bash
python run_pipeline.py
```

### Run with caching (skip phases with existing outputs)
```bash
python run_pipeline.py --skip
```

### Run a specific phase
```bash
python run_pipeline.py --phase 3      # Run only phase 3
python run_pipeline.py --from 4       # Run from phase 4 onwards
python run_pipeline.py --to 5         # Run up to phase 5
```

### Run individual phases directly
```bash
python -m pipeline.phase2_census
python -m pipeline.phase5_pruning
```

### List all phases
```bash
python run_pipeline.py --list
```

## Pipeline Phases

| Phase | Name | Input | Output |
|-------|------|-------|--------|
| 1 | Gold Book Extraction | GoldBook.pdf | NY_Generators_Full.csv |
| 2 | Census Data | Gazetteer file, Census API | NY/TX_Load_Nodes.csv |
| 3 | Clustering | Load nodes | NY/TX_Substations.csv |
| 4 | Initial Topology | Substations | NY/TX_Topology.gpickle |
| 5 | Pruning | Topology | NY/TX_Pruned.gpickle |
| 6 | Generation | Pruned + EIA data | NY/TX_Integrated.gpickle |
| 7 | Voltage | Integrated | NY/TX_Voltage.gpickle |
| 8 | RNG (Alternative) | Load nodes + EIA | NY/TX_Final.gpickle |

## Output Files

### Intermediate Data (`output/intermediate/`)
- CSV files for tabular data (generators, load nodes, substations)
- Pickle files for NetworkX graph objects

### Visualizations (`output/visualizations/`)
- `ny_load_nodes.png` / `tx_load_nodes.png` - Population-weighted load nodes
- `substations.png` - Clustered substation locations
- `backbone.png` - Pruned network topology
- `voltage_maps.png` - HV/LV voltage assignment

## Configuration

Edit `pipeline/config.py` to customize:
- File paths
- Number of substations (NY: 600, TX: 1250)
- Pruning target ratio (1.22)
- Generator capture distance (7 miles)
- Load percentile for HV assignment (85%)

## Dependencies

See `requirements.txt`:
- pdfplumber - PDF table extraction
- pandas, numpy - Data processing
- matplotlib - Visualization
- geopandas, shapely - Geospatial operations
- scikit-learn - Clustering
- scipy - Delaunay triangulation
- networkx - Graph algorithms
- requests - Census API
- openpyxl - Excel file reading
- Use `Ctrl+Shift+P` to open the command palette
- Install the Jupyter extension if you prefer working with notebook cells in VS Code
- Set up debugging by clicking on the Run and Debug icon in the left sidebar

## Troubleshooting

**Import errors?**
- Make sure your virtual environment is activated
- Run `pip install -r requirements.txt` again

**File not found errors?**
- Check that your file paths are correct
- Make sure files are in the right directories (data/ and output/)

**VS Code not recognizing Python?**
- Use `Ctrl+Shift+P` and search for "Python: Select Interpreter"
- Choose the interpreter from your virtual environment

## Next Steps

1. Review the code in `dartboard_analysis.py`
2. Update any file paths to match your local setup
3. Run the script section by section to understand what it does
4. Modify as needed for your analysis
