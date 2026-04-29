"""
Build NYISO load zone boundaries from US Census county GeoJSON.

NYISO zones map to NY counties (with exceptions for Westchester which is
split across G/H/I). This script fetches NY county boundaries from the
Census Bureau and aggregates them into zone polygons.

Zones H (Millwood) and I (Dunwoodie) are parts of Westchester County.
Since we can't split a county polygon, we assign all of Westchester to
zone G (Hudson Valley) and handle H/I load allocation in run_sced.py
by distributing proportionally.

Usage:
    python fetch_nyiso_zones.py
"""

import json
import os

import requests

# US Census Bureau TIGERweb county boundaries API
# Returns GeoJSON for a given state FIPS code
CENSUS_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/tigerWMS_Current/MapServer/82/query"
)

# New York state FIPS code
NY_FIPS = "36"

# NYISO zone-to-county FIPS mapping
# Source: NYISO Sub-Zone Boundaries (Table A-1)
# County FIPS codes are 3-digit (state prefix 36 omitted here)
ZONE_COUNTY_FIPS = {
    "A": ["013", "009", "029", "063", "003"],  # Chautauqua, Cattaraugus, Erie, Niagara, Allegany
    "B": ["037", "121", "073", "051", "055", "117", "069",
           "123", "099", "101", "097", "015"],  # Genesee, Wyoming, Orleans, Livingston, Monroe, Wayne, Ontario, Yates, Seneca, Steuben, Schuyler, Chemung
    "C": ["109", "107", "023", "007", "017", "011",
           "067", "075", "053", "065", "077", "043"],  # Tompkins, Tioga, Cortland, Broome, Chenango, Cayuga, Onondaga, Oswego, Madison, Oneida, Otsego, Herkimer
    "D": ["045", "049", "089", "041", "031", "019",
           "033", "113", "115", "035"],  # Jefferson, Lewis, St. Lawrence, Hamilton, Essex, Clinton, Franklin, Warren, Washington, Fulton
    "E": ["025", "095", "057", "093", "091"],  # Delaware, Schoharie, Montgomery, Schenectady, Saratoga
    "F": ["001", "083", "021", "039"],  # Albany, Rensselaer, Columbia, Greene
    "G": ["027", "071", "079", "087", "105", "111"],  # Dutchess, Orange, Putnam, Rockland, Sullivan, Ulster + Westchester
    # H and I are sub-county (Westchester), merged into G for polygon purposes
    # Westchester FIPS = 119, assigned to G
    "J": ["005", "047", "061", "081", "085"],  # Bronx, Kings, New York, Queens, Richmond
    "K": ["059", "103"],  # Nassau, Suffolk
}

ZONE_NAMES = {
    "A": "West",
    "B": "Genesee",
    "C": "Central",
    "D": "North",
    "E": "Mohawk Valley",
    "F": "Capital",
    "G": "Hudson Valley",
    "H": "Millwood",
    "I": "Dunwoodie",
    "J": "New York City",
    "K": "Long Island",
}

# Full county FIPS to zone mapping (for point-in-polygon fallback)
# Westchester (119) goes to G; H and I are handled as sub-zones
COUNTY_FIPS_TO_ZONE = {}
for zone, fips_list in ZONE_COUNTY_FIPS.items():
    for fips in fips_list:
        COUNTY_FIPS_TO_ZONE[fips] = zone
# Westchester explicitly to G (covers H/I physically)
COUNTY_FIPS_TO_ZONE["119"] = "G"


def fetch_ny_counties():
    """Fetch all NY county boundaries from Census TIGERweb."""
    params = {
        "where": f"STATE='{NY_FIPS}'",
        "outFields": "STATE,COUNTY,NAME,BASENAME,GEOID",
        "f": "geojson",
        "outSR": "4326",
        "returnGeometry": "true",
    }

    print("Fetching NY county boundaries from Census TIGERweb...")
    resp = requests.get(CENSUS_URL, params=params, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    if "features" not in data or len(data["features"]) == 0:
        raise RuntimeError(f"No county features returned. Response keys: {list(data.keys())}")

    print(f"Received {len(data['features'])} county features")
    return data


def merge_counties_to_zones(county_geojson):
    """
    Merge county polygons into zone polygons.

    For simplicity, we don't do true polygon union (that requires shapely).
    Instead, we create a MultiPolygon for each zone containing all its
    constituent county polygons. This is sufficient for point-in-polygon
    zone assignment.
    """
    from collections import defaultdict

    zone_polygons = defaultdict(list)
    unmatched = []

    for feature in county_geojson["features"]:
        props = feature["properties"]
        county_fips = props.get("COUNTY", "")
        county_name = props.get("NAME", props.get("BASENAME", ""))
        geom = feature["geometry"]

        zone = COUNTY_FIPS_TO_ZONE.get(county_fips)
        if zone is None:
            unmatched.append(f"{county_name} ({county_fips})")
            continue

        # Collect polygons
        if geom["type"] == "Polygon":
            zone_polygons[zone].append(geom["coordinates"])
        elif geom["type"] == "MultiPolygon":
            for poly_coords in geom["coordinates"]:
                zone_polygons[zone].append(poly_coords)

    if unmatched:
        print(f"  Unmatched counties: {', '.join(unmatched)}")

    # Build zone features
    features = []
    for zone_letter in sorted(zone_polygons.keys()):
        polys = zone_polygons[zone_letter]
        if len(polys) == 1:
            geom = {"type": "Polygon", "coordinates": polys[0]}
        else:
            geom = {"type": "MultiPolygon", "coordinates": polys}

        feature = {
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "zone_letter": zone_letter,
                "zone_name": ZONE_NAMES.get(zone_letter, ""),
                "num_counties": len(polys),
            },
        }
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def save_geojson(geojson, path):
    """Save GeoJSON to file."""
    with open(path, "w") as f:
        json.dump(geojson, f)
    print(f"Saved {len(geojson.get('features', []))} features to {path}")


def print_summary(geojson):
    """Print summary of zone features."""
    features = geojson.get("features", [])
    print(f"\n{'=' * 50}")
    print(f"NYISO Load Zones (from county aggregation)")
    print(f"Total zone features: {len(features)}")
    print(f"{'=' * 50}")
    for f in features:
        props = f.get("properties", {})
        zone = props.get("zone_letter", "?")
        name = props.get("zone_name", "unknown")
        n_counties = props.get("num_counties", 0)
        geom_type = f.get("geometry", {}).get("type", "?")
        print(f"  Zone {zone} ({name:>15s}): {geom_type}, {n_counties} county polygons")
    print()
    print("Note: Zones H (Millwood) and I (Dunwoodie) are sub-county")
    print("      and merged into Zone G (Hudson Valley) at polygon level.")
    print("      Load allocation to H/I is handled in run_sced.py.")
    print()


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "grid_data")
    os.makedirs(data_dir, exist_ok=True)

    county_geojson = fetch_ny_counties()

    # Also save raw county data for reference
    county_path = os.path.join(data_dir, "ny_counties.geojson")
    save_geojson(county_geojson, county_path)

    zone_geojson = merge_counties_to_zones(county_geojson)

    geojson_path = os.path.join(data_dir, "nyiso_zones.geojson")
    save_geojson(zone_geojson, geojson_path)
    print_summary(zone_geojson)


if __name__ == "__main__":
    main()
