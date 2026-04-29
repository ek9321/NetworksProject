#!/usr/bin/env python3
"""
Prepare hourly load and CF profiles for a specific calibration day.

Reads NYISO actual load CSVs (from fetch_nyiso_load.py) and computes
hourly zonal load (MW) and wind/solar capacity factors.

Usage:
    python prepare_calibration_day.py --date 2024-07-17
    python prepare_calibration_day.py --date 2024-01-15
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

import pandas as pd

NYISO_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(NYISO_DIR, "grid_data")

ZONE_LETTERS = list("ABCDEFGHIJK")


def load_day(year, date_str):
    """Load hourly zonal load for a specific date from the annual CSV."""
    load_file = os.path.join(DATA_DIR, f"nyiso_load_{year}.csv")
    if not os.path.exists(load_file):
        print(f"  Load file not found: {load_file}")
        print(f"  Run: python fetch_nyiso_load.py --year {year}")
        return None

    df = pd.read_csv(load_file)
    day_df = df[df["date"] == date_str].copy()
    if len(day_df) == 0:
        print(f"  No data for date {date_str} in {load_file}")
        return None

    day_df = day_df.sort_values("hour")
    print(f"  Found {len(day_df)} hourly rows for {date_str}")
    return day_df


def compute_cf(date_str, gen_csv):
    """
    Compute hourly capacity factors from NYISO fuel mix data.
    For now, uses simple seasonal profiles since fuel mix CSV
    requires separate download.
    """
    month = int(date_str.split("-")[1])

    # Seasonal wind CF profiles (upstate NY wind pattern)
    # Higher in winter/spring, lower in summer
    if month in (12, 1, 2, 3):
        wind_base = 0.35
    elif month in (4, 5, 10, 11):
        wind_base = 0.30
    else:
        wind_base = 0.20

    # Simple diurnal solar profile
    solar_profile = [
        0.0, 0.0, 0.0, 0.0, 0.0, 0.02,  # 0-5
        0.10, 0.25, 0.45, 0.60, 0.70, 0.75,  # 6-11
        0.75, 0.70, 0.60, 0.45, 0.25, 0.10,  # 12-17
        0.02, 0.0, 0.0, 0.0, 0.0, 0.0,  # 18-23
    ]

    # Wind has mild diurnal variation (slightly higher overnight)
    wind_profile = [
        wind_base * 1.1, wind_base * 1.1, wind_base * 1.05, wind_base * 1.0,
        wind_base * 0.95, wind_base * 0.90, wind_base * 0.85, wind_base * 0.85,
        wind_base * 0.85, wind_base * 0.90, wind_base * 0.95, wind_base * 1.0,
        wind_base * 1.0, wind_base * 0.95, wind_base * 0.90, wind_base * 0.90,
        wind_base * 0.95, wind_base * 1.0, wind_base * 1.05, wind_base * 1.1,
        wind_base * 1.15, wind_base * 1.15, wind_base * 1.1, wind_base * 1.1,
    ]

    # Hydro: relatively flat with seasonal variation
    if month in (4, 5, 6):  # spring runoff
        hydro_cf = 0.70
    elif month in (7, 8, 9):
        hydro_cf = 0.45
    else:
        hydro_cf = 0.55

    return wind_profile, solar_profile, hydro_cf


def main():
    parser = argparse.ArgumentParser(description="Prepare NYISO calibration day profiles")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    args = parser.parse_args()

    date_str = args.date
    year = int(date_str.split("-")[0])

    print(f"Preparing calibration day: {date_str}")

    # Load zonal load
    day_df = load_day(year, date_str)

    if day_df is not None:
        # Write hourly load CSV
        # Merge H/I into G (G+H+I combined)
        load_path = os.path.join(DATA_DIR, f"hourly_load_{date_str.replace('-', '')}.csv")
        with open(load_path, "w", newline="") as f:
            writer = csv.writer(f)
            # Zones A-G (G includes H+I), J, K
            header = ["hour", "A", "B", "C", "D", "E", "F", "G", "J", "K"]
            writer.writerow(header)
            for _, row in day_df.iterrows():
                h = int(row["hour"])
                g_load = float(row.get("Zone_G", 0))
                h_load = float(row.get("Zone_H", 0))
                i_load = float(row.get("Zone_I", 0))
                vals = [
                    h,
                    row.get("Zone_A", 0),
                    row.get("Zone_B", 0),
                    row.get("Zone_C", 0),
                    row.get("Zone_D", 0),
                    row.get("Zone_E", 0),
                    row.get("Zone_F", 0),
                    g_load + h_load + i_load,  # G+H+I combined
                    row.get("Zone_J", 0),
                    row.get("Zone_K", 0),
                ]
                writer.writerow(vals)
        print(f"  Wrote {load_path}")

        # Print load summary
        total_by_hour = day_df[[f"Zone_{z}" for z in ZONE_LETTERS]].sum(axis=1)
        print(f"  Peak system load: {total_by_hour.max():,.0f} MW")
        print(f"  Min system load:  {total_by_hour.min():,.0f} MW")
    else:
        print("  Skipping load profile (no data)")

    # Compute CF profiles
    wind_cf, solar_cf, hydro_cf = compute_cf(date_str, None)

    cf_path = os.path.join(DATA_DIR, f"hourly_cf_{date_str.replace('-', '')}.csv")
    with open(cf_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["hour", "Wind", "Solar", "Hydro"])
        for h in range(24):
            writer.writerow([h, round(wind_cf[h], 4), round(solar_cf[h], 4), round(hydro_cf, 4)])
    print(f"  Wrote {cf_path}")


if __name__ == "__main__":
    main()
