"""
Extract Unit Capacities table from MORA_April2026.pdf (pages 6–22) into a CSV.

Column x-boundaries determined from word-position analysis:
  row_num     : x0 < 46
  unit_name   : 46 <= x0 < 400
  inr         : 400 <= x0 < 470
  unit_code   : 470 <= x0 < 610
  county      : 610 <= x0 < 738
  fuel        : 738 <= x0 < 869
  zone        : 869 <= x0 < 957
  in_service  : 957 <= x0 < 1035
  installed_mw: 1035 <= x0 < 1115
  apr2026_mora: x0 >= 1115
"""

import csv
import re
import pdfplumber

PDF_PATH = "ERCOT/MORA_April2026.pdf"
OUT_PATH = "ERCOT/MORA_April2026_unit_capacities.csv"

# Pages 6–22 are indices 5–21
PAGE_RANGE = range(5, 22)

# Column x-boundaries
COLS = {
    "row_num":      (0,     46),
    "unit_name":    (46,    400),
    "inr":          (400,   470),
    "unit_code":    (470,   610),
    "county":       (610,   738),
    "fuel":         (738,   869),
    "zone":         (869,   957),
    "in_service":   (957,   1035),
    "installed_mw": (1035,  1115),
    "apr2026_mora": (1115,  9999),
}

# Lines to skip entirely (section headers, footnotes, page markers, totals)
SKIP_PATTERNS = [
    r"^ERCOT PUBLIC",
    r"^\d+$",                        # bare page numbers
    r"^Unit Capacities",
    r"^INSTALLED",
    r"^CAPACITY\s+APR",
    r"^UNIT NAME\s+INR",
    r"^\(MW\)",
    r"^RATING\s+MORA",
    r"^\[",                          # footnote lines starting with [
    r"^Note",
    r"^Capacity Pending Retirement",
    r"^Available Mothball",
    r"^Private-Use Network",
    r"Capacity Total",               # subtotal rows
    r"Capacity Contribution",
    r"Settlement Only Distributed",
    r"^Operational Hydro Resources",
    r"^RMR and Other Resource Agreement Capacity Total",
    r"^Hydro SODG",
    r"Operational Capacity.*Total",
    r"^Switchable Capacity Total",
    r"^Non-Synchronous Ties Total",
]

# Section header patterns — captured as metadata, row skipped from data output
SECTION_PATTERNS = [
    r"^Operational Resources \(Thermal\)",
    r"^Operational Resources \(Wind\)",
    r"^Operational Resources \(Solar\)",
    r"^Operational Resources \(Storage\)",
    r"^Operational Resources \(Switchable\)",
    r"^Operational Resources \(Hydro\)",
    r"^Planned Resources",
    r"^Non-Synchronous Tie Resources",
    r"^Reliability Must-Run",
    r"^Operational Capacity",          # total rows
    r"^Switchable Capacity",           # subtotal
    r"^Hydro (SODG|Cap)",
    r"^Hydro Capacity",
    r"^Operational Hydro",
    r"^Synchronized but not Approved",
    r"^Operational Capacity.*Synchronized",
    r"^Synchronized but Not Approved",
    r"^Wind Operational Capacity Total",
    r"^Solar Operational Capacity Total",
    r"^Storage Operational Capacity Total",
    r"^Non-Synchronous Ties Total",
    r"^Operational Capacity.*Total",
    r"^\d+ Operational Capacity",
    r"^\d+ Wind Operational",
    r"^\d+ Solar Operational",
    r"^\d+ Storage Operational",
    r"^\d+ Switchable Capacity",
    r"^\d+ Hydro",
    r"^\d+ Non-Synchronous",
    r"^\d+ Planned",
    r"^\d+ Reliability Must",
    r"^\d+ Operational Resources",
    r"^\d+ Available Mothball",
    r"^\d+ Private-Use Network",
    r"^\d+ Capacity Pending",
]


def classify_x(x0):
    for col_name, (lo, hi) in COLS.items():
        if lo <= x0 < hi:
            return col_name
    return None


def group_words_by_row(words, y_tolerance=2.0):
    """Group words by their top (y) position."""
    rows = {}
    for w in words:
        top = w["top"]
        # Find an existing row within tolerance
        matched_key = None
        for key in rows:
            if abs(key - top) <= y_tolerance:
                matched_key = key
                break
        if matched_key is None:
            matched_key = top
            rows[matched_key] = {}
        col = classify_x(w["x0"])
        if col:
            rows[matched_key].setdefault(col, []).append(w["text"])
    return rows


def should_skip(line):
    for pat in SKIP_PATTERNS:
        if re.match(pat, line, re.IGNORECASE):
            return True
    return False


def is_section_header(line):
    for pat in SECTION_PATTERNS:
        if re.match(pat, line, re.IGNORECASE):
            return True
    return False


def clean_number(s):
    if not s or s.strip() in ("-", "–", ""):
        return ""
    return s.replace(",", "").strip()


def extract_rows():
    records = []
    current_section = ""

    with pdfplumber.open(PDF_PATH) as pdf:
        for page_idx in PAGE_RANGE:
            page = pdf.pages[page_idx]
            words = page.extract_words(x_tolerance=2, y_tolerance=2)
            grouped = group_words_by_row(words, y_tolerance=2.0)

            for top_y in sorted(grouped.keys()):
                cols = grouped[top_y]

                # Reconstruct readable text per column
                def col_text(name):
                    return " ".join(cols.get(name, [])).strip()

                row_num   = col_text("row_num")
                unit_name = col_text("unit_name")
                inr       = col_text("inr")
                unit_code = col_text("unit_code")
                county    = col_text("county")
                fuel      = col_text("fuel")
                zone      = col_text("zone")
                in_svc    = col_text("in_service")
                inst_mw   = col_text("installed_mw")
                mora      = col_text("apr2026_mora")

                # Full line for pattern matching
                full = " ".join(filter(None, [row_num, unit_name, inr, unit_code,
                                              county, fuel, zone, in_svc, inst_mw, mora]))
                if not full.strip():
                    continue

                if should_skip(full):
                    continue

                if is_section_header(full):
                    # Strip any leading row-number prefix (e.g. "504 Operational...")
                    current_section = re.sub(r"^\d+\s+", "", full.strip())
                    continue

                # A valid data row must have at least a unit_name
                if not unit_name:
                    continue

                # Strip leading row number from unit_name if present
                unit_name_clean = re.sub(r"^\d+\s+", "", unit_name).strip()
                if not unit_name_clean:
                    unit_name_clean = unit_name

                # Fix spaced-out field values caused by PDF character spacing
                def despacify(s):
                    # "S O L A R" -> "SOLAR", "G A S - C C" -> "GAS-CC"
                    if re.match(r"^([A-Z0-9] )+[A-Z0-9]$", s):
                        return s.replace(" ", "")
                    if re.match(r"^([A-Z0-9] )*[A-Z0-9]( [-][A-Z0-9]( [A-Z0-9])*)*$", s):
                        return s.replace(" ", "")
                    return s

                fuel_clean = despacify(fuel)
                zone_clean = despacify(zone)

                # Skip rows that are clearly totals/subtotals slipping through
                name_lower = unit_name_clean.lower()
                if any(kw in name_lower for kw in [
                    "capacity total", "capacity contribution", "settlement only distributed",
                    "tie resources total", "rmr and other resource agreement capacity",
                ]):
                    continue

                records.append({
                    "section":       current_section,
                    "row_num":       row_num.strip(),
                    "unit_name":     unit_name_clean,
                    "inr":           inr,
                    "unit_code":     unit_code,
                    "county":        county,
                    "fuel":          fuel_clean,
                    "zone":          zone_clean,
                    "in_service":    in_svc,
                    "installed_mw":  clean_number(inst_mw),
                    "apr2026_mora":  clean_number(mora),
                })

    # Drop rows whose section got misclassified as a total/contribution row
    bad_section_keywords = ["Capacity Total", "Capacity Contribution", "Mothballed"]
    records = [
        r for r in records
        if not any(kw in r["section"] for kw in bad_section_keywords)
        and r["unit_name"] not in ("Mothballed Resources",)
        and r["fuel"] != ""  # discard rows with no fuel (header bleed-through)
    ]

    return records


def main():
    print("Extracting...")
    records = extract_rows()
    print(f"Extracted {len(records)} rows")

    fieldnames = ["section", "row_num", "unit_name", "inr", "unit_code",
                  "county", "fuel", "zone", "in_service", "installed_mw", "apr2026_mora"]

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"Saved to {OUT_PATH}")

    # Print a sample
    print("\nSample rows:")
    for r in records[:5]:
        print(r)
    print("...")
    for r in records[400:403]:
        print(r)


if __name__ == "__main__":
    main()
