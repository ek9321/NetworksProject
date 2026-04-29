"""
MORA Matching: Passes 3.5 – 7

Runs on top of the existing OIM/FirstPass/texas_matched_substations.csv output.
Produces:
  OIM/FirstPass/texas_matched_substations_v2.csv   — updated match table
  ERCOT/mora_matching_report.md                    — summary report

Pass 3.5 — County-validate existing medium/high-confidence matches using MORA county
Pass 4   — MORA unit_name → OSM matching with county constraint
Pass 5   — MORA unit_code first-segment → ERCOT substation → county-centroid upgrade
Pass 6   — MORA unit_name → EIA-860 enhanced matching with county constraint
Pass 7   — INR → IX queue POI Location → OSM matching
"""

import csv
import json
import math
import os
import re
import sys
from collections import defaultdict

import pandas as pd
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ERCOT_DIR   = os.path.join(ROOT, "ERCOT")
OIM_DIR     = os.path.join(ROOT, "OIM")
SP_DIR      = os.path.join(ROOT, "SP_List_EB_Mapping")
EIA_DIR     = os.path.join(ROOT, "data", "eia8602023")
FIRST_PASS  = os.path.join(OIM_DIR, "FirstPass")

MORA_CSV    = os.path.join(ERCOT_DIR, "MORA_April2026_unit_capacities.csv")
MATCHED_CSV = os.path.join(FIRST_PASS, "texas_matched_substations.csv")
SP_CSV      = os.path.join(SP_DIR, "Settlement_Points_01292026_104938.csv")
OSM_GEO     = os.path.join(OIM_DIR, "data", "texas_substations.geojson")
EIA_XLSX    = os.path.join(EIA_DIR, "2___Plant_Y2023.xlsx")
IX_XLSX     = os.path.join(ERCOT_DIR, "IX_queue.xlsx")

OUT_CSV     = os.path.join(FIRST_PASS, "texas_matched_substations_v2.csv")
REPORT_MD   = os.path.join(ERCOT_DIR, "mora_matching_report.md")

# ---------------------------------------------------------------------------
# Shared helpers (mirrors match_nodes.py)
# ---------------------------------------------------------------------------
STRIP_WORDS = [
    "SUBSTATION", "SWITCHING", "STATION", "SWITCH", "PLANT",
    "GENERATING", "GENERATION", "GENERATOR", "POWER", "ENERGY",
    "ELECTRIC", "SOLAR", "WIND", "FARM", "CENTER", "FACILITY",
    "SS", "STN", "GEN", "SUB",
]
ABBREVIATION_MAP = {
    "MT": "MOUNT", "MTN": "MOUNTAIN", "FT": "FORT",
    "ST": "SAINT", "PT": "POINT", "LK": "LAKE",
    "CK": "CREEK", "CR": "CREEK", "RVR": "RIVER",
    "SPG": "SPRING", "SPGS": "SPRINGS", "JCT": "JUNCTION",
    "N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST",
    "NE": "NORTHEAST", "NW": "NORTHWEST", "SE": "SOUTHEAST", "SW": "SOUTHWEST",
}

def canonicalize(name):
    if not name:
        return ""
    s = str(name).upper().strip()
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    tokens = s.split()
    tokens = [t for t in tokens if t not in STRIP_WORDS]
    tokens = [ABBREVIATION_MAP.get(t, t) for t in tokens]
    while tokens and tokens[-1].isdigit():
        tokens.pop()
    return " ".join(tokens).strip()

def ensemble_score(s1, s2):
    if not s1 or not s2:
        return 0.0
    tsr   = fuzz.token_sort_ratio(s1, s2)
    tsetr = fuzz.token_set_ratio(s1, s2)
    jw    = JaroWinkler.normalized_similarity(s1, s2) * 100
    return 0.3 * tsr + 0.4 * tsetr + 0.3 * jw

def validate_match(ec, cc, raw):
    if raw <= 0:
        return 0.0
    e = ec.replace(" ", "")
    c = cc.replace(" ", "")
    if len(e) <= 3 and raw < 92:
        return 0.0
    if len(e) >= 2 and len(c) >= 2 and e[:2] != c[:2]:
        return 0.0
    if e and c:
        ratio = min(len(e), len(c)) / max(len(e), len(c))
        if ratio < 0.4:
            raw *= 0.8
    return raw

THRESHOLD_HIGH   = 92
THRESHOLD_MEDIUM = 82

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_mora():
    with open(MORA_CSV) as f:
        return list(csv.DictReader(f))

def load_existing_matches():
    """Returns dict: ercot_substation -> match record (mutable dict)."""
    with open(MATCHED_CSV) as f:
        rows = list(csv.DictReader(f))
    return {r["ercot_substation"]: dict(r) for r in rows}

def load_sp():
    with open(SP_CSV) as f:
        return list(csv.DictReader(f))

def load_osm_substations():
    with open(OSM_GEO) as f:
        data = json.load(f)
    subs = []
    for feat in data["features"]:
        props = feat["properties"]
        lon, lat = feat["geometry"]["coordinates"]
        name = props.get("name", "")
        if not name:
            continue
        subs.append({
            "osm_id":    props["osm_id"],
            "name":      name,
            "canonical": canonicalize(name),
            "lat":       lat,
            "lon":       lon,
        })
    return subs

def load_eia_plants():
    df = pd.read_excel(EIA_XLSX, skiprows=1)
    ba_col     = [c for c in df.columns if "balanc" in c.lower() and "code" in c.lower()][0]
    name_col   = [c for c in df.columns if "plant name" in c.lower()][0]
    code_col   = [c for c in df.columns if "plant code" in c.lower()][0]
    lat_col    = [c for c in df.columns if "lat" in c.lower()][0]
    lon_col    = [c for c in df.columns if "lon" in c.lower()][0]
    county_col = [c for c in df.columns if "county" in c.lower()][0]
    ercot = df[df[ba_col] == "ERCO"].copy()
    plants = []
    for _, row in ercot.iterrows():
        lat = row[lat_col]; lon = row[lon_col]
        if pd.isna(lat) or pd.isna(lon):
            continue
        plants.append({
            "plant_code": int(row[code_col]),
            "plant_name": str(row[name_col]).strip(),
            "county":     str(row[county_col]).strip().upper() if not pd.isna(row[county_col]) else "",
            "lat":        float(lat),
            "lon":        float(lon),
            "canonical":  canonicalize(str(row[name_col])),
        })
    return plants

def load_ix_queue():
    """Load IX queue Project Details - Large Gen with INR, County, POI Location."""
    df = pd.read_excel(IX_XLSX, sheet_name="Project Details - Large Gen", header=30)
    records = []
    for _, row in df.iterrows():
        inr = str(row.get("INR", "")).strip()
        if not inr or inr == "nan":
            continue
        records.append({
            "inr":          inr,
            "project_name": str(row.get("Project Name", "")).strip(),
            "county":       str(row.get("County", "")).strip().upper(),
            "zone":         str(row.get("CDR Reporting Zone", "")).strip().upper(),
            "fuel":         str(row.get("Fuel", "")).strip(),
            "poi":          str(row.get("POI Location", "")).strip(),
        })
    return records

# ---------------------------------------------------------------------------
# County centroid index
# ---------------------------------------------------------------------------

def build_county_centroids(eia_plants):
    """Derive county centroids from mean lat/lon of EIA-860 plants per county."""
    by_county = defaultdict(list)
    for p in eia_plants:
        if p["county"]:
            by_county[p["county"]].append((p["lat"], p["lon"]))
    centroids = {}
    for county, pts in by_county.items():
        lats = [p[0] for p in pts]
        lons = [p[1] for p in pts]
        centroids[county] = (sum(lats)/len(lats), sum(lons)/len(lons))
    return centroids

def county_centroid(county_name, centroids):
    """Return (lat, lon) for a county name, or None."""
    key = county_name.strip().upper()
    return centroids.get(key)

# ---------------------------------------------------------------------------
# MORA index structures
# ---------------------------------------------------------------------------

def build_mora_indexes(mora):
    """
    Returns:
      sub_to_mora:   ERCOT substation abbrev -> list of MORA rows (from unit_code first seg)
      code_to_mora:  PSSE_BUS_NAME -> MORA row (from direct unit_code match)
      inr_to_mora:   INR string -> MORA row
    """
    sub_to_mora  = defaultdict(list)
    code_to_mora = {}
    inr_to_mora  = {}

    for r in mora:
        uc  = r["unit_code"]
        inr = r["inr"]
        if uc:
            code_to_mora[uc] = r
            seg = uc.split("_")[0]
            sub_to_mora[seg].append(r)
        if inr:
            inr_to_mora[inr] = r

    return sub_to_mora, code_to_mora, inr_to_mora

# ---------------------------------------------------------------------------
# Pass 3.5 — County-validate existing medium/high matches
# ---------------------------------------------------------------------------

def pass_35_county_validate(matches, sub_to_mora, county_centroids):
    """
    For each medium/high-confidence match that also has MORA county data,
    check whether the current lat/lon is within 100 km of the MORA county centroid.
    Returns dict: substation -> {"county_ok": bool, "mora_county": str, "county_dist_km": float}
    """
    print("Pass 3.5: County-validating existing matches...")
    results = {}
    flagged = 0
    checked = 0

    for sub, m in matches.items():
        if m["confidence"] not in ("high", "medium"):
            continue
        mora_rows = sub_to_mora.get(sub, [])
        if not mora_rows:
            continue
        counties = list({r["county"] for r in mora_rows if r["county"]})
        if not counties:
            continue
        # Use the most common county
        county = max(counties, key=counties.count)
        centroid = county_centroid(county, county_centroids)
        if not centroid:
            continue

        checked += 1
        try:
            dist = haversine_km(float(m["lat"]), float(m["lon"]),
                                centroid[0], centroid[1])
        except (ValueError, TypeError):
            continue

        ok = dist <= 100.0
        if not ok:
            flagged += 1
        results[sub] = {
            "county_ok":      ok,
            "mora_county":    county,
            "county_dist_km": round(dist, 1),
        }

    print(f"  Checked {checked} medium/high matches with MORA county data")
    print(f"  Flagged {flagged} as county-mismatched (>100 km from MORA county centroid)")
    return results

# ---------------------------------------------------------------------------
# Pass 5 — MORA unit_code → PSSE bridge → county centroid upgrade
# ---------------------------------------------------------------------------

def pass5_county_upgrade(matches, sub_to_mora, county_centroids):
    """
    For substations currently at lz_centroid confidence that appear in MORA,
    upgrade to county-centroid geographic anchor.
    Returns dict of new match records.
    """
    print("Pass 5: County-centroid upgrades for lz_centroid substations...")
    upgrades = {}

    for sub, m in matches.items():
        if m["match_source"] != "lz_centroid":
            continue
        mora_rows = sub_to_mora.get(sub, [])
        if not mora_rows:
            continue
        counties = [r["county"] for r in mora_rows if r["county"]]
        if not counties:
            continue
        county = max(set(counties), key=counties.count)
        centroid = county_centroid(county, county_centroids)
        if not centroid:
            continue

        upgrades[sub] = {
            "lat":          round(centroid[0], 6),
            "lon":          round(centroid[1], 6),
            "match_source": "mora_county_centroid",
            "confidence":   "low",
            "score":        "",
            "matched_name": f"MORA county: {county}",
            "mora_county":  county,
            "mora_fuel":    "; ".join(sorted({r["fuel"] for r in mora_rows if r["fuel"]})),
        }

    print(f"  Upgraded {len(upgrades)} substations from lz_centroid → mora_county_centroid")
    return upgrades

# ---------------------------------------------------------------------------
# Pass 6 — MORA unit_name → EIA-860 enhanced matching
# ---------------------------------------------------------------------------

def pass6_mora_name_eia(matches, mora, sub_to_mora, eia_plants, county_centroids):
    """
    For substations not yet directly matched (propagated or lz_centroid),
    use MORA unit_name as the search string against EIA-860.
    County constraint: only accept if within 100 km of MORA county centroid.
    """
    print("Pass 6: MORA unit_name → EIA-860 enhanced matching...")

    # Build EIA prefix index
    eia_blocks = defaultdict(list)
    for p in eia_plants:
        key = p["canonical"][:3] if len(p["canonical"]) >= 3 else p["canonical"]
        eia_blocks[key].append(p)

    # Build set of substations we need to upgrade
    target_sources = {"propagated", "lz_centroid", "mora_county_centroid"}

    new_matches = {}
    attempted = 0

    # Group MORA rows by the substation they map to
    for sub, mora_rows in sub_to_mora.items():
        m = matches.get(sub, {})
        if m.get("match_source") not in target_sources:
            continue
        if m.get("confidence") in ("high", "medium"):
            continue

        # Try each unique unit_name for this substation
        best_score = 0
        best_plant = None
        best_mora_row = None

        for row in mora_rows:
            unit_name_canon = canonicalize(row["unit_name"])
            if not unit_name_canon or len(unit_name_canon) < 4:
                continue

            block_key = unit_name_canon[:3]
            candidates = eia_blocks.get(block_key, [])

            for plant in candidates:
                raw   = ensemble_score(unit_name_canon, plant["canonical"])
                score = validate_match(unit_name_canon, plant["canonical"], raw)
                if score <= 0:
                    continue

                # County constraint: if MORA has county and EIA has county,
                # reject cross-county matches
                mora_county = row.get("county", "").strip().upper()
                eia_county  = plant.get("county", "").strip().upper()
                if mora_county and eia_county:
                    if mora_county != eia_county:
                        score *= 0.5  # Heavy penalty for county mismatch

                if score > best_score:
                    best_score = score
                    best_plant = plant
                    best_mora_row = row

        attempted += 1
        if best_score >= THRESHOLD_MEDIUM and best_plant:
            conf = "high" if best_score >= THRESHOLD_HIGH else "medium"
            new_matches[sub] = {
                "lat":           round(best_plant["lat"], 6),
                "lon":           round(best_plant["lon"], 6),
                "match_source":  "mora_eia860",
                "confidence":    conf,
                "score":         round(best_score, 1),
                "matched_name":  best_plant["plant_name"],
                "eia_plant_code": best_plant["plant_code"],
                "mora_county":   best_mora_row.get("county", ""),
                "mora_fuel":     best_mora_row.get("fuel", ""),
            }

    print(f"  Attempted: {attempted} substations")
    print(f"  New matches: {len(new_matches)}")
    return new_matches

# ---------------------------------------------------------------------------
# Pass 4 — MORA unit_name → OSM matching with county constraint
# ---------------------------------------------------------------------------

def pass4_mora_name_osm(matches, mora, sub_to_mora, osm_subs, county_centroids):
    """
    For substations in the 341 'miss' cases (unit_code first seg not an ERCOT sub)
    and for propagated/centroid substations, try MORA unit_name → OSM matching.
    County constraint via distance from county centroid.
    """
    print("Pass 4: MORA unit_name → OSM matching...")

    # Build OSM prefix + skeleton indexes
    osm_by_prefix = defaultdict(list)
    for osub in osm_subs:
        key = osub["canonical"][:3] if len(osub["canonical"]) >= 3 else osub["canonical"]
        osm_by_prefix[key].append(osub)

    target_sources = {"propagated", "lz_centroid", "mora_county_centroid"}
    new_matches = {}
    attempted = 0

    for sub, mora_rows in sub_to_mora.items():
        m = matches.get(sub, {})
        if m.get("match_source") not in target_sources:
            continue
        if m.get("confidence") in ("high", "medium"):
            continue

        best_score = 0
        best_osub  = None
        best_mora_row = None

        for row in mora_rows:
            unit_name_canon = canonicalize(row["unit_name"])
            if not unit_name_canon or len(unit_name_canon) < 4:
                continue

            mora_county = row.get("county", "").strip().upper()
            county_cent = county_centroid(mora_county, county_centroids) if mora_county else None

            block_key  = unit_name_canon[:3]
            candidates = osm_by_prefix.get(block_key, [])

            for osub in candidates:
                raw   = ensemble_score(unit_name_canon, osub["canonical"])
                score = validate_match(unit_name_canon, osub["canonical"], raw)
                if score <= 0:
                    continue

                # County constraint: penalise if outside ~80 km of county centroid
                if county_cent:
                    dist = haversine_km(osub["lat"], osub["lon"],
                                       county_cent[0], county_cent[1])
                    if dist > 80:
                        score *= 0.6

                if score > best_score:
                    best_score = score
                    best_osub  = osub
                    best_mora_row = row

        attempted += 1
        if best_score >= THRESHOLD_MEDIUM and best_osub:
            conf = "high" if best_score >= THRESHOLD_HIGH else "medium"
            new_matches[sub] = {
                "lat":          round(best_osub["lat"], 6),
                "lon":          round(best_osub["lon"], 6),
                "match_source": "mora_osm",
                "confidence":   conf,
                "score":        round(best_score, 1),
                "matched_name": best_osub["name"],
                "osm_id":       best_osub["osm_id"],
                "mora_county":  best_mora_row.get("county", ""),
                "mora_fuel":    best_mora_row.get("fuel", ""),
            }

    print(f"  Attempted: {attempted} substations")
    print(f"  New matches: {len(new_matches)}")
    return new_matches

# ---------------------------------------------------------------------------
# Pass 7 — INR → IX queue → POI location → OSM
# ---------------------------------------------------------------------------

def pass7_inr_ix_queue(matches, mora, inr_to_mora, ix_queue, osm_subs,
                        psse_to_sub, county_centroids):
    """
    For MORA entries with INR numbers, look up the IX queue POI Location,
    parse the substation name from it, and try to match against OSM.
    Then link back to the ERCOT substation via MORA unit_code → PSSE → SUBSTATION.
    """
    print("Pass 7: INR → IX queue → POI → OSM matching...")

    # Build INR → IX queue record
    ix_by_inr = {r["inr"]: r for r in ix_queue if r["inr"]}

    # Build OSM prefix index
    osm_by_prefix = defaultdict(list)
    for osub in osm_subs:
        key = osub["canonical"][:3] if len(osub["canonical"]) >= 3 else osub["canonical"]
        osm_by_prefix[key].append(osub)

    target_sources = {"propagated", "lz_centroid", "mora_county_centroid"}
    new_matches = {}
    attempted = 0

    for mora_row in mora:
        inr = mora_row.get("inr", "").strip()
        if not inr:
            continue

        # Resolve ERCOT substation from this MORA row
        uc = mora_row.get("unit_code", "")
        sub_via_code = psse_to_sub.get(uc) if uc else None
        sub_via_seg  = uc.split("_")[0] if uc and "_" in uc else None

        # Pick the substation to try upgrading
        sub = sub_via_code or sub_via_seg
        if not sub:
            continue

        m = matches.get(sub, {})
        if m.get("match_source") not in target_sources:
            continue

        ix = ix_by_inr.get(inr)
        if not ix:
            continue

        # Parse POI Location — typically "12345 SubName 138kV" or "tap 345kV ... SubName"
        poi = ix["poi"]
        # Strip leading bus numbers and voltage tags, take remaining words as name
        poi_clean = re.sub(r"\b\d{4,6}\b", " ", poi)  # remove bus numbers
        poi_clean = re.sub(r"\b\d+\s*kV\b", " ", poi_clean, flags=re.IGNORECASE)
        poi_clean = re.sub(r"\btap\b", " ", poi_clean, flags=re.IGNORECASE)
        poi_clean = re.sub(r"\s+", " ", poi_clean).strip()
        poi_canon = canonicalize(poi_clean)

        if not poi_canon or len(poi_canon) < 3:
            continue

        mora_county = ix["county"].strip().upper()
        county_cent = county_centroid(mora_county, county_centroids) if mora_county else None

        block_key  = poi_canon[:3]
        candidates = osm_by_prefix.get(block_key, [])

        best_score = 0
        best_osub  = None

        for osub in candidates:
            raw   = ensemble_score(poi_canon, osub["canonical"])
            score = validate_match(poi_canon, osub["canonical"], raw)
            if score <= 0:
                continue
            if county_cent:
                dist = haversine_km(osub["lat"], osub["lon"],
                                   county_cent[0], county_cent[1])
                if dist > 80:
                    score *= 0.6
            if score > best_score:
                best_score = score
                best_osub  = osub

        attempted += 1
        if best_score >= THRESHOLD_MEDIUM and best_osub:
            conf = "high" if best_score >= THRESHOLD_HIGH else "medium"
            new_matches[sub] = {
                "lat":          round(best_osub["lat"], 6),
                "lon":          round(best_osub["lon"], 6),
                "match_source": "mora_ix_queue",
                "confidence":   conf,
                "score":        round(best_score, 1),
                "matched_name": best_osub["name"],
                "osm_id":       best_osub["osm_id"],
                "mora_county":  mora_county,
                "mora_fuel":    mora_row.get("fuel", ""),
                "inr":          inr,
                "poi_parsed":   poi_canon,
            }

    print(f"  Attempted: {attempted} INR lookups")
    print(f"  New matches: {len(new_matches)}")
    return new_matches

# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "ercot_substation", "lat", "lon", "match_source", "confidence",
    "score", "matched_name", "load_zone", "max_voltage_kv",
    "eia_plant_code", "osm_id", "propagated_from",
    "mora_county", "mora_fuel", "county_validated", "county_dist_km",
]

def write_csv(matches, sp_rows, out_path):
    sub_lz  = {r["SUBSTATION"]: r["SETTLEMENT_LOAD_ZONE"] for r in sp_rows}
    sub_volt = defaultdict(set)
    for r in sp_rows:
        v = r.get("VOLTAGE_LEVEL", "")
        if v:
            try:
                sub_volt[r["SUBSTATION"]].add(float(v))
            except ValueError:
                pass

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for sub, m in sorted(matches.items()):
            row = dict(m)
            row["ercot_substation"] = sub
            row["load_zone"] = sub_lz.get(sub, m.get("load_zone", ""))
            vs = sub_volt.get(sub, set())
            row["max_voltage_kv"] = max(vs) if vs else m.get("max_voltage_kv", "")
            writer.writerow(row)
    print(f"Saved: {out_path}")

def write_report(matches_v1, matches_v2, validation, out_path):
    from collections import Counter

    def breakdown(m):
        return Counter(v["match_source"] for v in m.values()), \
               Counter(v["confidence"]   for v in m.values())

    src1, conf1 = breakdown(matches_v1)
    src2, conf2 = breakdown(matches_v2)

    # Compute new matches (substations whose source changed)
    new_direct = {
        s for s, m in matches_v2.items()
        if matches_v1.get(s, {}).get("match_source") != m["match_source"]
        and m["match_source"] in ("mora_eia860", "mora_osm", "mora_ix_queue",
                                  "mora_county_centroid")
    }
    upgraded_from_centroid = {
        s for s in new_direct
        if matches_v1.get(s, {}).get("match_source") == "lz_centroid"
    }
    upgraded_from_prop = {
        s for s in new_direct
        if matches_v1.get(s, {}).get("match_source") == "propagated"
    }

    flagged_3_5 = {s for s, v in validation.items() if not v["county_ok"]}
    confirmed_3_5 = {s for s, v in validation.items() if v["county_ok"]}

    with open(out_path, "w") as f:
        f.write("# MORA Matching Results (Passes 3.5 – 7)\n\n")

        f.write("## Before vs After\n\n")
        f.write("| Source | V1 Count | V2 Count | Change |\n")
        f.write("|---|---|---|---|\n")
        all_srcs = sorted(set(src1) | set(src2))
        for s in all_srcs:
            c1 = src1.get(s, 0); c2 = src2.get(s, 0)
            f.write(f"| {s} | {c1} | {c2} | {c2-c1:+d} |\n")
        f.write(f"\n**Total substations:** {len(matches_v1)} → {len(matches_v2)}\n\n")

        f.write("## Pass 3.5 — County Validation\n\n")
        f.write(f"- Checked: **{len(validation)}** medium/high-confidence matches with MORA county data\n")
        f.write(f"- County-confirmed (within 100 km of MORA county centroid): **{len(confirmed_3_5)}**\n")
        f.write(f"- County-flagged (>100 km from MORA county centroid): **{len(flagged_3_5)}**\n\n")
        if flagged_3_5:
            f.write("### Flagged matches for review\n\n")
            f.write("| Substation | Source | Confidence | Score | Matched Name | MORA County | Dist (km) |\n")
            f.write("|---|---|---|---|---|---|---|\n")
            for s in sorted(flagged_3_5):
                m = matches_v1[s]
                v = validation[s]
                f.write(f"| {s} | {m['match_source']} | {m['confidence']} | "
                        f"{m.get('score','')} | {m.get('matched_name','')} | "
                        f"{v['mora_county']} | {v['county_dist_km']} |\n")
            f.write("\n")

        f.write("## Passes 4, 6, 7 — New Direct Matches\n\n")
        f.write(f"- New direct lat/lon matches via MORA: **{len(new_direct)}**\n")
        f.write(f"  - Upgraded from lz_centroid: {len(upgraded_from_centroid)}\n")
        f.write(f"  - Upgraded from propagated: {len(upgraded_from_prop)}\n\n")
        by_new_src = Counter(matches_v2[s]["match_source"] for s in new_direct)
        for s, n in by_new_src.most_common():
            f.write(f"  - `{s}`: {n}\n")
        f.write("\n")

        if new_direct:
            f.write("### Sample new matches\n\n")
            f.write("| Substation | Source | Confidence | Score | Matched Name | MORA County |\n")
            f.write("|---|---|---|---|---|---|\n")
            for s in sorted(new_direct)[:40]:
                m = matches_v2[s]
                f.write(f"| {s} | {m['match_source']} | {m['confidence']} | "
                        f"{m.get('score','')} | {m.get('matched_name','')} | "
                        f"{m.get('mora_county','')} |\n")
            f.write("\n")

        f.write("## Pass 5 — County Centroid Upgrades\n\n")
        n_upgraded = src2.get("mora_county_centroid", 0)
        f.write(f"- Substations upgraded from lz_centroid → mora_county_centroid: **{n_upgraded}**\n")
        f.write("  This replaces load-zone-level geographic fallback (~250,000 km²) ")
        f.write("with county-level (~2,600 km² average) anchoring.\n\n")

        f.write("## Confidence Summary\n\n")
        f.write("| Confidence | V1 | V2 | Change |\n")
        f.write("|---|---|---|---|\n")
        for c in ["high", "medium", "low", "none"]:
            c1 = conf1.get(c, 0); c2 = conf2.get(c, 0)
            f.write(f"| {c} | {c1} | {c2} | {c2-c1:+d} |\n")
        f.write("\n")

    print(f"Saved: {out_path}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading data...\n")
    mora     = load_mora()
    matches  = load_existing_matches()
    sp_rows  = load_sp()
    osm_subs = load_osm_substations()
    eia_plants = load_eia_plants()
    ix_queue = load_ix_queue()

    print(f"  MORA entries: {len(mora)}")
    print(f"  Existing matches: {len(matches)}")
    print(f"  OSM substations: {len(osm_subs)}")
    print(f"  EIA-860 ERCOT plants: {len(eia_plants)}")
    print(f"  IX queue entries: {len(ix_queue)}")
    print()

    # Build indexes
    county_centroids = build_county_centroids(eia_plants)
    print(f"  County centroids derived: {len(county_centroids)}")

    sub_to_mora, code_to_mora, inr_to_mora = build_mora_indexes(mora)
    psse_to_sub = {r["PSSE_BUS_NAME"]: r["SUBSTATION"] for r in sp_rows}
    print(f"  MORA substation index entries: {len(sub_to_mora)}")
    print()

    # Snapshot of v1 for reporting
    matches_v1 = {s: dict(m) for s, m in matches.items()}

    # Pass 3.5
    validation = pass_35_county_validate(matches, sub_to_mora, county_centroids)
    print()

    # Add validation metadata to matches
    for sub, v in validation.items():
        matches[sub]["county_validated"] = str(v["county_ok"])
        matches[sub]["county_dist_km"]   = str(v["county_dist_km"])
        matches[sub]["mora_county"]      = v["mora_county"]

    # Pass 5
    p5 = pass5_county_upgrade(matches, sub_to_mora, county_centroids)
    for sub, new_m in p5.items():
        matches[sub].update(new_m)
    print()

    # Pass 6
    p6 = pass6_mora_name_eia(matches, mora, sub_to_mora, eia_plants, county_centroids)
    for sub, new_m in p6.items():
        matches[sub].update(new_m)
    print()

    # Pass 4
    p4 = pass4_mora_name_osm(matches, mora, sub_to_mora, osm_subs, county_centroids)
    for sub, new_m in p4.items():
        if sub not in p6:  # don't overwrite a direct EIA match
            matches[sub].update(new_m)
    print()

    # Pass 7
    p7 = pass7_inr_ix_queue(matches, mora, inr_to_mora, ix_queue,
                             osm_subs, psse_to_sub, county_centroids)
    for sub, new_m in p7.items():
        if sub not in p6 and sub not in p4:
            matches[sub].update(new_m)
    print()

    # Write outputs
    write_csv(matches, sp_rows, OUT_CSV)
    write_report(matches_v1, matches, validation, REPORT_MD)

    # Print final summary to stdout
    from collections import Counter
    src_counter = Counter(m["match_source"] for m in matches.values())
    conf_counter = Counter(m["confidence"] for m in matches.values())
    print("\n=== FINAL SUMMARY ===")
    print("By source:")
    for s, n in src_counter.most_common():
        print(f"  {n:5d}  {s}")
    print("By confidence:")
    for c in ["high", "medium", "low", "none"]:
        print(f"  {conf_counter.get(c,0):5d}  {c}")


if __name__ == "__main__":
    main()
