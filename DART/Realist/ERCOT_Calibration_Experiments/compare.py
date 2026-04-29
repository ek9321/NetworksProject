"""
compare.py — Summarize all ERCOT calibration experiment results.

Usage:
    python compare.py

Reads results/<tag>/hourly_summary.csv for each experiment and prints a
comparison table. Also writes comparison_summary.csv next to this script.
"""

import csv
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"

# Canonical order for display; any tags not listed here appear at the end.
DISPLAY_ORDER = ["v1", "cluster_v1", "v2", "v3", "v4", "v5", "floor", "2x"]


def load_hourly(path):
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            rows.append({
                k: (float(v) if k not in ("Date",) else v)
                for k, v in row.items()
            })
    return rows


def summarize(rows):
    n = len(rows)
    steady = [r for r in rows if r["Hour"] >= 9]
    avail = sum(r["RenewablesAvailable"] for r in rows)
    return {
        "h0_shed_mw":    rows[0]["LoadShedding"],
        "ss_shed_mw":    sum(r["LoadShedding"] for r in steady) / len(steady),
        "mean_shed_mw":  sum(r["LoadShedding"] for r in rows) / n,
        "curtail_mw":    sum(r["RenewablesCurtailment"] for r in steady) / len(steady),
        "renew_used_mw": sum(r["RenewablesUsed"] for r in rows) / n,
        "renew_util_pct": 100 * sum(r["RenewablesUsed"] for r in rows) / avail if avail else 0,
        "price_mwh":     sum(r["Price"] for r in rows) / n,
        "demand_mw":     rows[0]["Demand"],
    }


def main():
    experiments = {}
    for path in sorted(RESULTS_DIR.glob("*/hourly_summary.csv")):
        tag = path.parent.name
        try:
            experiments[tag] = summarize(load_hourly(path))
        except Exception as e:
            print(f"  [skip] {tag}: {e}")

    if not experiments:
        print("No results found. Place hourly_summary.csv files in results/<tag>/")
        return

    # Sort by display order, then alphabetically for unknowns.
    def sort_key(tag):
        try:
            return (0, DISPLAY_ORDER.index(tag))
        except ValueError:
            return (1, tag)

    tags = sorted(experiments.keys(), key=sort_key)

    # Print table.
    header = (
        f"{'tag':<14}  {'h0_shed':>9}  {'ss_shed':>9}  "
        f"{'curtail':>9}  {'renew%':>7}  {'price':>8}  {'demand':>9}"
    )
    sep = "-" * len(header)
    print(header)
    print(sep)
    for tag in tags:
        s = experiments[tag]
        print(
            f"{tag:<14}  {s['h0_shed_mw']:>9,.0f}  {s['ss_shed_mw']:>9,.0f}  "
            f"{s['curtail_mw']:>9,.0f}  {s['renew_util_pct']:>6.1f}%  "
            f"{s['price_mwh']:>8.2f}  {s['demand_mw']:>9,.0f}"
        )

    # Write CSV.
    out_path = Path(__file__).parent / "comparison_summary.csv"
    fields = ["tag", "h0_shed_mw", "ss_shed_mw", "curtail_mw",
              "renew_util_pct", "price_mwh", "demand_mw"]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for tag in tags:
            s = experiments[tag]
            w.writerow({"tag": tag, **{k: s[k] for k in fields[1:]}})
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
