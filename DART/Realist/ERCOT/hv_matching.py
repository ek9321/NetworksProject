"""
HV Matching: Pass 9

Match unresolved 345 kV ERCOT settlement point substations against two sources:

Pass 9A — PSSE name → 345 kV OSM substations (fuzzy name matching)
  For each unresolved 345 kV substation:
    1. Decode its PSSE bus name to a readable form (strip voltage suffixes, prefixes)
    2. Also prepare the MORA unit_name if a MORA entry exists (fuller human name)
    3. Fuzzy-match both candidate names against ALL named 345 kV+ OSM substations
    4. Accept best score ≥ 80, constrained to load zone bounding box
    5. Source: "hv_osm_345"

Pass 9B — 345 kV line endpoint clustering → geographic anchor
  For substations still unresolved after Pass 9A:
    1. Extract all 345 kV+ line endpoints from texas_hv_lines.geojson
    2. Cluster endpoints within 150 m of each other (same physical substation)
    3. For each unresolved 345 kV ERCOT substation, find nearest endpoint cluster
       within the load zone and within 75 km
    4. Assign cluster centroid as lat/lon; source: "hv_endpoint"
    5. Confidence: "low" (no name validation, only geographic proximity)

Inputs:
  OIM/FirstPass/texas_matched_substations_v3.csv
  OIM/data/texas_substations.geojson
  OIM/data/texas_hv_lines.geojson
  SP_List_EB_Mapping/Settlement_Points_01292026_104938.csv
  ERCOT/MORA_April2026_unit_capacities.csv

Outputs:
  OIM/FirstPass/texas_matched_substations_v4.csv
  ERCOT/hv_matching_report.md
"""

import json
import math
import os
import re
from collections import defaultdict

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCHED_V3  = os.path.join(ROOT, "OIM", "FirstPass", "texas_matched_substations_v3.csv")
OSM_SUBS    = os.path.join(ROOT, "OIM", "data", "texas_substations.geojson")
HV_LINES    = os.path.join(ROOT, "OIM", "data", "texas_hv_lines.geojson")
SP_CSV      = os.path.join(ROOT, "SP_List_EB_Mapping", "Settlement_Points_01292026_104938.csv")
MORA_CSV    = os.path.join(ROOT, "ERCOT", "MORA_April2026_unit_capacities.csv")
OUT_CSV     = os.path.join(ROOT, "OIM", "FirstPass", "texas_matched_substations_v4.csv")
REPORT_MD   = os.path.join(ROOT, "ERCOT", "hv_matching_report.md")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Load zone approximate bounding boxes (lat_min, lat_max, lon_min, lon_max)
LZ_BOUNDS = {
    "LZ_WEST":    (27.0, 35.5, -106.5, -99.0),
    "LZ_NORTH":   (31.5, 36.5, -100.0, -94.0),
    "LZ_HOUSTON": (28.5, 31.0,  -96.5, -93.5),
    "LZ_SOUTH":   (25.5, 31.0, -100.5, -95.5),
}

THRESHOLD_HIGH   = 90
THRESHOLD_MEDIUM = 80

# Minimum voltage for HV line endpoint clustering
HV_LINE_KV       = 345

# Maximum distance from a line endpoint cluster to count as a match (km)
ENDPOINT_MAX_KM  = 75

# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------

STRIP_WORDS = {
    "SUBSTATION", "SUB", "SWITCHING", "STATION", "SWITCH", "PLANT",
    "GENERATING", "GENERATION", "GENERATOR", "POWER", "ENERGY",
    "ELECTRIC", "SOLAR", "WIND", "FARM", "CENTER", "FACILITY",
    "SWITCHYARD", "INTERCONNECT", "PROJECT", "COMPLEX",
}


def canonicalize(name):
    """Uppercase, strip punctuation and filler words."""
    if not name:
        return ""
    s = name.upper().strip()
    s = re.sub(r'\(.*?\)', '', s)
    s = re.sub(r'[^A-Z0-9\s]', ' ', s)
    tokens = [t for t in s.split() if t not in STRIP_WORDS]
    return " ".join(tokens).strip()


def decode_psse_345(substation, psse):
    """
    Decode a 345 kV PSSE bus name to a human-readable form.

    Patterns handled (all ERCOT voltage codes where 5 = 345 kV):
      ADICKS__B345   -> ADICKS     (CenterPoint double-underscore + B345)
      L_AMOSCR5_1Y   -> AMOSCR     (LCRA load bus prefix)
      AGUAYO_5       -> AGUAYO     (_5 voltage suffix)
      BALE_S5        -> BALE       (S5 suffix)
      ANGSTRM7A      -> ANGSTRM    (AEP 7A zone suffix)
      ANOL_ESS_6     -> ANOL ESS   (_6 = 500 kV, strip)
      BENDAVIS_5     -> BENDAVIS   (_5 suffix)
    """
    if not psse or not isinstance(psse, str):
        return substation.replace('_', ' ').strip()

    s = psse.strip().upper()

    # Remove TN prefix (TNMP)
    s = re.sub(r'^TN', '', s)

    # Remove L_ prefix (LCRA)
    s = re.sub(r'^L_', '', s)

    # CenterPoint: NAME__B345 → take before __
    if '__' in s:
        s = s.split('__')[0]

    # Strip trailing _1Y (load bus marker)
    s = re.sub(r'_1Y$', '', s)

    # Strip _5, _6 voltage suffixes (345 kV, 500 kV)
    s = re.sub(r'_[56]$', '', s)

    # Strip S5, S6 suffix (e.g. BALE_S5 → BALE)
    s = re.sub(r'S[56]$', '', s)

    # Strip AEP zone+voltage suffix: 7A, 5A, 4A
    s = re.sub(r'[57]A$', '', s)

    # Strip _TL (tie-line suffix)
    s = re.sub(r'_TL$', '', s)

    # Strip trailing generator unit: _G1, _G2
    s = re.sub(r'_G[0-9]+$', '', s)

    # Strip trailing voltage code: _B345, B345
    s = re.sub(r'_?B345$', '', s)

    # Strip trailing single digit
    s = re.sub(r'_[0-9]$', '', s)

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
    import csv
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def load_osm_substations_345():
    """Return list of named 345 kV+ OSM substations with lat/lon and OSM id."""
    with open(OSM_SUBS, encoding='utf-8') as f:
        data = json.load(f)

    # Texas bounding box
    def in_texas(coords):
        lon, lat = coords
        return 25.8 <= lat <= 36.6 and -106.7 <= lon <= -93.5

    # Exclude Mexican/Oklahoma operators
    exclude_ops = {
        "Oklahoma Gas & Electric", "Oklahoma Gas and Electric Co.",
        "Public Service Company of Oklahoma",
        "Southwestern Electric Power Company",
        "Comisión Federal de Electricidad",
        "Grand River Dam Authority",
    }

    result = []
    for feat in data['features']:
        p = feat['properties']
        kv = p.get('voltage_kv')
        if not kv or kv < 345:
            continue
        name = p.get('name', '').strip()
        if not name:
            continue
        op = p.get('operator') or ''
        if op in exclude_ops:
            continue
        coords = feat['geometry']['coordinates']
        if not in_texas(coords):
            continue
        result.append({
            'osm_id':   p['osm_id'],
            'name':     name,
            'canon':    canonicalize(name),
            'lat':      coords[1],
            'lon':      coords[0],
            'voltage':  kv,
            'operator': op,
        })
    return result


def load_hv_line_endpoints():
    """
    Extract endpoint coordinates (first and last point) of all 345 kV+ lines.
    Returns list of (lat, lon) tuples.
    """
    with open(HV_LINES, encoding='utf-8') as f:
        data = json.load(f)

    endpoints = []
    for feat in data['features']:
        kv = feat['properties'].get('voltage_kv', 0) or 0
        if kv < HV_LINE_KV:
            continue
        coords = feat['geometry']['coordinates']
        # start and end point of each line segment
        endpoints.append((coords[0][1],  coords[0][0]))   # (lat, lon)
        endpoints.append((coords[-1][1], coords[-1][0]))
    return endpoints


def cluster_endpoints(endpoints, radius_km=0.15):
    """
    Simple greedy clustering: group endpoints within radius_km of each other.
    Returns list of cluster centroids as (lat, lon).
    """
    clusters = []   # list of [lat, lon, count]
    for lat, lon in endpoints:
        matched = None
        for c in clusters:
            if haversine_km(lat, lon, c[0], c[1]) <= radius_km:
                matched = c
                break
        if matched:
            n = matched[2]
            matched[0] = (matched[0] * n + lat) / (n + 1)
            matched[1] = (matched[1] * n + lon) / (n + 1)
            matched[2] += 1
        else:
            clusters.append([lat, lon, 1])
    # Only return clusters with at least 2 contributing endpoints
    # (a single endpoint may just be a line mid-point artifact)
    return [(c[0], c[1]) for c in clusters if c[2] >= 2]


def load_mora_index():
    """
    Build index: substation_name (uppercase) → best MORA unit_name.
    Uses first segment of unit_code as substation key (mirrors existing pipeline).
    """
    mora_rows = load_csv(MORA_CSV)
    index = {}
    for row in mora_rows:
        code = row.get('unit_code', '').strip().upper()
        name = row.get('unit_name', '').strip().upper()
        if not code or not name:
            continue
        # First segment before '_'
        seg = code.split('_')[0]
        if seg and seg not in index:
            index[seg] = name
        # Also full code prefix
        if code not in index:
            index[code] = name
    return index


def load_sp_psse():
    """
    Build index: SUBSTATION (uppercase) → best (highest voltage) PSSE_BUS_NAME.
    """
    rows = load_csv(SP_CSV)
    # Sort descending by VOLTAGE_LEVEL so highest-voltage entry wins
    def safe_float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    rows_sorted = sorted(rows, key=lambda r: safe_float(r.get('VOLTAGE_LEVEL', 0)), reverse=True)
    index = {}
    for r in rows_sorted:
        sub = r.get('SUBSTATION', '').strip().upper()
        psse = r.get('PSSE_BUS_NAME', '').strip()
        if sub and psse and sub not in index:
            index[sub] = psse
    return index


# ---------------------------------------------------------------------------
# Pass 9A: PSSE name → 345 kV OSM fuzzy matching
# ---------------------------------------------------------------------------

def pass_9a(unresolved_345, osm_345, sp_psse, mora_index, matched_osm_ids):
    """
    Returns list of match dicts:
      {sub, lat, lon, osm_id, score, matched_name, candidate_name, confidence}
    """
    new_matches = []
    used_osm_ids = set(matched_osm_ids)

    for row in unresolved_345:
        sub = row['ercot_substation'].upper()
        lz  = row.get('load_zone', '')

        # Build candidate names to try
        psse = sp_psse.get(sub, '')
        decoded = decode_psse_345(sub, psse)
        candidates = []

        # Decoded PSSE name (primary)
        c1 = canonicalize(decoded)
        if c1:
            candidates.append((c1, decoded))

        # Raw substation abbreviation (secondary)
        c2 = canonicalize(sub)
        if c2 and c2 != c1:
            candidates.append((c2, sub))

        # MORA unit_name (tertiary — fullest human name)
        mora_name = mora_index.get(sub, '')
        if not mora_name:
            # Try first segment of substation name
            seg = sub.split('_')[0]
            mora_name = mora_index.get(seg, '')
        if mora_name:
            c3 = canonicalize(mora_name)
            if c3 and c3 not in {c1, c2}:
                candidates.append((c3, mora_name))

        if not candidates:
            continue

        best_score = 0
        best_match = None

        for osm in osm_345:
            if osm['osm_id'] in used_osm_ids:
                continue
            # Geographic constraint
            if not in_lz_bounds(osm['lat'], osm['lon'], lz):
                continue

            osm_canon = osm['canon']
            for cand_canon, _ in candidates:
                sc = ensemble_score(cand_canon, osm_canon)
                if sc > best_score:
                    best_score = sc
                    best_match = osm
                    best_cand  = cand_canon

        if best_score >= THRESHOLD_MEDIUM and best_match:
            confidence = 'high' if best_score >= THRESHOLD_HIGH else 'medium'
            new_matches.append({
                'sub':          sub,
                'lat':          best_match['lat'],
                'lon':          best_match['lon'],
                'osm_id':       best_match['osm_id'],
                'score':        round(best_score, 1),
                'matched_name': best_match['name'],
                'candidate':    best_cand,
                'confidence':   confidence,
                'voltage':      best_match['voltage'],
            })
            used_osm_ids.add(best_match['osm_id'])

    return new_matches, used_osm_ids


# ---------------------------------------------------------------------------
# Pass 9B: HV line endpoint clustering → geographic anchor
# ---------------------------------------------------------------------------

def pass_9b(still_unresolved, endpoint_clusters, lz_bounds=LZ_BOUNDS):
    """
    For each unresolved substation, find the nearest endpoint cluster
    within the load zone bounds and within ENDPOINT_MAX_KM.
    Returns list of match dicts.
    """
    new_matches = []

    for row in still_unresolved:
        lz = row.get('load_zone', '')

        # Filter clusters to load zone + buffer
        if lz in lz_bounds:
            lat_min, lat_max, lon_min, lon_max = lz_bounds[lz]
            buf = 1.5
            zone_clusters = [
                (lat, lon) for lat, lon in endpoint_clusters
                if lat_min - buf <= lat <= lat_max + buf
                and lon_min - buf <= lon <= lon_max + buf
            ]
        else:
            zone_clusters = endpoint_clusters

        if not zone_clusters:
            continue

        # Current (bad) position of this substation
        try:
            cur_lat = float(row['lat'])
            cur_lon = float(row['lon'])
        except (TypeError, ValueError):
            cur_lat, cur_lon = None, None

        # Find nearest cluster
        best_dist = float('inf')
        best_cluster = None
        for clat, clon in zone_clusters:
            d = haversine_km(clat, clon,
                             cur_lat or clat,   # if no position, any cluster in LZ
                             cur_lon or clon)
            if d < best_dist:
                best_dist = d
                best_cluster = (clat, clon)

        if best_cluster and best_dist <= ENDPOINT_MAX_KM:
            new_matches.append({
                'sub':        row['ercot_substation'].upper(),
                'lat':        round(best_cluster[0], 6),
                'lon':        round(best_cluster[1], 6),
                'dist_km':    round(best_dist, 1),
                'confidence': 'low',
            })

    return new_matches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import csv as csv_mod

    print("Loading data…")
    rows = load_csv(MATCHED_V3)
    sp_psse = load_sp_psse()
    mora_index = load_mora_index()
    osm_345 = load_osm_substations_345()
    print(f"  OSM 345 kV+ named substations in Texas: {len(osm_345)}")

    # Already-matched OSM IDs (don't reuse them)
    matched_osm_ids = set()
    for r in rows:
        try:
            matched_osm_ids.add(int(float(r['osm_id'])))
        except (TypeError, ValueError):
            pass

    # Unresolved 345 kV substations (true 345, not 34.5 kV)
    unresolved_345 = [
        r for r in rows
        if r['match_source'] in ('propagated', 'lz_centroid')
        and float(r.get('max_voltage_kv') or 0) >= 340
    ]
    print(f"  Unresolved 345 kV+ substations: {len(unresolved_345)}")

    # -----------------------------------------------------------------------
    # Pass 9A
    # -----------------------------------------------------------------------
    print("\nPass 9A: PSSE name → 345 kV OSM fuzzy matching…")
    matches_9a, used_osm_ids = pass_9a(
        unresolved_345, osm_345, sp_psse, mora_index, matched_osm_ids
    )
    print(f"  New matches from Pass 9A: {len(matches_9a)}")

    # Build lookup: sub → match
    match_lookup_9a = {m['sub']: m for m in matches_9a}

    # Substations still unresolved after 9A
    resolved_by_9a = set(match_lookup_9a.keys())
    still_unresolved = [
        r for r in unresolved_345
        if r['ercot_substation'].upper() not in resolved_by_9a
    ]
    print(f"  Still unresolved after 9A: {len(still_unresolved)}")

    # -----------------------------------------------------------------------
    # Pass 9B: HV line endpoint clustering
    # -----------------------------------------------------------------------
    print("\nPass 9B: 345 kV line endpoint clustering…")
    endpoints = load_hv_line_endpoints()
    print(f"  Raw 345 kV+ line endpoints: {len(endpoints)}")

    clusters = cluster_endpoints(endpoints, radius_km=0.15)
    print(f"  Endpoint clusters (≥2 contributing lines): {len(clusters)}")

    matches_9b = pass_9b(still_unresolved, clusters)
    print(f"  New geographic anchors from Pass 9B: {len(matches_9b)}")

    match_lookup_9b = {m['sub']: m for m in matches_9b}

    # -----------------------------------------------------------------------
    # Write output CSV
    # -----------------------------------------------------------------------
    print("\nWriting output CSV…")

    # Extend rows with new columns
    new_col_9a  = 'hv_osm_345_id'
    new_col_9b  = 'hv_endpoint_dist_km'

    out_rows = []
    stats_9a = {'high': 0, 'medium': 0}
    stats_9b = 0

    for r in rows:
        sub = r['ercot_substation'].upper()

        if sub in match_lookup_9a:
            m = match_lookup_9a[sub]
            r['lat']          = m['lat']
            r['lon']          = m['lon']
            r['match_source'] = 'hv_osm_345'
            r['confidence']   = m['confidence']
            r['score']        = m['score']
            r['matched_name'] = m['matched_name']
            r['osm_id']       = m['osm_id']
            r[new_col_9a]     = m['osm_id']
            r[new_col_9b]     = ''
            stats_9a[m['confidence']] += 1

        elif sub in match_lookup_9b:
            m = match_lookup_9b[sub]
            r['lat']          = m['lat']
            r['lon']          = m['lon']
            r['match_source'] = 'hv_endpoint'
            r['confidence']   = 'low'
            r[new_col_9a]     = ''
            r[new_col_9b]     = m['dist_km']
            stats_9b += 1

        else:
            r.setdefault(new_col_9a, '')
            r.setdefault(new_col_9b, '')

        out_rows.append(r)

    # Write
    fieldnames = list(rows[0].keys())
    for col in [new_col_9a, new_col_9b]:
        if col not in fieldnames:
            fieldnames.append(col)

    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv_mod.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"  Written: {OUT_CSV}")

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    from collections import Counter
    src_counter = Counter(r['match_source'] for r in out_rows)
    conf_counter = Counter(r['confidence'] for r in out_rows)

    still_unresolved_final = [
        r for r in out_rows
        if r['match_source'] in ('propagated', 'lz_centroid')
    ]

    report_lines = [
        "# HV Matching Results (Passes 9A & 9B)\n",
        "## Before vs After\n",
        "| Source | V3 Count | V4 Count | Change |",
        "|---|---|---|---|",
    ]

    v3_src = Counter(r['match_source'] for r in rows)
    for src in sorted(set(list(v3_src.keys()) + list(src_counter.keys()))):
        v3 = v3_src.get(src, 0)
        v4 = src_counter.get(src, 0)
        report_lines.append(f"| {src} | {v3} | {v4} | {v4-v3:+d} |")

    report_lines += [
        f"\n**Total substations:** {len(rows)} → {len(out_rows)}",
        "\n## Confidence Summary\n",
        "| Confidence | V3 | V4 | Change |",
        "|---|---|---|---|",
    ]

    v3_conf = Counter(r['confidence'] for r in rows)
    for conf in ('high', 'medium', 'low', 'none'):
        v3 = v3_conf.get(conf, 0)
        v4 = conf_counter.get(conf, 0)
        report_lines.append(f"| {conf} | {v3} | {v4} | {v4-v3:+d} |")

    report_lines += [
        "\n## Pass 9A — PSSE Name → 345 kV OSM Matching\n",
        f"- Attempted: **{len(unresolved_345)}** unresolved 345 kV substations",
        f"- New matches: **{len(matches_9a)}**",
        f"  - High confidence: {stats_9a['high']}",
        f"  - Medium confidence: {stats_9a['medium']}",
        "\n### Sample new 9A matches\n",
        "| Substation | OSM Name | Score | Confidence |",
        "|---|---|---|---|",
    ]

    for m in sorted(matches_9a, key=lambda x: -x['score'])[:30]:
        report_lines.append(
            f"| {m['sub']} | {m['matched_name']} | {m['score']} | {m['confidence']} |"
        )

    report_lines += [
        "\n## Pass 9B — 345 kV Line Endpoint Clustering\n",
        f"- Raw 345 kV+ endpoints: **{len(endpoints)}**",
        f"- Endpoint clusters (≥2 lines): **{len(clusters)}**",
        f"- New geographic anchors: **{stats_9b}**",
        f"\n**Still unresolved after both passes:** {len(still_unresolved_final)}",
    ]

    report_text = "\n".join(report_lines) + "\n"
    with open(REPORT_MD, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f"  Report: {REPORT_MD}")

    print(f"\nDone. New matches: {len(matches_9a)} OSM + {stats_9b} endpoint anchors")
    print(f"Unresolved (propagated + lz_centroid): {len(still_unresolved_final)}")


if __name__ == "__main__":
    main()
