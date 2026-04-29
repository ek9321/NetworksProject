#!/usr/bin/env python3
"""
Prepare hourly load and capacity factor CSVs for a given ERCOT simulation date.

Reads ERCOT public data files (native load, wind/solar generation) and
produces two CSVs compatible with run_sced.py's HOURLY_LOAD_CSV and HOURLY_CF_CSV
env vars:

  hourly_load_YYYYMMDD.csv  — columns: hour (0-23), NORTH, HOUSTON, SOUTH, WEST (MW)
  hourly_cf_YYYYMMDD.csv    — columns: hour (0-23), Wind (0-1), Solar (0-1)

Usage:
  python prepare_calibration_day.py --date 2024-06-17 \
      --native-load Native_Load_2024.csv \
      --wind-output wind_actual_2024.csv \
      --solar-output solar_actual_2024.csv \
      --gen-csv /path/to/sced_inputs/SourceData/gen.csv \
      --out-dir /scratch/network/js0735/dartboard

ERCOT data sources:
  Native Load (by weather zone, hourly):
    NP6-345-CD at https://www.ercot.com/mp/data-products/data-product-details?id=NP6-345-CD
    File: Native_Load_<YEAR>.zip → Native_Load_<YEAR>.csv
    Columns: HourEnding, COAST, EAST, FAR_WEST, NORTH, NORTH_C, SOUTHERN, SOUTH_C, WEST, ERCOT
    HourEnding: "MM/DD/YYYY HH:MM" (CST), hour 1:00 = first hour of the day

  Wind actual output (statewide, hourly):
    NP4-742-CD at https://www.ercot.com/mp/data-products/data-product-details?id=NP4-742-CD
    File: ERCOT_60MIN_STWPF_*.csv or similar
    Columns: DSTFlag, HourEnding, SYSTEM_WIDE, LZ_SOUTH_HOUSTON, PANHANDLE, NORTH, WEST, COASTAL

  Solar actual output (statewide, hourly):
    NP4-745-CD at https://www.ercot.com/mp/data-products/data-product-details?id=NP4-745-CD
    File: ERCOT_60MIN_STPPF_*.csv or similar

  Alternative: Fuel Mix report (NP3-966-ER or similar) has all fuels in one file.

Weather zone → Settlement zone mapping (approximate):
  NORTH settlement zone  = NORTH + NORTH_C + EAST weather zones
  HOUSTON settlement zone = COAST weather zone
  SOUTH settlement zone  = SOUTH_C + SOUTHERN weather zones
  WEST settlement zone   = FAR_WEST + WEST weather zones
  (El Paso / CPS are not in ERCOT but FAR_WEST is the Midland/Abilene area.)
"""

import argparse
import datetime
import sys
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Weather zone → settlement zone mapping
# ---------------------------------------------------------------------------
# ERCOT Native Load weather zones map to our 4 settlement zones as follows.
# Source: ERCOT Network Operations Guide & Load Profiles documentation.
WEATHER_TO_SETTLEMENT = {
    "NORTH":    "NORTH",
    "NORTH_C":  "NORTH",
    "EAST":     "NORTH",    # East TX load (Beaumont area) is in NORTH settlement zone
    "COAST":    "HOUSTON",
    "SOUTH_C":  "SOUTH",
    "SOUTHERN": "SOUTH",
    "FAR_WEST": "WEST",
    "WEST":     "WEST",
}


def parse_hourly_load(native_load_csv: Path, date: datetime.date) -> pd.DataFrame:
    """
    Parse ERCOT Native Load CSV and extract hourly (0-23) load by settlement zone
    for the given date.

    Returns DataFrame with columns: hour (int 0-23), NORTH, HOUSTON, SOUTH, WEST (MW).

    The Native Load file uses HourEnding convention: hour 1 = 00:00-01:00 (i.e., the MW
    for "hour 1" counts from midnight to 1 AM).  We convert to 0-indexed hours:
      HourEnding 1:00 → hour 0
      HourEnding 24:00 → hour 23
    """
    df = pd.read_csv(native_load_csv, parse_dates=False)

    # Normalize column names
    df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

    # The HourEnding column format is "M/D/YYYY H:MM" or "MM/DD/YYYY HH:MM"
    # with the time being the end of the interval.
    # Handle DST: some files have a DSTFlag column; ignore for now.
    he_col = next(c for c in df.columns if "HOURENDING" in c or "HOUR_ENDING" in c)

    # Parse date portion
    df["_parsed"] = pd.to_datetime(df[he_col], format="mixed", dayfirst=False, errors="coerce")
    date_mask = df["_parsed"].dt.date == date
    day_df = df[date_mask].copy()

    if day_df.empty:
        raise ValueError(
            f"No data found for {date} in {native_load_csv}. "
            f"Check file covers this date range."
        )

    # HourEnding → 0-indexed hour: HourEnding hour 1 = first hour of day = index 0
    day_df["hour"] = (day_df["_parsed"].dt.hour - 1) % 24

    # Sum weather zone columns into settlement zones
    records = []
    for _, row in day_df.iterrows():
        settlement = {"NORTH": 0.0, "HOUSTON": 0.0, "SOUTH": 0.0, "WEST": 0.0}
        for wz, sz in WEATHER_TO_SETTLEMENT.items():
            if wz in row.index:
                val = pd.to_numeric(row[wz], errors="coerce")
                if not pd.isna(val):
                    settlement[sz] += val
        records.append({
            "hour": int(row["hour"]),
            "NORTH":   round(settlement["NORTH"],   1),
            "HOUSTON": round(settlement["HOUSTON"], 1),
            "SOUTH":   round(settlement["SOUTH"],   1),
            "WEST":    round(settlement["WEST"],    1),
        })

    result = (
        pd.DataFrame(records)
        .sort_values("hour")
        .reset_index(drop=True)
    )
    assert len(result) == 24, f"Expected 24 hours, got {len(result)}"
    return result


def parse_wind_actual(wind_csv: Path, date: datetime.date) -> pd.Series:
    """
    Parse ERCOT wind actual output CSV.
    Returns a Series indexed 0-23 with statewide wind MW for each hour.

    Expected columns: HourEnding, SYSTEM_WIDE (or similar).
    """
    df = pd.read_csv(wind_csv)
    df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

    he_col = next(c for c in df.columns if "HOURENDING" in c or "HOUR_ENDING" in c)
    df["_parsed"] = pd.to_datetime(df[he_col], format="mixed", dayfirst=False, errors="coerce")
    day_df = df[df["_parsed"].dt.date == date].copy()

    if day_df.empty:
        raise ValueError(f"No wind data found for {date} in {wind_csv}.")

    day_df["hour"] = (day_df["_parsed"].dt.hour - 1) % 24

    # Look for system-wide column
    mw_col = next(
        (c for c in day_df.columns if "SYSTEM_WIDE" in c or "SYSTEMWIDE" in c or "TOTAL" in c),
        None
    )
    if mw_col is None:
        # Try first numeric column after HourEnding
        mw_col = [c for c in day_df.columns if c not in (he_col, "_parsed", "hour", "DSTFLAG")][0]

    return day_df.set_index("hour")[mw_col].apply(pd.to_numeric, errors="coerce").sort_index()


def parse_solar_actual(solar_csv: Path, date: datetime.date) -> pd.Series:
    """
    Parse ERCOT solar actual output CSV.  Same format as wind.
    Returns Series indexed 0-23 with statewide solar MW.
    """
    return parse_wind_actual(solar_csv, date)   # same logic, different file


def compute_cfs(
    wind_mw: pd.Series,
    solar_mw: pd.Series,
    gen_csv: Path,
) -> pd.DataFrame:
    """
    Compute hourly wind and solar capacity factors.

    CF = actual_mw / installed_capacity_in_gen_csv

    The installed capacity in gen.csv is PMax MW summed over all wind (or solar)
    generators.  This gives a system-wide average CF that is then applied uniformly
    to all generators of that type in create_timeseries().

    Returns DataFrame with columns: hour (0-23), Wind (0-1), Solar (0-1).
    """
    gen_df = pd.read_csv(gen_csv)
    total_wind_mw  = gen_df.loc[gen_df["Fuel"] == "Wind",  "PMax MW"].sum()
    total_solar_mw = gen_df.loc[gen_df["Fuel"] == "Solar", "PMax MW"].sum()

    print(f"  Total wind capacity in gen.csv:  {total_wind_mw:,.0f} MW")
    print(f"  Total solar capacity in gen.csv: {total_solar_mw:,.0f} MW")

    records = []
    for h in range(24):
        w_mw = float(wind_mw.get(h, 0.0))
        s_mw = float(solar_mw.get(h, 0.0))
        w_cf = min(1.0, w_mw / total_wind_mw) if total_wind_mw > 0 else 0.0
        s_cf = min(1.0, s_mw / total_solar_mw) if total_solar_mw > 0 else 0.0
        records.append({"hour": h, "Wind": round(w_cf, 4), "Solar": round(s_cf, 4)})

    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date",         required=True,  help="Simulation date YYYY-MM-DD")
    parser.add_argument("--native-load",  required=True,  help="Path to Native_Load_YEAR.csv")
    parser.add_argument("--wind-output",  default="",     help="Path to wind actual output CSV")
    parser.add_argument("--solar-output", default="",     help="Path to solar actual output CSV")
    parser.add_argument("--gen-csv",      required=True,  help="Path to SourceData/gen.csv")
    parser.add_argument("--out-dir",      required=True,  help="Output directory for hourly CSVs")
    args = parser.parse_args()

    date = datetime.date.fromisoformat(args.date)
    date_str = date.strftime("%Y%m%d")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Preparing calibration data for {date}...")

    # --- Hourly load ---
    print(f"\nParsing native load from {args.native_load}...")
    load_df = parse_hourly_load(Path(args.native_load), date)
    print(load_df.to_string(index=False))
    print(f"\nTotal system load range: {(load_df.NORTH + load_df.HOUSTON + load_df.SOUTH + load_df.WEST).min():.0f}–"
          f"{(load_df.NORTH + load_df.HOUSTON + load_df.SOUTH + load_df.WEST).max():.0f} MW")

    load_out = out_dir / f"hourly_load_{date_str}.csv"
    load_df.to_csv(load_out, index=False)
    print(f"Wrote {load_out}")

    # --- Hourly CFs ---
    if args.wind_output and args.solar_output:
        print(f"\nParsing wind output from {args.wind_output}...")
        wind_mw  = parse_wind_actual(Path(args.wind_output),  date)
        print(f"  Wind range: {wind_mw.min():.0f}–{wind_mw.max():.0f} MW")

        print(f"Parsing solar output from {args.solar_output}...")
        solar_mw = parse_solar_actual(Path(args.solar_output), date)
        print(f"  Solar range: {solar_mw.min():.0f}–{solar_mw.max():.0f} MW")

        print(f"\nComputing CFs against gen.csv capacity...")
        cf_df = compute_cfs(wind_mw, solar_mw, Path(args.gen_csv))
        print(cf_df.to_string(index=False))

        cf_out = out_dir / f"hourly_cf_{date_str}.csv"
        cf_df.to_csv(cf_out, index=False)
        print(f"Wrote {cf_out}")
    else:
        print("\nNo wind/solar files specified — skipping CF computation.")
        print("Run with --wind-output and --solar-output to generate hourly_cf CSV.")

    print(f"\nDone. Outputs in {out_dir}/")
    print(f"  Set HOURLY_LOAD_CSV={out_dir}/hourly_load_{date_str}.csv")
    print(f"  Set HOURLY_CF_CSV={out_dir}/hourly_cf_{date_str}.csv")
    print(f"  Set SCED_DATE={date}")


if __name__ == "__main__":
    main()
