"""
Fetch power substations from OpenStreetMap via Overpass API.

Queries power=substation nodes/ways within a region bounding box,
extracts name, voltage, operator, and centroid coordinates.

Usage:
    python fetch_substations.py texas
"""

import argparse
import csv
import json
import os
import time

import requests

REGIONS = {
    "texas": (25.83, -106.65, 36.50, -93.51),
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def query_overpass(bbox, timeout=180):
    """Query Overpass for substations. Splits into quadrants for large areas."""
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
    """Fetch substations from a single bbox."""
    south, west, north, east = bbox
    # Query both nodes and ways tagged power=substation
    query = f"""
    [out:json][timeout:{timeout}];
    (
      node["power"="substation"]({south},{west},{north},{east});
      way["power"="substation"]({south},{west},{north},{east});
      relation["power"="substation"]({south},{west},{north},{east});
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


def parse_voltage_kv(voltage_str):
    """Parse voltage tag to max kV. Returns None if unparseable."""
    if not voltage_str:
        return None
    parts = voltage_str.split(";")
    values = []
    for part in parts:
        part = part.strip()
        try:
            values.append(int(part) / 1000)
        except ValueError:
            continue
    return max(values) if values else None


def parse_substations(elements):
    """
    Parse Overpass elements into substation records.
    For way/relation substations, compute centroid from constituent nodes.
    Returns list of dicts: osm_id, name, voltage_kv, operator, lat, lon, osm_type
    """
    # Build node lookup
    nodes = {}
    for el in elements:
        if el["type"] == "node":
            nodes[el["id"]] = (el.get("lat"), el.get("lon"))

    substations = []
    seen_ids = set()

    for el in elements:
        tags = el.get("tags", {})
        if tags.get("power") != "substation":
            continue

        osm_id = el["id"]
        osm_type = el["type"]
        key = (osm_type, osm_id)
        if key in seen_ids:
            continue
        seen_ids.add(key)

        name = tags.get("name", "")
        voltage_kv = parse_voltage_kv(tags.get("voltage"))
        operator = tags.get("operator", "")
        substation_type = tags.get("substation", "")  # transmission, distribution, etc.

        if osm_type == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        elif osm_type == "way":
            # Compute centroid from way nodes
            node_ids = el.get("nodes", [])
            lats, lons = [], []
            for nid in node_ids:
                if nid in nodes and nodes[nid][0] is not None:
                    lats.append(nodes[nid][0])
                    lons.append(nodes[nid][1])
            if not lats:
                continue
            lat = sum(lats) / len(lats)
            lon = sum(lons) / len(lons)
        else:
            # Relations — skip for now (rare for substations)
            continue

        if lat is None or lon is None:
            continue

        substations.append({
            "osm_id": osm_id,
            "osm_type": osm_type,
            "name": name,
            "voltage_kv": voltage_kv,
            "operator": operator,
            "substation_type": substation_type,
            "lat": lat,
            "lon": lon,
        })

    return substations


def save_geojson(substations, path):
    """Save substations as GeoJSON FeatureCollection of Points."""
    features = []
    for s in substations:
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [s["lon"], s["lat"]],
            },
            "properties": {
                "osm_id": s["osm_id"],
                "osm_type": s["osm_type"],
                "name": s["name"],
                "voltage_kv": s["voltage_kv"],
                "operator": s["operator"],
                "substation_type": s["substation_type"],
            },
        }
        features.append(feature)

    collection = {"type": "FeatureCollection", "features": features}
    with open(path, "w") as f:
        json.dump(collection, f)
    print(f"Saved {len(features)} substations to {path}")


def save_csv(substations, path):
    """Save substations as CSV."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["osm_id", "osm_type", "name", "voltage_kv", "operator",
                         "substation_type", "lat", "lon"])
        for s in substations:
            writer.writerow([
                s["osm_id"], s["osm_type"], s["name"], s["voltage_kv"],
                s["operator"], s["substation_type"],
                round(s["lat"], 6), round(s["lon"], 6),
            ])
    print(f"Saved CSV to {path}")


def print_summary(substations, region):
    """Print summary stats."""
    named = sum(1 for s in substations if s["name"])
    with_voltage = sum(1 for s in substations if s["voltage_kv"] is not None)
    transmission = sum(1 for s in substations if s["substation_type"] == "transmission")
    distribution = sum(1 for s in substations if s["substation_type"] == "distribution")

    print(f"\n{'=' * 50}")
    print(f"Region: {region}")
    print(f"Total substations: {len(substations)}")
    print(f"  Named:        {named}")
    print(f"  With voltage: {with_voltage}")
    print(f"  Transmission: {transmission}")
    print(f"  Distribution: {distribution}")
    print(f"{'=' * 50}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Fetch substations from OSM via Overpass API")
    parser.add_argument("region", choices=list(REGIONS.keys()), help="Region to query")
    args = parser.parse_args()

    region = args.region
    bbox = REGIONS[region]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "..", "grid_data")
    os.makedirs(data_dir, exist_ok=True)

    print(f"Fetching substations for {region}...")
    print(f"Bounding box: {bbox}")
    print()

    elements = query_overpass(bbox)
    substations = parse_substations(elements)

    print_summary(substations, region)

    geojson_path = os.path.join(data_dir, f"{region}_substations.geojson")
    csv_path = os.path.join(data_dir, f"{region}_substations.csv")

    save_geojson(substations, geojson_path)
    save_csv(substations, csv_path)


if __name__ == "__main__":
    main()
