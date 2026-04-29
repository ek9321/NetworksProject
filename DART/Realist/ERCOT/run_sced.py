#!/usr/bin/env python3
"""
Step 8 — Load, distribute demand, run Vatic DC-SCED for 2025-11-05.

RealistLoader subclasses GridLoader from Birchfield/vatic and provides
constant 24-hour timeseries for each bus (load) and renewable generator.

Load distribution:
  Fallback zonal MW for 2025-11-05 17:00 CST:
    NORTH   23,000 MW
    HOUSTON 11,500 MW
    SOUTH   10,500 MW
    WEST     7,000 MW
  Distributed proportional to Census 2020 county population.
  Each bus is assigned to its nearest Texas county centroid (haversine).
  Zone MW is split among buses weighted by their county's population.

DC tie fixed injections (net imports, added as negative MW Load on nearest bus).

Output: sced_inputs/results/  (Vatic CSV output)
"""

import sys
import math
import datetime
from pathlib import Path
from collections import defaultdict

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
import os

if os.environ.get("DARTBOARD_SCRATCH"):
    # Running on cluster: vatic is installed in the conda env as a package;
    # no sys.path injection needed.
    SCRATCH  = Path(os.environ["DARTBOARD_SCRATCH"])
    instance = os.environ.get("SCED_INSTANCE", "")
    SCED_DIR = SCRATCH / (f"sced_inputs_{instance}" if instance else "sced_inputs")
    SOLVER   = "gurobi"
    SOLVER_OPTIONS = {"Threads": int(os.environ.get("SLURM_CPUS_PER_TASK", 8))}
else:
    # Running locally: load vatic from repo
    REPO     = Path(__file__).resolve().parents[2]
    SCED_DIR = REPO / "Realist" / "grid_data" / "sced_inputs"
    sys.path.insert(0, str(REPO / "Realist"))
    SOLVER   = "cbc"
    SOLVER_OPTIONS = {}

tag     = os.environ.get("EXPERIMENT_TAG", "")
SRC_DIR = SCED_DIR / "SourceData"
RES_DIR = SCED_DIR / (f"results_{tag}" if tag else "results")
RES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Branch scaling: BRANCH_SCALE env var
#   unset or "1"  → no change (baseline)
#   "0"           → remove all limits (set Cont Rating to 999999 MVA)
#   "2.0"         → double all ratings, etc.
# Applied before RealistLoader reads branch.csv.
# ---------------------------------------------------------------------------
_branch_scale_raw = os.environ.get("BRANCH_SCALE", "1")
_branch_scale = float(_branch_scale_raw)
_branch_csv   = SRC_DIR / "branch.csv"

if _branch_scale != 1.0 and _branch_csv.exists():
    _br = pd.read_csv(_branch_csv)
    if "Cont Rating" in _br.columns:
        if _branch_scale == 0.0:
            _br["Cont Rating"] = 999_999.0
            print(f"BRANCH_SCALE=0 → all Cont Ratings set to 999,999 MVA (floor case)")
        else:
            _br["Cont Rating"] = (_br["Cont Rating"] * _branch_scale).round(2)
            print(f"BRANCH_SCALE={_branch_scale} → all Cont Ratings scaled by {_branch_scale}x")
        _br.to_csv(_branch_csv, index=False)

# ---------------------------------------------------------------------------
# SPL cap removal: NO_SPL_CAP env var
#   "1" → set Cont Rating to 999,999 MVA on any branch whose From Bus or To Bus
#         is a synthetic split point (is_split = True in bus.csv).
# Applied after BRANCH_SCALE, before RealistLoader reads branch.csv.
# ---------------------------------------------------------------------------
if os.environ.get("NO_SPL_CAP", "0") == "1" and _branch_csv.exists():
    _bus_csv = SRC_DIR / "bus.csv"
    _bus_df  = pd.read_csv(_bus_csv, dtype=str)
    _split_ids = set(
        _bus_df.loc[
            _bus_df["is_split"].str.lower().isin(["true", "1"]), "Bus ID"
        ].astype(int)
    )
    _br2 = pd.read_csv(_branch_csv)
    _spl_mask = (
        _br2["From Bus"].astype(int).isin(_split_ids) |
        _br2["To Bus"].astype(int).isin(_split_ids)
    )
    _br2.loc[_spl_mask, "Cont Rating"] = 999_999.0
    _br2.to_csv(_branch_csv, index=False)
    print(f"NO_SPL_CAP=1 → {_spl_mask.sum()} SPL-connected branches set to 999,999 MVA "
          f"({(~_spl_mask).sum()} real-substation branches unchanged)")

# ---------------------------------------------------------------------------
# NO_PLANT_CAP env var: unconstrain plant outlet and bus-section stubs
#   "1" → set Cont Rating to 999,999 MVA on branches that are either:
#     (a) one endpoint Bus Name contains "_Plant" (generation plant outlets), or
#     (b) haversine distance between endpoints < 0.5 km (bus sections / stubs).
#   Physical justification: plant outlet stubs are constrained by the generator's
#   own output limit in gen.csv, not by the wire rating.  Bus sections are
#   switching paths whose thermal limit is set by connected equipment, not the
#   branch itself.
# ---------------------------------------------------------------------------
if os.environ.get("NO_PLANT_CAP", "0") == "1" and _branch_csv.exists():
    _bus_csv2 = SRC_DIR / "bus.csv"
    _bus_df2  = pd.read_csv(_bus_csv2, dtype=str)
    _bus_df2["Bus ID"] = _bus_df2["Bus ID"].astype(int)
    _bus_df2["_lat"]   = pd.to_numeric(_bus_df2["lat"],  errors="coerce")
    _bus_df2["_lng"]   = pd.to_numeric(_bus_df2["lng"],  errors="coerce")
    _bus_pos   = _bus_df2.set_index("Bus ID")[["Bus Name","_lat","_lng"]].to_dict("index")

    _br_plant = pd.read_csv(_branch_csv)

    def _hav_km(r):
        import math
        fi = _bus_pos.get(int(r["From Bus"]), {}); ti = _bus_pos.get(int(r["To Bus"]), {})
        if not fi or not ti: return 999.0
        dlat = math.radians(ti["_lat"] - fi["_lat"])
        dlon = math.radians(ti["_lng"] - fi["_lng"])
        a = math.sin(dlat/2)**2 + math.cos(math.radians(fi["_lat"])) * math.cos(math.radians(ti["_lat"])) * math.sin(dlon/2)**2
        return 6371.0 * 2 * math.asin(math.sqrt(a))

    _from_names = _br_plant["From Bus"].astype(int).map(lambda b: _bus_pos.get(b, {}).get("Bus Name", ""))
    _to_names   = _br_plant["To Bus"].astype(int).map(lambda b: _bus_pos.get(b, {}).get("Bus Name", ""))
    _plant_mask = _from_names.str.contains("_Plant", case=False, na=False) | \
                  _to_names.str.contains("_Plant", case=False, na=False)
    _dist_km    = _br_plant.apply(_hav_km, axis=1)
    _stub_mask  = _dist_km < 0.5
    _outlet_mask = (_plant_mask | _stub_mask) & (_br_plant["Cont Rating"] < 999_000)
    _br_plant.loc[_outlet_mask, "Cont Rating"] = 999_999.0
    _br_plant.to_csv(_branch_csv, index=False)
    print(f"NO_PLANT_CAP=1 → {_outlet_mask.sum()} plant outlet/stub branches unconstrained "
          f"({_plant_mask.sum()} _Plant endpoints, {_stub_mask.sum()} stubs <0.5 km)")

# ---------------------------------------------------------------------------
# SCALE_345KV env var: scale 345 kV+ real-substation branch ratings
#   "2.0" → double all Cont Ratings >= 1,000 MVA and < 999,000 MVA
#   (Applied after NO_SPL_CAP so unconstrained SPL branches are not scaled.)
# ---------------------------------------------------------------------------
_scale_345kv_raw = os.environ.get("SCALE_345KV", "")
if _scale_345kv_raw and _branch_csv.exists():
    _scale_345kv = float(_scale_345kv_raw)
    _br3 = pd.read_csv(_branch_csv)
    _hv_mask = (_br3["Cont Rating"] >= 1_000) & (_br3["Cont Rating"] < 999_000)
    _br3.loc[_hv_mask, "Cont Rating"] = (_br3.loc[_hv_mask, "Cont Rating"] * _scale_345kv).round(2)
    _br3.to_csv(_branch_csv, index=False)
    print(f"SCALE_345KV={_scale_345kv} → {_hv_mask.sum()} 345 kV+ branches scaled "
          f"(min now {_br3.loc[_hv_mask,'Cont Rating'].min():.0f} MVA, "
          f"max {_br3.loc[_hv_mask,'Cont Rating'].max():.0f} MVA)")

# ---------------------------------------------------------------------------
# SCALE_138KV env var: scale 138 kV branch ratings
#   "2.0" → double all Cont Ratings in [100, 1000) MVA and < 999,000 MVA
#   (Applied after NO_SPL_CAP so unconstrained SPL branches are not scaled.)
# ---------------------------------------------------------------------------
_scale_138kv_raw = os.environ.get("SCALE_138KV", "")
if _scale_138kv_raw and _branch_csv.exists():
    _scale_138kv = float(_scale_138kv_raw)
    _br4 = pd.read_csv(_branch_csv)
    _lv_mask = (_br4["Cont Rating"] >= 100) & (_br4["Cont Rating"] < 1_000) & (_br4["Cont Rating"] < 999_000)
    _br4.loc[_lv_mask, "Cont Rating"] = (_br4.loc[_lv_mask, "Cont Rating"] * _scale_138kv).round(2)
    _br4.to_csv(_branch_csv, index=False)
    print(f"SCALE_138KV={_scale_138kv} → {_lv_mask.sum()} 138 kV branches scaled "
          f"(min now {_br4.loc[_lv_mask,'Cont Rating'].min():.0f} MVA, "
          f"max {_br4.loc[_lv_mask,'Cont Rating'].max():.0f} MVA)")

# ---------------------------------------------------------------------------
# UPGRADE_LINES env var: comma-separated list of branch UIDs to double (250→500).
#   Targeted upgrade for specific binding lines identified from SCED results.
# ---------------------------------------------------------------------------
_upgrade_raw = os.environ.get("UPGRADE_LINES", "")
if _upgrade_raw and _branch_csv.exists():
    _upgrade_uids = [u.strip() for u in _upgrade_raw.split(",") if u.strip()]
    _br5 = pd.read_csv(_branch_csv)
    _up_mask = _br5["UID"].isin(_upgrade_uids) & (_br5["Cont Rating"] < 999_000)
    _br5.loc[_up_mask, "Cont Rating"] = (_br5.loc[_up_mask, "Cont Rating"] * 2).round(2)
    _br5.to_csv(_branch_csv, index=False)
    print(f"UPGRADE_LINES → {_up_mask.sum()} branches doubled "
          f"(of {len(_upgrade_uids)} requested)")

# ---------------------------------------------------------------------------
# FLOOR_RATINGS_CSV env var: path to CSV with columns (UID, MinRating).
#   For each line, sets Cont Rating = max(current_rating, MinRating).
#   Generated from a floor run's line_detail.csv: min_rating = min(max_flow × 1.1, 800).
# ---------------------------------------------------------------------------
_floor_csv = os.environ.get("FLOOR_RATINGS_CSV", "")
if _floor_csv and os.path.exists(_floor_csv) and _branch_csv.exists():
    _floor_df = pd.read_csv(_floor_csv)
    _floor_map = dict(zip(_floor_df["UID"], _floor_df["MinRating"]))
    _br6 = pd.read_csv(_branch_csv)
    _n_raised = 0
    for idx, row in _br6.iterrows():
        uid = row["UID"]
        if uid in _floor_map and row["Cont Rating"] < 999_000:
            new_r = max(row["Cont Rating"], _floor_map[uid])
            if new_r > row["Cont Rating"]:
                _br6.at[idx, "Cont Rating"] = round(new_r, 2)
                _n_raised += 1
    _br6.to_csv(_branch_csv, index=False)
    print(f"FLOOR_RATINGS_CSV → {_n_raised} branches raised "
          f"(of {len(_floor_map)} in CSV)")

from vatic.data.loaders import GridLoader
from vatic.engines import Simulator

# ---------------------------------------------------------------------------
# Simulation date: SCED_DATE env var (default 2025-11-05)
# Used for timeseries timestamps and Simulator start_date.
# ---------------------------------------------------------------------------
import datetime as _dt_mod
_sced_date_raw = os.environ.get("SCED_DATE", "2025-11-05")
SCED_DATE = _dt_mod.date.fromisoformat(_sced_date_raw)

# ---------------------------------------------------------------------------
# Zone load (MW) — fallback constants when HOURLY_LOAD_CSV is not provided.
# Used as the reference totals for spatial distribution in distribute_load().
# ---------------------------------------------------------------------------
ZONE_LOAD_MW = {
    "NORTH":   23_000.0,
    "HOUSTON": 11_500.0,
    "SOUTH":   10_500.0,
    "WEST":     7_000.0,
}

# ---------------------------------------------------------------------------
# HOURLY_LOAD_CSV env var: path to CSV with columns
#   hour (0-23 int), NORTH, HOUSTON, SOUTH, WEST (MW float)
# If provided, create_timeseries() builds per-bus hourly load profiles by
# scaling each bus's reference MW Load by (hourly_zone_mw / ref_zone_mw).
# ---------------------------------------------------------------------------
_hourly_load_csv_path = os.environ.get("HOURLY_LOAD_CSV", "")
HOURLY_ZONE_LOAD = None   # dict: zone -> list[float] of 24 values (MW)
if _hourly_load_csv_path and Path(_hourly_load_csv_path).exists():
    _hl_df = pd.read_csv(_hourly_load_csv_path)
    _hl_df = _hl_df.sort_values("hour").reset_index(drop=True)
    HOURLY_ZONE_LOAD = {z: _hl_df[z].tolist() for z in ["NORTH", "HOUSTON", "SOUTH", "WEST"]}
    print(f"HOURLY_LOAD_CSV: loaded 24-hour zonal load profile from {_hourly_load_csv_path}")
    for z in ["NORTH", "HOUSTON", "SOUTH", "WEST"]:
        print(f"  {z}: min={min(HOURLY_ZONE_LOAD[z]):.0f} MW  max={max(HOURLY_ZONE_LOAD[z]):.0f} MW")

# ---------------------------------------------------------------------------
# LOAD_SCALE env var: uniform multiplier applied to all zone loads.
# Used for stress-test / floor scenarios (e.g., 1.10 = +10% load).
# Applied to both HOURLY_ZONE_LOAD and static ZONE_LOAD_MW.
# ---------------------------------------------------------------------------
LOAD_SCALE = float(os.environ.get("LOAD_SCALE", "1.0"))
if LOAD_SCALE != 1.0:
    print(f"LOAD_SCALE={LOAD_SCALE:.4f} — scaling all zone loads")
    for z in ZONE_LOAD_MW:
        ZONE_LOAD_MW[z] *= LOAD_SCALE
    if HOURLY_ZONE_LOAD is not None:
        for z in HOURLY_ZONE_LOAD:
            HOURLY_ZONE_LOAD[z] = [v * LOAD_SCALE for v in HOURLY_ZONE_LOAD[z]]

# ---------------------------------------------------------------------------
# HOURLY_CF_CSV env var: path to CSV with columns
#   hour (0-23 int), Wind (fraction 0-1), Solar (fraction 0-1)
# If provided, each renewable generator's PMax timeseries is scaled by the
# hourly CF for its fuel type.  Solar CF = 0.0 during nighttime hours.
# When HOURLY_CF_CSV is not provided, DEFAULT_CF is used as a flat constant.
# PMax in gen.csv is nameplate capacity; CF is the only scaling applied here.
# ---------------------------------------------------------------------------
DEFAULT_CF = {"Wind": 0.45, "Solar": 0.05}

_hourly_cf_csv_path = os.environ.get("HOURLY_CF_CSV", "")
HOURLY_CF = None   # dict: fuel -> list[float] of 24 values (fraction 0-1)
if _hourly_cf_csv_path and Path(_hourly_cf_csv_path).exists():
    _hc_df = pd.read_csv(_hourly_cf_csv_path)
    _hc_df = _hc_df.sort_values("hour").reset_index(drop=True)
    HOURLY_CF = {"Wind": _hc_df["Wind"].tolist(), "Solar": _hc_df["Solar"].tolist()}
    print(f"HOURLY_CF_CSV: loaded 24-hour wind/solar CF profile from {_hourly_cf_csv_path}")
    print(f"  Wind:  min={min(HOURLY_CF['Wind']):.3f}  max={max(HOURLY_CF['Wind']):.3f}")
    print(f"  Solar: min={min(HOURLY_CF['Solar']):.3f}  max={max(HOURLY_CF['Solar']):.3f}")

# DC tie fixed injections (MW, positive = import to ERCOT)
# Modelled as negative MW Load adjustments on the nearest bus.
DC_TIES = [
    ("OKLAUNION",  220.0),   # DC_N  (SPP interconnect, Oklaunion substation)
    ("MONTICELLO", 600.0),   # DC_E  (SPP/SWEPCO, Monticello substation)
    ("EAGLE",       36.0),   # Eagle Pass (CFE) — nearest SOUTH bus
    ("MCALLEN",    150.0),   # McAllen (CFE)   — nearest SOUTH bus
    ("LAREDO",     100.0),   # Laredo VFT (CFE)— nearest SOUTH bus
]

# ---------------------------------------------------------------------------
# Nodal-RUC proxy: must-run thermal units in import-constrained zones.
#
# Real ERCOT runs a nodal SCUC that sees transmission constraints in the
# commitment decision and keeps local generation committed in zones that
# can't import enough.  Our Vatic RUC is system-wide and doesn't see
# transmission constraints, so it decommits expensive local units even when
# the zone needs them.
#
# Fix: compute peak hourly demand per zone from HOURLY_ZONE_LOAD.  Compare
# to local thermal nameplate from gen.csv.  In zones where peak demand
# exceeds local thermal capacity (meaning the zone MUST import even with
# all local units online), flag all thermal units >= MUST_RUN_MIN_MW as
# must-run.  This keeps them committed but still dispatches them
# economically — they run at PMin overnight and ramp up during peak.
# The 345 kV corridors still bind and create realistic congestion pricing.
#
# MUST_RUN_MIN_MW env var: minimum unit size to flag (default 100 MW).
# Set to 0 to disable must-run (revert to system-wide RUC only).
# ---------------------------------------------------------------------------

_MUST_RUN_MIN_MW = float(os.environ.get("MUST_RUN_MIN_MW", "100"))
_MUST_RUN_UIDS: set = set()

_gen_csv_path = SRC_DIR / "gen.csv"
_bus_csv_path = SRC_DIR / "bus.csv"
if _MUST_RUN_MIN_MW > 0 and _gen_csv_path.exists():
    _mr_gen = pd.read_csv(_gen_csv_path)
    _mr_bus = pd.read_csv(_bus_csv_path, dtype=str) if _bus_csv_path.exists() else pd.DataFrame()

    if not _mr_bus.empty and "Zone" in _mr_bus.columns:
        _mr_bus_zone = dict(zip(
            pd.to_numeric(_mr_bus["Bus ID"], errors="coerce").astype(int),
            _mr_bus["Zone"]))
        _mr_gen["_zone"] = _mr_gen["Bus ID"].map(_mr_bus_zone)

        # Peak demand per zone (from hourly load or static fallback)
        _mr_peak = {}
        for z in ["NORTH", "HOUSTON", "SOUTH", "WEST"]:
            if HOURLY_ZONE_LOAD is not None:
                _mr_peak[z] = max(HOURLY_ZONE_LOAD[z])
            else:
                _mr_peak[z] = ZONE_LOAD_MW.get(z, 0)

        # Local thermal nameplate per zone (Gas + Coal only, not Wind/Solar/Nuclear)
        _mr_thermal = _mr_gen[_mr_gen["Fuel"].isin(["Gas", "Coal"])]
        _mr_local_cap = _mr_thermal.groupby("_zone")["PMax MW"].sum().to_dict()

        # Estimate renewable output at peak hour to avoid flagging
        # wind-surplus zones (like WEST).  Use min CF as conservative
        # estimate — if renewables cover the deficit even at low output,
        # the zone doesn't need must-runs.
        _mr_renew = _mr_gen[_mr_gen["Fuel"].isin(["Wind", "Solar"])]
        _mr_renew_cap = {}
        for z in ["NORTH", "HOUSTON", "SOUTH", "WEST"]:
            wind_mw = _mr_renew.loc[
                (_mr_renew["_zone"] == z) & (_mr_renew["Fuel"] == "Wind"), "PMax MW"
            ].sum()
            solar_mw = _mr_renew.loc[
                (_mr_renew["_zone"] == z) & (_mr_renew["Fuel"] == "Solar"), "PMax MW"
            ].sum()
            # Use conservative CFs: min hourly CF if available, else low defaults
            if HOURLY_CF is not None:
                w_cf = min(HOURLY_CF["Wind"])
                s_cf = min(c for c in HOURLY_CF["Solar"] if c > 0) if any(
                    c > 0 for c in HOURLY_CF["Solar"]) else 0.0
            else:
                w_cf = DEFAULT_CF.get("Wind", 0.2)
                s_cf = 0.05
            _mr_renew_cap[z] = wind_mw * w_cf + solar_mw * s_cf

        # Flag must-run only in zones with a large import dependency.
        # A nodal RUC would keep local units committed when it sees that
        # transmission corridors into the zone will saturate.  We proxy
        # this by flagging zones where peak demand exceeds local thermal
        # by > 20% — meaning the zone relies heavily on imports and can't
        # afford to decommit local generation.  Within those zones, flag
        # the largest units first, just enough to close the gap between
        # local thermal and peak demand (so corridors aren't overloaded).
        _MR_DEFICIT_THRESHOLD = 0.20   # 20% — only flag heavily import-dependent zones
        _mr_flagged_zones = []
        for z in ["NORTH", "HOUSTON", "SOUTH", "WEST"]:
            peak = _mr_peak.get(z, 0)
            local = _mr_local_cap.get(z, 0) + _mr_renew_cap.get(z, 0)
            if local <= 0 or peak <= 0:
                continue
            deficit_frac = (peak - local) / local
            if deficit_frac > _MR_DEFICIT_THRESHOLD:
                # Zone is heavily import-dependent — flag largest units
                zone_units = _mr_thermal[
                    (_mr_thermal["_zone"] == z) &
                    (_mr_thermal["PMax MW"] >= _MUST_RUN_MIN_MW)
                ].sort_values("PMax MW", ascending=False)
                # Flag enough to close gap: need committed ≈ peak - corridor_headroom
                # We don't know exact corridor capacity, so flag all eligible units
                # in this zone — there are typically only 10-30 per zone.
                for uid in zone_units["GEN UID"]:
                    _MUST_RUN_UIDS.add(uid)
                _mr_flagged_zones.append(
                    f"    {z}: peak {peak:.0f} MW, local thermal {local:.0f} MW "
                    f"(deficit {deficit_frac:.0%}) → {len(zone_units)} units must-run")

        if _MUST_RUN_UIDS:
            _mr_total_mw = _mr_thermal[
                _mr_thermal["GEN UID"].isin(_MUST_RUN_UIDS)]["PMax MW"].sum()
            print(f"MUST_RUN (nodal RUC proxy): {len(_MUST_RUN_UIDS)} units, "
                  f"{_mr_total_mw:.0f} MW (threshold {_MUST_RUN_MIN_MW:.0f} MW)")
            for line in _mr_flagged_zones:
                print(line)
        else:
            print(f"MUST_RUN: no deficit zones (all zones have local thermal >= peak demand)")

# ---------------------------------------------------------------------------
# Texas county populations (Census 2020) and approximate centroids (lat, lon)
# 254 counties; used to distribute zone MW proportional to population.
# ---------------------------------------------------------------------------

TEXAS_COUNTY_POP = {
    # county_name: (centroid_lat, centroid_lon, census_2020_pop)
    "Anderson":      (31.82,  -95.65,   57_863),
    "Andrews":       (32.31, -102.64,   18_705),
    "Angelina":      (31.37,  -94.62,   86_771),
    "Aransas":       (28.12,  -97.05,   23_510),
    "Archer":        (33.62,  -98.69,    8_474),
    "Armstrong":     (34.97, -101.36,    1_848),
    "Atascosa":      (28.89,  -98.53,   48_781),
    "Austin":        (29.89,  -96.28,   30_167),
    "Bailey":        (34.07, -102.83,    6_985),
    "Bandera":       (29.75,  -99.25,   21_941),
    "Bastrop":       (30.10,  -97.31,   97_216),
    "Baylor":        (33.62,  -99.22,    3_530),
    "Bee":           (28.42,  -97.74,   32_691),
    "Bell":          (31.05,  -97.48,  362_924),
    "Bexar":         (29.45,  -98.52, 2_009_324),
    "Blanco":        (30.26,  -98.41,   11_279),
    "Borden":        (32.74, -101.43,      641),
    "Bosque":        (31.90,  -97.64,   18_685),
    "Bowie":         (33.44,  -94.16,   94_090),
    "Brazoria":      (29.17,  -95.49,  372_031),
    "Brazos":        (30.66,  -96.30,  229_211),
    "Brewster":      (29.79, -103.25,    9_203),
    "Briscoe":       (34.53, -101.20,    1_546),
    "Brooks":        (27.03,  -98.22,    7_076),
    "Brown":         (31.77,  -99.00,   37_864),
    "Burleson":      (30.49,  -96.61,   18_443),
    "Burnet":        (30.79,  -98.23,   47_597),
    "Caldwell":      (29.83,  -97.62,   45_883),
    "Calhoun":       (28.44,  -96.61,   21_290),
    "Callahan":      (32.30,  -99.37,   13_943),
    "Cameron":       (26.15,  -97.58,  423_163),
    "Camp":          (33.00,  -94.98,   13_094),
    "Carson":        (35.40, -101.35,    5_926),
    "Cass":          (33.07,  -94.34,   30_016),
    "Castro":        (34.53, -102.26,    7_530),
    "Chambers":      (29.71,  -94.63,   45_689),
    "Cherokee":      (31.83,  -95.17,   52_646),
    "Childress":     (34.53, -100.21,    7_306),
    "Clay":          (33.78,  -98.20,   10_303),
    "Cochran":       (33.60, -102.84,    2_547),
    "Coke":          (31.89, -100.52,    3_009),
    "Coleman":       (31.77,  -99.43,    8_547),
    "Collin":        (33.19,  -96.57, 1_064_465),
    "Collingsworth": (34.96, -100.27,    2_920),
    "Colorado":      (29.62,  -96.53,   21_493),
    "Comal":         (29.82,  -98.27,  156_209),
    "Comanche":      (31.95,  -98.56,   13_635),
    "Concho":        (31.32,  -99.74,    2_726),
    "Cooke":         (33.64,  -97.21,   41_071),
    "Coryell":       (31.39,  -97.79,   80_766),
    "Cottle":        (34.08, -100.28,    1_398),
    "Crane":         (31.43, -102.35,    4_797),
    "Crockett":      (30.72, -101.42,    3_405),
    "Crosby":        (33.61, -101.30,    5_737),
    "Culberson":     (31.44, -104.52,    2_163),
    "Dallam":        (36.28, -102.60,    6_703),
    "Dallas":        (32.77,  -96.80, 2_613_539),
    "Dawson":        (32.74, -101.95,   12_547),
    "Deaf Smith":    (34.96, -102.60,   18_546),
    "Delta":         (33.39,  -95.68,    5_331),
    "Denton":        (33.21,  -97.13,  906_422),
    "DeWitt":        (29.09,  -97.35,   20_097),
    "Dickens":       (33.62, -100.79,    2_211),
    "Dimmit":        (28.43,  -99.75,   10_124),
    "Donley":        (34.96, -100.81,    3_278),
    "Duval":         (27.68,  -98.49,   11_157),
    "Eastland":      (32.31,  -98.82,   18_583),
    "Ector":         (31.87, -102.53,  166_223),
    "Edwards":       (29.98, -100.30,    1_932),
    "El Paso":       (31.77, -106.49,  865_657),
    "Ellis":         (32.35,  -96.76,  185_141),
    "Erath":         (32.23,  -98.20,   43_564),
    "Falls":         (31.27,  -96.93,   17_297),
    "Fannin":        (33.59,  -96.11,   36_496),
    "Fayette":       (29.88,  -96.92,   25_066),
    "Fisher":        (32.74, -100.40,    3_848),
    "Floyd":         (33.97, -101.30,    5_728),
    "Foard":         (33.98,  -99.78,    1_186),
    "Fort Bend":     (29.53,  -95.77,  811_688),
    "Franklin":      (33.17,  -95.22,   10_720),
    "Freestone":     (31.70,  -96.15,   19_717),
    "Frio":          (28.87,  -99.11,   20_306),
    "Gaines":        (32.74, -102.63,   22_010),
    "Galveston":     (29.37,  -94.85,  342_139),
    "Garza":         (33.18, -101.30,    6_229),
    "Gillespie":     (30.32,  -98.94,   26_208),
    "Glasscock":     (31.87, -101.52,    1_408),
    "Goliad":        (28.66,  -97.45,    7_658),
    "Gonzales":      (29.46,  -97.49,   20_837),
    "Gray":          (35.40, -100.81,   21_886),
    "Grayson":       (33.62,  -96.68,  136_212),
    "Gregg":         (32.47,  -94.82,  123_945),
    "Grimes":        (30.54,  -95.93,   28_880),
    "Guadalupe":     (29.61,  -97.96,  166_847),
    "Hale":          (34.07, -101.82,   33_406),
    "Hall":          (34.53, -100.68,    2_964),
    "Hamilton":      (31.69,  -98.11,    8_461),
    "Hansford":      (36.28, -101.35,    5_399),
    "Hardeman":      (34.29,  -99.75,    3_801),
    "Hardin":        (30.27,  -94.36,   57_602),
    "Harris":        (29.85,  -95.40, 4_731_145),
    "Harrison":      (32.55,  -94.38,   66_553),
    "Hartley":       (35.84, -102.60,    5_576),
    "Haskell":       (33.18,  -99.73,    5_336),
    "Hays":          (30.06,  -98.03,  246_521),
    "Hemphill":      (35.84, -100.27,    3_819),
    "Henderson":     (32.22,  -95.85,   82_737),
    "Hidalgo":       (26.40,  -98.10,  870_781),
    "Hill":          (31.99,  -97.13,   35_399),
    "Hockley":       (33.61, -102.35,   23_006),
    "Hood":          (32.44,  -97.82,   64_099),
    "Hopkins":       (33.15,  -95.56,   37_084),
    "Houston":       (31.32,  -95.42,   22_968),
    "Howard":        (32.31, -101.44,   36_664),
    "Hudspeth":      (31.46, -105.38,    4_886),
    "Hunt":          (33.13,  -96.09,   99_630),
    "Hutchinson":    (35.84, -101.35,   21_061),
    "Irion":         (31.32, -100.98,    1_536),
    "Jack":          (33.23,  -98.17,    9_003),
    "Jackson":       (28.96,  -96.58,   14_591),
    "Jasper":        (30.72,  -93.99,   35_710),
    "Jeff Davis":    (30.72, -104.12,    2_274),
    "Jefferson":     (30.04,  -94.17,  252_358),
    "Jim Hogg":      (27.06,  -99.08,    5_300),
    "Jim Wells":     (27.73,  -98.08,   40_128),
    "Johnson":       (32.38,  -97.37,  179_685),
    "Jones":         (32.74,  -99.87,   19_891),
    "Karnes":        (28.89,  -97.86,   15_505),
    "Kaufman":       (32.60,  -96.28,  136_154),
    "Kendall":       (29.95,  -98.70,   46_687),
    "Kenedy":        (26.93,  -97.65,      404),
    "Kent":          (33.18, -100.77,      762),
    "Kerr":          (30.06,  -99.34,   53_635),
    "Kimble":        (30.50,  -99.74,    4_472),
    "King":          (33.62, -100.26,      272),
    "Kinney":        (29.35, -100.42,    3_667),
    "Kleberg":       (27.43,  -97.81,   31_549),
    "Knox":          (33.60,  -99.76,    3_664),
    "La Salle":      (28.34,  -99.10,    7_430),
    "Lamar":         (33.67,  -95.54,   49_532),
    "Lamb":          (34.07, -102.35,   13_262),
    "Lampasas":      (31.19,  -98.24,   21_281),
    "Lavaca":        (29.38,  -96.92,   20_154),
    "Lee":           (30.32,  -97.04,   17_239),
    "Leon":          (31.29,  -95.97,   17_151),
    "Liberty":       (30.17,  -94.82,   90_697),
    "Limestone":     (31.54,  -96.59,   23_437),
    "Lipscomb":      (36.28, -100.27,    3_233),
    "Live Oak":      (28.35,  -98.12,   12_207),
    "Llano":         (30.71,  -98.69,   20_860),
    "Loving":        (31.85, -103.59,       64),
    "Lubbock":       (33.61, -101.82,  310_569),
    "Lynn":          (33.18, -101.82,    5_808),
    "Madison":       (30.97,  -95.92,   14_218),
    "Marion":        (33.00,  -94.36,   10_083),
    "Martin":        (32.31, -101.95,    5_771),
    "Mason":         (30.73,  -99.23,    4_274),
    "Matagorda":     (28.79,  -96.01,   36_702),
    "Maverick":      (28.74, -100.31,   57_887),
    "McCulloch":     (31.20,  -99.34,    7_984),
    "McLennan":      (31.55,  -97.17,  262_065),
    "McMullen":      (28.35,  -98.57,      707),
    "Medina":        (29.35,  -99.11,   50_607),
    "Menard":        (30.88,  -99.82,    2_148),
    "Midland":       (32.00, -102.08,  169_895),
    "Milam":         (30.79,  -96.97,   24_823),
    "Mills":         (31.49,  -98.60,    4_873),
    "Mitchell":      (32.31, -100.92,    8_545),
    "Montague":      (33.67,  -97.73,   19_546),
    "Montgomery":    (30.30,  -95.50,  620_443),
    "Moore":         (35.84, -101.89,   21_904),
    "Morris":        (33.11,  -94.71,   12_388),
    "Motley":        (34.07, -100.79,    1_156),
    "Nacogdoches":   (31.62,  -94.65,   64_785),
    "Navarro":       (32.05,  -96.47,   50_125),
    "Newton":        (30.77,  -93.73,   13_488),
    "Nolan":         (32.31, -100.40,   14_669),
    "Nueces":        (27.73,  -97.59,  342_510),
    "Ochiltree":     (36.28, -100.81,    9_836),
    "Oldham":        (35.40, -102.60,    1_911),
    "Orange":        (30.13,  -93.86,   84_047),
    "Palo Pinto":    (32.74,  -98.30,   28_409),
    "Panola":        (32.15,  -94.31,   23_440),
    "Parker":        (32.77,  -97.81,  148_222),
    "Parmer":        (34.53, -102.78,    9_605),
    "Pecos":         (30.79, -102.72,   15_823),
    "Polk":          (30.82,  -94.83,   51_353),
    "Potter":        (35.40, -101.88,  117_415),
    "Presidio":      (29.79, -104.35,    6_131),
    "Rains":         (32.87,  -95.79,   12_514),
    "Randall":       (34.96, -101.89,  140_977),
    "Reagan":        (31.37, -101.52,    3_367),
    "Real":          (29.83,  -99.83,    3_389),
    "Red River":     (33.63,  -94.99,   12_023),
    "Reeves":        (31.32, -103.69,   15_976),
    "Refugio":       (28.33,  -97.16,    7_236),
    "Roberts":       (35.84, -100.81,      885),
    "Robertson":     (31.02,  -96.51,   16_953),
    "Rockwall":      (32.92,  -96.41,  107_741),
    "Runnels":       (31.83,  -99.97,   10_264),
    "Rusk":          (32.11,  -94.77,   53_595),
    "Sabine":        (31.35,  -93.87,   10_542),
    "San Augustine": (31.39,  -94.17,    8_490),
    "San Jacinto":   (30.57,  -95.10,   29_773),
    "San Patricio":  (27.97,  -97.52,   67_138),
    "San Saba":      (31.17,  -98.72,    6_055),
    "Schleicher":    (30.90, -100.54,    2_793),
    "Scurry":        (32.74, -100.91,   16_703),
    "Shackelford":   (32.74,  -99.35,    3_282),
    "Shelby":        (31.79,  -94.14,   25_048),
    "Sherman":       (36.28, -101.89,    3_034),
    "Smith":         (32.38,  -95.27,  232_751),
    "Somervell":     (32.22,  -97.77,    9_128),
    "Starr":         (26.56,  -98.77,   64_633),
    "Stephens":      (32.73,  -98.82,    9_366),
    "Sterling":      (31.83, -101.05,    1_291),
    "Stonewall":     (33.18, -100.25,    1_285),
    "Sutton":        (30.51, -100.53,    3_786),
    "Swisher":       (34.53, -101.74,    7_236),
    "Tarrant":       (32.77,  -97.29, 2_110_640),
    "Taylor":        (32.31,  -99.89,  138_034),
    "Terrell":       (30.22, -102.08,      775),
    "Terry":         (33.18, -102.35,   12_004),
    "Throckmorton":  (33.18,  -99.21,    1_517),
    "Titus":         (33.21,  -94.96,   32_750),
    "Tom Green":     (31.40, -100.45,  119_664),
    "Travis":        (30.33,  -97.77, 1_290_188),
    "Trinity":       (31.09,  -95.37,   14_585),
    "Tyler":         (30.77,  -94.35,   21_672),
    "Upshur":        (32.73,  -94.96,   41_782),
    "Upton":         (31.37, -102.05,    3_657),
    "Uvalde":        (29.36,  -99.78,   25_926),
    "Val Verde":     (29.89, -101.15,   48_879),
    "Van Zandt":     (32.56,  -95.83,   56_590),
    "Victoria":      (28.80,  -96.98,   92_084),
    "Walker":        (30.74,  -95.57,   72_791),
    "Waller":        (30.00,  -95.99,   55_246),
    "Ward":          (31.51, -103.10,   11_998),
    "Washington":    (30.21,  -96.39,   34_796),
    "Webb":          (27.74,  -99.51,  276_652),
    "Wharton":       (29.31,  -96.21,   41_551),
    "Wheeler":       (35.40, -100.27,    5_056),
    "Wichita":       (33.99,  -98.71,  131_818),
    "Wilbarger":     (34.09,  -99.25,   12_769),
    "Willacy":       (26.47,  -97.82,   20_880),
    "Williamson":    (30.65,  -97.60,  609_017),
    "Wilson":        (29.18,  -98.07,   51_584),
    "Winkler":       (31.85, -103.06,    7_802),
    "Wise":          (33.21,  -97.65,   77_028),
    "Wood":          (32.78,  -95.38,   45_539),
    "Yoakum":        (33.18, -102.82,    8_713),
    "Young":         (33.17,  -98.68,   17_806),
    "Zapata":        (27.07,  -99.17,   14_179),
    "Zavala":        (28.86,  -99.76,   12_166),
}

_COUNTY_LIST = list(TEXAS_COUNTY_POP.values())   # (lat, lon, pop) tuples


def _haversine_km(lat1, lon1, lat2, lon2):
    """Return great-circle distance in km between two (lat, lon) points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _nearest_county_pop(lat, lon):
    """Return Census 2020 population of the nearest Texas county centroid."""
    best_dist = float("inf")
    best_pop  = 1           # default: treat as 1 person (avoid zero weight)
    for clat, clon, pop in _COUNTY_LIST:
        d = _haversine_km(lat, lon, clat, clon)
        if d < best_dist:
            best_dist = d
            best_pop  = pop
    return best_pop


# ---------------------------------------------------------------------------
# Census tract population data (6,896 Texas tracts, Census 2020)
# Used by LOAD_ALLOC=tract_degree for sub-county load weighting.
# ---------------------------------------------------------------------------

_TRACT_LIST = None   # lazy-loaded: list of (lat, lon, pop) tuples


def _load_tract_data():
    """Load Texas census tract population + centroid CSV.

    Looks for texas_tract_pop_2020.csv in grid_data/ (relative to this script
    or under DARTBOARD_SCRATCH).  Returns list of (lat, lon, pop) tuples.
    """
    global _TRACT_LIST
    if _TRACT_LIST is not None:
        return _TRACT_LIST

    candidates = [
        Path(__file__).resolve().parent.parent / "grid_data" / "texas_tract_pop_2020.csv",
        SRC_DIR.parent / "texas_tract_pop_2020.csv",
    ]
    scratch = os.environ.get("DARTBOARD_SCRATCH", "")
    if scratch:
        candidates.insert(0, Path(scratch) / "texas_tract_pop_2020.csv")

    tract_csv = None
    for p in candidates:
        if p.exists():
            tract_csv = p
            break

    if tract_csv is None:
        print("  WARNING: texas_tract_pop_2020.csv not found, falling back to county data")
        _TRACT_LIST = _COUNTY_LIST
        return _TRACT_LIST

    tracts = []
    with open(tract_csv) as f:
        import csv as _csv
        reader = _csv.DictReader(f)
        for row in reader:
            pop = int(row["population"])
            lat = float(row["lat"])
            lng = float(row["lng"])
            if pop > 0:
                tracts.append((lat, lng, pop))
    _TRACT_LIST = tracts
    print(f"  Loaded {len(tracts)} census tracts from {tract_csv.name}")
    return _TRACT_LIST


def _nearest_tract_pop(lat, lon):
    """Return Census 2020 population of the nearest Texas census tract."""
    tracts = _load_tract_data()
    best_dist = float("inf")
    best_pop = 1
    for tlat, tlon, pop in tracts:
        d = _haversine_km(lat, lon, tlat, tlon)
        if d < best_dist:
            best_dist = d
            best_pop = pop
    return best_pop


# ---------------------------------------------------------------------------
# Step 1: Distribute zonal load to buses and write updated SourceData/bus.csv
# ---------------------------------------------------------------------------

def distribute_load(src_bus_csv: Path) -> Path:
    """
    Read SourceData/bus.csv, distribute zone MW load weighted by Census 2020
    county population, apply DC tie injections, write updated file back.
    Returns the path to the updated file.
    """
    bus = pd.read_csv(src_bus_csv, dtype=str)
    bus["_lat"] = pd.to_numeric(bus["lat"], errors="coerce")
    bus["_lon"] = pd.to_numeric(bus["lng"], errors="coerce")
    bus["MW Load"] = 0.0

    # Decide population data source based on allocation method
    load_alloc = os.environ.get("LOAD_ALLOC", "pop").lower()
    use_tracts = load_alloc in ("tract_degree", "tract")

    if use_tracts:
        print("  Using census tract population (sub-county granularity)")
        pop_fn = _nearest_tract_pop
    else:
        pop_fn = _nearest_county_pop

    pop_weights = []
    for _, row in bus.iterrows():
        lat = row["_lat"]
        lon = row["_lon"]
        if pd.isna(lat) or pd.isna(lon):
            pop_weights.append(1.0)
        else:
            pop_weights.append(float(pop_fn(float(lat), float(lon))))
    bus["_pop"] = pop_weights

    # Compute bus degree from branch table (for degree-weighted allocation)
    if load_alloc == "tract_degree":
        _branch_path = src_bus_csv.parent / "branch.csv"
        _degree = defaultdict(int)
        if _branch_path.exists():
            _br_df = pd.read_csv(_branch_path)
            for _, _br_row in _br_df.iterrows():
                _degree[int(_br_row["From Bus"])] += 1
                _degree[int(_br_row["To Bus"])] += 1
        _alpha = float(os.environ.get("DEGREE_ALPHA", "1.0"))
        bus_ids = pd.to_numeric(bus["Bus ID"], errors="coerce").fillna(-1).astype(int)
        bus["_degree"] = bus_ids.map(lambda bid: max(_degree.get(bid, 0), 1))
        bus["_degree_factor"] = bus["_degree"].apply(lambda d: d ** _alpha)
        print(f"  Degree-weighted allocation: alpha={_alpha}, "
              f"degree range {bus['_degree'].min()}–{bus['_degree'].max()}")

    # Only assign load to 138 kV substations (not split points, not 345 kV
    # pure-transmission buses).  Split points are T-junction wire nodes with
    # no real load connection; 345 kV buses are bulk-transfer nodes whose load
    # actually connects downstream at 138 kV.
    base_kv = pd.to_numeric(bus["BaseKV"], errors="coerce").fillna(0.0)
    is_split = bus["is_split"].astype(str).str.lower().isin(["true", "1"])
    is_load_bus = (~is_split) & (base_kv >= 100) & (base_kv < 300)

    # LOAD_NAMED_ONLY env var: further restrict to named substations only.
    # Excludes unnamed OSM geographic waypoints ("OSM_XXXX" names) and
    # generation plant substations ("_Plant" in name), which should not
    # receive distribution load.
    if os.environ.get("LOAD_NAMED_ONLY", "0") == "1":
        bus_name = bus["Bus Name"].fillna("")
        is_named = ~bus_name.str.startswith("OSM_") & ~bus_name.str.contains("_Plant", case=False)
        n_before = is_load_bus.sum()
        is_load_bus = is_load_bus & is_named
        print(f"LOAD_NAMED_ONLY=1 → load buses: {n_before} → {is_load_bus.sum()} "
              f"(excluded {n_before - is_load_bus.sum()} unnamed/plant buses)")

    # LOAD_ALLOC env var: choose load allocation method.
    #   "pop"          — proportional to county population (default)
    #   "uniform"      — equal MW per load bus within each zone
    #   "sqrt"         — proportional to sqrt(county population)
    #   "pop08"        — proportional to pop^0.8
    #   "cap75"        — population-weighted, capped at 75 MW/bus
    #   "tract"        — proportional to census tract population (sub-county)
    #   "tract_degree" — tract population × bus_degree^alpha (DEGREE_ALPHA env var)
    print(f"  Load allocation method: {load_alloc}")

    # Compute raw weights based on method
    import math as _math
    if load_alloc == "uniform":
        bus["_weight"] = 1.0
    elif load_alloc == "sqrt":
        bus["_weight"] = bus["_pop"].apply(lambda p: _math.sqrt(max(p, 1.0)))
    elif load_alloc == "pop08":
        bus["_weight"] = bus["_pop"].apply(lambda p: max(p, 1.0) ** 0.8)
    elif load_alloc == "tract":
        bus["_weight"] = bus["_pop"]
    elif load_alloc == "tract_degree":
        bus["_weight"] = bus["_pop"] * bus["_degree_factor"]
    else:
        bus["_weight"] = bus["_pop"]

    # Zero weight for non-load buses
    bus.loc[~is_load_bus, "_weight"] = 0.0

    # Zone total weight using only eligible load buses
    zone_total_wt = bus[is_load_bus].groupby("Zone")["_weight"].sum().to_dict()

    # Assign weighted MW load per bus
    load_col = []
    for idx, row in bus.iterrows():
        if not is_load_bus[idx]:
            load_col.append(0.0)
            continue
        zone     = str(row.get("Zone", "")).strip()
        zone_mw  = ZONE_LOAD_MW.get(zone, 0.0)
        ztotal   = zone_total_wt.get(zone, 0.0)
        wt       = row["_weight"]
        if ztotal > 0:
            load_col.append(round(zone_mw * wt / ztotal, 6))
        else:
            load_col.append(0.0)
    bus["MW Load"] = load_col

    # LMP-based load relief: reduce demand at buses that a prior run showed
    # are behind stressed feeders (high LMP), and redistribute to their
    # nearest non-stressed neighbors.  Keeps total zone demand constant.
    #
    #   LOAD_RELIEF_CSV  — path to a prior run's bus_detail.csv
    #   RELIEF_LMP_THRESH — LMP above which a bus is "stressed" (default 2000)
    #   RELIEF_PCT        — fraction to shave off stressed buses (default 0.05)
    #   RELIEF_K_NEAREST  — number of nearest non-stressed buses to receive
    #                       each bus's excess (default 5)
    #   RELIEF_ZERO_BUSES — comma-separated bus names to zero out entirely
    #                       (transit junctions where load allocation is wrong)
    #
    # The approach: LMP from a prior SCED tells us which buses are behind
    # congested feeders.  A small haircut (5%) at those buses, redistributed
    # to nearby non-stressed buses, relieves pressure without distorting the
    # geographic load pattern.  Buses in RELIEF_ZERO_BUSES are set to 10 MW
    # (realistic distribution tap) regardless of LMP threshold.
    _relief_csv = os.environ.get("LOAD_RELIEF_CSV", "")
    if _relief_csv:
        _relief_path = Path(_relief_csv)
        if not _relief_path.exists() and os.environ.get("DARTBOARD_SCRATCH"):
            _relief_path = Path(os.environ["DARTBOARD_SCRATCH"]) / _relief_csv
        _lmp_thresh = float(os.environ.get("RELIEF_LMP_THRESH", "2000"))
        _relief_pct = float(os.environ.get("RELIEF_PCT", "0.05"))
        _k_nearest = int(os.environ.get("RELIEF_K_NEAREST", "5"))

        if _relief_path.exists():
            # Read prior run's peak-hour LMPs to identify stressed buses
            _prior = pd.read_csv(_relief_path)
            # Find the hour with max shedding (or max avg LMP) as the stress hour
            _hourly_lmp = _prior.groupby("Hour")["LMP"].mean()
            _stress_hour = int(_hourly_lmp.idxmax())
            _prior_peak = _prior[_prior["Hour"] == _stress_hour].copy()
            _prior_peak = _prior_peak[pd.to_numeric(_prior_peak["Demand"],
                                                     errors="coerce") > 1]
            _stressed_names = set(
                _prior_peak.loc[_prior_peak["LMP"].astype(float) > _lmp_thresh,
                                "Bus"].values
            )
            print(f"  LOAD_RELIEF: {len(_stressed_names)} stressed buses "
                  f"(LMP > ${_lmp_thresh:.0f} at hour {_stress_hour}), "
                  f"haircut {_relief_pct:.0%}, redistribute to {_k_nearest} "
                  f"nearest neighbors each")

            # Build lat/lon index for nearest-neighbor lookup
            _bus_coords = {}
            for idx in bus.index[is_load_bus]:
                _blat = bus.loc[idx, "_lat"]
                _blon = bus.loc[idx, "_lon"]
                if pd.notna(_blat) and pd.notna(_blon):
                    _bus_coords[idx] = (float(_blat), float(_blon))

            _stressed_idx = set()
            for idx in bus.index[is_load_bus]:
                if bus.loc[idx, "Bus Name"] in _stressed_names:
                    _stressed_idx.add(idx)

            # Zero-bus override: set specific transit junctions to 10 MW
            _zero_buses = os.environ.get("RELIEF_ZERO_BUSES", "")
            _zero_set = set(b.strip() for b in _zero_buses.split(",")
                           if b.strip())
            if _zero_set:
                _TAP_MW = float(os.environ.get("RELIEF_TAP_MW", "10.0"))
                for idx in bus.index[is_load_bus]:
                    bname = bus.loc[idx, "Bus Name"]
                    if bname in _zero_set:
                        old_load = float(bus.loc[idx, "MW Load"])
                        if old_load > _TAP_MW:
                            excess = old_load - _TAP_MW
                            bus.loc[idx, "MW Load"] = _TAP_MW
                            # Redistribute to nearest non-stressed neighbors
                            if idx in _bus_coords:
                                _slat, _slon = _bus_coords[idx]
                                _dists = [
                                    ((_slat - _bus_coords[ni][0]) ** 2
                                     + (_slon - _bus_coords[ni][1]) ** 2, ni)
                                    for ni in bus.index[is_load_bus]
                                    if ni != idx and ni in _bus_coords
                                       and ni not in _stressed_idx
                                ]
                                _dists.sort()
                                _recips = [ni for _, ni in _dists[:_k_nearest]]
                                if _recips:
                                    _per = excess / len(_recips)
                                    for ni in _recips:
                                        bus.loc[ni, "MW Load"] = (
                                            float(bus.loc[ni, "MW Load"]) + _per)
                            _stressed_idx.discard(idx)  # don't double-haircut
                            print(f"    ZERO: {bname}: {old_load:.0f} → "
                                  f"{_TAP_MW:.0f} MW ({excess:.0f} MW to "
                                  f"neighbors)")

            _non_stressed_idx = [
                idx for idx in bus.index[is_load_bus]
                if idx not in _stressed_idx and idx in _bus_coords
            ]

            _total_relieved = 0.0
            _total_redistributed = 0.0
            _zone_summary = defaultdict(lambda: {"n": 0, "mw": 0.0})
            for idx in _stressed_idx:
                old_load = float(bus.loc[idx, "MW Load"])
                if old_load <= 0:
                    continue
                excess = old_load * _relief_pct
                bus.loc[idx, "MW Load"] = old_load - excess
                _total_relieved += excess
                _zone = str(bus.loc[idx, "Zone"])
                _zone_summary[_zone]["n"] += 1
                _zone_summary[_zone]["mw"] += excess

                # Find k nearest NON-stressed load buses by Euclidean distance
                if idx not in _bus_coords:
                    continue
                _slat, _slon = _bus_coords[idx]
                _dists = []
                for nidx in _non_stressed_idx:
                    _nlat, _nlon = _bus_coords[nidx]
                    _d = (_slat - _nlat) ** 2 + (_slon - _nlon) ** 2
                    _dists.append((_d, nidx))
                _dists.sort()
                _recipients = [nidx for _, nidx in _dists[:_k_nearest]]
                if _recipients:
                    _per_recip = excess / len(_recipients)
                    for nidx in _recipients:
                        bus.loc[nidx, "MW Load"] = (
                            float(bus.loc[nidx, "MW Load"]) + _per_recip
                        )
                    _total_redistributed += excess

            for _z in sorted(_zone_summary):
                _zs = _zone_summary[_z]
                print(f"    {_z}: {_zs['n']} buses relieved, "
                      f"{_zs['mw']:.0f} MW to neighbors")
            print(f"    Total: {_total_relieved:.0f} MW relieved, "
                  f"{_total_redistributed:.0f} MW redistributed nearby")
        else:
            print(f"  WARNING: LOAD_RELIEF_CSV={_relief_csv} not found, skipping")

    # Cap method: redistribute excess above per-bus cap
    if load_alloc == "cap75":
        CAP_MW = 75.0
        for zone in ZONE_LOAD_MW:
            zmask = (bus["Zone"] == zone) & is_load_bus
            excess = (bus.loc[zmask, "MW Load"] - CAP_MW).clip(lower=0).sum()
            if excess > 0:
                bus.loc[zmask, "MW Load"] = bus.loc[zmask, "MW Load"].clip(upper=CAP_MW)
                # Redistribute excess to uncapped buses in same zone
                uncapped = zmask & (bus["MW Load"] < CAP_MW)
                n_uncapped = uncapped.sum()
                if n_uncapped > 0:
                    bus.loc[uncapped, "MW Load"] += excess / n_uncapped

    # DC tie adjustments: subtract import MW from nearest matching bus.
    # For named substations (OKLAUNION, MONTICELLO): search Sub Name.
    # For geographic ties (EAGLE, MCALLEN, LAREDO): use nearest SOUTH bus
    # by approximate substation name match.
    sub_name_col = bus["Sub Name"].fillna("").str.upper()

    def apply_dc_tie(keyword, import_mw):
        """Subtract import_mw from MW Load of nearest matching bus."""
        matches = bus.index[sub_name_col.str.contains(keyword, regex=False)]
        if len(matches) == 0:
            matches = bus.index[bus["Zone"] == "SOUTH"]
        if len(matches) > 0:
            idx = matches[0]
            bus.loc[idx, "MW Load"] = float(bus.loc[idx, "MW Load"]) - import_mw

    for keyword, import_mw in DC_TIES:
        apply_dc_tie(keyword, import_mw)

    # Print diagnostic: per-zone load distribution summary
    for _z in ["WEST", "NORTH", "SOUTH", "HOUSTON"]:
        _zmask = (bus["Zone"] == _z) & is_load_bus
        _zloads = pd.to_numeric(bus.loc[_zmask, "MW Load"], errors="coerce")
        if len(_zloads) > 0:
            print(f"    {_z}: {_zmask.sum()} buses, "
                  f"load {_zloads.min():.1f}–{_zloads.max():.1f} MW, "
                  f"median {_zloads.median():.1f}, total {_zloads.sum():.0f} MW")

    # Drop internal helper columns
    _drop_cols = ["_lat", "_lon", "_pop", "_weight"]
    if "_degree" in bus.columns:
        _drop_cols += ["_degree", "_degree_factor"]
    bus = bus.drop(columns=[c for c in _drop_cols if c in bus.columns])
    bus.to_csv(src_bus_csv, index=False)
    return src_bus_csv


# ---------------------------------------------------------------------------
# RealistLoader: subclass of GridLoader
# ---------------------------------------------------------------------------

class RealistLoader(GridLoader):
    """Loads our custom Realist ERCOT grid for Vatic DC-SCED."""

    grid_lbl = "Realist"
    _data_dir = "SourceData"

    # Fuel strings must match what is written in SourceData/gen.csv
    thermal_gen_types = {
        "Nuclear": "N",
        "Coal":    "C",
        "Gas":     "G",
    }
    renew_gen_types = {
        "Wind":  "W",
        "Solar": "S",
    }

    @property
    def data_path(self) -> Path:
        """GridLoader reads from data_path/SourceData/*.csv."""
        return SCED_DIR

    @property
    def init_state_file(self) -> Path:
        return SRC_DIR / "init_state.csv"

    @property
    def utc_offset(self) -> pd.Timedelta:
        return -pd.Timedelta(hours=6)   # CST = UTC-6

    @property
    def timeseries_cohorts(self) -> set:
        # Not used by create_timeseries override, but required by ABC.
        return {"Wind", "Solar"}

    @staticmethod
    def get_dispatch_types(renew_types):
        return {
            "DispatchRenewables":    set(renew_types),
            "NondispatchRenewables": set(),
            "ForecastRenewables":    set(renew_types),
        }

    @staticmethod
    def process_actuals(actuals_file, start_date=None, end_date=None):
        # Not used — create_timeseries provides all data directly.
        return pd.DataFrame()

    @classmethod
    def must_gen_run(cls, gen):
        if gen.Fuel == "Nuclear":
            return True
        return gen.ID in _MUST_RUN_UIDS

    def get_generator_type(self, gen: str) -> str:
        row = self.gen_df.loc[self.gen_df["GEN UID"] == gen]
        if row.empty:
            return "G"
        fuel = str(row["Fuel"].iloc[0])
        if fuel == "Wind":
            return "WIND"
        if fuel == "Solar":
            return "PV"
        return "G"

    def get_generator_zone(self, gen: str) -> str:
        row = self.gen_df.loc[self.gen_df["GEN UID"] == gen]
        if row.empty:
            return "NORTH"
        bus_id = row["Bus ID"].iloc[0]
        bus_row = self.bus_df.loc[self.bus_df["Bus ID"].astype(str) == str(bus_id)]
        if bus_row.empty:
            return "NORTH"
        return str(bus_row["Zone"].iloc[0])

    @classmethod
    def parse_generator(cls, gen_info: pd.Series):
        """
        Parse gen.csv row to a Generator namedtuple.
        Implements T7kLoader.parse_generator logic with our column names.
        """
        import math as _math

        break_cols  = [c for c in gen_info.index if c.startswith("MW Break")]
        price_cols  = [c for c in gen_info.index if c.startswith("MWh Price")]

        break_indxs = {int(c.split(" Break ")[1]): c for c in break_cols}
        price_indxs = {int(c.split(" Price ")[1]): c for c in price_cols}
        cost_indxs  = sorted(set(break_indxs) & set(price_indxs))

        if not cost_indxs:
            cost_values = [0.0, 0.0]
        else:
            cost_values = [
                float(gen_info["Fixed Cost($/hr)"])
                + float(gen_info[price_indxs[cost_indxs[0]]])
                * float(gen_info[break_indxs[cost_indxs[0]]])
            ]
            for i in range(len(cost_indxs) - 1):
                cost_values.append(
                    cost_values[-1]
                    + float(gen_info[price_indxs[cost_indxs[i]]])
                    * (float(gen_info[break_indxs[cost_indxs[i + 1]]])
                       - float(gen_info[break_indxs[cost_indxs[i]]]))
                )
            cost_values.append(
                cost_values[-1]
                + float(gen_info[price_indxs[cost_indxs[-1]]])
                * (float(gen_info["PMax MW"])
                   - float(gen_info[break_indxs[cost_indxs[-1]]]))
            )

        cost_points = [float(gen_info[c]) for c in break_cols] + [float(gen_info["PMax MW"])]

        return cls.Generator(
            gen_info["GEN UID"],
            int(float(gen_info["Bus ID"])),
            gen_info["Unit Group"],
            gen_info["Unit Type"],
            gen_info["Fuel"],
            float(gen_info["PMin MW"]),
            float(gen_info["PMax MW"]),
            int(_math.ceil(float(gen_info["Min Down Time Hr"]))),
            int(_math.ceil(float(gen_info["Min Up Time Hr"]))),
            float(gen_info["Ramp Rate MW/Min"]),
            int(float(gen_info["Start Time Cold Hr"])),
            int(float(gen_info["Start Time Warm Hr"])),
            int(float(gen_info["Start Time Hot Hr"])),
            float(gen_info["Start Heat Cold MBTU"]),
            float(gen_info["Start Heat Warm MBTU"]),
            float(gen_info["Start Heat Hot MBTU"]),
            float(gen_info["Fuel Price $/MMBTU"]),
            cost_points,
            cost_values,
        )

    def create_timeseries(self, start_date=None, end_date=None):
        """
        Build 48-hour timeseries for SCED_DATE + SCED_DATE+1 (UTC).

        gen_data: one column per renewable generator.  If HOURLY_CF is set,
            PMax is scaled by the hourly CF for that fuel type; otherwise constant.
        load_data: one column per bus.  If HOURLY_ZONE_LOAD is set, each bus
            load is scaled per hour by (hourly_zone_mw / ref_zone_mw); otherwise
            constant at the reference MW Load from bus.csv.

        Day 2 (hours 24-47) repeats Day 1 (lookahead horizon for RUC).
        Both DataFrames have MultiIndex columns: (fcst/actl, asset_name).
        """
        date_str = SCED_DATE.isoformat()
        times = pd.date_range(
            f"{date_str}T00:00:00", periods=48, freq="h", tz="UTC"
        )

        # --- Renewable generator timeseries ---
        renew_gens = [g for g in self.generators if g.Fuel in self.renew_gen_types]

        gen_cols = {}
        for g in renew_gens:
            if HOURLY_CF is not None and g.Fuel in HOURLY_CF:
                # Day 1: actual hourly CF profile; Day 2: repeat Day 1
                cf_24 = HOURLY_CF[g.Fuel]
                vals = [round(g.MaxPower * cf_24[h], 4) for h in range(24)] * 2
            else:
                default_cf = DEFAULT_CF.get(g.Fuel, 1.0)
                vals = [round(g.MaxPower * default_cf, 4)] * 48
            for tag in ("fcst", "actl"):
                gen_cols[(tag, g.ID)] = vals

        if gen_cols:
            gen_df = pd.DataFrame(gen_cols, index=times)
            gen_df.columns = pd.MultiIndex.from_tuples(gen_df.columns)
        else:
            gen_df = pd.DataFrame(index=times)
            gen_df.columns = pd.MultiIndex.from_tuples([], names=[None, None])

        # --- Load bus timeseries ---
        bus_name_col = self.bus_df["Bus Name"].fillna("")
        mw_load_col  = pd.to_numeric(self.bus_df["MW Load"], errors="coerce").fillna(0.0)
        zone_col     = self.bus_df["Zone"].fillna("").astype(str)

        # Precompute hourly scaling factors per zone (if hourly profile provided)
        if HOURLY_ZONE_LOAD is not None:
            zone_scale = {}
            for z in ["NORTH", "HOUSTON", "SOUTH", "WEST"]:
                ref_mw = ZONE_LOAD_MW.get(z, 1.0) or 1.0
                zone_scale[z] = [HOURLY_ZONE_LOAD[z][h] / ref_mw for h in range(24)]
        else:
            zone_scale = None

        load_cols = {}
        for bus_name, mw_load, zone in zip(bus_name_col, mw_load_col, zone_col):
            bname = str(bus_name).strip()
            if not bname:
                continue
            ref = float(mw_load)
            if zone_scale is not None and zone in zone_scale:
                # Day 1: hourly scaled; Day 2: repeat Day 1
                vals = [round(ref * zone_scale[zone][h], 4) for h in range(24)] * 2
            else:
                vals = [round(ref, 4)] * 48
            for tag in ("fcst", "actl"):
                load_cols[(tag, bname)] = vals

        load_df = pd.DataFrame(load_cols, index=times)
        load_df.columns = pd.MultiIndex.from_tuples(load_df.columns)
        load_df = load_df.sort_index(axis=1)

        return gen_df, load_df


# ---------------------------------------------------------------------------
# Step 2: Distribute load to buses
# ---------------------------------------------------------------------------

print("Distributing zonal load to buses...")
src_bus = SRC_DIR / "bus.csv"
if not src_bus.exists():
    raise FileNotFoundError(
        f"{src_bus} not found. Run build_branch_table.py first."
    )
distribute_load(src_bus)
print("  Load distributed and DC ties applied.")

# Print zone load summary
bus_check = pd.read_csv(src_bus, dtype=str)
bus_check["_load"] = pd.to_numeric(bus_check["MW Load"], errors="coerce").fillna(0.0)
zone_totals = bus_check.groupby("Zone")["_load"].sum()
print("  Zonal load totals:")
for zone, mw in zone_totals.items():
    print(f"    {zone:10s}: {mw:>10,.0f} MW")
print(f"    {'TOTAL':10s}: {zone_totals.sum():>10,.0f} MW")

# ---------------------------------------------------------------------------
# Step 3: Verify SourceData files exist
# ---------------------------------------------------------------------------

for fname in ("gen.csv", "branch.csv", "bus.csv", "init_state.csv"):
    fpath = SRC_DIR / fname
    if not fpath.exists():
        raise FileNotFoundError(
            f"Missing {fpath}. Run the build_* scripts first."
        )

# ---------------------------------------------------------------------------
# Step 4: Instantiate RealistLoader and create timeseries
# ---------------------------------------------------------------------------

print("\nInitializing RealistLoader...")
loader = RealistLoader()

n_thermal = len([g for g in loader.generators
                 if g.Fuel in loader.thermal_gen_types])
n_renew   = len([g for g in loader.generators
                 if g.Fuel in loader.renew_gen_types])
n_branches = len(loader.branches)
n_buses    = len(loader.buses)

print(f"  Buses:             {n_buses:,}")
print(f"  Branches:          {n_branches:,}")
print(f"  Thermal generators:{n_thermal:,}")
print(f"  Renewable gens:    {n_renew:,}")

if n_branches == 0:
    raise RuntimeError("No transmission branches loaded. Run build_branch_table.py.")
if n_thermal == 0:
    raise RuntimeError("No thermal generators loaded. Run build_gen_table.py.")

gen_df, load_df = loader.create_timeseries()
print(f"  gen_data shape:    {gen_df.shape}  (renew generators × 48 h × 2 tags)")
print(f"  load_data shape:   {load_df.shape} (load buses × 48 h × 2 tags)")

# Verify indices match
assert (gen_df.index == load_df.index).all() or (
    gen_df.empty and not load_df.empty
), "gen_data and load_data indices do not match."

# Pad gen_df index to match load_df if gen_df is empty
if gen_df.empty and not load_df.empty:
    gen_df = pd.DataFrame(index=load_df.index)
    gen_df.columns = pd.MultiIndex.from_tuples([], names=[None, None])

# ---------------------------------------------------------------------------
# Step 4b: Load energy storage (BESS) from storage.csv
#
# Vatic's PickleProvider.create_vatic_model_dict() always initialises
# model_data['elements']['storage'] to an empty dict.  We inject BESS elements
# by monkey-patching the PickleProvider *instance* after the Simulator builds
# it, using a closure over _storage_elements built here.
#
# The storage element dict format follows the Egret model schema used by
# Prescient / Vatic.  Each entry is keyed by the storage UID and contains:
#   bus                     — OSM bus ID (int, as string to match bus names)
#   min_discharge_rate      — minimum discharge MW (0 = always feasible)
#   max_discharge_rate      — rated discharge MW (= installed_mw from MORA)
#   min_charge_rate         — minimum charge MW (0)
#   max_charge_rate         — rated charge MW (= installed_mw, symmetric)
#   energy_capacity         — nameplate energy capacity MWh
#   initial_state_of_charge — starting SOC (50% of energy_capacity)
#   charge_efficiency       — one-way Li-ion efficiency (0.96)
#   discharge_efficiency    — one-way Li-ion efficiency (0.96)
#   initial_status          — 1 = online/available at t=0
#
# If storage.csv does not exist (build_storage_table.py not yet run), this
# block is silently skipped and the simulation runs without storage.
# ---------------------------------------------------------------------------

STORAGE_CSV = SRC_DIR / "storage.csv"
_storage_elements: dict = {}   # uid → Egret storage element dict

# ---------------------------------------------------------------------------
# STORAGE_AGGREGATE env var: controls how storage units are aggregated to
# reduce MIP binary variable count.  Each Egret storage unit creates 2
# binary variables per time period (InputStorage, OutputStorage), so 289
# individual units × 24 hours = 13,872 binaries.  Combined with thermal
# generator binaries (~34k), this creates ~48k total binaries that make
# the RUC MILP intractable when hourly-varying load/CF profiles break
# temporal symmetry.
#
#   "zone"  → aggregate all storage within each ERCOT zone into one unit
#             (4 units total, 192 binaries).  DEFAULT.
#   "bus"   → aggregate storage at each bus into one unit (~200 units).
#   "none"  → no aggregation (289 individual units, may hang with varying
#             load/CF profiles).
# ---------------------------------------------------------------------------
_storage_aggregate = os.environ.get("STORAGE_AGGREGATE", "zone").lower()

if STORAGE_CSV.exists():
    _stor_df = pd.read_csv(STORAGE_CSV, dtype=str)

    # Filter out diagnostic-only rows where bus_id is missing
    _stor_df = _stor_df[_stor_df["Bus ID"].notna() & (_stor_df["Bus ID"] != "")]

    # Build individual storage element dicts first
    _raw_storage: list = []   # list of (uid, elem_dict)
    for _, _srow in _stor_df.iterrows():
        _uid = str(_srow["STORAGE UID"]).strip()
        if not _uid:
            continue

        _bus_id_int = int(float(_srow["Bus ID"]))
        _discharge_mw = float(_srow["Discharge Rate MW"])
        _charge_mw    = float(_srow["Charge Rate MW"])
        _energy_mwh   = float(_srow["Energy Capacity MWh"])
        _init_soc_mwh = float(_srow["Initial SOC MWh"])
        _init_soc_frac = _init_soc_mwh / _energy_mwh if _energy_mwh > 0 else 0.5
        _zone = str(_srow.get("_zone", "")).strip()

        _raw_storage.append((_uid, {
            "bus":                    _bus_id_int,
            "min_discharge_rate":     0.0,
            "max_discharge_rate":     _discharge_mw,
            "min_charge_rate":        0.0,
            "max_charge_rate":        _charge_mw,
            "energy_capacity":        _energy_mwh,
            "initial_state_of_charge": _init_soc_frac,
            "charge_efficiency":      float(_srow["Charge Efficiency"]),
            "discharge_efficiency":   float(_srow["Discharge Efficiency"]),
            # Egret has a typo: it reads 'discharge_efficienty' (missing 'c')
            # from storage_attrs.  Provide both spellings so the value is
            # actually used instead of silently falling back to default=1.0.
            "discharge_efficienty":   float(_srow["Discharge Efficiency"]),
            "initial_status":         1,
            "ramp_up_output_60min":   _discharge_mw,
            "ramp_down_output_60min": _discharge_mw,
            "ramp_up_input_60min":    _charge_mw,
            "ramp_down_input_60min":  _charge_mw,
            "_zone":                  _zone,
        }))

    # Aggregate storage units to reduce binary variable count
    if _storage_aggregate == "none":
        # No aggregation: use individual units as-is
        for _uid, _elem in _raw_storage:
            _elem_clean = {k: v for k, v in _elem.items() if not k.startswith("_")}
            _storage_elements[_uid] = _elem_clean

    elif _storage_aggregate == "bus":
        # Aggregate by bus: merge all units at same bus into one
        _bus_groups: dict = defaultdict(list)
        for _uid, _elem in _raw_storage:
            _bus_groups[_elem["bus"]].append(_elem)

        for _bus_id, _elems in _bus_groups.items():
            _agg_discharge = sum(e["max_discharge_rate"] for e in _elems)
            _agg_charge    = sum(e["max_charge_rate"] for e in _elems)
            _agg_energy    = sum(e["energy_capacity"] for e in _elems)
            # Weighted average SOC (by energy capacity)
            _agg_soc = sum(
                e["initial_state_of_charge"] * e["energy_capacity"]
                for e in _elems
            ) / _agg_energy if _agg_energy > 0 else 0.5
            # Weighted average efficiencies (by discharge capacity)
            _total_dis = sum(e["max_discharge_rate"] for e in _elems) or 1.0
            _agg_eff_chg = sum(
                e["charge_efficiency"] * e["max_discharge_rate"]
                for e in _elems
            ) / _total_dis
            _agg_eff_dis = sum(
                e["discharge_efficiency"] * e["max_discharge_rate"]
                for e in _elems
            ) / _total_dis

            _storage_elements[f"BESS_Bus{_bus_id}"] = {
                "bus":                    _bus_id,
                "min_discharge_rate":     0.0,
                "max_discharge_rate":     _agg_discharge,
                "min_charge_rate":        0.0,
                "max_charge_rate":        _agg_charge,
                "energy_capacity":        _agg_energy,
                "initial_state_of_charge": _agg_soc,
                "charge_efficiency":      round(_agg_eff_chg, 4),
                "discharge_efficiency":   round(_agg_eff_dis, 4),
                "discharge_efficienty":   round(_agg_eff_dis, 4),
                "initial_status":         1,
                "ramp_up_output_60min":   _agg_discharge,
                "ramp_down_output_60min": _agg_discharge,
                "ramp_up_input_60min":    _agg_charge,
                "ramp_down_input_60min":  _agg_charge,
            }

    elif _storage_aggregate == "zone":
        # Aggregate by ERCOT zone: one storage unit per zone.
        # The aggregate unit is placed at the bus with the largest
        # storage capacity in that zone (most realistic injection point).
        _zone_groups: dict = defaultdict(list)
        for _uid, _elem in _raw_storage:
            _z = _elem.get("_zone", "UNKNOWN") or "UNKNOWN"
            _zone_groups[_z].append(_elem)

        for _zone, _elems in _zone_groups.items():
            _agg_discharge = sum(e["max_discharge_rate"] for e in _elems)
            _agg_charge    = sum(e["max_charge_rate"] for e in _elems)
            _agg_energy    = sum(e["energy_capacity"] for e in _elems)
            _agg_soc = sum(
                e["initial_state_of_charge"] * e["energy_capacity"]
                for e in _elems
            ) / _agg_energy if _agg_energy > 0 else 0.5
            _total_dis = sum(e["max_discharge_rate"] for e in _elems) or 1.0
            _agg_eff_chg = sum(
                e["charge_efficiency"] * e["max_discharge_rate"]
                for e in _elems
            ) / _total_dis
            _agg_eff_dis = sum(
                e["discharge_efficiency"] * e["max_discharge_rate"]
                for e in _elems
            ) / _total_dis
            # Place at bus with largest discharge capacity in this zone
            _best_bus = max(_elems, key=lambda e: e["max_discharge_rate"])["bus"]

            _storage_elements[f"BESS_{_zone}"] = {
                "bus":                    _best_bus,
                "min_discharge_rate":     0.0,
                "max_discharge_rate":     _agg_discharge,
                "min_charge_rate":        0.0,
                "max_charge_rate":        _agg_charge,
                "energy_capacity":        _agg_energy,
                "initial_state_of_charge": _agg_soc,
                "charge_efficiency":      round(_agg_eff_chg, 4),
                "discharge_efficiency":   round(_agg_eff_dis, 4),
                "discharge_efficienty":   round(_agg_eff_dis, 4),
                "initial_status":         1,
                "ramp_up_output_60min":   _agg_discharge,
                "ramp_down_output_60min": _agg_discharge,
                "ramp_up_input_60min":    _agg_charge,
                "ramp_down_input_60min":  _agg_charge,
            }

    else:
        print(f"WARNING: unknown STORAGE_AGGREGATE={_storage_aggregate}, "
              f"falling back to 'zone'")

    _stor_total_mw  = sum(e["max_discharge_rate"] for e in _storage_elements.values())
    _stor_total_mwh = sum(e["energy_capacity"]     for e in _storage_elements.values())
    print(f"\nStorage: loaded {len(_raw_storage):,} BESS units from storage.csv")
    print(f"  Aggregation:          {_storage_aggregate} "
          f"({len(_raw_storage):,} → {len(_storage_elements):,} model units)")
    print(f"  Total discharge capacity: {_stor_total_mw:,.1f} MW")
    print(f"  Total energy capacity:    {_stor_total_mwh:,.1f} MWh")
    if _storage_aggregate == "zone":
        for _uid, _elem in sorted(_storage_elements.items()):
            print(f"    {_uid}: {_elem['max_discharge_rate']:,.1f} MW / "
                  f"{_elem['energy_capacity']:,.1f} MWh at bus {_elem['bus']}")
else:
    print("\nStorage: storage.csv not found — running without BESS "
          "(run build_storage_table.py to add storage)")

# Patch PickleProvider.create_vatic_model_dict to inject storage elements.
# We do this by wrapping the class-level method with a closure that merges in
# _storage_elements after the base method builds the empty dict.  The patch is
# applied here (before Simulator instantiation) so the PickleProvider instance
# created inside Simulator.__init__ already sees the wrapped method.
#
# The bus field in each storage element must match a key in model_data['elements']['bus'].
# Vatic builds bus keys from data['Buses'], which are bus *name* strings (e.g. "3042").
# osm_bus.csv stores Bus ID as an integer and Bus Name as a string; we need the
# name.  Load the Bus Name → Bus ID mapping now.
if _storage_elements:
    _osm_bus_df = pd.read_csv(SRC_DIR / "bus.csv", dtype=str)
    # bus.csv has columns: Bus ID, Bus Name, ...
    _bid_to_bname = (
        _osm_bus_df.set_index(
            _osm_bus_df["Bus ID"].astype(int)
        )["Bus Name"]
        .to_dict()
    )   # int(bus_id) → "Bus Name string"

    # Remap bus field in _storage_elements from int bus_id to string bus_name
    _remapped_storage: dict = {}
    _bus_miss = 0
    for _uid, _elem in _storage_elements.items():
        _bname = _bid_to_bname.get(_elem["bus"])
        if _bname is None:
            _bus_miss += 1
            continue
        _new_elem = dict(_elem)
        _new_elem["bus"] = str(_bname)
        _remapped_storage[_uid] = _new_elem

    if _bus_miss > 0:
        print(f"  Warning: {_bus_miss} storage units had Bus IDs not in bus.csv "
              f"and were dropped.")

    _storage_elements = _remapped_storage
    print(f"  Storage units with valid bus mapping: {len(_storage_elements):,}")

    # Monkey-patch PickleProvider.create_vatic_model_dict
    from vatic.data_providers import PickleProvider as _PickleProvider
    _orig_create = _PickleProvider.create_vatic_model_dict

    def _patched_create(self, data: dict) -> dict:
        """Wrap original create_vatic_model_dict to inject BESS elements."""
        model_dict = _orig_create(self, data)
        # Merge storage elements into the elements dict.
        # Only include units whose bus name appears in the model's bus dict.
        model_buses = set(model_dict["elements"]["bus"].keys())
        injected = 0
        skipped = []
        for _uid, _elem in _storage_elements.items():
            if _elem["bus"] in model_buses:
                model_dict["elements"]["storage"][_uid] = _elem
                injected += 1
            else:
                skipped.append((_uid, _elem["bus"]))
        print(f"  [Storage injection] {injected} units injected into model, "
              f"{len(skipped)} skipped (bus not in model)")
        if skipped:
            for s_uid, s_bus in skipped:
                print(f"    SKIPPED: {s_uid} at bus '{s_bus}'")
        return model_dict

    _PickleProvider.create_vatic_model_dict = _patched_create

# ---------------------------------------------------------------------------
# Step 5: Run Vatic Simulator
# ---------------------------------------------------------------------------

print(f"\nStarting Vatic Simulator for {SCED_DATE}...")
print(f"  Solver: {SOLVER}  |  LMPs: True  |  MIPgap: 1%")
print(f"  Experiment: {tag or 'baseline'}")
print(f"  Branch scale: {_branch_scale_raw}")
print(f"  Hourly load: {'yes (' + _hourly_load_csv_path + ')' if HOURLY_ZONE_LOAD else 'no (constant)'}")
print(f"  Load scale:  {LOAD_SCALE}")
print(f"  Hourly CFs:  {'yes (' + _hourly_cf_csv_path + ')' if HOURLY_CF else 'no (constant)'}")
print(f"  Output: {RES_DIR}")

sim = Simulator(
    template_data=loader.template,
    gen_data=gen_df,
    load_data=load_df,
    out_dir=RES_DIR,
    start_date=SCED_DATE,
    num_days=1,
    solver=SOLVER,
    solver_options=SOLVER_OPTIONS,
    run_lmps=True,
    mipgap=0.01,
    load_shed_penalty=1e4,
    reserve_shortfall_penalty=float(os.environ.get("RESERVE_PENALTY", "1e3")),
    reserve_factor=float(os.environ.get("RESERVE_FACTOR", "0.05")),
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

# ---------------------------------------------------------------------------
# Step 5b: Feedback-based commitment (two-pass SCED)
#
# Real ERCOT's nodal SCUC commits local thermals in congested areas.
# Vatic's RUC sometimes under-commits because it doesn't fully discover
# all binding constraints during the MILP.  Fix: after each hourly SCED,
# if there's load shedding, find uncommitted thermal generators near the
# shedding buses, force-commit them for min_up_time hours, and re-solve.
#
# FEEDBACK_COMMIT env var: "1" (default) to enable, "0" to disable.
# FEEDBACK_SHED_THRESHOLD: min MW shedding at a bus to trigger (default 1.0).
# FEEDBACK_MAX_HOPS: how many branch hops to search for generators (default 3).
# ---------------------------------------------------------------------------

_FEEDBACK_COMMIT = os.environ.get("FEEDBACK_COMMIT", "1") == "1"
_FEEDBACK_SHED_THRESHOLD = float(os.environ.get("FEEDBACK_SHED_THRESHOLD", "1.0"))
_FEEDBACK_MAX_HOPS = int(os.environ.get("FEEDBACK_MAX_HOPS", "3"))

if _FEEDBACK_COMMIT:
    # Build bus adjacency graph and gen-to-bus mapping from SourceData
    _fb_branch = pd.read_csv(SRC_DIR / "branch.csv")
    _fb_gen = pd.read_csv(SRC_DIR / "gen.csv")
    _fb_bus = pd.read_csv(SRC_DIR / "bus.csv", dtype=str)

    # Bus Name → Bus ID mapping (Vatic uses Bus Name as key in model)
    _fb_bname_to_bid = dict(zip(_fb_bus["Bus Name"], _fb_bus["Bus ID"].astype(int)))
    _fb_bid_to_bname = dict(zip(_fb_bus["Bus ID"].astype(int), _fb_bus["Bus Name"]))

    # Adjacency: Bus ID → set of neighbor Bus IDs
    _fb_adj: dict[int, set] = defaultdict(set)
    for _, row in _fb_branch.iterrows():
        f, t = int(row["From Bus"]), int(row["To Bus"])
        _fb_adj[f].add(t)
        _fb_adj[t].add(f)

    # Thermal generators: Bus ID → list of (GEN UID, PMax, MinUpTime)
    _fb_thermals_at_bus: dict[int, list] = defaultdict(list)
    for _, row in _fb_gen.iterrows():
        if row["Fuel"] in ("Gas", "Coal"):
            _fb_thermals_at_bus[int(row["Bus ID"])].append((
                row["GEN UID"],
                float(row["PMax MW"]),
                max(1, int(float(row["Min Up Time Hr"]))),
            ))
    # Sort largest first at each bus for greedy selection
    for bus_id in _fb_thermals_at_bus:
        _fb_thermals_at_bus[bus_id].sort(key=lambda x: -x[1])

    def _find_nearby_thermals(shed_bus_names: list[str], max_hops: int) -> list[tuple[str, int]]:
        """Find thermal generators within max_hops of shedding buses.

        Returns list of (GEN UID, min_up_time) sorted by PMax descending.
        """
        # Convert shedding bus names to bus IDs
        shed_bids = set()
        for bname in shed_bus_names:
            bid = _fb_bname_to_bid.get(bname)
            if bid is not None:
                shed_bids.add(bid)

        # BFS to find all bus IDs within max_hops
        visited = set(shed_bids)
        frontier = set(shed_bids)
        for _ in range(max_hops):
            next_frontier = set()
            for bid in frontier:
                for nbr in _fb_adj.get(bid, set()):
                    if nbr not in visited:
                        visited.add(nbr)
                        next_frontier.add(nbr)
            frontier = next_frontier
            if not frontier:
                break

        # Collect thermal generators at all visited buses
        candidates = []
        for bid in visited:
            for gen_uid, pmax, min_up in _fb_thermals_at_bus.get(bid, []):
                candidates.append((gen_uid, pmax, min_up))

        # Sort by PMax descending (commit largest first)
        candidates.sort(key=lambda x: -x[1])
        return [(uid, mut) for uid, _, mut in candidates]

    # Monkey-patch Simulator.call_oracle to add feedback loop
    from vatic.engines import Simulator as _Sim

    _orig_call_oracle = _Sim.call_oracle

    def _feedback_call_oracle(self):
        """Two-pass SCED: solve, check shedding, recommit, re-solve."""
        if self.verbosity > 0:
            print("\nSolving SCED instance (pass 1)")

        # --- Pass 1: solve SCED normally ---
        pass1 = self.solve_sced(hours_in_objective=1,
                                sced_horizon=self.sced_horizon)
        total_shed = pass1.load_shedding

        if total_shed > _FEEDBACK_SHED_THRESHOLD:
            # Find buses with shedding
            shed_buses = []
            shed_total_by_bus = {}
            for bname, bdata in pass1._data['elements']['bus'].items():
                violation = bdata['p_balance_violation']['values'][0]
                if violation > _FEEDBACK_SHED_THRESHOLD:
                    shed_buses.append(bname)
                    shed_total_by_bus[bname] = violation

            if shed_buses:
                print(f"  Pass 1 shedding: {total_shed:.1f} MW across "
                      f"{len(shed_buses)} buses — searching for generators "
                      f"within {_FEEDBACK_MAX_HOPS} hops")

                # Find nearby uncommitted thermal generators
                candidates = _find_nearby_thermals(shed_buses, _FEEDBACK_MAX_HOPS)

                # Filter to generators that are currently uncommitted
                state = self._simulation_state
                newly_committed = []
                for gen_uid, min_up in candidates:
                    if gen_uid not in state._commits:
                        continue
                    commits = list(state._commits[gen_uid])
                    if len(commits) == 0 or commits[0] == 1:
                        continue  # already committed or no data

                    # Force-commit for min_up_time hours (current + future)
                    for h in range(min(min_up, len(commits))):
                        commits[h] = 1
                    state._commits[gen_uid] = tuple(commits)
                    newly_committed.append(gen_uid)

                if newly_committed:
                    print(f"  Feedback commit: {len(newly_committed)} generators "
                          f"force-committed for pass 2")

                    # --- Pass 2: re-solve SCED with updated commitments ---
                    pass2 = self.solve_sced(hours_in_objective=1,
                                            sced_horizon=self.sced_horizon)
                    shed2 = pass2.load_shedding
                    print(f"  Pass 2 shedding: {shed2:.1f} MW "
                          f"(reduction: {total_shed - shed2:.1f} MW)")

                    # Use pass 2 result
                    current_sced_instance = pass2
                else:
                    print(f"  No uncommitted generators found near shedding buses")
                    current_sced_instance = pass1
            else:
                current_sced_instance = pass1
        else:
            current_sced_instance = pass1

        # --- LMPs and state update (same as original) ---
        if self.verbosity > 0:
            print("Solving for LMPs")

        if self.run_lmps:
            lmp_sced = self.solve_lmp(current_sced_instance)
        else:
            lmp_sced = None

        self._simulation_state.apply_sced(current_sced_instance)
        self._prior_sced_instance = current_sced_instance

        self._stats_manager.collect_sced_solution(
            self._current_timestep, current_sced_instance, lmp_sced,
            pre_quickstart_cache=None
        )

    _Sim.call_oracle = _feedback_call_oracle
    print(f"\nFeedback commitment: ENABLED "
          f"(threshold={_FEEDBACK_SHED_THRESHOLD} MW, "
          f"max_hops={_FEEDBACK_MAX_HOPS})")
else:
    print("\nFeedback commitment: DISABLED")

sim.simulate()

# ---------------------------------------------------------------------------
# Step 6: Parse and print results
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print(f"RESULTS SUMMARY — {SCED_DATE}")
print("=" * 60)

def _find_csv(directory: Path, keyword: str):
    """Find first CSV in directory whose name contains keyword (case-insensitive)."""
    for f in sorted(directory.glob("*.csv")):
        if keyword.lower() in f.stem.lower():
            return f
    return None


# --- LMP results ---
lmp_file = _find_csv(RES_DIR, "lmp")
if lmp_file and lmp_file.exists():
    lmp_df = pd.read_csv(lmp_file)
    # Try to find bus-level LMP column
    lmp_cols = [c for c in lmp_df.columns if "lmp" in c.lower() or "price" in c.lower()]
    bus_cols  = [c for c in lmp_df.columns if "bus" in c.lower() or "name" in c.lower()]

    if lmp_cols and bus_cols:
        lmp_df["_lmp"] = pd.to_numeric(lmp_df[lmp_cols[0]], errors="coerce")
        lmp_df["_bus"] = lmp_df[bus_cols[0]].astype(str)

        bus_lmp_avg = lmp_df.groupby("_bus")["_lmp"].mean().dropna()
        if not bus_lmp_avg.empty:
            print("\nTop 10 MOST EXPENSIVE buses (average LMP $/MWh):")
            for bus_name, lmp in bus_lmp_avg.nlargest(10).items():
                print(f"  {bus_name:40s}: ${lmp:8.2f}/MWh")

            print("\nTop 10 CHEAPEST buses (average LMP $/MWh):")
            for bus_name, lmp in bus_lmp_avg.nsmallest(10).items():
                print(f"  {bus_name:40s}: ${lmp:8.2f}/MWh")

            # Zone averages using bus.csv zone mapping
            bus_zone = (
                pd.read_csv(src_bus, dtype=str)[["Bus Name", "Zone"]]
                .set_index("Bus Name")["Zone"]
                .to_dict()
            )
            bus_lmp_avg_df = bus_lmp_avg.reset_index()
            bus_lmp_avg_df.columns = ["Bus Name", "LMP"]
            bus_lmp_avg_df["Zone"] = bus_lmp_avg_df["Bus Name"].map(bus_zone)
            zone_avg = bus_lmp_avg_df.groupby("Zone")["LMP"].mean()

            print("\nZone average LMPs:")
            for z, lmp in zone_avg.items():
                print(f"  {z:10s}: ${lmp:8.2f}/MWh")

            west_lmp  = zone_avg.get("WEST",  float("nan"))
            north_lmp = zone_avg.get("NORTH", float("nan"))
            if not math.isnan(west_lmp) and not math.isnan(north_lmp):
                spread = north_lmp - west_lmp
                print(f"\nWest–North LMP spread: ${spread:.2f}/MWh "
                      f"({'positive → West Texas export constraint active' if spread > 0 else 'negative'})")

# --- Shadow prices / binding constraints ---
shadow_file = _find_csv(RES_DIR, "shadow")
if shadow_file and shadow_file.exists():
    shadow_df = pd.read_csv(shadow_file)
    print("\nBinding transmission constraints (shadow price ≠ 0):")
    price_cols = [c for c in shadow_df.columns
                  if "shadow" in c.lower() or "price" in c.lower() or "dual" in c.lower()]
    if price_cols:
        shadow_df["_price"] = pd.to_numeric(shadow_df[price_cols[0]], errors="coerce")
        binding = shadow_df[shadow_df["_price"].abs() > 0.01].sort_values(
            "_price", key=abs, ascending=False
        )
        if binding.empty:
            print("  None (no binding constraints found)")
        else:
            for _, row in binding.head(10).iterrows():
                print(f"  {row.iloc[0]:40s}: shadow = ${row['_price']:.2f}/MWh")

print("\nResults written to:", RES_DIR)

# List output files
output_files = sorted(RES_DIR.glob("*.csv"))
print(f"Output files ({len(output_files)}):")
for f in output_files:
    size_kb = f.stat().st_size / 1024
    print(f"  {f.name:40s} ({size_kb:.0f} KB)")
