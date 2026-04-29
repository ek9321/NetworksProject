"""
Fetch all power lines/cables from OpenStreetMap via Overpass API.

Queries power=line, power=cable, and power=minor_line ways within a region
bounding box, classifies into voltage tiers, and saves GeoJSON + summary CSV.
No voltage floor — pulls everything OSM has.

Usage:
    python fetch_hv_lines.py texas
"""

import argparse
import csv
import json
import math
import os
import sys
import time

import requests

# Region bounding boxes: (south, west, north, east)
REGIONS = {
    "texas": (25.83, -106.65, 36.50, -93.51),
}

# Voltage tier classification (kV)
VOLTAGE_TIERS = [
    (0, 68, "<69 kV"),
    (69, 114, "69-114 kV"),
    (115, 229, "115-229 kV"),
    (230, 344, "230-344 kV"),
    (345, 499, "345-499 kV"),
    (500, 9999, "500+ kV"),
]

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


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
            values.append(int(part) / 1000)  # Convert V to kV
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
    """
    Query Overpass API for power lines/cables in the given bbox.
    Splits into tiles to avoid timeouts. Uses 3x3 grid for the full
    Texas bbox since cable+minor_line data is much larger than lines-only.
    Returns raw JSON elements list.
    """
    south, west, north, east = bbox
    lat_span = north - south
    lon_span = east - west

    # Use 3x3 grid for large areas (cable/minor_line makes payloads huge)
    if lat_span > 3 or lon_span > 4:
        n_lat = max(2, int(math.ceil(lat_span / 3.5)))
        n_lon = max(2, int(math.ceil(lon_span / 4.5)))
        total = n_lat * n_lon
        print(f"  Large bbox ({lat_span:.1f} x {lon_span:.1f} deg), splitting into {n_lat}x{n_lon} = {total} tiles...")

        lat_step = lat_span / n_lat
        lon_step = lon_span / n_lon

        all_elements = []
        tile_num = 0
        for i_lat in range(n_lat):
            for i_lon in range(n_lon):
                tile_num += 1
                t_south = south + i_lat * lat_step
                t_west = west + i_lon * lon_step
                t_north = t_south + lat_step
                t_east = t_west + lon_step
                tile = (t_south, t_west, t_north, t_east)
                print(f"  Tile {tile_num}/{total}: ({t_south:.2f},{t_west:.2f},{t_north:.2f},{t_east:.2f})")
                elements = _fetch_single_bbox(tile, timeout)
                all_elements.extend(elements)
                if tile_num < total:
                    print("  Waiting 5s (rate limiting)...")
                    time.sleep(5)
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
      way["power"="cable"]({south},{west},{north},{east});
      way["power"="minor_line"]({south},{west},{north},{east});
    );
    out body;
    >;
    out skel qt;
    """
    print(f"  Querying Overpass API...")
    for attempt in range(5):
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=timeout + 30)
            resp.raise_for_status()
            data = resp.json()
            elements = data.get("elements", [])
            print(f"  Received {len(elements)} elements")
            return elements
        except (requests.RequestException, ValueError) as e:
            wait = 15 * (attempt + 1)
            print(f"  Attempt {attempt + 1}/5 failed: {e}")
            if attempt < 4:
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print("  All attempts failed.")
                raise


def parse_elements(elements):
    """
    Parse Overpass elements into line features.
    Returns list of dicts with keys: osm_id, power_type, voltage_kv, voltage_tier,
    cables, operator, coords [(lon, lat), ...], length_km
    """
    POWER_TYPES = {"line", "cable", "minor_line"}

    # Build node lookup
    nodes = {}
    for el in elements:
        if el["type"] == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])

    # Parse ways
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
        power_type = tags.get("power", "")
        if power_type not in POWER_TYPES:
            continue

        voltage_kv = parse_voltage_tag(tags.get("voltage"))
        # Keep lines even without a voltage tag (voltage_kv = None → 0)
        effective_kv = voltage_kv if voltage_kv is not None else 0

        # Resolve node coordinates
        coords = []
        for nid in el.get("nodes", []):
            if nid in nodes:
                coords.append(nodes[nid])
        if len(coords) < 2:
            continue

        lines.append({
            "osm_id": osm_id,
            "power_type": power_type,
            "voltage_kv": effective_kv,
            "voltage_tier": classify_voltage(effective_kv),
            "cables": tags.get("cables", ""),
            "operator": tags.get("operator", ""),
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
                "power_type": line["power_type"],
                "voltage_kv": line["voltage_kv"],
                "voltage_tier": line["voltage_tier"],
                "cables": line["cables"],
                "operator": line["operator"],
                "length_km": round(line["length_km"], 2),
            },
        }
        features.append(feature)

    collection = {
        "type": "FeatureCollection",
        "features": features,
    }

    with open(path, "w") as f:
        json.dump(collection, f)
    print(f"Saved {len(features)} features to {path}")


def save_summary_csv(lines, path):
    """Save a summary CSV of all lines."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["osm_id", "power_type", "voltage_kv", "voltage_tier", "cables", "operator", "num_nodes", "length_km"])
        for line in lines:
            writer.writerow([
                line["osm_id"],
                line["power_type"],
                line["voltage_kv"],
                line["voltage_tier"],
                line["cables"],
                line["operator"],
                len(line["coords"]),
                round(line["length_km"], 2),
            ])
    print(f"Saved summary CSV to {path}")


def print_summary(lines, region):
    """Print summary statistics."""
    print(f"\n{'=' * 60}")
    print(f"Region: {region}")
    print(f"Total features fetched: {len(lines)}")
    print(f"{'=' * 60}")

    # By power type
    print("  By type:")
    for ptype in ("line", "cable", "minor_line"):
        subset = [l for l in lines if l["power_type"] == ptype]
        total_km = sum(l["length_km"] for l in subset)
        print(f"    {ptype:>12s}:  {len(subset):5d} ways,  {total_km:8.1f} km")

    # By voltage tier
    print("  By voltage:")
    for _, _, tier_label in VOLTAGE_TIERS:
        tier_lines = [l for l in lines if l["voltage_tier"] == tier_label]
        total_km = sum(l["length_km"] for l in tier_lines)
        print(f"    {tier_label:>12s}:  {len(tier_lines):5d} ways,  {total_km:8.1f} km")

    # Untagged voltage
    no_voltage = [l for l in lines if l["voltage_kv"] == 0]
    if no_voltage:
        total_km = sum(l["length_km"] for l in no_voltage)
        print(f"    {'no voltage':>12s}:  {len(no_voltage):5d} ways,  {total_km:8.1f} km")

    total_km = sum(l["length_km"] for l in lines)
    print(f"    {'TOTAL':>12s}:  {len(lines):5d} ways,  {total_km:8.1f} km")
    print()


def main():
    parser = argparse.ArgumentParser(description="Fetch HV lines from OpenStreetMap via Overpass API")
    parser.add_argument("region", choices=list(REGIONS.keys()), help="Region to query")
    args = parser.parse_args()

    region = args.region
    bbox = REGIONS[region]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "..", "grid_data")
    os.makedirs(data_dir, exist_ok=True)

    print(f"Fetching all power lines/cables for {region}...")
    print(f"Bounding box: {bbox}")
    print(f"Power types: line, cable, minor_line (no voltage floor)")
    print()

    elements = query_overpass(bbox)
    lines = parse_elements(elements)

    print_summary(lines, region)

    geojson_path = os.path.join(data_dir, f"{region}_hv_lines.geojson")
    csv_path = os.path.join(data_dir, f"{region}_hv_lines_summary.csv")

    save_geojson(lines, geojson_path)
    save_summary_csv(lines, csv_path)


if __name__ == "__main__":
    main()
