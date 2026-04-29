"""
Load Census Gazetteer and ACS population data into LoadNode records.

Input files:
  - Census Gazetteer TSV (tab-separated, from data/raw/census_gazetteer_2020.txt)
  - Census ACS 2020 API for population by ZCTA

Output:
  - list[LoadNode] for a given state, filtered by ZCTA prefix

Cached to data/processed/ as CSV to avoid re-fetching the Census API.
For Texas data, automatic boundary filtering is applied to remove load nodes
outside the state boundary.
"""

import os

import pandas as pd
import requests

from core.graph_types import LoadNode


def load_gazetteer(gaz_path: str) -> pd.DataFrame:
    """Load and clean the Census Gazetteer file.

    The file is tab-separated with columns including GEOID, INTPTLAT,
    INTPTLONG. Column names have trailing whitespace that must be stripped.
    GEOID must be zero-padded to 5 digits.
    """
    df = pd.read_csv(gaz_path, sep="\t")
    df.columns = df.columns.str.strip()
    df["GEOID"] = df["GEOID"].astype(str).str.zfill(5)
    return df


def fetch_acs_population() -> pd.DataFrame:
    """Fetch population by ZCTA from Census ACS 2020 API.

    Returns a DataFrame with columns: GEOID, POPULATION.
    """
    url = (
        "https://api.census.gov/data/2020/acs/acs5"
        "?get=B01003_001E&for=zip%20code%20tabulation%20area:*"
    )
    response = requests.get(url)
    response.raise_for_status()

    data = response.json()
    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.rename(columns={
        "B01003_001E": "POPULATION",
        "zip code tabulation area": "GEOID",
    })
    df["POPULATION"] = pd.to_numeric(df["POPULATION"])
    return df


def load_nodes_for_state(
    gaz_path: str,
    zcta_prefixes: tuple[str, ...],
    load_factor: float = 0.002,
    apply_texas_boundary_filter: bool = True,
) -> list[LoadNode]:
    """Load Census data and return LoadNodes for a state.

    Args:
        gaz_path: Path to the Census Gazetteer TSV file.
        zcta_prefixes: ZCTA prefix strings that identify this state.
            Texas: ("73", "75", "76", "77", "78", "79")
            New York: ("10", "11", "12", "13", "14")
        load_factor: MW per person. Default 0.002 per Birchfield methodology.
        apply_texas_boundary_filter: If True and processing Texas data, 
            apply boundary filtering to remove nodes outside state boundary.

    Returns:
        List of LoadNode instances for the filtered ZCTAs.
    """
    gaz_df = load_gazetteer(gaz_path)
    pop_df = fetch_acs_population()

    state_gaz = gaz_df[gaz_df["GEOID"].str.startswith(zcta_prefixes)]
    merged = pd.merge(
        state_gaz, pop_df[["GEOID", "POPULATION"]], on="GEOID", how="inner"
    )

    nodes = []
    for _, row in merged.iterrows():
        nodes.append(LoadNode(
            zcta=row["GEOID"],
            lat=float(row["INTPTLAT"]),
            lon=float(row["INTPTLONG"]),
            population=int(row["POPULATION"]),
            load_mw=float(row["POPULATION"]) * load_factor,
        ))

    # Apply Texas boundary filtering if this is Texas data
    texas_prefixes = ("73", "75", "76", "77", "78", "79")
    if apply_texas_boundary_filter and zcta_prefixes == texas_prefixes:
        try:
            from ingest.boundary_filter import filter_load_nodes_by_boundary
            texas_boundary_path = "vatic/data/grids/Texas-7k/Texas_State_Boundary-shp.zip"
            nodes = filter_load_nodes_by_boundary(nodes, texas_boundary_path, "Texas")
        except ImportError:
            print("Warning: boundary_filter module not available, skipping Texas boundary filtering")
        except Exception as e:
            print(f"Warning: Texas boundary filtering failed: {e}")
            print("Proceeding with unfiltered nodes")

    return nodes


def save_load_nodes(nodes: list[LoadNode], csv_path: str) -> None:
    """Write LoadNodes to a CSV file."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    df = pd.DataFrame([
        {"zcta": n.zcta, "lat": n.lat, "lon": n.lon,
         "population": n.population, "load_mw": n.load_mw}
        for n in nodes
    ])
    df.to_csv(csv_path, index=False)


def load_load_nodes(csv_path: str) -> list[LoadNode]:
    """Read LoadNodes from a cached CSV file."""
    df = pd.read_csv(csv_path, dtype={"zcta": str})
    df["zcta"] = df["zcta"].str.zfill(5)
    return [
        LoadNode(
            zcta=row["zcta"],
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            population=int(row["population"]),
            load_mw=float(row["load_mw"]),
        )
        for _, row in df.iterrows()
    ]


def load_texas_nodes_with_boundary_filter(
    gaz_path: str,
    load_factor: float = 0.002,
    texas_boundary_path: str = "vatic/data/grids/Texas-7k/Texas_State_Boundary-shp.zip",
    apply_boundary_filter: bool = True,
) -> list[LoadNode]:
    """Load Texas LoadNodes with optional boundary filtering.
    
    Args:
        gaz_path: Path to the Census Gazetteer TSV file.
        load_factor: MW per person. Default 0.002 per Birchfield methodology.
        texas_boundary_path: Path to Texas state boundary shapefile.
        apply_boundary_filter: If True, filter out nodes outside Texas boundary.
        
    Returns:
        List of LoadNode instances for Texas, optionally filtered by boundary.
    """
    # Load nodes using standard ZCTA prefixes for Texas
    texas_prefixes = ("73", "75", "76", "77", "78", "79")
    nodes = load_nodes_for_state(gaz_path, texas_prefixes, load_factor)
    
    # Apply boundary filtering if requested
    if apply_boundary_filter:
        try:
            from ingest.boundary_filter import filter_load_nodes_by_boundary
            nodes = filter_load_nodes_by_boundary(nodes, texas_boundary_path, "Texas")
        except ImportError:
            print("Warning: boundary_filter module not available, skipping boundary filtering")
        except Exception as e:
            print(f"Warning: boundary filtering failed: {e}")
            print("Proceeding with unfiltered nodes")
    
    return nodes


def save_texas_load_nodes_filtered(
    gaz_path: str,
    csv_path: str = "data/processed/tx_load_nodes_filtered.csv",
    load_factor: float = 0.002,
) -> None:
    """Load Texas nodes with boundary filtering and save to CSV.
    
    Args:
        gaz_path: Path to the Census Gazetteer TSV file.
        csv_path: Where to save the filtered CSV.
        load_factor: MW per person.
    """
    nodes = load_texas_nodes_with_boundary_filter(gaz_path, load_factor)
    save_load_nodes(nodes, csv_path)
    print(f"Saved {len(nodes)} filtered Texas load nodes to {csv_path}")
