"""
Shared configuration for the Dartboard pipeline.
All paths and constants are defined here.
"""

import os

# Base directories
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)  # Go up one more level to IW directory
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
INTERMEDIATE_DIR = os.path.join(OUTPUT_DIR, "intermediate")

# Input data paths
PDF_PATH = os.path.join(PROJECT_ROOT, "GoldBook.pdf")
GAZ_PATH = os.path.join(PROJECT_ROOT, "2020_Gaz_zcta_national 2 (1).txt")
EIA_DIR = os.path.join(PROJECT_ROOT, "eia8602023")

# Intermediate output paths
NY_GENERATORS_PATH = os.path.join(INTERMEDIATE_DIR, "NY_Generators_Full.csv")
NY_LOAD_NODES_PATH = os.path.join(INTERMEDIATE_DIR, "NY_Load_Nodes.csv")
TX_LOAD_NODES_PATH = os.path.join(INTERMEDIATE_DIR, "TX_Load_Nodes.csv")
NY_SUBSTATIONS_PATH = os.path.join(INTERMEDIATE_DIR, "NY_Substations.csv")
TX_SUBSTATIONS_PATH = os.path.join(INTERMEDIATE_DIR, "TX_Substations.csv")
NY_TOPOLOGY_PATH = os.path.join(INTERMEDIATE_DIR, "NY_Topology.gpickle")
TX_TOPOLOGY_PATH = os.path.join(INTERMEDIATE_DIR, "TX_Topology.gpickle")
NY_PRUNED_PATH = os.path.join(INTERMEDIATE_DIR, "NY_Pruned.gpickle")
TX_PRUNED_PATH = os.path.join(INTERMEDIATE_DIR, "TX_Pruned.gpickle")
NY_INTEGRATED_PATH = os.path.join(INTERMEDIATE_DIR, "NY_Integrated.gpickle")
TX_INTEGRATED_PATH = os.path.join(INTERMEDIATE_DIR, "TX_Integrated.gpickle")
NY_VOLTAGE_PATH = os.path.join(INTERMEDIATE_DIR, "NY_Voltage.gpickle")
TX_VOLTAGE_PATH = os.path.join(INTERMEDIATE_DIR, "TX_Voltage.gpickle")
NY_FINAL_PATH = os.path.join(INTERMEDIATE_DIR, "NY_Final.gpickle")
TX_FINAL_PATH = os.path.join(INTERMEDIATE_DIR, "TX_Final.gpickle")
EIA_GENERATORS_PATH = os.path.join(INTERMEDIATE_DIR, "EIA_Generators.csv")

# Visualization output paths
VIZ_DIR = os.path.join(OUTPUT_DIR, "visualizations")

# Pipeline parameters
NY_SUBSTATIONS_COUNT = 600
TX_SUBSTATIONS_COUNT = 1250
PRUNE_TARGET_RATIO = 1.22
CAPTURE_MILES = 7
LOAD_PERCENTILE = 0.85

# Bounding boxes for outlier removal
NY_BOUNDS = {"lat_min": 40.0, "lat_max": 45.5, "lon_min": -80.0, "lon_max": -71.0}
TX_BOUNDS = {"lat_min": 25.5, "lat_max": 37.0, "lon_min": -107.0, "lon_max": -93.0}


def ensure_directories():
    """Create output directories if they don't exist."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(INTERMEDIATE_DIR, exist_ok=True)
    os.makedirs(VIZ_DIR, exist_ok=True)


if __name__ == "__main__":
    ensure_directories()
    print("Configuration loaded successfully.")
    print(f"  SCRIPT_DIR: {SCRIPT_DIR}")
    print(f"  OUTPUT_DIR: {OUTPUT_DIR}")
    print(f"  INTERMEDIATE_DIR: {INTERMEDIATE_DIR}")
