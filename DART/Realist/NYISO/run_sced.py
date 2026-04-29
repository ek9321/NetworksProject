#!/usr/bin/env python3
"""
NYISO DC-SCED Runner — adapted from ERCOT run_sced.py.

Loads the OSM-native bus/branch/gen/storage tables, distributes zonal load,
builds renewable timeseries, and runs the Vatic DC-SCED simulator.

Environment variables (all optional):
  SCED_DATE          — simulation date (default: 2025-07-20, summer peak)
  EXPERIMENT_TAG     — results directory suffix (default: "baseline")
  DARTBOARD_SCRATCH  — cluster scratch dir (triggers Gurobi solver)
  HOURLY_LOAD_CSV    — hourly zonal load CSV (zones A-K)
  HOURLY_CF_CSV      — hourly wind/solar CF CSV
  BRANCH_SCALE       — multiply all branch ratings (0 = unconstrained)
  STORAGE_AGGREGATE  — "zone" (default), "bus", or "none"
  LOAD_NAMED_ONLY    — 1 to restrict load to named substations

Usage:
  python run_sced.py                    # local (CBC solver)
  sbatch run_sced_array.slurm           # cluster (Gurobi solver)
"""

import csv
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------
SCED_DATE_STR  = os.environ.get("SCED_DATE", "2025-07-20")
EXPERIMENT_TAG = os.environ.get("EXPERIMENT_TAG",
                 os.environ.get("SCED_INSTANCE", "baseline"))
SCRATCH        = os.environ.get("DARTBOARD_SCRATCH", "")
BRANCH_SCALE   = float(os.environ.get("BRANCH_SCALE", "1"))
STORAGE_AGG    = os.environ.get("STORAGE_AGGREGATE", "zone")
LOAD_NAMED     = os.environ.get("LOAD_NAMED_ONLY", "0") == "1"
HOURLY_LOAD    = os.environ.get("HOURLY_LOAD_CSV", "")
HOURLY_CF      = os.environ.get("HOURLY_CF_CSV", "")

SCED_DATE = date.fromisoformat(SCED_DATE_STR)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
if SCRATCH:
    BASE     = Path(SCRATCH)
    DATA     = BASE / "grid_data"
    SCED_DIR = BASE / f"sced_inputs_{EXPERIMENT_TAG}"
    SRC_DIR  = SCED_DIR / "SourceData"
    RES_DIR  = SCED_DIR / f"results_{EXPERIMENT_TAG}"
    USE_GUROBI = True
    THREADS  = int(os.environ.get("SLURM_CPUS_PER_TASK", "8"))
else:
    NYISO_DIR = Path(__file__).resolve().parent
    DATA      = NYISO_DIR / "grid_data"
    SCED_DIR  = DATA / "sced_inputs"
    SRC_DIR   = SCED_DIR / "SourceData"
    RES_DIR   = SCED_DIR / f"results_{EXPERIMENT_TAG}"
    USE_GUROBI = False
    THREADS  = 1

SRC_DIR.mkdir(parents=True, exist_ok=True)
RES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# NYISO zone load distribution
# ---------------------------------------------------------------------------
# Gold Book 2025 summer coincident peak demands (MW)
# Zones H (Millwood) and I (Dunwoodie) are sub-county, merged into G at
# polygon level. For load distribution we allocate G+H+I as one block
# and the DC-SCED treats it as zone G buses.
ZONE_LOAD_MW = {
    "A": 2_864.0,   # West
    "B": 1_855.0,   # Genesee
    "C": 2_516.0,   # Central
    "D":   691.0,   # North
    "E": 1_310.0,   # Mohawk Valley
    "F": 2_269.0,   # Capital
    "G": 4_199.0,   # Hudson Valley + Millwood + Dunwoodie (2264+619+1316)
    "J": 10_764.0,  # New York City
    "K": 5_003.0,   # Long Island
}
# Total: ~31,471 MW

# Default renewable capacity factors (constant; overridden by HOURLY_CF_CSV)
DEFAULT_CF = {"Wind": 0.30, "Solar": 0.10, "Hydro": 0.50}

# ---------------------------------------------------------------------------
# DC tie / interconnection injections (fixed MW imports)
#
# NYISO imports from: HQ (Zone D), PJM (Zones A, F, G, J), ISO-NE (Zones K, F)
# These are rough annual average scheduled interchanges.
# Positive = import into NYISO (reduces load at boundary bus).
# ---------------------------------------------------------------------------
DC_TIES = [
    # (search_keyword_in_SubName, import_MW, fallback_zone)
    ("CHATEAUGUAY",   1000.0, "D"),   # Hydro-Quebec → Zone D (HVDC)
    ("MASSENA",        200.0, "D"),   # HQ Phase II → Zone D
    ("NIAGARA",        500.0, "A"),   # Ontario → Zone A
    ("RAMAPO",         600.0, "G"),   # PJM → Zone G (Ramapo tie)
    ("LINDEN",         300.0, "J"),   # PJM → Zone J (Linden VFT)
    ("NORTHPORT",      100.0, "K"),   # ISO-NE → Zone K (Cross Sound Cable)
]


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Step 1: Apply branch rating modifications
# ---------------------------------------------------------------------------
print(f"=== NYISO SCED — {SCED_DATE_STR} (tag: {EXPERIMENT_TAG}) ===")
print(f"  Solver: {'Gurobi' if USE_GUROBI else 'CBC'}")

branch_path = SRC_DIR / "branch.csv"
if not branch_path.exists():
    # Copy from build output if running on cluster
    import shutil
    src = DATA / "sced_inputs" / "SourceData" / "branch.csv"
    if src.exists():
        shutil.copy(src, branch_path)
        for f in ("bus.csv", "gen.csv", "init_state.csv", "storage.csv"):
            sf = DATA / "sced_inputs" / "SourceData" / f
            if sf.exists():
                shutil.copy(sf, SRC_DIR / f)

branch = pd.read_csv(branch_path)
print(f"\nStep 1: Branch ratings ({len(branch)} branches)")

if BRANCH_SCALE != 1.0:
    if BRANCH_SCALE == 0:
        branch["Cont Rating"] = 999_999.0
        print(f"  BRANCH_SCALE=0 → all branches unconstrained")
    else:
        branch["Cont Rating"] *= BRANCH_SCALE
        print(f"  BRANCH_SCALE={BRANCH_SCALE} applied")

branch.to_csv(branch_path, index=False)

# ---------------------------------------------------------------------------
# Step 2: Distribute zonal load to buses
# ---------------------------------------------------------------------------
print("\nStep 2: Load distribution")

bus_path = SRC_DIR / "bus.csv"
bus = pd.read_csv(bus_path)

# Census 2020 NY county population for weighting
# (top counties only — the rest get equal weight)
NY_COUNTY_POP = {
    "Kings": 2736074, "Queens": 2405464, "New York": 1694251,
    "Suffolk": 1525920, "Bronx": 1472654, "Nassau": 1395774,
    "Westchester": 1004457, "Erie": 954236, "Monroe": 759443,
    "Richmond": 495747, "Onondaga": 476516, "Orange": 401310,
    "Rockland": 338329, "Albany": 314848, "Dutchess": 295911,
    "Saratoga": 235509, "Oneida": 232125, "Niagara": 212666,
    "Broome": 198683, "Ulster": 181851, "Rensselaer": 161130,
    "Schenectady": 158061, "Chautauqua": 127657, "Oswego": 117525,
    "Jefferson": 116721, "Ontario": 112458, "St. Lawrence": 108505,
    "Tompkins": 105740, "Steuben": 95379, "Cattaraugus": 77042,
    "Chemung": 84148, "Livingston": 62914, "Clinton": 79843,
    "Washington": 63216, "Columbia": 61570, "Madison": 68470,
    "Warren": 65737, "Cayuga": 76576, "Herkimer": 61319,
    "Genesee": 58388, "Wayne": 89918, "Putnam": 97714,
    "Sullivan": 78624, "Montgomery": 49532, "Otsego": 59493,
    "Tioga": 48455, "Allegany": 46091, "Greene": 47188,
    "Schoharie": 30999, "Delaware": 44135, "Cortland": 47581,
    "Seneca": 33814, "Chenango": 47220, "Franklin": 50692,
    "Wyoming": 40531, "Orleans": 40343, "Fulton": 53383,
    "Essex": 37381, "Schuyler": 17807, "Lewis": 26296,
    "Yates": 24774, "Hamilton": 4836,
}

# For each bus, find nearest county centroid and get population weight
# Simple approach: use bus lat/lon to assign approximate population weight
# based on zone. Distribute within zone proportional to kV tier
# (higher kV substations serve larger load areas).

# Filter eligible load buses
load_mask = (
    (bus["is_split"].astype(str).str.lower().isin(["false", "0", "false"])) &
    (bus["BaseKV"] >= 100) & (bus["BaseKV"] < 400)
)
if LOAD_NAMED:
    load_mask &= ~bus["Bus Name"].str.startswith("OSM_")

eligible = bus[load_mask].copy()
print(f"  Eligible load buses: {len(eligible)} / {len(bus)}")

# Assign load proportionally within each zone
# Weight: BaseKV^1.5 as proxy (larger substations serve more load)
eligible["_weight"] = eligible["BaseKV"].astype(float) ** 1.5

bus["MW Load"] = 0.0

for zone, zone_mw in ZONE_LOAD_MW.items():
    zone_buses = eligible[eligible["Zone"] == zone]
    if len(zone_buses) == 0:
        print(f"  WARNING: No eligible buses in zone {zone}, skipping {zone_mw:.0f} MW")
        continue
    total_weight = zone_buses["_weight"].sum()
    if total_weight == 0:
        continue
    for idx in zone_buses.index:
        frac = zone_buses.loc[idx, "_weight"] / total_weight
        bus.loc[idx, "MW Load"] = round(zone_mw * frac, 2)

total_load = bus["MW Load"].sum()
print(f"  Total load distributed: {total_load:,.0f} MW")

# Apply DC tie injections
print("  Applying DC tie injections...")
sub_name_col = bus["Sub Name"].str.upper()
for keyword, import_mw, fallback_zone in DC_TIES:
    matches = bus.index[sub_name_col.str.contains(keyword.upper(), regex=False, na=False)]
    if len(matches) == 0:
        # Fallback: nearest bus in the fallback zone
        zone_buses = bus[bus["Zone"] == fallback_zone]
        if len(zone_buses) > 0:
            matches = zone_buses.index[:1]
    if len(matches) > 0:
        idx = matches[0]
        bus.loc[idx, "MW Load"] = float(bus.loc[idx, "MW Load"]) - import_mw
        print(f"    {keyword}: {import_mw:.0f} MW import at bus {bus.loc[idx, 'Bus Name']}")
    else:
        print(f"    {keyword}: no bus found, skipped")

total_net = bus["MW Load"].sum()
print(f"  Net load after ties: {total_net:,.0f} MW")

bus.to_csv(bus_path, index=False)

# ---------------------------------------------------------------------------
# Step 3: Load Vatic and create RealistLoader
# ---------------------------------------------------------------------------
print("\nStep 3: Loading Vatic framework...")

try:
    from vatic.data import GridLoader
    from vatic.engines import Simulator
except ImportError:
    print("ERROR: vatic not installed. Run: pip install vatic")
    print("  Or: pip install pyomo egret")
    sys.exit(1)


class NYISOLoader(GridLoader):
    """NYISO grid loader for Vatic DC-SCED."""

    grid_lbl = "NYISO"
    _data_dir = "SourceData"

    thermal_gen_types = {
        "Nuclear": "N", "Coal": "C", "Gas": "G", "Oil": "O",
        "Biomass": "B",
    }
    renew_gen_types = {"Wind": "W", "Solar": "S", "Hydro": "H"}

    @property
    def data_path(self):
        return SCED_DIR

    @property
    def init_state_file(self):
        return SRC_DIR / "init_state.csv"

    @property
    def utc_offset(self):
        return -pd.Timedelta(hours=5)  # EST = UTC-5

    @property
    def timeseries_cohorts(self):
        return {"Wind", "Solar", "Hydro"}

    @staticmethod
    def get_dispatch_types(renew_types):
        return {
            "DispatchRenewables": renew_types,
            "NondispatchRenewables": {},
            "ForecastRenewables": renew_types,
        }

    @staticmethod
    def process_actuals(actuals_file, start_date, end_date):
        return pd.DataFrame()

    @staticmethod
    def must_gen_run(gen):
        return gen.Fuel == "Nuclear"

    def get_generator_type(self, gen_uid):
        fuel = self._gen_df.loc[
            self._gen_df["GEN UID"] == gen_uid, "Fuel"
        ].iloc[0]
        if fuel == "Wind":
            return "WIND"
        elif fuel == "Solar":
            return "PV"
        elif fuel == "Hydro":
            return "HYDRO"
        return "G"

    def get_generator_zone(self, gen_uid):
        bus_id = self._gen_df.loc[
            self._gen_df["GEN UID"] == gen_uid, "Bus ID"
        ].iloc[0]
        zone = self._bus_df.loc[
            self._bus_df["Bus ID"] == bus_id, "Zone"
        ]
        return zone.iloc[0] if len(zone) > 0 else "C"

    def create_timeseries(self, start_date=None, end_date=None):
        """Build 48-hour timeseries for generators and loads."""
        gen = self._gen_df
        bus_df = self._bus_df

        # Load hourly CF if provided
        hourly_cf = {}
        if HOURLY_CF:
            cf_df = pd.read_csv(HOURLY_CF)
            for fuel in ("Wind", "Solar", "Hydro"):
                if fuel in cf_df.columns:
                    hourly_cf[fuel] = cf_df[fuel].tolist()[:24]

        # Load hourly zonal load if provided
        hourly_zone_load = {}
        if HOURLY_LOAD:
            load_df = pd.read_csv(HOURLY_LOAD)
            for zone in ZONE_LOAD_MW:
                col = f"Zone_{zone}" if f"Zone_{zone}" in load_df.columns else zone
                if col in load_df.columns:
                    hourly_zone_load[zone] = load_df[col].tolist()[:24]

        # --- Generator timeseries ---
        hours_48 = list(range(48))
        dt_base = pd.Timestamp(SCED_DATE)
        dt_index = pd.DatetimeIndex([dt_base + pd.Timedelta(hours=h) for h in hours_48])

        gen_data = {}
        for _, g in gen.iterrows():
            uid = g["GEN UID"]
            fuel = g["Fuel"]
            pmax = float(g["PMax MW"])

            if fuel in ("Wind", "Solar", "Hydro"):
                if fuel in hourly_cf:
                    cf_24 = hourly_cf[fuel]
                    vals = [pmax * cf_24[h % 24] for h in hours_48]
                else:
                    cf = DEFAULT_CF.get(fuel, 0.3)
                    vals = [pmax * cf] * 48
            else:
                vals = [pmax] * 48

            gen_data[uid] = vals

        gen_df = pd.DataFrame(gen_data, index=dt_index)
        # Multi-level columns: (tag, asset)
        gen_df.columns = pd.MultiIndex.from_tuples(
            [("fcst", c) for c in gen_df.columns]
        )
        # Add "actl" = same as fcst
        actl_df = gen_df.copy()
        actl_df.columns = pd.MultiIndex.from_tuples(
            [("actl", c[1]) for c in actl_df.columns]
        )
        gen_df = pd.concat([gen_df, actl_df], axis=1)

        # --- Load timeseries ---
        load_data = {}
        for _, b in bus_df.iterrows():
            bus_name = b["Bus Name"]
            ref_mw = float(b["MW Load"])
            zone = b["Zone"]

            if zone in hourly_zone_load and ref_mw != 0:
                ref_zone_mw = ZONE_LOAD_MW.get(zone, 1)
                hourly = hourly_zone_load[zone]
                vals = [ref_mw * (hourly[h % 24] / ref_zone_mw) for h in hours_48]
            else:
                vals = [ref_mw] * 48

            load_data[bus_name] = vals

        load_df = pd.DataFrame(load_data, index=dt_index)
        load_df.columns = pd.MultiIndex.from_tuples(
            [("fcst", c) for c in load_df.columns]
        )
        actl_load = load_df.copy()
        actl_load.columns = pd.MultiIndex.from_tuples(
            [("actl", c[1]) for c in actl_load.columns]
        )
        load_df = pd.concat([load_df, actl_load], axis=1)

        return gen_df, load_df


# ---------------------------------------------------------------------------
# Step 4: Instantiate loader
# ---------------------------------------------------------------------------
print("\nStep 4: Building RealistLoader template...")

loader = NYISOLoader()
loader._gen_df = pd.read_csv(SRC_DIR / "gen.csv")
loader._bus_df = pd.read_csv(bus_path)

gen_df, load_df = loader.create_timeseries()
print(f"  Generator timeseries: {gen_df.shape}")
print(f"  Load timeseries:      {load_df.shape}")

# ---------------------------------------------------------------------------
# Step 4b: Storage injection
# ---------------------------------------------------------------------------
storage_path = SRC_DIR / "storage.csv"
if storage_path.exists():
    print("\nStep 4b: Loading storage...")
    stor_df = pd.read_csv(storage_path)
    print(f"  {len(stor_df)} storage units, {stor_df['Discharge Rate MW'].sum():,.0f} MW total")

    # Bus name lookup
    bus_name_map = loader._bus_df.set_index("Bus ID")["Bus Name"].to_dict()
    bus_zone_map = loader._bus_df.set_index("Bus ID")["Zone"].to_dict()

    # Aggregation
    if STORAGE_AGG == "zone":
        agg = defaultdict(lambda: {
            "discharge": 0, "charge": 0, "energy": 0,
            "soc": 0, "eff_wt": 0, "bus_id": None, "max_disch": 0
        })
        for _, s in stor_df.iterrows():
            bid = int(s["Bus ID"])
            zone = bus_zone_map.get(bid, "C")
            d = float(s["Discharge Rate MW"])
            agg[zone]["discharge"] += d
            agg[zone]["charge"] += float(s["Charge Rate MW"])
            agg[zone]["energy"] += float(s["Energy Capacity MWh"])
            agg[zone]["soc"] += float(s["Initial SOC MWh"])
            agg[zone]["eff_wt"] += d * float(s.get("Charge Efficiency", 0.96))
            if d > agg[zone]["max_disch"]:
                agg[zone]["max_disch"] = d
                agg[zone]["bus_id"] = bid

        storage_elements = {}
        for zone, a in agg.items():
            if a["discharge"] == 0:
                continue
            bus_id = a["bus_id"]
            bname = bus_name_map.get(bus_id, f"Bus_{bus_id}")
            eff = a["eff_wt"] / a["discharge"] if a["discharge"] else 0.96
            storage_elements[f"BESS_{zone}"] = {
                "bus": bname,
                "min_discharge_rate": 0.0,
                "max_discharge_rate": a["discharge"],
                "min_charge_rate": 0.0,
                "max_charge_rate": a["charge"],
                "energy_capacity": a["energy"],
                "initial_state_of_charge": a["soc"] / a["energy"] if a["energy"] else 0.5,
                "charge_efficiency": round(eff, 4),
                "discharge_efficiency": round(eff, 4),
                "discharge_efficienty": round(eff, 4),
                "initial_status": 1,
                "ramp_up_output_60min": a["discharge"],
                "ramp_down_output_60min": a["discharge"],
                "ramp_up_input_60min": a["charge"],
                "ramp_down_input_60min": a["charge"],
            }
        print(f"  Aggregated to {len(storage_elements)} zone-level BESS units")
        for uid, se in storage_elements.items():
            print(f"    {uid}: {se['max_discharge_rate']:.0f} MW @ {se['bus']}")
    else:
        storage_elements = {}
        print(f"  Storage aggregation '{STORAGE_AGG}' — {len(stor_df)} individual units")
else:
    storage_elements = {}
    print("\nNo storage.csv found, skipping storage.")

# ---------------------------------------------------------------------------
# Step 5: Run Vatic Simulator
# ---------------------------------------------------------------------------
print(f"\nStep 5: Running Vatic SCED (date={SCED_DATE_STR})...")

solver = "gurobi" if USE_GUROBI else "cbc"
solver_opts = {"Threads": THREADS} if USE_GUROBI else {}

try:
    sim = Simulator(
        template_data=loader.template,
        gen_data=gen_df,
        load_data=load_df,
        out_dir=RES_DIR,
        start_date=SCED_DATE,
        num_days=1,
        solver=solver,
        solver_options=solver_opts,
        run_lmps=True,
        mipgap=0.01,
        load_shed_penalty=1e4,
        reserve_shortfall_penalty=1e3,
        reserve_factor=0.05,
        output_detail=3,
        prescient_sced_forecasts=False,
        ruc_prescience_hour=0,
        ruc_execution_hour=16,
        ruc_every_hours=24,
        ruc_horizon=24,
        sced_horizon=1,
        lmp_shortfall_costs=False,
        enforce_sced_shutdown_ramprate=False,
        no_startup_shutdown_curves=False,
        init_ruc_file=None,
        verbosity=1,
        output_max_decimals=4,
        create_plots=False,
        renew_costs=None,
        save_to_csv=True,
        last_conditions_file=None,
    )

    # Inject storage if present
    if storage_elements:
        from vatic.data import PickleProvider
        _orig_create = PickleProvider.create_vatic_model_dict

        def _patched_create(self, *args, **kwargs):
            md = _orig_create(self, *args, **kwargs)
            bus_dict = md.data.get("elements", {}).get("bus", {})
            for uid, se in storage_elements.items():
                if se["bus"] in bus_dict:
                    if "storage" not in md.data["elements"]:
                        md.data["elements"]["storage"] = {}
                    md.data["elements"]["storage"][uid] = se
            return md

        PickleProvider.create_vatic_model_dict = _patched_create
        print(f"  Storage injected: {len(storage_elements)} units")

    sim.simulate()
    print(f"\nResults written to: {RES_DIR}")

except Exception as e:
    print(f"\nSCED FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 6: Quick summary
# ---------------------------------------------------------------------------
print("\n=== Quick Summary ===")
summary_files = list(RES_DIR.glob("*hourly*summary*"))
if summary_files:
    summary = pd.read_csv(summary_files[0])
    print(summary.to_string(index=False))
else:
    print("  No hourly summary found — check results directory")
