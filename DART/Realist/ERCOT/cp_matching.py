"""
CenterPoint Matching: Pass 10

Match unresolved CenterPoint Houston-area substations against OSM substations
using the decoded PSSE bus name (the segment before the double-underscore).

CenterPoint's PSSE bus naming: NAME__S##_8 or NAME__B138 or NAME__X##B8
The segment before '__' is the substation location name (often abbreviated
but phonetically close to the OSM full name).

Examples:
  CLINTN__B138  → CLINTN  → matches "Clinton Substation"
  DWNTWN__B138  → DWNTWN  → matches "Downtown Substation"
  BUSCH__S08_8  → BUSCH   → matches "Busch Substation"
  BAYWAY__B138  → BAYWAY  → matches "Bayway Substation"

Strategy:
  1. For each unresolved substation with '__' in its PSSE bus name:
     - Decode the pre-underscore name
     - Fuzzy-match against all named OSM substations in the load zone area
     - Use a broad Houston area bound (CenterPoint territory: ~29°N, ~95°W)
  2. Threshold: high ≥90, medium ≥82
  3. Avoid reusing OSM IDs already claimed by prior passes

Inputs:
  OIM/FirstPass/texas_matched_substations_v4.csv
  OIM/data/texas_substations.geojson
  SP_List_EB_Mapping/Settlement_Points_01292026_104938.csv

Outputs:
  OIM/FirstPass/texas_matched_substations_v5.csv
  ERCOT/cp_matching_report.md
"""

import csv as csv_mod
import json
import math
import os
import re
from collections import Counter

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCHED_V4 = os.path.join(ROOT, "OIM", "FirstPass", "texas_matched_substations_v4.csv")
OSM_SUBS   = os.path.join(ROOT, "OIM", "data", "texas_substations.geojson")
SP_CSV     = os.path.join(ROOT, "SP_List_EB_Mapping", "Settlement_Points_01292026_104938.csv")
OUT_CSV    = os.path.join(ROOT, "OIM", "FirstPass", "texas_matched_substations_v5.csv")
REPORT_MD  = os.path.join(ROOT, "ERCOT", "cp_matching_report.md")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# LZ bounding boxes (lat_min, lat_max, lon_min, lon_max)
LZ_BOUNDS = {
    "LZ_WEST":    (27.0, 35.5, -106.5, -99.0),
    "LZ_NORTH":   (31.5, 36.5, -100.0, -94.0),
    "LZ_HOUSTON": (28.5, 31.0,  -96.5, -93.5),
    "LZ_SOUTH":   (25.5, 31.0, -100.5, -95.5),
}

THRESHOLD_HIGH   = 90
THRESHOLD_MEDIUM = 82    # slightly tighter than default 80

# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------

STRIP_WORDS = {
    "SUBSTATION", "SUB", "SWITCHING", "STATION", "SWITCH", "PLANT",
    "GENERATING", "GENERATION", "GENERATOR", "POWER", "ENERGY",
    "ELECTRIC", "SOLAR", "WIND", "FARM", "CENTER", "FACILITY",
    "SWITCHYARD", "INTERCONNECT", "PROJECT", "COMPLEX", "DISTRIBUTION",
}


def canonicalize(s):
    if not s:
        return ""
    s = s.upper().strip()
    s = re.sub(r'\(.*?\)', '', s)
    s = re.sub(r'[^A-Z0-9\s]', ' ', s)
    tokens = [t for t in s.split() if t not in STRIP_WORDS]
    return " ".join(tokens).strip()


def decode_double_underscore(psse):
    """
    Extract the location name from a double-underscore PSSE bus name.

    Handles:
      CLINTN__B138    → CLINTN
      BUSCH__S08_8    → BUSCH
      BAYWAY__B138    → BAYWAY
      L_CICO__8_1Y   → CICO    (strip L_ prefix first)
      TNNALVIN__1    → NALVIN  (strip TN prefix first)
      BASF___POI_8   → BASF    (triple underscore variant)
    """
    s = psse.strip().upper()

    # Strip known prefixes
    if s.startswith('L_'):
        s = s[2:]
    if s.startswith('TN'):
        s = s[2:]

    # Split on double (or triple) underscore — take first segment
    if '__' in s:
        s = s.split('__')[0]
    elif '___' in s:
        s = s.split('___')[0]

    # Clean up trailing underscores and replace remaining with spaces
    s = re.sub(r'_+$', '', s)
    return s.replace('_', ' ').strip()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def ensemble_score(s1, s2):
    if not s1 or not s2:
        return 0.0
    tsr   = fuzz.token_sort_ratio(s1, s2)
    tsetr = fuzz.token_set_ratio(s1, s2)
    jw    = JaroWinkler.normalized_similarity(s1, s2) * 100
    return 0.3 * tsr + 0.4 * tsetr + 0.3 * jw


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


def in_lz_bounds(lat, lon, lz, buffer=1.5):
    if lz not in LZ_BOUNDS:
        return True
    lat_min, lat_max, lon_min, lon_max = LZ_BOUNDS[lz]
    return (lat_min - buffer <= lat <= lat_max + buffer and
            lon_min - buffer <= lon <= lon_max + buffer)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv_mod.DictReader(f))


def load_sp_psse():
    rows = load_csv(SP_CSV)
    def safe_float(v):
        try: return float(v)
        except: return 0.0
    rows_sorted = sorted(rows, key=lambda r: safe_float(r.get('VOLTAGE_LEVEL', 0)), reverse=True)
    index = {}
    for r in rows_sorted:
        sub = r.get('SUBSTATION', '').strip().upper()
        psse = r.get('PSSE_BUS_NAME', '').strip()
        if sub and psse and sub not in index:
            index[sub] = psse
    return index


def load_osm_all_lz(matched_osm_ids):
    """Load all named OSM substations, indexed by load zone."""
    with open(OSM_SUBS, encoding='utf-8') as f:
        data = json.load(f)

    result = []
    for feat in data['features']:
        p = feat['properties']
        name = p.get('name', '').strip()
        if not name:
            continue
        osm_id = p['osm_id']
        if osm_id in matched_osm_ids:
            continue
        lon, lat = feat['geometry']['coordinates']
        result.append({
            'osm_id':   osm_id,
            'name':     name,
            'canon':    canonicalize(name),
            'lat':      lat,
            'lon':      lon,
            'voltage':  p.get('voltage_kv'),
            'operator': p.get('operator') or '',
        })
    return result


# ---------------------------------------------------------------------------
# Pass 10: double-underscore PSSE → OSM matching
# ---------------------------------------------------------------------------

def pass_10(unresolved_dd, osm_feats, used_osm_ids):
    """
    unresolved_dd: list of rows with '__' in PSSE name, still unresolved
    osm_feats: all available (unmatched) named OSM substations
    Returns list of match dicts and updated used_osm_ids set.
    """
    new_matches = []
    local_used = set(used_osm_ids)

    for item in unresolved_dd:
        sub = item['sub']
        decoded = item['decoded']
        lz = item['lz']

        if not decoded:
            continue

        cand_canon = canonicalize(decoded)
        if not cand_canon:
            continue

        best_score = 0
        best_match = None

        for osm in osm_feats:
            if osm['osm_id'] in local_used:
                continue
            # Geographic constraint
            if not in_lz_bounds(osm['lat'], osm['lon'], lz):
                continue
            sc = ensemble_score(cand_canon, osm['canon'])
            if sc > best_score:
                best_score = sc
                best_match = osm

        if best_score >= THRESHOLD_MEDIUM and best_match:
            confidence = 'high' if best_score >= THRESHOLD_HIGH else 'medium'
            new_matches.append({
                'sub':          sub,
                'lat':          best_match['lat'],
                'lon':          best_match['lon'],
                'osm_id':       best_match['osm_id'],
                'score':        round(best_score, 1),
                'matched_name': best_match['name'],
                'decoded':      decoded,
                'confidence':   confidence,
            })
            local_used.add(best_match['osm_id'])

    return new_matches, local_used


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading data…")
    rows = load_csv(MATCHED_V4)
    sp_psse = load_sp_psse()

    # Build matched OSM IDs set
    matched_osm_ids = set()
    for r in rows:
        try:
            matched_osm_ids.add(int(float(r['osm_id'])))
        except (TypeError, ValueError):
            pass

    # Load all unmatched named OSM substations
    osm_all = load_osm_all_lz(matched_osm_ids)
    print(f"  Available (unmatched) OSM substations: {len(osm_all)}")

    # Find unresolved substations with double-underscore PSSE names
    unresolved = [r for r in rows if r['match_source'] in ('propagated', 'lz_centroid')]
    unresolved_dd = []
    for r in unresolved:
        sub = r['ercot_substation'].upper()
        psse = sp_psse.get(sub, '')
        if '__' in psse or '___' in psse:
            decoded = decode_double_underscore(psse)
            unresolved_dd.append({
                'sub': sub, 'psse': psse, 'decoded': decoded,
                'lz': r.get('load_zone', ''), 'kv': r.get('max_voltage_kv', ''),
            })

    print(f"  Unresolved double-underscore substations: {len(unresolved_dd)}")

    # Run Pass 10
    print("\nPass 10: double-underscore PSSE → OSM matching…")
    matches, _ = pass_10(unresolved_dd, osm_all, matched_osm_ids)
    print(f"  New matches: {len(matches)}")

    match_lookup = {m['sub']: m for m in matches}
    high_count = sum(1 for m in matches if m['confidence'] == 'high')
    med_count  = sum(1 for m in matches if m['confidence'] == 'medium')

    # -----------------------------------------------------------------------
    # Write output CSV
    # -----------------------------------------------------------------------
    print("\nWriting output CSV…")
    out_rows = []
    for r in rows:
        sub = r['ercot_substation'].upper()
        if sub in match_lookup:
            m = match_lookup[sub]
            r['lat']          = m['lat']
            r['lon']          = m['lon']
            r['match_source'] = 'cp_osm'
            r['confidence']   = m['confidence']
            r['score']        = m['score']
            r['matched_name'] = m['matched_name']
            r['osm_id']       = m['osm_id']
        out_rows.append(r)

    fieldnames = list(rows[0].keys())
    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv_mod.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"  Written: {OUT_CSV}")

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    v4 = rows   # rows was already updated in-place (same dicts)
    v5 = out_rows
    v4_src  = Counter(r['match_source'] for r in load_csv(MATCHED_V4))
    v5_src  = Counter(r['match_source'] for r in v5)
    v4_conf = Counter(r['confidence'] for r in load_csv(MATCHED_V4))
    v5_conf = Counter(r['confidence'] for r in v5)

    report_lines = [
        "# CenterPoint Matching Results (Pass 10)\n",
        "## Before vs After\n",
        "| Source | V4 Count | V5 Count | Change |",
        "|---|---|---|---|",
    ]
    for src in sorted(set(list(v4_src) + list(v5_src))):
        v4c, v5c = v4_src.get(src, 0), v5_src.get(src, 0)
        report_lines.append(f"| {src} | {v4c} | {v5c} | {v5c-v4c:+d} |")

    report_lines += [
        f"\n**Total substations:** {len(v4)} → {len(v5)}",
        "\n## Confidence Summary\n",
        "| Confidence | V4 | V5 | Change |",
        "|---|---|---|---|",
    ]
    for c in ('high', 'medium', 'low', 'none'):
        v4c, v5c = v4_conf.get(c, 0), v5_conf.get(c, 0)
        report_lines.append(f"| {c} | {v4c} | {v5c} | {v5c-v4c:+d} |")

    report_lines += [
        "\n## Pass 10 — CenterPoint Double-Underscore → OSM\n",
        f"- Attempted: **{len(unresolved_dd)}** unresolved double-underscore substations",
        f"- New matches: **{len(matches)}** (high: {high_count}, medium: {med_count})",
        f"- Still unresolved: **{v5_src.get('propagated', 0) + v5_src.get('lz_centroid', 0)}**",
        "\n### All new matches\n",
        "| Substation | PSSE Name | Decoded | OSM Match | Score | Conf |",
        "|---|---|---|---|---|---|",
    ]
    for m in sorted(matches, key=lambda x: -x['score']):
        item = next(i for i in unresolved_dd if i['sub'] == m['sub'])
        report_lines.append(
            f"| {m['sub']} | {item['psse']} | {m['decoded']} | {m['matched_name']} | {m['score']} | {m['confidence']} |"
        )

    report = "\n".join(report_lines) + "\n"
    with open(REPORT_MD, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  Report: {REPORT_MD}")

    print(f"\nDone. {len(matches)} new matches (high={high_count}, medium={med_count}).")
    print(f"Still unresolved: {v5_src.get('propagated',0) + v5_src.get('lz_centroid',0)}")


if __name__ == "__main__":
    main()
