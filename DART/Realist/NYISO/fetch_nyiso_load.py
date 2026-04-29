"""
Fetch NYISO hourly zonal load data from the MIS public archive.

Downloads integrated real-time actual load CSVs (palIntegrated) from
mis.nyiso.com. Each monthly ZIP contains a CSV with timestamps and
load values for zones A through K.

Usage:
    python fetch_nyiso_load.py              # current year
    python fetch_nyiso_load.py --year 2024  # specific year
    python fetch_nyiso_load.py --year 2024 --month 7  # specific month
"""

import argparse
import csv
import io
import os
import sys
import zipfile
from datetime import datetime

import requests

# NYISO MIS archive base URL for integrated actual load
# Format: YYYYMMDD01pal_csv.zip
BASE_URL = "http://mis.nyiso.com/public/csv/palIntegrated/"

ZONE_LETTERS = list("ABCDEFGHIJK")
ZONE_NAMES = {
    "A": "WEST", "B": "GENESE", "C": "CENTRL", "D": "NORTH",
    "E": "MHK VL", "F": "CAPITL", "G": "HUD VL", "H": "MILLWD",
    "I": "DUNWOD", "J": "N.Y.C.", "K": "LONGIL",
}


def download_month(year, month, data_dir):
    """Download one month of load data. Returns path to extracted CSV or None."""
    date_str = f"{year}{month:02d}01"
    filename = f"{date_str}palIntegrated_csv.zip"
    url = BASE_URL + filename

    zip_path = os.path.join(data_dir, filename)
    csv_filename = f"{date_str}palIntegrated.csv"
    csv_path = os.path.join(data_dir, csv_filename)

    if os.path.exists(csv_path):
        print(f"  Already have: {csv_filename}")
        return csv_path

    print(f"  Downloading {filename}...")
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  Failed: {e}")
        return None

    # Extract CSV from ZIP
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
            # Find the CSV inside
            csv_name = None
            for n in names:
                if n.endswith(".csv"):
                    csv_name = n
                    break
            if csv_name is None:
                print(f"  No CSV found in ZIP. Contents: {names}")
                return None

            with open(csv_path, "wb") as f:
                f.write(zf.read(csv_name))
            print(f"  Extracted: {csv_filename}")
            return csv_path
    except zipfile.BadZipFile:
        print(f"  Bad ZIP file")
        return None


def parse_load_csv(csv_path):
    """
    Parse a NYISO palIntegrated CSV into hourly zone loads.

    NYISO format (varies slightly by year):
    - Columns: Time Stamp, Time Zone, Name, PTID, Load
    - One row per zone per timestamp
    - Name is the zone name (e.g., "CAPITL", "N.Y.C.")

    Returns list of dicts: {timestamp, hour, zone_letter, zone_name, load_mw}
    """
    records = []
    name_to_letter = {}
    for letter, name in ZONE_NAMES.items():
        name_to_letter[name.upper()] = letter

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_str = row.get("Time Stamp", "").strip()
            name = row.get("Name", "").strip().upper()
            load_str = row.get("Load", row.get("Integrated Load", "")).strip()

            if not ts_str or not name or not load_str:
                continue

            # Skip system-wide totals
            if name in ("NYCA", "TOTAL"):
                continue

            zone_letter = name_to_letter.get(name)
            if zone_letter is None:
                # Try partial match
                for zname, zletter in name_to_letter.items():
                    if zname in name or name in zname:
                        zone_letter = zletter
                        break
            if zone_letter is None:
                continue

            try:
                load_mw = float(load_str)
            except ValueError:
                continue

            # Parse timestamp
            try:
                # NYISO format: "MM/DD/YYYY HH:MM:SS" or "MM/DD/YYYY HH:MM"
                for fmt in ["%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        ts = datetime.strptime(ts_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    continue
                hour = ts.hour
            except Exception:
                continue

            records.append({
                "timestamp": ts_str,
                "date": ts.strftime("%Y-%m-%d"),
                "hour": hour,
                "zone_letter": zone_letter,
                "zone_name": name,
                "load_mw": load_mw,
            })

    return records


def aggregate_hourly(records):
    """Aggregate 5-min records to hourly by zone (take max or average)."""
    from collections import defaultdict

    # Group by (date, hour, zone)
    groups = defaultdict(list)
    for r in records:
        key = (r["date"], r["hour"], r["zone_letter"])
        groups[key].append(r["load_mw"])

    hourly = []
    for (date, hour, zone), loads in sorted(groups.items()):
        hourly.append({
            "date": date,
            "hour": hour,
            "zone": zone,
            "load_mw": sum(loads) / len(loads),  # average over intervals
        })
    return hourly


def save_hourly_csv(hourly_records, path):
    """Save hourly load as a wide-format CSV (one column per zone)."""
    from collections import defaultdict

    # Pivot: rows = (date, hour), columns = zones A-K
    pivot = defaultdict(dict)
    for r in hourly_records:
        key = (r["date"], r["hour"])
        pivot[key][r["zone"]] = r["load_mw"]

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        header = ["date", "hour"] + [f"Zone_{z}" for z in ZONE_LETTERS]
        writer.writerow(header)
        for (date, hour) in sorted(pivot.keys()):
            row = [date, hour]
            for z in ZONE_LETTERS:
                row.append(round(pivot[(date, hour)].get(z, 0), 1))
            writer.writerow(row)

    print(f"Saved {len(pivot)} hourly rows to {path}")


def print_summary(hourly_records, year):
    """Print load summary."""
    from collections import defaultdict

    zone_totals = defaultdict(float)
    zone_peaks = defaultdict(float)
    for r in hourly_records:
        zone_totals[r["zone"]] += r["load_mw"]
        zone_peaks[r["zone"]] = max(zone_peaks[r["zone"]], r["load_mw"])

    total_peak = 0
    # Find system peak (sum across zones for each hour)
    from collections import Counter
    hour_sums = Counter()
    for r in hourly_records:
        hour_sums[(r["date"], r["hour"])] += r["load_mw"]
    if hour_sums:
        total_peak = max(hour_sums.values())

    print(f"\n{'=' * 60}")
    print(f"NYISO Load Summary — {year}")
    print(f"{'=' * 60}")
    print(f"System peak: {total_peak:,.0f} MW")
    print(f"\nZone peaks:")
    for z in ZONE_LETTERS:
        if z in zone_peaks:
            zname = ZONE_NAMES.get(z, "?")
            print(f"  Zone {z} ({zname:>8s}): {zone_peaks[z]:8,.0f} MW peak")
    print()


def main():
    parser = argparse.ArgumentParser(description="Fetch NYISO hourly zonal load data")
    parser.add_argument("--year", type=int, default=datetime.now().year,
                        help="Year to download (default: current year)")
    parser.add_argument("--month", type=int, default=None,
                        help="Specific month (1-12). If omitted, downloads all available months.")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "grid_data")
    os.makedirs(data_dir, exist_ok=True)

    year = args.year
    months = [args.month] if args.month else list(range(1, 13))

    print(f"Fetching NYISO load data for {year}...")

    all_records = []
    for month in months:
        csv_path = download_month(year, month, data_dir)
        if csv_path:
            records = parse_load_csv(csv_path)
            all_records.extend(records)
            print(f"  Month {month:02d}: {len(records)} records")

    if not all_records:
        print("No data retrieved.")
        return

    hourly = aggregate_hourly(all_records)
    print_summary(hourly, year)

    out_path = os.path.join(data_dir, f"nyiso_load_{year}.csv")
    save_hourly_csv(hourly, out_path)


if __name__ == "__main__":
    main()
