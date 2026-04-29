"""
Fetch high-voltage transmission lines from OpenStreetMap via Overpass API for New York state.

Queries power=line ways within the NY bounding box, filters to >= 115 kV,
classifies into voltage tiers, and saves GeoJSON + summary CSV.

NYISO uses 765 kV, 345 kV, 230 kV, 138 kV, and 115 kV transmission.

Usage:
    python fetch_ny_transmission.py
"""

import csv
import json
import math
import os
import time

import requests

# New York state bounding box: (south, west, north, east)
NY_BBOX = (40.47, -79.77, 45.02, -71.85)

VOLTAGE_TIERS = [
    (115, 229, "115-229 kV"),
    (230, 344, "230-344 kV"),
    (345, 499, "345-499 kV"),
    (500, 9999, "500+ kV"),
]

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
MIN_VOLTAGE_KV = 115


def classify_voltage(voltage_kv):
    """Return the voltage tier label for a given kV value."""
    for lo, hi, label in VOLTAGE_TIERS:
        if lo <= voltage_kv <= hi:
            return label
    return "unknown"


def parse_voltage_tag(voltage_str):
    """Parse OSM voltage tag (volts, possibly semicolon-separated). Return max kV or None."""
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


def haversine_km(lat1, lon1, lat2, lon2):
    """Haversine distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def line_length_km(coords):
    """Total length of a polyline in km."""
    total = 0.0
    for i in range(len(coords) - 1):
        total += haversine_km(coords[i][1], coords[i][0], coords[i + 1][1], coords[i + 1][0])
    return total


def query_overpass(bbox, timeout=180):
    """Query Overpass API for power=line ways. Splits into quadrants for large areas."""
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
                print("  Waiting 15s between queries (rate limiting)...")
                time.sleep(15)
        return all_elements
    else:
        return _fetch_single_bbox(bbox, timeout)


def _fetch_single_bbox(bbox, timeout):
    """Fetch a single bbox from Overpass."""
    south, west, north, east = bbox
    query = f"""
    [out:json][timeout:{timeout}];
    (
      way["power"="line"]({south},{west},{north},{east});
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
                print("  All attempts failed.")
                raise


def parse_elements(elements):
    """Parse Overpass elements into line features. Filter >= 115 kV."""
    nodes = {}
    for el in elements:
        if el["type"] == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])

    lines = []
    seen_ids = set()
    for el in elements:
        if el["type"] != "way":
            continue
        osm_id = el["id"]
        if osm_id in seen_ids:
            continue
        seen_ids.add(osm_id)

        tags = el.get("tags", {})
        if tags.get("power") != "line":
            continue

        voltage_kv = parse_voltage_tag(tags.get("voltage"))
        if voltage_kv is None or voltage_kv < MIN_VOLTAGE_KV:
            continue

        coords = []
        for nid in el.get("nodes", []):
            if nid in nodes:
                coords.append(nodes[nid])
        if len(coords) < 2:
            continue

        lines.append({
            "osm_id": osm_id,
            "voltage_kv": voltage_kv,
            "voltage_tier": classify_voltage(voltage_kv),
            "cables": tags.get("cables", ""),
            "circuits": tags.get("circuits", ""),
            "operator": tags.get("operator", ""),
            "name": tags.get("name", ""),
            "coords": coords,
            "length_km": line_length_km(coords),
        })

    return lines


def save_geojson(lines, path):
    """Save lines as a GeoJSON FeatureCollection."""
    features = []
    for line in lines:
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": line["coords"],
            },
            "properties": {
                "osm_id": line["osm_id"],
                "voltage_kv": line["voltage_kv"],
                "voltage_tier": line["voltage_tier"],
                "cables": line["cables"],
                "circuits": line["circuits"],
                "operator": line["operator"],
                "name": line["name"],
                "length_km": round(line["length_km"], 2),
            },
        }
        features.append(feature)

    collection = {"type": "FeatureCollection", "features": features}
    with open(path, "w") as f:
        json.dump(collection, f)
    print(f"Saved {len(features)} features to {path}")


def save_summary_csv(lines, path):
    """Save a summary CSV of all lines."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["osm_id", "voltage_kv", "voltage_tier", "cables", "circuits",
                         "operator", "name", "num_nodes", "length_km"])
        for line in lines:
            writer.writerow([
                line["osm_id"],
                line["voltage_kv"],
                line["voltage_tier"],
                line["cables"],
                line["circuits"],
                line["operator"],
                line["name"],
                len(line["coords"]),
                round(line["length_km"], 2),
            ])
    print(f"Saved summary CSV to {path}")


def print_summary(lines):
    """Print summary statistics."""
    print(f"\n{'=' * 50}")
    print(f"Region: New York")
    print(f"Total HV lines fetched: {len(lines)}")
    print(f"{'=' * 50}")
    for _, _, tier_label in VOLTAGE_TIERS:
        tier_lines = [l for l in lines if l["voltage_tier"] == tier_label]
        total_km = sum(l["length_km"] for l in tier_lines)
        print(f"  {tier_label:>12s}:  {len(tier_lines):5d} lines,  {total_km:8.1f} km")
    total_km = sum(l["length_km"] for l in lines)
    print(f"  {'TOTAL':>12s}:  {len(lines):5d} lines,  {total_km:8.1f} km")
    print()


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "grid_data")
    os.makedirs(data_dir, exist_ok=True)

    print(f"Fetching HV lines for New York...")
    print(f"Bounding box: {NY_BBOX}")
    print(f"Minimum voltage: {MIN_VOLTAGE_KV} kV")
    print()

    elements = query_overpass(NY_BBOX)
    lines = parse_elements(elements)

    print_summary(lines)

    geojson_path = os.path.join(data_dir, "ny_hv_lines.geojson")
    csv_path = os.path.join(data_dir, "ny_hv_lines_summary.csv")

    save_geojson(lines, geojson_path)
    save_summary_csv(lines, csv_path)


if __name__ == "__main__":
    main()
