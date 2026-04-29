"""
Load EIA-860 Form 2023 plant and generator data.

Input files (in data/eia8602023/):
  - 2___Plant_Y2023.xlsx: Plant-level data (location, voltage, region)
  - 3_1_Generator_Y2023.xlsx: Generator-level data (capacity, fuel, status)

Output:
  - list[PlantRecord] for plant locations
  - list[GeneratorRecord] for generators merged with plant data

Cached to data/processed/ as CSV to avoid re-parsing Excel files.
"""

import os

import pandas as pd

from core.graph_types import PlantRecord, GeneratorRecord


def _safe_float(val) -> float | None:
    """Convert a value to float, returning None for NaN, empty string, etc."""
    if val is None:
        return None
    if isinstance(val, str):
        val = val.strip()
        if val == "":
            return None
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (ValueError, TypeError):
        return None


def _match_plant_columns(df: pd.DataFrame) -> dict[str, str]:
    """Build a column rename map for the Plant file using substring matching.

    EIA column names have inconsistent casing and spacing across form years.
    We lowercase all columns and match by substring.
    """
    rename = {}
    seen = set()

    for c in df.columns:
        cl = c.lower() if isinstance(c, str) else str(c).lower()

        if "plant code" in cl and "Plant Code" not in seen:
            rename[c] = "Plant Code"
            seen.add("Plant Code")
        elif "state" in cl and "guidelines" not in cl and "State" not in seen:
            rename[c] = "State"
            seen.add("State")
        elif "latitude" in cl and "Latitude" not in seen:
            rename[c] = "Latitude"
            seen.add("Latitude")
        elif "longitude" in cl and "Longitude" not in seen:
            rename[c] = "Longitude"
            seen.add("Longitude")
        elif "nerc" in cl and "region" in cl and "NERC Region" not in seen:
            rename[c] = "NERC Region"
            seen.add("NERC Region")
        elif "balancing" in cl and "code" in cl and "BA Code" not in seen:
            rename[c] = "BA Code"
            seen.add("BA Code")
        elif "grid voltage" in cl and "kv" in cl:
            if "2" in cl and "Voltage 2" not in seen:
                rename[c] = "Voltage 2"
                seen.add("Voltage 2")
            elif "3" in cl and "Voltage 3" not in seen:
                rename[c] = "Voltage 3"
                seen.add("Voltage 3")
            elif "Voltage 1" not in seen:
                rename[c] = "Voltage 1"
                seen.add("Voltage 1")

    return rename


def _match_gen_columns(df: pd.DataFrame) -> dict[str, str]:
    """Build a column rename map for the Generator file."""
    rename = {}
    seen = set()

    for c in df.columns:
        cl = c.lower() if isinstance(c, str) else str(c).lower()

        if "plant code" in cl and "Plant Code" not in seen:
            rename[c] = "Plant Code"
            seen.add("Plant Code")
        elif "generator id" in cl and "Generator ID" not in seen:
            rename[c] = "Generator ID"
            seen.add("Generator ID")
        elif "nameplate" in cl and "mw" in cl and "Nameplate MW" not in seen:
            rename[c] = "Nameplate MW"
            seen.add("Nameplate MW")
        elif "summer" in cl and "capacity" in cl and "mw" in cl and "Summer MW" not in seen:
            rename[c] = "Summer MW"
            seen.add("Summer MW")
        elif "winter" in cl and "capacity" in cl and "mw" in cl and "Winter MW" not in seen:
            rename[c] = "Winter MW"
            seen.add("Winter MW")
        elif "minimum" in cl and "load" in cl and "mw" in cl and "Min Load" not in seen:
            rename[c] = "Min Load"
            seen.add("Min Load")
        elif "technology" in cl and "Technology" not in seen:
            rename[c] = "Technology"
            seen.add("Technology")
        elif "prime mover" in cl and "Prime Mover" not in seen:
            rename[c] = "Prime Mover"
            seen.add("Prime Mover")
        elif "energy source 1" in cl and "Energy Source 1" not in seen:
            rename[c] = "Energy Source 1"
            seen.add("Energy Source 1")
        elif "energy source 2" in cl and "Energy Source 2" not in seen:
            rename[c] = "Energy Source 2"
            seen.add("Energy Source 2")
        elif cl == "status" and "Status" not in seen:
            rename[c] = "Status"
            seen.add("Status")

    return rename


def load_plants(plant_xlsx: str) -> list[PlantRecord]:
    """Load EIA-860 plant records from the Plant Excel file.

    The file has a header row that must be skipped (skiprows=1).
    Plants are deduplicated by Plant Code. Missing grid voltage defaults
    to 115 kV.
    """
    df = pd.read_excel(plant_xlsx, skiprows=1)
    rename = _match_plant_columns(df)
    df = df.rename(columns=rename)

    # Deduplicate by Plant Code
    if "Plant Code" not in df.columns:
        raise ValueError("Could not find 'Plant Code' column in plant file")
    df = df.drop_duplicates(subset=["Plant Code"])

    plants = []
    for _, row in df.iterrows():
        lat = _safe_float(row.get("Latitude"))
        lon = _safe_float(row.get("Longitude"))
        if lat is None or lon is None:
            continue

        v1 = row.get("Voltage 1")
        v2 = row.get("Voltage 2")
        v3 = row.get("Voltage 3")

        fv1 = _safe_float(v1)
        fv2 = _safe_float(v2)
        fv3 = _safe_float(v3)

        nerc = row.get("NERC Region")
        ba = row.get("BA Code")

        plants.append(PlantRecord(
            plant_code=int(row["Plant Code"]),
            lat=lat,
            lon=lon,
            state=str(row.get("State", "")),
            grid_voltage_kv=fv1 if fv1 is not None else 115.0,
            grid_voltage_2_kv=fv2,
            grid_voltage_3_kv=fv3,
            nerc_region=str(nerc).strip() if pd.notna(nerc) and str(nerc).strip() else None,
            balancing_authority=str(ba).strip() if pd.notna(ba) and str(ba).strip() else None,
        ))

    return plants


def load_generators(
    gen_xlsx: str,
    plants: list[PlantRecord],
    status_filter: str = "OP",
) -> list[GeneratorRecord]:
    """Load EIA-860 generator records merged with plant locations.

    The file has a header row that must be skipped (skiprows=1).
    Only generators matching status_filter are returned. Each generator
    inherits lat/lon/state/voltage from its parent plant.
    """
    df = pd.read_excel(gen_xlsx, skiprows=1)
    rename = _match_gen_columns(df)
    df = df.rename(columns=rename)

    if "Plant Code" not in df.columns:
        raise ValueError("Could not find 'Plant Code' column in generator file")

    plant_lookup = {p.plant_code: p for p in plants}

    # Filter by status
    if "Status" in df.columns:
        df = df[df["Status"] == status_filter].copy()

    generators = []
    for _, row in df.iterrows():
        pc = int(row["Plant Code"])
        plant = plant_lookup.get(pc)
        if plant is None:
            continue

        cap = _safe_float(row.get("Nameplate MW"))
        if cap is None:
            continue

        gen_id = row.get("Generator ID", "")

        def _safe_str(val) -> str | None:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            s = str(val).strip()
            return s if s else None

        generators.append(GeneratorRecord(
            plant_code=pc,
            generator_id=str(gen_id).strip() if pd.notna(gen_id) else "",
            lat=plant.lat,
            lon=plant.lon,
            state=plant.state,
            nameplate_capacity_mw=cap,
            summer_capacity_mw=_safe_float(row.get("Summer MW")),
            winter_capacity_mw=_safe_float(row.get("Winter MW")),
            minimum_load_mw=_safe_float(row.get("Min Load")),
            technology=_safe_str(row.get("Technology")),
            prime_mover=_safe_str(row.get("Prime Mover")),
            energy_source_1=_safe_str(row.get("Energy Source 1")),
            energy_source_2=_safe_str(row.get("Energy Source 2")),
            status=status_filter,
            grid_voltage_kv=plant.grid_voltage_kv,
        ))

    return generators


def load_eia860(
    eia_dir: str,
    status_filter: str = "OP",
) -> tuple[list[PlantRecord], list[GeneratorRecord]]:
    """Load both plants and generators from the EIA-860 data directory.

    Args:
        eia_dir: Path to directory containing EIA-860 Excel files.
        status_filter: Only return generators with this status code.

    Returns:
        (plants, generators) tuple of typed record lists.
    """
    plant_xlsx = os.path.join(eia_dir, "2___Plant_Y2023.xlsx")
    gen_xlsx = os.path.join(eia_dir, "3_1_Generator_Y2023.xlsx")

    plants = load_plants(plant_xlsx)
    generators = load_generators(gen_xlsx, plants, status_filter)
    return plants, generators


# ---------------------------------------------------------------------------
# Cache save/load
# ---------------------------------------------------------------------------

def save_plants(plants: list[PlantRecord], csv_path: str) -> None:
    """Write PlantRecords to a CSV file."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    df = pd.DataFrame([
        {
            "plant_code": p.plant_code,
            "lat": p.lat,
            "lon": p.lon,
            "state": p.state,
            "grid_voltage_kv": p.grid_voltage_kv,
            "grid_voltage_2_kv": p.grid_voltage_2_kv,
            "grid_voltage_3_kv": p.grid_voltage_3_kv,
            "nerc_region": p.nerc_region,
            "balancing_authority": p.balancing_authority,
        }
        for p in plants
    ])
    df.to_csv(csv_path, index=False)


def load_plants_csv(csv_path: str) -> list[PlantRecord]:
    """Read PlantRecords from a cached CSV file."""
    df = pd.read_csv(csv_path)
    return [
        PlantRecord(
            plant_code=int(row["plant_code"]),
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            state=str(row["state"]),
            grid_voltage_kv=float(row["grid_voltage_kv"]),
            grid_voltage_2_kv=float(row["grid_voltage_2_kv"]) if pd.notna(row["grid_voltage_2_kv"]) else None,
            grid_voltage_3_kv=float(row["grid_voltage_3_kv"]) if pd.notna(row["grid_voltage_3_kv"]) else None,
            nerc_region=str(row["nerc_region"]) if pd.notna(row["nerc_region"]) else None,
            balancing_authority=str(row["balancing_authority"]) if pd.notna(row["balancing_authority"]) else None,
        )
        for _, row in df.iterrows()
    ]


def save_generators(generators: list[GeneratorRecord], csv_path: str) -> None:
    """Write GeneratorRecords to a CSV file."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    df = pd.DataFrame([
        {
            "plant_code": g.plant_code,
            "generator_id": g.generator_id,
            "lat": g.lat,
            "lon": g.lon,
            "state": g.state,
            "nameplate_capacity_mw": g.nameplate_capacity_mw,
            "summer_capacity_mw": g.summer_capacity_mw,
            "winter_capacity_mw": g.winter_capacity_mw,
            "minimum_load_mw": g.minimum_load_mw,
            "technology": g.technology,
            "prime_mover": g.prime_mover,
            "energy_source_1": g.energy_source_1,
            "energy_source_2": g.energy_source_2,
            "status": g.status,
            "grid_voltage_kv": g.grid_voltage_kv,
        }
        for g in generators
    ])
    df.to_csv(csv_path, index=False)


def load_generators_csv(csv_path: str) -> list[GeneratorRecord]:
    """Read GeneratorRecords from a cached CSV file."""
    df = pd.read_csv(csv_path)
    return [
        GeneratorRecord(
            plant_code=int(row["plant_code"]),
            generator_id=str(row["generator_id"]),
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            state=str(row["state"]),
            nameplate_capacity_mw=float(row["nameplate_capacity_mw"]),
            summer_capacity_mw=float(row["summer_capacity_mw"]) if pd.notna(row["summer_capacity_mw"]) else None,
            winter_capacity_mw=float(row["winter_capacity_mw"]) if pd.notna(row["winter_capacity_mw"]) else None,
            minimum_load_mw=float(row["minimum_load_mw"]) if pd.notna(row["minimum_load_mw"]) else None,
            technology=str(row["technology"]) if pd.notna(row["technology"]) else None,
            prime_mover=str(row["prime_mover"]) if pd.notna(row["prime_mover"]) else None,
            energy_source_1=str(row["energy_source_1"]) if pd.notna(row["energy_source_1"]) else None,
            energy_source_2=str(row["energy_source_2"]) if pd.notna(row["energy_source_2"]) else None,
            status=str(row["status"]),
            grid_voltage_kv=float(row["grid_voltage_kv"]),
        )
        for _, row in df.iterrows()
    ]
