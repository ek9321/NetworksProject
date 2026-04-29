"""
Geographic boundary filtering utilities for load and generation data.

Functions for filtering load nodes and generators by state/region boundaries
using shapefiles.
"""

import os
import sys
import zipfile
from typing import List
import tempfile

# Add the project root to Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from core.graph_types import LoadNode, GeneratorRecord


def filter_load_nodes_by_boundary(
    load_nodes: List[LoadNode], 
    shapefile_path: str,
    region_name: str = "boundary"
) -> List[LoadNode]:
    """Filter load nodes to only include those within a geographic boundary.
    
    Args:
        load_nodes: List of LoadNode instances to filter
        shapefile_path: Path to shapefile (can be .zip or directory)
        region_name: Name of region for logging
        
    Returns:
        List of LoadNode instances within the boundary
    """
    print(f"Filtering {len(load_nodes)} load nodes by {region_name} boundary...")
    
    # Load the boundary shapefile
    boundary_gdf = _load_shapefile(shapefile_path)
    
    # Create points for each load node
    points = [Point(node.lon, node.lat) for node in load_nodes]
    
    # Filter points that are within the boundary
    filtered_nodes = []
    for i, point in enumerate(points):
        if boundary_gdf.contains(point).any():
            filtered_nodes.append(load_nodes[i])
    
    print(f"Filtered from {len(load_nodes)} to {len(filtered_nodes)} load nodes")
    return filtered_nodes


def filter_generators_by_boundary(
    generators: List[GeneratorRecord], 
    shapefile_path: str,
    region_name: str = "boundary"
) -> List[GeneratorRecord]:
    """Filter generators to only include those within a geographic boundary.
    
    Args:
        generators: List of GeneratorRecord instances to filter
        shapefile_path: Path to shapefile (can be .zip or directory)
        region_name: Name of region for logging
        
    Returns:
        List of GeneratorRecord instances within the boundary
    """
    print(f"Filtering {len(generators)} generators by {region_name} boundary...")
    
    # Load the boundary shapefile
    boundary_gdf = _load_shapefile(shapefile_path)
    
    # Create points for each generator
    points = [Point(gen.lon, gen.lat) for gen in generators]
    
    # Filter points that are within the boundary
    filtered_generators = []
    for i, point in enumerate(points):
        if boundary_gdf.contains(point).any():
            filtered_generators.append(generators[i])
    
    print(f"Filtered from {len(generators)} to {len(filtered_generators)} generators")
    return filtered_generators


def _load_shapefile(shapefile_path: str) -> gpd.GeoDataFrame:
    """Load a shapefile, handling both .zip files and directories.
    
    Args:
        shapefile_path: Path to shapefile (.zip or directory)
        
    Returns:
        GeoDataFrame containing the boundary geometry
    """
    if shapefile_path.endswith('.zip'):
        # Extract zip file to temporary directory and load shapefile
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(shapefile_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Find the .shp file in the extracted contents
            shp_files = []
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.shp'):
                        shp_files.append(os.path.join(root, file))
            
            if not shp_files:
                raise ValueError(f"No .shp file found in {shapefile_path}")
            elif len(shp_files) > 1:
                print(f"Warning: Multiple .shp files found, using {shp_files[0]}")
            
            gdf = gpd.read_file(shp_files[0])
    else:
        # Assume it's a directory or direct path to .shp file
        gdf = gpd.read_file(shapefile_path)
    
    # Ensure we have a valid CRS - assume WGS84 if not specified
    if gdf.crs is None:
        print("Warning: No CRS found in shapefile, assuming WGS84 (EPSG:4326)")
        gdf = gdf.set_crs("EPSG:4326")
    
    # Convert to WGS84 if needed (since our lat/lon data is in WGS84)
    if gdf.crs != "EPSG:4326":
        print(f"Converting from {gdf.crs} to WGS84")
        gdf = gdf.to_crs("EPSG:4326")
    
    return gdf


def filter_texas_load_nodes_csv(
    input_csv_path: str,
    output_csv_path: str,
    texas_boundary_path: str = "vatic/data/grids/Texas-7k/Texas_State_Boundary-shp.zip"
) -> None:
    """Filter a CSV file of Texas load nodes to only include those within Texas boundary.
    
    Args:
        input_csv_path: Path to input CSV file with load nodes
        output_csv_path: Path where filtered CSV should be saved
        texas_boundary_path: Path to Texas boundary shapefile
    """
    print(f"Filtering Texas load nodes from {input_csv_path}")
    
    # Read the CSV file
    df = pd.read_csv(input_csv_path)
    print(f"Loaded {len(df)} load nodes from CSV")
    
    # Convert to LoadNode objects
    load_nodes = []
    for _, row in df.iterrows():
        load_node = LoadNode(
            zcta=str(row['zcta']),
            lat=float(row['lat']),
            lon=float(row['lon']),
            population=int(row['population']),
            load_mw=float(row['load_mw'])
        )
        load_nodes.append(load_node)
    
    # Filter by Texas boundary
    filtered_nodes = filter_load_nodes_by_boundary(
        load_nodes, texas_boundary_path, "Texas"
    )
    
    # Convert back to DataFrame
    filtered_data = []
    for node in filtered_nodes:
        filtered_data.append({
            'zcta': node.zcta,
            'lat': node.lat,
            'lon': node.lon,
            'population': node.population,
            'load_mw': node.load_mw
        })
    
    filtered_df = pd.DataFrame(filtered_data)
    
    # Save filtered data
    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
    filtered_df.to_csv(output_csv_path, index=False)
    
    print(f"Saved {len(filtered_df)} filtered load nodes to {output_csv_path}")


if __name__ == "__main__":
    # Test the Texas load filtering
    input_file = "data/processed/tx_load_nodes.csv"
    output_file = "data/processed/tx_load_nodes_filtered.csv"
    
    filter_texas_load_nodes_csv(input_file, output_file)
    print("Texas load node filtering complete!")