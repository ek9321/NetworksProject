"""
Fetch power plants from OpenStreetMap via Overpass API.

Queries power=plant nodes/ways/relations within the ERCOT bounding box,
extracts name, fuel source, capacity, operator, and centroid coordinates.

Usage:
    python fetch_plants.py texas
"""

import argparse
import csv
import json
import os
import re
import time

import requests

REGIONS = {
    "texas": (25.83, -106.65, 36.50, -93.51),
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def query_overpass(bbox, timeout=180):
    """Query Overpass for power plants. Splits into quadrants for large areas."""
    south, west, north, east = bbox
    lat_span = north - south
    lon_span = east - west

    if lat_span > 5 or lon_span > 7:
        print(f"  Large bbox ({lat_span:.1f} x {lon_span:.1f} deg), splitting into quadrants...")
        mid_lat = (south + north) / 2
        mid_lon = (west + east) / 2
        quadrants = [
            (south, west, mid_lat, mid_lon),
            (south, mid_lon, mid_lat, east),
            (mid_lat, west, north, mid_lon),
            (mid_lat, mid_lon, north, east),
        ]
        all_elements = []
        for i, q in enumerate(quadrants):
            print(f"  Quadrant {i + 1}/4: ({q[0]:.2f},{q[1]:.2f},{q[2]:.2f},{q[3]:.2f})")
            elements = _fetch_single_bbox(q, timeout)
            all_elements.extend(elements)
            if i < 3:
                print("  Waiting 5s between queries (rate limiting)...")
                time.sleep(5)
        return all_elements
    else:
        return _fetch_single_bbox(bbox, timeout)


def _fetch_single_bbox(bbox, timeout):
    """Fetch power plants from a single bbox."""
    south, west, north, east = bbox
    query = f"""
    [out:json][timeout:{timeout}];
    (
      node["power"="plant"]({south},{west},{north},{east});
      way["power"="plant"]({south},{west},{north},{east});
      relation["power"="plant"]({south},{west},{north},{east});
    );
    out body;
    >;
    out skel qt;
    """
    print(f"  Querying Overpass API...")
    for attempt in range(3):
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=timeout + 30)
            resp.raise_for_status()
            data = resp.json()
            elements = data.get("elements", [])
            print(f"  Received {len(elements)} elements")
            return elements
        except (requests.RequestException, ValueError) as e:
            wait = 10 * (attempt + 1)
            print(f"  Attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def parse_capacity_mw(value):
    """
    Parse plant:output:electricity tag to MW float.

    Handles formats:
      "150 MW"   -> 150.0
      "1.5 GW"   -> 1500.0
      "500 kW"   -> 0.5
      "150000000"-> 150.0   (bare watts assumed)
      "150 MW;200 MW" -> 350.0 (sum of semicolon-separated values)
    """
    if not value:
        return None

    total = 0.0
    found = False

    for part in value.split(";"):
        part = part.strip()
        # Try "number unit" format first
        m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(GW|MW|kW|W)?$", part, re.IGNORECASE)
        if m:
            num = float(m.group(1))
            unit = (m.group(2) or "W").upper()
            if unit == "GW":
                num *= 1000
            elif unit == "KW":
                num /= 1000
            elif unit == "W":
                num /= 1_000_000
            total += num
            found = True

    return round(total, 2) if found else None


def parse_plants(elements):
    """
    Parse Overpass elements into power plant records.
    Computes centroids for way and relation geometries.
    Returns list of dicts.
    """
    # Build node coordinate lookup (lat/lon for every node element)
    node_coords = {}
    for el in elements:
        if el["type"] == "node":
            node_coords[el["id"]] = (el.get("lat"), el.get("lon"))

    # Build way node-list lookup
    way_nodes = {}
    for el in elements:
        if el["type"] == "way":
            way_nodes[el["id"]] = el.get("nodes", [])

    plants = []
    seen_ids = set()

    for el in elements:
        tags = el.get("tags", {})
        if tags.get("power") != "plant":
            continue

        osm_id  = el["id"]
        osm_type = el["type"]
        key = (osm_type, osm_id)
        if key in seen_ids:
            continue
        seen_ids.add(key)

        name     = tags.get("name", "")
        fuel     = tags.get("plant:source", tags.get("plant:type", ""))
        mw       = parse_capacity_mw(tags.get("plant:output:electricity"))
        operator = tags.get("operator", "")

        if osm_type == "node":
            lat = el.get("lat")
            lon = el.get("lon")

        elif osm_type == "way":
            nids = el.get("nodes", [])
            lats = [node_coords[n][0] for n in nids if n in node_coords and node_coords[n][0] is not None]
            lons = [node_coords[n][1] for n in nids if n in node_coords and node_coords[n][1] is not None]
            if not lats:
                continue
            lat = sum(lats) / len(lats)
            lon = sum(lons) / len(lons)

        elif osm_type == "relation":
            # Collect all node coords from member ways
            lats, lons = [], []
            for member in el.get("members", []):
                if member.get("type") == "way":
                    wid = member.get("ref")
                    for nid in way_nodes.get(wid, []):
                        if nid in node_coords and node_coords[nid][0] is not None:
                            lats.append(node_coords[nid][0])
                            lons.append(node_coords[nid][1])
            if not lats:
                continue
            lat = sum(lats) / len(lats)
            lon = sum(lons) / len(lons)

        else:
            continue

        if lat is None or lon is None:
            continue

        plants.append({
            "osm_id":   osm_id,
            "osm_type": osm_type,
            "name":     name,
            "fuel":     fuel.lower() if fuel else "",
            "mw":       mw,
            "operator": operator,
            "lat":      lat,
            "lon":      lon,
        })

    return plants


def save_geojson(plants, path):
    features = []
    for p in plants:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [p["lon"], p["lat"]],
            },
            "properties": {
                "osm_id":   p["osm_id"],
                "osm_type": p["osm_type"],
                "name":     p["name"],
                "fuel":     p["fuel"],
                "mw":       p["mw"],
                "operator": p["operator"],
            },
        })
    collection = {"type": "FeatureCollection", "features": features}
    with open(path, "w") as f:
        json.dump(collection, f)
    print(f"Saved {len(features)} plants to {path}")


def save_csv(plants, path):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["osm_id", "osm_type", "name", "fuel", "mw", "operator", "lat", "lon"])
        for p in plants:
            writer.writerow([
                p["osm_id"], p["osm_type"], p["name"], p["fuel"],
                p["mw"] if p["mw"] is not None else "",
                p["operator"],
                round(p["lat"], 6), round(p["lon"], 6),
            ])
    print(f"Saved CSV to {path}")


def print_summary(plants):
    from collections import Counter
    named = sum(1 for p in plants if p["name"])
    with_mw = sum(1 for p in plants if p["mw"] is not None)
    fuels = Counter(p["fuel"] for p in plants if p["fuel"])
    print(f"\n{'=' * 50}")
    print(f"Total plants: {len(plants)}")
    print(f"  Named:         {named}")
    print(f"  With capacity: {with_mw}")
    print(f"  Fuel types:")
    for fuel, count in fuels.most_common():
        print(f"    {fuel}: {count}")
    print(f"{'=' * 50}\n")


def main():
    parser = argparse.ArgumentParser(description="Fetch power plants from OSM via Overpass API")
    parser.add_argument("region", choices=list(REGIONS.keys()), help="Region to query")
    args = parser.parse_args()

    region = args.region
    bbox   = REGIONS[region]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Save alongside the other grid_data files one level up
    data_dir = os.path.join(script_dir, "..", "grid_data")
    os.makedirs(data_dir, exist_ok=True)

    print(f"Fetching power plants for {region}...")
    print(f"Bounding box: {bbox}\n")

    elements = query_overpass(bbox)
    plants   = parse_plants(elements)

    print_summary(plants)

    save_geojson(plants, os.path.join(data_dir, f"{region}_plants.geojson"))
    save_csv(plants,    os.path.join(data_dir, f"{region}_plants.csv"))


if __name__ == "__main__":
    main()
