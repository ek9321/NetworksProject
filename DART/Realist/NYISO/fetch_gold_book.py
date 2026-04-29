"""
Fetch and parse NYISO Gold Book generator data.

Downloads the Gold Book Baseline Forecast Tables Excel file and extracts
unit-level generator capacity, fuel type, zone, and operating parameters.

The Gold Book is NYISO's equivalent of ERCOT's MORA report — the authoritative
public list of generating units with nameplate/summer/winter MW ratings.

Usage:
    python fetch_gold_book.py
"""

import csv
import os
import sys

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

try:
    import openpyxl
except ImportError:
    print("pip install openpyxl")
    sys.exit(1)


# NYISO Gold Book 2025 Baseline Forecast Tables (Excel)
GOLD_BOOK_URL = (
    "https://www.nyiso.com/documents/20142/51231901/"
    "2025-Gold-Book-Baseline-Forecast-Tables.xlsx"
)

# NYISO zone letters and names
ZONE_NAMES = {
    "A": "West", "B": "Genesee", "C": "Central", "D": "North",
    "E": "Mohawk Valley", "F": "Capital", "G": "Hudson Valley",
    "H": "Millwood", "I": "Dunwoodie", "J": "New York City", "K": "Long Island",
}

# Fuel type normalization — Gold Book uses various names
FUEL_MAP = {
    "gas": "Gas",
    "natural gas": "Gas",
    "ng": "Gas",
    "gas turbine": "Gas",
    "combined cycle": "Gas",
    "steam turbine": "Gas",  # most NY steam units are gas/dual-fuel
    "oil": "Oil",
    "fuel oil": "Oil",
    "no. 2 oil": "Oil",
    "no. 6 oil": "Oil",
    "dual fuel": "Oil",      # NYC peakers often dual-fuel gas/oil
    "kerosene": "Oil",
    "jet fuel": "Oil",
    "nuclear": "Nuclear",
    "hydro": "Hydro",
    "hydroelectric": "Hydro",
    "pumped storage": "Hydro_PS",
    "wind": "Wind",
    "solar": "Solar",
    "photovoltaic": "Solar",
    "biomass": "Biomass",
    "wood": "Biomass",
    "refuse": "Biomass",
    "landfill gas": "Biomass",
    "methane": "Biomass",
    "coal": "Coal",
}


def download_gold_book(dest_path):
    """Download Gold Book Excel file if not already present."""
    if os.path.exists(dest_path):
        print(f"Gold Book already downloaded: {dest_path}")
        return

    print(f"Downloading Gold Book from NYISO...")
    resp = requests.get(GOLD_BOOK_URL, timeout=120)
    resp.raise_for_status()

    with open(dest_path, "wb") as f:
        f.write(resp.content)
    print(f"Saved {len(resp.content) / 1024:.0f} KB to {dest_path}")


def parse_gold_book(xlsx_path):
    """
    Parse Gold Book Excel for generator data.

    The Gold Book structure varies by year. Common patterns:
    - Sheet names like "Table III-2" or "Generating Facilities"
    - Columns: Unit Name, Zone, Fuel/Prime Mover, Summer MW, Winter MW, etc.

    Returns list of dicts with standardized fields.
    """
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)

    print(f"Sheets in workbook: {wb.sheetnames}")

    generators = []

    # Try to find the generating facilities sheet
    gen_sheet = None
    for name in wb.sheetnames:
        name_lower = name.lower()
        if any(kw in name_lower for kw in ["generat", "iii-2", "capacity", "existing"]):
            gen_sheet = wb[name]
            print(f"Using sheet: '{name}'")
            break

    if gen_sheet is None:
        # Fall back to trying each sheet
        print("Could not identify generator sheet by name. Trying all sheets...")
        for name in wb.sheetnames:
            sheet = wb[name]
            # Check first few rows for generator-like headers
            for row in sheet.iter_rows(min_row=1, max_row=5, values_only=True):
                row_str = " ".join(str(c).lower() for c in row if c)
                if "zone" in row_str and ("mw" in row_str or "capacity" in row_str):
                    gen_sheet = sheet
                    print(f"Found generator data in sheet: '{name}'")
                    break
            if gen_sheet:
                break

    if gen_sheet is None:
        print("WARNING: Could not find generator sheet. Listing all sheets for manual inspection:")
        for name in wb.sheetnames:
            sheet = wb[name]
            rows = list(sheet.iter_rows(min_row=1, max_row=3, values_only=True))
            print(f"  '{name}': {rows[:2]}")
        wb.close()
        return generators

    # Parse the sheet: find header row, then extract data
    header_row = None
    col_map = {}

    for row_idx, row in enumerate(gen_sheet.iter_rows(min_row=1, max_row=20, values_only=True), 1):
        row_strs = [str(c).lower().strip() if c else "" for c in row]
        row_combined = " ".join(row_strs)

        # Look for a row with zone + capacity/mw indicators
        if "zone" in row_combined and any(kw in row_combined for kw in ["mw", "cap", "summer", "winter"]):
            header_row = row_idx
            for col_idx, val in enumerate(row_strs):
                if not val:
                    continue
                if "zone" in val and "sub" not in val:
                    col_map["zone"] = col_idx
                elif "unit" in val or "plant" in val or "station" in val or "facility" in val:
                    if "name" in val or col_idx == 0:
                        col_map["name"] = col_idx
                elif "fuel" in val or "type" in val or "prime" in val:
                    col_map["fuel"] = col_idx
                elif "summer" in val and ("mw" in val or "cap" in val or "rating" in val):
                    col_map["summer_mw"] = col_idx
                elif "winter" in val and ("mw" in val or "cap" in val or "rating" in val):
                    col_map["winter_mw"] = col_idx
                elif "nameplate" in val:
                    col_map["nameplate_mw"] = col_idx
                elif "owner" in val or "company" in val:
                    col_map["owner"] = col_idx
            print(f"Header row {header_row}: {dict((k, row[v]) for k, v in col_map.items())}")
            break

    if not header_row:
        print("WARNING: Could not find header row with zone + MW columns")
        # Dump first 10 rows for debugging
        for row_idx, row in enumerate(gen_sheet.iter_rows(min_row=1, max_row=10, values_only=True), 1):
            print(f"  Row {row_idx}: {row}")
        wb.close()
        return generators

    # If we don't have a name column, use index 0
    if "name" not in col_map:
        col_map["name"] = 0

    # Extract data rows
    for row in gen_sheet.iter_rows(min_row=header_row + 1, values_only=True):
        # Skip empty rows
        if not row or all(c is None for c in row):
            continue

        name = str(row[col_map["name"]]).strip() if col_map.get("name") is not None and row[col_map["name"]] else ""
        if not name or name.lower() in ("none", "total", "subtotal", ""):
            continue

        zone = ""
        if "zone" in col_map and row[col_map["zone"]]:
            zone = str(row[col_map["zone"]]).strip().upper()
            if len(zone) > 1 and zone[0] in "ABCDEFGHIJK":
                zone = zone[0]  # Take first letter if zone is like "A - West"
            if zone not in ZONE_NAMES:
                zone = ""

        fuel_raw = ""
        if "fuel" in col_map and row[col_map["fuel"]]:
            fuel_raw = str(row[col_map["fuel"]]).strip()

        fuel = normalize_fuel(fuel_raw)

        summer_mw = parse_mw(row[col_map["summer_mw"]]) if "summer_mw" in col_map else None
        winter_mw = parse_mw(row[col_map["winter_mw"]]) if "winter_mw" in col_map else None
        nameplate_mw = parse_mw(row[col_map["nameplate_mw"]]) if "nameplate_mw" in col_map else None

        # Use summer MW as primary, fall back to nameplate
        pmax = summer_mw or nameplate_mw or winter_mw
        if pmax is None or pmax <= 0:
            continue

        owner = ""
        if "owner" in col_map and row[col_map["owner"]]:
            owner = str(row[col_map["owner"]]).strip()

        generators.append({
            "name": name,
            "zone": zone,
            "fuel_raw": fuel_raw,
            "fuel": fuel,
            "summer_mw": summer_mw,
            "winter_mw": winter_mw,
            "nameplate_mw": nameplate_mw,
            "pmax_mw": pmax,
            "owner": owner,
        })

    wb.close()
    return generators


def normalize_fuel(fuel_raw):
    """Normalize fuel string to standard categories."""
    if not fuel_raw:
        return "Unknown"
    fuel_lower = fuel_raw.lower().strip()
    for pattern, normalized in FUEL_MAP.items():
        if pattern in fuel_lower:
            return normalized
    return "Other"


def parse_mw(val):
    """Parse a MW value from Excel cell. Returns float or None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def save_csv(generators, path):
    """Save parsed generators to CSV."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "zone", "fuel_raw", "fuel", "summer_mw",
                         "winter_mw", "nameplate_mw", "pmax_mw", "owner"])
        for g in generators:
            writer.writerow([
                g["name"], g["zone"], g["fuel_raw"], g["fuel"],
                g["summer_mw"], g["winter_mw"], g["nameplate_mw"],
                g["pmax_mw"], g["owner"],
            ])
    print(f"Saved {len(generators)} generators to {path}")


def print_summary(generators):
    """Print summary by fuel type and zone."""
    from collections import defaultdict

    print(f"\n{'=' * 60}")
    print(f"NYISO Gold Book Generator Summary")
    print(f"Total units: {len(generators)}")
    total_mw = sum(g["pmax_mw"] for g in generators)
    print(f"Total capacity: {total_mw:,.0f} MW")
    print(f"{'=' * 60}")

    # By fuel
    fuel_stats = defaultdict(lambda: {"count": 0, "mw": 0})
    for g in generators:
        fuel_stats[g["fuel"]]["count"] += 1
        fuel_stats[g["fuel"]]["mw"] += g["pmax_mw"]
    print(f"\nBy Fuel:")
    for fuel in sorted(fuel_stats, key=lambda f: -fuel_stats[f]["mw"]):
        s = fuel_stats[fuel]
        print(f"  {fuel:>12s}: {s['count']:4d} units, {s['mw']:8,.0f} MW")

    # By zone
    zone_stats = defaultdict(lambda: {"count": 0, "mw": 0})
    for g in generators:
        z = g["zone"] or "?"
        zone_stats[z]["count"] += 1
        zone_stats[z]["mw"] += g["pmax_mw"]
    print(f"\nBy Zone:")
    for z in sorted(zone_stats):
        s = zone_stats[z]
        zname = ZONE_NAMES.get(z, "Unknown")
        print(f"  Zone {z} ({zname:>15s}): {s['count']:4d} units, {s['mw']:8,.0f} MW")
    print()


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "grid_data")
    os.makedirs(data_dir, exist_ok=True)

    xlsx_path = os.path.join(data_dir, "2025_Gold_Book_Tables.xlsx")
    csv_path = os.path.join(data_dir, "gold_book_generators.csv")

    download_gold_book(xlsx_path)
    generators = parse_gold_book(xlsx_path)

    if generators:
        print_summary(generators)
        save_csv(generators, csv_path)
    else:
        print("No generators parsed. Check the Excel file structure manually.")
        print(f"File saved at: {xlsx_path}")


if __name__ == "__main__":
    main()
