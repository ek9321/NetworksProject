"""
Data type definitions for the Dartboard synthetic grid pipeline.

Three layers of types:
  1. Ingestion types (LoadNode, PlantRecord, GeneratorRecord)
     Raw data from Census/EIA-860 sources.
  2. Pipeline types (Bus, Branch, Generator)
     Match the final SourceData CSV schemas (bus.csv, branch.csv, gen.csv).
     Fields are filled progressively across pipeline stages; unfilled fields
     default to None.
  3. Export helpers (bus_to_csv_row, branch_to_csv_row, generator_to_csv_row)
     Convert dataclass instances to dicts with exact CSV column names
     compatible with vatic loaders.
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Ingestion types
# ---------------------------------------------------------------------------

@dataclass
class LoadNode:
    """A ZCTA-level load point from Census data.

    Produced by ingest/census.py. Consumed by core/load_nodes_clustering.py (stage 1).
    """
    zcta: str
    lat: float
    lon: float
    population: int
    load_mw: float


@dataclass
class PlantRecord:
    """An EIA-860 power plant location record.

    Produced by ingest/eia860.py. Consumed by core/generator_assignment.py (stage 1)
    and core/voltage_partition.py (stage 2).
    """
    plant_code: int
    lat: float
    lon: float
    state: str
    grid_voltage_kv: float = 115.0
    grid_voltage_2_kv: Optional[float] = None
    grid_voltage_3_kv: Optional[float] = None
    nerc_region: Optional[str] = None
    balancing_authority: Optional[str] = None


@dataclass
class GeneratorRecord:
    """An EIA-860 generator merged with its plant location.

    Produced by ingest/eia860.py. Consumed by core/generator_assignment.py (stage 1)
    when attaching generation capacity to substations.
    """
    plant_code: int
    generator_id: str
    lat: float
    lon: float
    state: str
    nameplate_capacity_mw: float
    summer_capacity_mw: Optional[float] = None
    winter_capacity_mw: Optional[float] = None
    minimum_load_mw: Optional[float] = None
    technology: Optional[str] = None
    prime_mover: Optional[str] = None
    energy_source_1: Optional[str] = None
    energy_source_2: Optional[str] = None
    status: str = "OP"
    grid_voltage_kv: float = 115.0


# ---------------------------------------------------------------------------
# Pipeline types — fields match SourceData CSV schemas
# ---------------------------------------------------------------------------

@dataclass
class Bus:
    """A bus in the synthetic grid. Maps to bus.csv (26 columns).

    Fields are filled across pipeline stages:
      - Stage 1 (substations): bus_id, lat, lng, mw_load, sub_name, sub_num
      - Stage 2 (voltage):     base_kv, zone, area
      - Stage 5+ (DC-PF):      gen_mw, gen_mvar
      - Stage 9 (AC-PF):       pu_volt, volt_kv, angle_deg, bus_type, mismatch
    """
    # Identity — stage 1
    bus_id: int
    lat: float
    lng: float

    # Substation — stage 1
    sub_name: Optional[str] = None
    bus_name: Optional[str] = None
    sub_num: Optional[int] = None

    # Load — stage 1
    mw_load: float = 0.0
    load_mvar: float = 0.0

    # Voltage — stage 2
    base_kv: Optional[float] = None

    # Zone/Area — stages 1-2
    zone: Optional[int] = None
    zone_num: Optional[int] = None
    area: Optional[str] = None
    bus_area: Optional[int] = None
    sub_area: Optional[int] = None

    # Generation — stage 5+
    gen_mw: Optional[float] = None
    gen_mvar: Optional[float] = None

    # Power flow results — stage 9
    pu_volt: Optional[float] = None
    volt_kv: Optional[float] = None
    angle_deg: Optional[float] = None
    bus_type: Optional[str] = None
    switched_shunts_mvar: Optional[float] = None
    act_g_shunt_mw: float = 0.0
    act_b_shunt_mvar: float = 0.0
    mismatch_mw: Optional[float] = None
    mismatch_mvar: Optional[float] = None
    mismatch_mva: Optional[float] = None


@dataclass
class Branch:
    """A transmission line or transformer. Maps to branch.csv (15 columns).

    Fields are filled across pipeline stages:
      - Stage 3 (MST):         uid, from_bus, to_bus (artificial x)
      - Stages 4-7 (topology): additional branches added
      - Stage 8 (conductors):  r, x, b, cont_rating
    """
    uid: str
    from_bus: int
    to_bus: int

    from_name: Optional[str] = None
    to_name: Optional[str] = None

    # Electrical — stage 8
    r: Optional[float] = None
    x: Optional[float] = None
    b: Optional[float] = None
    cont_rating: Optional[float] = None

    # Metadata
    circuit: int = 1
    status: str = "Closed"
    branch_device_type: str = "Line"
    xfrmr: str = "NO"
    lim_mva_b: float = 0.0
    lim_mva_c: float = 0.0


@dataclass
class Generator:
    """A generator unit. Maps to gen.csv (54 columns).

    Created when EIA generator data is attached to buses. Fields are filled
    across pipeline stages; cost curves and operational parameters come from
    conductor/capacity assignment (stage 8).
    """
    # Identity
    gen_uid: str
    bus_id: int
    bus_uid: Optional[str] = None
    name_of_bus: Optional[str] = None
    sub_num_of_bus: Optional[int] = None
    gen_id: str = "1"
    status: str = "Closed"

    # Power output
    gen_mw: Optional[float] = None
    gen_mvar: Optional[float] = None
    pmin_mw: Optional[float] = None
    pmax_mw: Optional[float] = None
    min_mvar: Optional[float] = None
    max_mvar: Optional[float] = None

    # Cost
    fuel_price_per_mmbtu: Optional[float] = None
    variable_om: Optional[float] = None
    fixed_cost_per_hr: Optional[float] = None
    num_cost_curve_points: Optional[int] = None
    cost_model: Optional[str] = None
    mw_breaks: Optional[list[float]] = field(default=None)
    mwh_prices: Optional[list[float]] = field(default=None)

    # Internal cost curve parameters
    iob: Optional[float] = None
    ioc: Optional[float] = None
    iod: Optional[float] = None
    tcc_x: Optional[list[float]] = field(default=None)
    tcc_y: Optional[list[float]] = field(default=None)

    # Type classification
    unit_type: Optional[str] = None
    fuel: Optional[str] = None
    plant_code: Optional[int] = None
    unit_group: Optional[str] = None

    # Control
    agc: Optional[str] = None
    avr: Optional[str] = None
    reg_bus_num: Optional[int] = None
    set_volt: Optional[float] = None
    enforce_mw_limits: Optional[str] = None
    part_factor: Optional[float] = None

    # Operational
    ramp_rate_mw_per_min: Optional[float] = None
    min_up_time_hr: Optional[float] = None
    min_down_time_hr: Optional[float] = None
    time_cold_to_full: Optional[str] = None
    start_time_cold_hr: Optional[float] = None
    start_time_warm_hr: Optional[float] = None
    start_time_hot_hr: Optional[float] = None
    start_heat_cold_mbtu: Optional[float] = None
    start_heat_warm_mbtu: Optional[float] = None
    start_heat_hot_mbtu: Optional[float] = None
    non_fuel_start_cost: Optional[float] = None


# ---------------------------------------------------------------------------
# Export helpers — exact CSV column name mapping
# ---------------------------------------------------------------------------

def bus_to_csv_row(bus: Bus) -> dict:
    """Convert a Bus to a dict with exact bus.csv column names."""
    return {
        "Bus ID": bus.bus_id,
        "lat": bus.lat,
        "lng": bus.lng,
        "Zone": bus.zone,
        "Sub Name": bus.sub_name,
        "Bus Name": bus.bus_name,
        "Area": bus.area,
        "BaseKV": bus.base_kv,
        "PU Volt": bus.pu_volt,
        "Volt (kV)": bus.volt_kv,
        "Angle (Deg)": bus.angle_deg,
        "MW Load": bus.mw_load,
        "Load Mvar": bus.load_mvar,
        "Gen MW": bus.gen_mw,
        "Sub Num": bus.sub_num,
        "Gen Mvar": bus.gen_mvar,
        "Switched Shunts Mvar": bus.switched_shunts_mvar,
        "Act G Shunt MW": bus.act_g_shunt_mw,
        "Act B Shunt Mvar": bus.act_b_shunt_mvar,
        "Zone Num": bus.zone_num,
        "Bus Type": bus.bus_type,
        "Mismatch MW": bus.mismatch_mw,
        "Mismatch Mvar": bus.mismatch_mvar,
        "Mismatch MVA": bus.mismatch_mva,
        "Bus Area": bus.bus_area,
        "Sub Area": bus.sub_area,
    }


def branch_to_csv_row(branch: Branch) -> dict:
    """Convert a Branch to a dict with exact branch.csv column names.

    Note: branch.csv has an unnamed integer index column as the first column.
    The caller should let pandas add the index when writing to CSV.
    """
    return {
        "UID": branch.uid,
        "From Bus": branch.from_bus,
        "From Name": branch.from_name,
        "To Bus": branch.to_bus,
        "To Name": branch.to_name,
        "Circuit": branch.circuit,
        "Status": branch.status,
        "Branch Device Type": branch.branch_device_type,
        "Xfrmr": branch.xfrmr,
        "R": branch.r,
        "X": branch.x,
        "B": branch.b,
        "Cont Rating": branch.cont_rating,
        "Lim MVA B": branch.lim_mva_b,
        "Lim MVA C": branch.lim_mva_c,
    }


def _expand_list_field(values: list[float] | None, prefix: str,
                       count: int) -> dict:
    """Expand a list field into numbered columns (e.g. MW Break 1..5)."""
    result = {}
    for i in range(1, count + 1):
        if values is not None and i <= len(values):
            result[f"{prefix} {i}"] = values[i - 1]
        else:
            result[f"{prefix} {i}"] = None
    return result


def generator_to_csv_row(gen: Generator) -> dict:
    """Convert a Generator to a dict with exact gen.csv column names."""
    row = {
        "BUS UID": gen.bus_uid,
        "Sub Num of Bus": gen.sub_num_of_bus,
        "Bus ID": gen.bus_id,
        "Name of Bus": gen.name_of_bus,
        "ID": gen.gen_id,
        "Status": gen.status,
        "Gen MW": gen.gen_mw,
        "Gen Mvar": gen.gen_mvar,
        "PMin MW": gen.pmin_mw,
        "PMax MW": gen.pmax_mw,
        "AGC": gen.agc,
        "# Cost Curve Points": gen.num_cost_curve_points,
        "IOB": gen.iob,
        "IOC": gen.ioc,
        "Variable O&M": gen.variable_om,
        "Fuel Price $/MMBTU": gen.fuel_price_per_mmbtu,
        "IOD": gen.iod,
        "AVR": gen.avr,
        "RegBus Num": gen.reg_bus_num,
        "Fuel": gen.fuel,
        "Set Volt": gen.set_volt,
        "Min Mvar": gen.min_mvar,
        "Max Mvar": gen.max_mvar,
        "Enforce MW Limits": gen.enforce_mw_limits,
        "Part. Factor": gen.part_factor,
        "Cost Model": gen.cost_model,
        "GEN UID": gen.gen_uid,
        "Plant Code": gen.plant_code,
        "Unit Type": gen.unit_type,
        "Ramp Rate MW/Min": gen.ramp_rate_mw_per_min,
        "Min Up Time Hr": gen.min_up_time_hr,
        "Min Down Time Hr": gen.min_down_time_hr,
        "Time from Cold Shutdown to Full Load": gen.time_cold_to_full,
        "Unit Group": gen.unit_group,
        "Start Time Cold Hr": gen.start_time_cold_hr,
        "Start Time Warm Hr": gen.start_time_warm_hr,
        "Start Time Hot Hr": gen.start_time_hot_hr,
        "Start Heat Cold MBTU": gen.start_heat_cold_mbtu,
        "Start Heat Warm MBTU": gen.start_heat_warm_mbtu,
        "Start Heat Hot MBTU": gen.start_heat_hot_mbtu,
        "Non Fuel Start Cost $": gen.non_fuel_start_cost,
        "Fixed Cost($/hr)": gen.fixed_cost_per_hr,
    }

    row.update(_expand_list_field(gen.mw_breaks, "MW Break", 5))
    row.update(_expand_list_field(gen.mwh_prices, "MWh Price", 5))

    row["TCC_x"] = gen.tcc_x
    row["TCC_y"] = gen.tcc_y

    return row
