"""
GNIS Matching: Pass 8

Match unresolved ERCOT settlement point substations against the USGS GNIS
Texas feature database (populated places, civil areas, streams, etc.)

Strategy:
  1. Extract the human-readable portion of the PSSE_BUS_NAME
  2. Canonicalize and fuzzy-match against GNIS feature names
  3. Geographic constraint: feature must fall within the substation's load zone bounds
  4. Feature class priority: Populated Place / Civil / Census first, others penalised
  5. Write updated match CSV and report

Inputs:
  data/raw/gnis/Text/DomesticNames_TX.txt
  OIM/FirstPass/texas_matched_substations_v2.csv
  SP_List_EB_Mapping/Settlement_Points_01292026_104938.csv

Outputs:
  OIM/FirstPass/texas_matched_substations_v3.csv
  ERCOT/gnis_matching_report.md
"""

import csv
import math
import os
import re
from collections import defaultdict, Counter

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GNIS_TXT   = os.path.join(ROOT, "data", "raw", "gnis", "Text", "DomesticNames_TX.txt")
MATCHED_V2 = os.path.join(ROOT, "OIM", "FirstPass", "texas_matched_substations_v2.csv")
SP_CSV     = os.path.join(ROOT, "SP_List_EB_Mapping", "Settlement_Points_01292026_104938.csv")
OUT_CSV    = os.path.join(ROOT, "OIM", "FirstPass", "texas_matched_substations_v3.csv")
REPORT_MD  = os.path.join(ROOT, "ERCOT", "gnis_matching_report.md")

# Load zone approximate bounding boxes (same as match_nodes.py)
LZ_BOUNDS = {
    "LZ_WEST":    (27.0, 35.5, -106.5, -99.0),
    "LZ_NORTH":   (31.5, 36.5, -100.0, -94.0),
    "LZ_HOUSTON": (28.5, 31.0,  -96.5, -93.5),
    "LZ_SOUTH":   (25.5, 31.0, -100.5, -95.5),
}

# GNIS feature classes in descending match priority
PRIORITY_CLASSES = {
    "Populated Place": 1.00,
    "Civil":           1.00,
    "Census":          0.95,
    "Locale":          0.90,
    "Building":        0.85,
    "Airport":         0.80,
    "School":          0.75,
    "Church":          0.70,
    "Post Office":     0.70,
    "Hospital":        0.70,
    "Stream":          0.60,
    "Lake":            0.55,
    "Reservoir":       0.55,
    "Valley":          0.50,
    "Park":            0.50,
    "Summit":          0.45,
}
DEFAULT_PRIORITY = 0.40

THRESHOLD_HIGH   = 90
THRESHOLD_MEDIUM = 80

# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------

STRIP_WORDS = {
    "SUBSTATION", "SWITCHING", "STATION", "SWITCH", "PLANT",
    "GENERATING", "GENERATION", "GENERATOR", "POWER", "ENERGY",
    "ELECTRIC", "SOLAR", "WIND", "FARM", "CENTER", "FACILITY",
    "COMMUNITY", "HISTORICAL", "HIST", "CDP",
}

def canonicalize(name):
    if not name:
        return ""
    s = name.upper().strip()
    # Remove parenthetical suffixes like "(historical)"
    s = re.sub(r'\(.*?\)', '', s)
    s = re.sub(r'[^A-Z0-9\s]', ' ', s)
    tokens = [t for t in s.split() if t not in STRIP_WORDS]
    return " ".join(tokens).strip()

def psse_to_readable(psse_bus_name):
    """
    Extract the human-readable place name from a PSSE bus name.

    Patterns handled:
      ACTON              -> ACTON
      ACTON_8            -> ACTON      (strip _voltage_digit)
      ACTON2_8           -> ACTON      (strip trailing digits + voltage)
      L_ADAMSV8_1Y       -> ADAMSV     (strip L_ prefix and suffix)
      ADICKS__B138       -> ADICKS     (CenterPoint double-underscore)
      ALMEDA26T3_8       -> ALMEDA     (strip digits+tap+voltage)
      ALIEF__S09_8       -> ALIEF      (CenterPoint)
      AIRPRO POI         -> AIRPRO     (strip POI)
      TNABBYBEND1        -> ABBYBEND   (strip TN prefix)
      ACTON4A            -> ACTON      (AEP _4A/_7A suffix)
      ABERNATH           -> ABERNATH
    """
    s = psse_bus_name.strip().upper()

    # Remove TN prefix (TNMP buses)
    s = re.sub(r'^TN', '', s)

    # Remove L_ prefix
    s = re.sub(r'^L_', '', s)

    # CenterPoint double-underscore: take only first segment
    if '__' in s:
        s = s.split('__')[0]

    # Strip trailing _voltcode patterns: _8, _5, _9, _2, _1Y etc.
    s = re.sub(r'_[0-9]+[A-Z]*$', '', s)
    s = re.sub(r'_[0-9]+[A-Z]*_[0-9]+[A-Z]*$', '', s)

    # Strip AEP zone+voltage suffix: 4A, 7A, 2A, 9, 8
    s = re.sub(r'[479]A$', '', s)
    s = re.sub(r'[289]$', '', s)

    # Strip trailing digits and common suffixes
    s = re.sub(r'(POI|TAP[A-Z]?|SW|RD|LN|STA|_RC|_FD)$', '', s)
    s = re.sub(r'[0-9]+[A-Z]?$', '', s)

    # Replace underscores with spaces
    s = s.replace('_', ' ').strip()

    # Remove very short trailing tokens (single chars)
    tokens = [t for t in s.split() if len(t) > 1]
    return " ".join(tokens).strip()

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

def in_lz_bounds(lat, lon, lz):
    if lz not in LZ_BOUNDS:
        return True
    lat_min, lat_max, lon_min, lon_max = LZ_BOUNDS[lz]
    # Allow 1-degree buffer around LZ bounds
    return (lat_min - 1 <= lat <= lat_max + 1 and
            lon_min - 1 <= lon <= lon_max + 1)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_gnis():
    features = []
    with open(GNIS_TXT, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter='|')
        for row in reader:
            try:
                lat = float(row['prim_lat_dec'])
                lon = float(row['prim_long_dec'])
            except (ValueError, KeyError):
                continue
            if not row['feature_name']:
                continue
            features.append({
                'name':      row['feature_name'],
                'canonical': canonicalize(row['feature_name']),
                'class':     row['feature_class'],
                'county':    row['county_name'].upper().strip(),
                'lat':       lat,
                'lon':       lon,
            })
    return features

def load_matches_v2():
    with open(MATCHED_V2) as f:
        return {r['ercot_substation']: dict(r) for r in csv.DictReader(f)}

def load_sp():
    sp_by_sub = defaultdict(list)
    with open(SP_CSV) as f:
        for r in csv.DictReader(f):
            sp_by_sub[r['SUBSTATION']].append(r)
    return sp_by_sub

# ---------------------------------------------------------------------------
# Build GNIS index
# ---------------------------------------------------------------------------

def build_gnis_index(features):
    """
    Returns a dict: first_token (4+ chars) -> list of features.
    Also a full-name exact lookup dict.
    """
    by_prefix = defaultdict(list)
    exact = {}
    for feat in features:
        canon = feat['canonical']
        if not canon:
            continue
        # Exact canonical lookup
        exact[canon] = feat
        # Prefix index on first token
        first = canon.split()[0] if canon.split() else ''
        if len(first) >= 3:
            by_prefix[first[:4]].append(feat)
        # Also index on full 5-char prefix of the whole canonical string
        by_prefix[canon[:5]].append(feat)
    return by_prefix, exact

# ---------------------------------------------------------------------------
# Pass 8: GNIS matching
# ---------------------------------------------------------------------------

def run_gnis_pass(matches, sp_by_sub, gnis_features):
    print("Pass 8: GNIS place-name matching...")

    by_prefix, exact_lookup = build_gnis_index(gnis_features)

    target_sources = {'propagated', 'lz_centroid', 'mora_county_centroid'}
    new_matches = {}
    attempted = 0
    skipped_short = 0

    for sub, m in matches.items():
        if m.get('match_source') not in target_sources:
            continue
        if m.get('confidence') in ('high', 'medium'):
            continue

        sp_rows = sp_by_sub.get(sub, [])
        if not sp_rows:
            continue

        psse = sp_rows[0]['PSSE_BUS_NAME']
        lz   = sp_rows[0]['SETTLEMENT_LOAD_ZONE']

        readable = psse_to_readable(psse)
        canon    = canonicalize(readable)

        if not canon or len(canon) < 3:
            skipped_short += 1
            continue

        attempted += 1

        # Candidate gathering: prefix index + exact
        first_token = canon.split()[0] if canon.split() else ''
        candidates = list(by_prefix.get(first_token[:4], []))
        candidates += by_prefix.get(canon[:5], [])
        if canon in exact_lookup:
            candidates.append(exact_lookup[canon])

        # Deduplicate by (name, lat, lon)
        seen = set()
        unique = []
        for c in candidates:
            key = (c['name'], c['lat'], c['lon'])
            if key not in seen:
                seen.add(key)
                unique.append(c)

        best_score = 0.0
        best_feat  = None

        for feat in unique:
            # Geographic filter
            if not in_lz_bounds(feat['lat'], feat['lon'], lz):
                continue

            raw = ensemble_score(canon, feat['canonical'])
            if raw <= 0:
                continue

            # Feature class priority multiplier
            priority = PRIORITY_CLASSES.get(feat['class'], DEFAULT_PRIORITY)
            score = raw * priority

            # Exact-match bonus
            if canon == feat['canonical']:
                score = min(100.0, score * 1.05)

            # Length-ratio guard: penalise if one name is much longer
            e = canon.replace(' ', '')
            c = feat['canonical'].replace(' ', '')
            if e and c:
                ratio = min(len(e), len(c)) / max(len(e), len(c))
                if ratio < 0.35:
                    score *= 0.6

            if score > best_score:
                best_score = score
                best_feat  = feat

        if best_score >= THRESHOLD_MEDIUM and best_feat:
            conf = 'high' if best_score >= THRESHOLD_HIGH else 'medium'
            new_matches[sub] = {
                'lat':          round(best_feat['lat'], 6),
                'lon':          round(best_feat['lon'], 6),
                'match_source': 'gnis',
                'confidence':   conf,
                'score':        round(best_score, 1),
                'matched_name': best_feat['name'],
                'gnis_class':   best_feat['class'],
                'gnis_county':  best_feat['county'],
                'psse_readable': readable,
            }

    print(f"  Attempted: {attempted}  Skipped (name too short): {skipped_short}")
    print(f"  New matches: {len(new_matches)}")
    return new_matches

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

FIELDNAMES = [
    'ercot_substation', 'lat', 'lon', 'match_source', 'confidence',
    'score', 'matched_name', 'load_zone', 'max_voltage_kv',
    'eia_plant_code', 'osm_id', 'propagated_from',
    'mora_county', 'mora_fuel', 'county_validated', 'county_dist_km',
    'gnis_class', 'gnis_county', 'psse_readable',
]

def write_csv(matches, sp_by_sub, out_path):
    sub_lz   = {sub: rows[0]['SETTLEMENT_LOAD_ZONE'] for sub, rows in sp_by_sub.items() if rows}
    sub_volt = {}
    for sub, rows in sp_by_sub.items():
        vs = set()
        for r in rows:
            try: vs.add(float(r['VOLTAGE_LEVEL']))
            except: pass
        if vs:
            sub_volt[sub] = max(vs)

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
        writer.writeheader()
        for sub, m in sorted(matches.items()):
            row = dict(m)
            row['ercot_substation'] = sub
            row.setdefault('load_zone', sub_lz.get(sub, ''))
            row.setdefault('max_voltage_kv', sub_volt.get(sub, ''))
            writer.writerow(row)
    print(f"Saved: {out_path}")

def write_report(matches_v2, matches_v3, new_matches, out_path):
    src_v2 = Counter(m['match_source'] for m in matches_v2.values())
    src_v3 = Counter(m['match_source'] for m in matches_v3.values())
    conf_v2 = Counter(m['confidence'] for m in matches_v2.values())
    conf_v3 = Counter(m['confidence'] for m in matches_v3.values())

    # Break down new matches by confidence and GNIS class
    conf_new  = Counter(m['confidence']  for m in new_matches.values())
    class_new = Counter(m['gnis_class']  for m in new_matches.values())
    lz_new    = Counter(
        matches_v3[s].get('load_zone', '')
        for s in new_matches
    )

    with open(out_path, 'w') as f:
        f.write("# GNIS Matching Results (Pass 8)\n\n")

        f.write("## Summary\n\n")
        f.write(f"- New GNIS matches: **{len(new_matches)}**\n")
        f.write(f"  - High confidence (≥{THRESHOLD_HIGH}): {conf_new.get('high', 0)}\n")
        f.write(f"  - Medium confidence ({THRESHOLD_MEDIUM}–{THRESHOLD_HIGH}): {conf_new.get('medium', 0)}\n\n")

        f.write("## Before vs After\n\n")
        all_srcs = sorted(set(src_v2) | set(src_v3))
        f.write("| Source | V2 | V3 | Change |\n|---|---|---|---|\n")
        for s in all_srcs:
            c2 = src_v2.get(s, 0); c3 = src_v3.get(s, 0)
            f.write(f"| {s} | {c2} | {c3} | {c3-c2:+d} |\n")
        f.write(f"\n**Total:** {len(matches_v2)} → {len(matches_v3)}\n\n")

        f.write("## Confidence Summary\n\n")
        f.write("| Confidence | V2 | V3 | Change |\n|---|---|---|---|\n")
        for c in ['high', 'medium', 'low', 'none']:
            c2 = conf_v2.get(c, 0); c3 = conf_v3.get(c, 0)
            f.write(f"| {c} | {c2} | {c3} | {c3-c2:+d} |\n")
        f.write("\n")

        f.write("## New Matches by GNIS Feature Class\n\n")
        f.write("| Feature Class | Count |\n|---|---|\n")
        for cls, n in class_new.most_common():
            f.write(f"| {cls} | {n} |\n")
        f.write("\n")

        f.write("## New Matches by Load Zone\n\n")
        f.write("| Load Zone | Count |\n|---|---|\n")
        for lz, n in lz_new.most_common():
            f.write(f"| {lz} | {n} |\n")
        f.write("\n")

        f.write("## Sample Matches\n\n")
        f.write("| Substation | PSSE Readable | Matched GNIS Name | Class | County | Score | Conf |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        # Sort by score desc, show up to 60
        sorted_new = sorted(new_matches.items(), key=lambda x: -x[1]['score'])
        for sub, m in sorted_new[:60]:
            f.write(f"| {sub} | {m.get('psse_readable','')} | {m['matched_name']} | "
                    f"{m['gnis_class']} | {m['gnis_county'].title()} | "
                    f"{m['score']} | {m['confidence']} |\n")
        f.write("\n")

        # Flag suspicious matches (short PSSE name matched a long GNIS name)
        suspicious = {s: m for s, m in new_matches.items()
                      if len(m.get('psse_readable','')) <= 4
                      and m['confidence'] == 'medium'}
        if suspicious:
            f.write("## Short-Name Matches to Review\n\n")
            f.write("These matched on a PSSE name of ≤4 characters — worth spot-checking.\n\n")
            f.write("| Substation | PSSE Readable | Matched | Score |\n|---|---|---|---|\n")
            for sub, m in sorted(suspicious.items()):
                f.write(f"| {sub} | {m.get('psse_readable','')} | {m['matched_name']} | {m['score']} |\n")

    print(f"Saved: {out_path}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading data...")
    gnis_features = load_gnis()
    matches_v2    = load_matches_v2()
    sp_by_sub     = load_sp()

    tx_features = [f for f in gnis_features]  # all are TX from this file
    print(f"  GNIS Texas features: {len(tx_features)}")
    print(f"  Existing matches (v2): {len(matches_v2)}")
    print()

    # Run pass
    new_matches = run_gnis_pass(matches_v2, sp_by_sub, tx_features)
    print()

    # Merge
    matches_v3 = {s: dict(m) for s, m in matches_v2.items()}
    for sub, new_m in new_matches.items():
        matches_v3[sub].update(new_m)

    # Enrich with load_zone
    for sub, m in matches_v3.items():
        rows = sp_by_sub.get(sub, [])
        if rows:
            m.setdefault('load_zone', rows[0]['SETTLEMENT_LOAD_ZONE'])

    # Write
    write_csv(matches_v3, sp_by_sub, OUT_CSV)
    write_report(matches_v2, matches_v3, new_matches, REPORT_MD)

    # Stdout summary
    src_v3  = Counter(m['match_source'] for m in matches_v3.values())
    conf_v3 = Counter(m['confidence']   for m in matches_v3.values())
    print("\n=== FINAL SUMMARY (v3) ===")
    print("By source:")
    for s, n in src_v3.most_common():
        print(f"  {n:5d}  {s}")
    print("By confidence:")
    for c in ['high', 'medium', 'low', 'none']:
        print(f"  {conf_v3.get(c,0):5d}  {c}")

    remaining = sum(1 for m in matches_v3.values()
                    if m['match_source'] in ('propagated', 'lz_centroid'))
    print(f"\nStill unresolved (propagated/lz_centroid): {remaining}")

if __name__ == '__main__':
    main()
