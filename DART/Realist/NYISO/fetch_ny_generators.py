"""
Extract NY generators from EIA-860 and prepare for SCED model.

Uses the existing EIA-860 processed CSV (Birchfield/data/processed/eia860_generators.csv)
filtered for New York state. This is the unit-level source with lat/lon coordinates
needed for geo-snapping to OSM buses.

Also downloads the Gold Book Baseline Forecast Tables for zone peak demand
calibration data (not generator-level — that's PDF-only).

Usage:
    python fetch_ny_generators.py
"""

import csv
import os
from collections import defaultdict

# EIA-860 fuel code to standard fuel mapping
FUEL_MAP = {
    # Gas
    "NG": "Gas", "OG": "Gas", "BFG": "Gas", "LFG": "Biomass",
    # Oil
    "DFO": "Oil", "RFO": "Oil", "JF": "Oil", "KER": "Oil", "PC": "Oil",
    "WO": "Oil",
    # Coal
    "BIT": "Coal", "SUB": "Coal", "LIG": "Coal", "RC": "Coal", "WC": "Coal",
    "ANT": "Coal",
    # Nuclear
    "NUC": "Nuclear", "UR": "Nuclear",
    # Hydro
    "WAT": "Hydro",
    # Wind
    "WND": "Wind",
    # Solar
    "SUN": "Solar",
    # Biomass
    "WDS": "Biomass", "BLQ": "Biomass", "AB": "Biomass", "MSW": "Biomass",
    "OBS": "Biomass", "WDL": "Biomass", "OBL": "Biomass", "SLW": "Biomass",
    "OBG": "Biomass", "MSB": "Biomass",
    # Other
    "GEO": "Other", "MWH": "Storage", "PUR": "Other", "WH": "Other",
    "TDF": "Other", "OTH": "Other", "H2": "Other",
}

# Prime mover to unit type mapping
PRIME_MOVER_MAP = {
    "CA": "CC",   # Combined cycle steam (part)
    "CS": "CC",   # Combined cycle single-shaft
    "CT": "CC",   # Combined cycle combustion turbine
    "GT": "GT",   # Gas turbine
    "IC": "IC",   # Internal combustion
    "ST": "ST",   # Steam turbine
    "HA": "HY",   # Hydraulic turbine
    "HB": "HY",   # Hydraulic turbine (reversible — pumped storage)
    "HK": "HY",   # Hydraulic kinetic
    "HY": "HY",   # Hydraulic
    "PS": "PS",   # Pumped storage
    "WT": "WT",   # Wind turbine (onshore)
    "WS": "WT",   # Wind turbine (offshore)
    "PV": "PV",   # Photovoltaic
    "CP": "PV",   # Concentrated photovoltaic
    "BA": "BA",   # Battery
    "ES": "BA",   # Energy storage (other)
    "FW": "BA",   # Flywheel
    "FC": "FC",   # Fuel cell
    "BT": "ST",   # Binary cycle turbine
    "CE": "ST",   # Compressed air energy
    "OT": "OT",   # Other
}


def load_eia860_ny(eia_path):
    """Load EIA-860 generators filtered for NY state."""
    generators = []
    with open(eia_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("state") != "NY":
                continue
            if row.get("status") not in ("OP", ""):  # Operable only
                continue

            plant_code = row.get("plant_code", "")
            gen_id = row.get("generator_id", "")
            lat = safe_float(row.get("lat"))
            lon = safe_float(row.get("lon"))
            nameplate_mw = safe_float(row.get("nameplate_capacity_mw"))
            summer_mw = safe_float(row.get("summer_capacity_mw"))
            winter_mw = safe_float(row.get("winter_capacity_mw"))
            min_load_mw = safe_float(row.get("minimum_load_mw"))
            fuel_code = row.get("energy_source_1", "")
            prime_mover = row.get("prime_mover", "")
            technology = row.get("technology", "")
            grid_kv = safe_float(row.get("grid_voltage_kv"))

            fuel = FUEL_MAP.get(fuel_code, "Other")
            unit_type = PRIME_MOVER_MAP.get(prime_mover, "OT")

            # Skip storage units (handled separately)
            if fuel == "Storage" or unit_type in ("BA", "PS"):
                continue

            pmax = summer_mw or nameplate_mw or winter_mw
            if pmax is None or pmax <= 0:
                continue

            generators.append({
                "plant_code": plant_code,
                "generator_id": gen_id,
                "gen_uid": f"EIA_{plant_code}_{gen_id}",
                "lat": lat,
                "lon": lon,
                "nameplate_mw": nameplate_mw,
                "summer_mw": summer_mw,
                "winter_mw": winter_mw,
                "min_load_mw": min_load_mw,
                "pmax_mw": pmax,
                "fuel_code": fuel_code,
                "fuel": fuel,
                "prime_mover": prime_mover,
                "unit_type": unit_type,
                "technology": technology,
                "grid_kv": grid_kv,
            })

    return generators


def load_eia860_ny_storage(eia_path):
    """Load EIA-860 storage units for NY state."""
    storage = []
    with open(eia_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("state") != "NY":
                continue
            if row.get("status") not in ("OP", ""):
                continue

            fuel_code = row.get("energy_source_1", "")
            prime_mover = row.get("prime_mover", "")
            fuel = FUEL_MAP.get(fuel_code, "Other")
            unit_type = PRIME_MOVER_MAP.get(prime_mover, "OT")

            if fuel != "Storage" and unit_type not in ("BA", "PS"):
                continue

            plant_code = row.get("plant_code", "")
            gen_id = row.get("generator_id", "")
            lat = safe_float(row.get("lat"))
            lon = safe_float(row.get("lon"))
            nameplate_mw = safe_float(row.get("nameplate_capacity_mw"))
            summer_mw = safe_float(row.get("summer_capacity_mw"))

            pmax = summer_mw or nameplate_mw
            if pmax is None or pmax <= 0:
                continue

            storage.append({
                "plant_code": plant_code,
                "generator_id": gen_id,
                "storage_uid": f"BESS_{plant_code}_{gen_id}",
                "lat": lat,
                "lon": lon,
                "nameplate_mw": nameplate_mw,
                "summer_mw": summer_mw,
                "pmax_mw": pmax,
                "prime_mover": prime_mover,
                "unit_type": unit_type,
                "technology": row.get("technology", ""),
            })

    return storage


def safe_float(val):
    """Convert to float, return None if invalid."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def save_csv(generators, path, fields):
    """Save list of dicts as CSV."""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(generators)
    print(f"Saved {len(generators)} records to {path}")


def print_summary(generators, label="Generators"):
    """Print summary by fuel type."""
    fuel_stats = defaultdict(lambda: {"count": 0, "mw": 0})
    for g in generators:
        fuel = g.get("fuel", g.get("unit_type", "?"))
        fuel_stats[fuel]["count"] += 1
        fuel_stats[fuel]["mw"] += g["pmax_mw"]

    total_mw = sum(g["pmax_mw"] for g in generators)

    print(f"\n{'=' * 60}")
    print(f"NY {label} (from EIA-860)")
    print(f"Total units: {len(generators)}")
    print(f"Total capacity: {total_mw:,.0f} MW")
    print(f"{'=' * 60}")
    for fuel in sorted(fuel_stats, key=lambda f: -fuel_stats[f]["mw"]):
        s = fuel_stats[fuel]
        print(f"  {fuel:>10s}: {s['count']:4d} units, {s['mw']:8,.0f} MW")
    print()

    # Geographic coverage
    with_coords = sum(1 for g in generators if g.get("lat") and g.get("lon"))
    print(f"With coordinates: {with_coords}/{len(generators)} ({100*with_coords/len(generators):.0f}%)")
    print()


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    data_dir = os.path.join(script_dir, "grid_data")
    os.makedirs(data_dir, exist_ok=True)

    # Path to existing EIA-860 processed CSV
    eia_path = os.path.join(project_root, "Birchfield", "data", "processed",
                            "eia860_generators.csv")
    if not os.path.exists(eia_path):
        print(f"EIA-860 file not found: {eia_path}")
        print("Run the Birchfield EIA-860 pipeline first, or download from eia.gov.")
        return

    print(f"Loading EIA-860 from: {eia_path}")

    # Generators
    generators = load_eia860_ny(eia_path)
    print_summary(generators, "Generators")

    gen_fields = ["gen_uid", "plant_code", "generator_id", "lat", "lon",
                  "nameplate_mw", "summer_mw", "winter_mw", "min_load_mw",
                  "pmax_mw", "fuel_code", "fuel", "prime_mover", "unit_type",
                  "technology", "grid_kv"]
    gen_path = os.path.join(data_dir, "ny_generators_eia860.csv")
    save_csv(generators, gen_path, gen_fields)

    # Storage
    storage = load_eia860_ny_storage(eia_path)
    if storage:
        print_summary(storage, "Storage")
        stor_fields = ["storage_uid", "plant_code", "generator_id", "lat", "lon",
                       "nameplate_mw", "summer_mw", "pmax_mw", "prime_mover",
                       "unit_type", "technology"]
        stor_path = os.path.join(data_dir, "ny_storage_eia860.csv")
        save_csv(storage, stor_path, stor_fields)
    else:
        print("No storage units found in EIA-860.")

    # Also extract Gold Book zone peak demands for calibration
    gold_book_path = os.path.join(data_dir, "2025_Gold_Book_Tables.xlsx")
    if os.path.exists(gold_book_path):
        extract_zone_peaks(gold_book_path, data_dir)


def extract_zone_peaks(xlsx_path, data_dir):
    """Extract zone peak demands from Gold Book Table I-3a for load calibration."""
    try:
        import openpyxl
    except ImportError:
        print("openpyxl not available, skipping Gold Book peak extraction")
        return

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    sheet = wb["I-3a"]

    # Row 8 has 2015 actuals; we want the most recent year (2025 = row 18 typically)
    # Columns: C=Year, D=A, E=B, F=C, G=D, H=E, I=F, J=G, K=H, L=I, M=J, N=K, O=Total
    zones = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"]

    peak_data = {}
    for row in sheet.iter_rows(min_row=8, max_row=50, values_only=True):
        year_val = row[2] if len(row) > 2 else None
        if year_val is None:
            continue
        try:
            year = int(year_val)
        except (ValueError, TypeError):
            continue
        if year == 2025:
            for i, zone in enumerate(zones):
                col_idx = 3 + i
                if col_idx < len(row) and row[col_idx]:
                    try:
                        peak_data[zone] = float(row[col_idx])
                    except (ValueError, TypeError):
                        pass
            break

    wb.close()

    if peak_data:
        print(f"\nGold Book 2025 Summer Coincident Peak Demands (MW):")
        total = 0
        for z in zones:
            if z in peak_data:
                print(f"  Zone {z}: {peak_data[z]:,.0f} MW")
                total += peak_data[z]
        print(f"  TOTAL: {total:,.0f} MW")

        # Save as CSV
        peak_path = os.path.join(data_dir, "nyiso_zone_peaks_2025.csv")
        with open(peak_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["zone", "summer_peak_mw"])
            for z in zones:
                writer.writerow([z, peak_data.get(z, "")])
        print(f"Saved to {peak_path}")


if __name__ == "__main__":
    main()
