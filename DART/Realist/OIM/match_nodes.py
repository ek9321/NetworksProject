"""
Match ERCOT settlement point substations to geographic coordinates.

Three-pass matching:
  Pass 1: EIA-860 plant names → ERCOT resource node / substation names
  Pass 2: OSM substation names → ERCOT substation names
  Pass 3: Topology propagation (NODE_NAME siblings) + load zone centroid fallback

Outputs to OIM/FirstPass/:
  texas_matched_substations.csv
  texas_matched_substations.geojson
  texas_match_report.txt

Usage:
    python match_nodes.py
"""

import csv
import json
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
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OIM_DIR = os.path.dirname(os.path.abspath(__file__))
SP_DIR = os.path.join(PROJECT_ROOT, "SP_List_EB_Mapping")
EIA_DIR = os.path.join(PROJECT_ROOT, "data", "eia8602023")
OUTPUT_DIR = os.path.join(OIM_DIR, "FirstPass")

# Load zone approximate bounding boxes for geographic sanity checks
LZ_BOUNDS = {
    "LZ_WEST":    {"lat_min": 27.0, "lat_max": 35.5, "lon_min": -106.5, "lon_max": -99.0},
    "LZ_NORTH":   {"lat_min": 31.5, "lat_max": 36.5, "lon_min": -100.0, "lon_max": -94.0},
    "LZ_HOUSTON": {"lat_min": 28.5, "lat_max": 31.0, "lon_min": -96.5, "lon_max": -93.5},
    "LZ_SOUTH":   {"lat_min": 25.5, "lat_max": 31.0, "lon_min": -100.5, "lon_max": -95.5},
}


# ---------------------------------------------------------------------------
# Normalizer
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
    """Normalize a substation/plant name for fuzzy matching."""
    if not name:
        return ""
    s = name.upper().strip()
    # Remove punctuation except spaces
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    # Remove strip words
    tokens = s.split()
    tokens = [t for t in tokens if t not in STRIP_WORDS]
    # Expand known abbreviations
    tokens = [ABBREVIATION_MAP.get(t, t) for t in tokens]
    # Strip trailing digit-only tokens (e.g., "2", "345")
    while tokens and tokens[-1].isdigit():
        tokens.pop()
    return " ".join(tokens).strip()


def consonant_skeleton(name):
    """Extract consonant skeleton for blocking."""
    if not name:
        return ""
    s = canonicalize(name)
    # Remove vowels and spaces
    return re.sub(r"[AEIOU\s]", "", s)


def ensemble_score(s1, s2):
    """Compute ensemble fuzzy match score (0-100) using multiple scorers."""
    if not s1 or not s2:
        return 0.0
    tsr = fuzz.token_sort_ratio(s1, s2)
    tsetr = fuzz.token_set_ratio(s1, s2)
    jw = JaroWinkler.normalized_similarity(s1, s2) * 100
    # Weighted mean — token_set_ratio gets highest weight as it handles
    # partial matches well (e.g., "VICTORIA" vs "VICTORIA PLANT")
    raw = 0.3 * tsr + 0.4 * tsetr + 0.3 * jw
    return raw


def validate_match(ercot_canonical, candidate_canonical, raw_score):
    """
    Apply structural validation to reject false positives.
    Returns adjusted score (0 if rejected).
    """
    if raw_score <= 0:
        return 0.0

    ec = ercot_canonical.replace(" ", "")
    cc = candidate_canonical.replace(" ", "")

    # Reject very short ERCOT names (<=3 chars) unless near-exact
    if len(ec) <= 3 and raw_score < 92:
        return 0.0

    # Require first 2 characters to match (catches KIMBRO→"East Blackland" type garbage)
    if len(ec) >= 2 and len(cc) >= 2:
        if ec[:2] != cc[:2]:
            return 0.0

    # Penalize large length ratio mismatch (e.g., "FT" vs "FORT BEND SOLAR LLC")
    if ec and cc:
        ratio = min(len(ec), len(cc)) / max(len(ec), len(cc))
        if ratio < 0.4:
            raw_score *= 0.8  # Heavy penalty

    return raw_score


# Thresholds — tightened for clean output
THRESHOLD_HIGH = 92
THRESHOLD_MEDIUM = 82


def classify_confidence(score):
    """Classify match confidence into tiers."""
    if score >= THRESHOLD_HIGH:
        return "high"
    elif score >= THRESHOLD_MEDIUM:
        return "medium"
    else:
        return "low"


def point_in_lz(lat, lon, lz):
    """Check if a point falls within a load zone's approximate bounds."""
    if lz not in LZ_BOUNDS:
        return True  # Can't check, assume OK
    b = LZ_BOUNDS[lz]
    return (b["lat_min"] <= lat <= b["lat_max"] and
            b["lon_min"] <= lon <= b["lon_max"])


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_settlement_points():
    """Load ERCOT settlement points CSV."""
    path = os.path.join(SP_DIR, "Settlement_Points_01292026_104938.csv")
    with open(path) as f:
        return list(csv.DictReader(f))


def load_resource_node_to_unit():
    """Load ERCOT resource node to unit mapping."""
    path = os.path.join(SP_DIR, "Resource_Node_to_Unit_01292026_104938.csv")
    with open(path) as f:
        return list(csv.DictReader(f))


def load_eia_plants():
    """Load EIA-860 plants filtered to ERCOT, returning plant_code, name, lat, lon."""
    plant_xlsx = os.path.join(EIA_DIR, "2___Plant_Y2023.xlsx")
    df = pd.read_excel(plant_xlsx, skiprows=1)

    ba_col = [c for c in df.columns if "balanc" in c.lower() and "code" in c.lower()][0]
    name_col = [c for c in df.columns if "plant name" in c.lower()][0]
    code_col = [c for c in df.columns if "plant code" in c.lower()][0]
    lat_col = [c for c in df.columns if "lat" in c.lower()][0]
    lon_col = [c for c in df.columns if "lon" in c.lower()][0]

    ercot = df[df[ba_col] == "ERCO"].copy()
    plants = []
    for _, row in ercot.iterrows():
        lat = row[lat_col]
        lon = row[lon_col]
        if pd.isna(lat) or pd.isna(lon):
            continue
        plants.append({
            "plant_code": int(row[code_col]),
            "plant_name": str(row[name_col]).strip(),
            "lat": float(lat),
            "lon": float(lon),
            "canonical": canonicalize(str(row[name_col])),
        })
    return plants


def load_osm_substations():
    """Load OSM substations GeoJSON for Texas."""
    path = os.path.join(OIM_DIR, "data", "texas_substations.geojson")
    with open(path) as f:
        data = json.load(f)
    subs = []
    for feat in data["features"]:
        props = feat["properties"]
        lon, lat = feat["geometry"]["coordinates"]
        name = props.get("name", "")
        if not name:
            continue
        subs.append({
            "osm_id": props["osm_id"],
            "name": name,
            "canonical": canonicalize(name),
            "skeleton": consonant_skeleton(name),
            "voltage_kv": props.get("voltage_kv"),
            "lat": lat,
            "lon": lon,
        })
    return subs


# ---------------------------------------------------------------------------
# Pass 1: EIA-860 → ERCOT resource nodes
# ---------------------------------------------------------------------------

def run_pass1(settlement_points, resource_nodes, eia_plants):
    """Match EIA-860 plants to ERCOT substations via resource node names."""
    print("=" * 60)
    print("PASS 1: EIA-860 Plant Name → ERCOT Resource Node / Substation")
    print("=" * 60)

    # Build substation → resource_nodes mapping
    sub_to_resource = defaultdict(set)
    for rn in resource_nodes:
        sub = rn["UNIT_SUBSTATION"]
        rnode = rn["RESOURCE_NODE"]
        sub_to_resource[sub].add(rnode)

    # Also get resource nodes from settlement points
    sp_resource_subs = defaultdict(set)
    for sp in settlement_points:
        rn = sp.get("RESOURCE_NODE", "").strip()
        sub = sp["SUBSTATION"]
        if rn:
            sp_resource_subs[sub].add(rn)

    # Get unique substations
    all_subs = set(sp["SUBSTATION"] for sp in settlement_points)

    # Build EIA plant lookup with blocking by first 3 chars of canonical name
    eia_blocks = defaultdict(list)
    for p in eia_plants:
        key = p["canonical"][:3] if len(p["canonical"]) >= 3 else p["canonical"]
        eia_blocks[key].append(p)

    matches = {}
    stats = {"high": 0, "medium": 0, "low": 0, "tried": 0}

    for sub in sorted(all_subs):
        sub_canonical = canonicalize(sub)
        if not sub_canonical:
            continue

        # Collect all names to try: substation name + any resource node names
        names_to_try = [sub_canonical]
        for rn in sub_to_resource.get(sub, set()) | sp_resource_subs.get(sub, set()):
            rn_clean = canonicalize(rn)
            if rn_clean and rn_clean != sub_canonical:
                names_to_try.append(rn_clean)

        best_score = 0
        best_plant = None
        best_via = None

        for try_name in names_to_try:
            is_sub_name = (try_name == sub_canonical)

            # Blocking: check EIA plants with same first 3 chars + full scan for short names
            block_key = try_name[:3] if len(try_name) >= 3 else try_name
            candidates = eia_blocks.get(block_key, [])
            # Also try skeleton-based blocking
            try_skel = consonant_skeleton(try_name)
            if len(try_skel) >= 3:
                for k, plants in eia_blocks.items():
                    for p in plants:
                        if consonant_skeleton(p["canonical"])[:4] == try_skel[:4] and p not in candidates:
                            candidates.append(p)

            for plant in candidates:
                raw = ensemble_score(try_name, plant["canonical"])
                score = validate_match(try_name, plant["canonical"], raw)

                # If matched via resource node (not substation name directly),
                # verify the substation name also shares first char with plant.
                # Prevents COBSW→"Shannon Wind" type errors where resource node
                # aliases connect unrelated substations to distant plants.
                if not is_sub_name and score > 0:
                    sub_first = sub_canonical.replace(" ", "")[:1].upper()
                    plant_first = plant["canonical"].replace(" ", "")[:1].upper()
                    if sub_first and plant_first and sub_first != plant_first:
                        score = 0  # Reject: substation and plant names don't align

                if score > best_score:
                    best_score = score
                    best_plant = plant
                    best_via = try_name

        stats["tried"] += 1

        if best_score >= THRESHOLD_MEDIUM and best_plant is not None:
            conf = classify_confidence(best_score)
            if conf == "low":
                continue  # Below medium threshold after validation
            stats[conf] += 1
            matches[sub] = {
                "lat": best_plant["lat"],
                "lon": best_plant["lon"],
                "source": "eia860",
                "confidence": conf,
                "score": round(best_score, 1),
                "matched_name": best_plant["plant_name"],
                "eia_plant_code": best_plant["plant_code"],
                "matched_via": best_via,
            }

    total = stats["high"] + stats["medium"]
    print(f"  Substations tried: {stats['tried']}")
    print(f"  High confidence (≥{THRESHOLD_HIGH}): {stats['high']}")
    print(f"  Medium confidence ({THRESHOLD_MEDIUM}-{THRESHOLD_HIGH}): {stats['medium']}")
    print(f"  Total accepted: {total}")
    print()

    return matches


# ---------------------------------------------------------------------------
# Pass 2: OSM substations → ERCOT substations
# ---------------------------------------------------------------------------

def run_pass2(settlement_points, osm_subs, already_matched):
    """Match OSM substation names to unmatched ERCOT substations."""
    print("=" * 60)
    print("PASS 2: OSM Substation Name → ERCOT Substation Name")
    print("=" * 60)

    # Get unique unmatched substations with their load zones
    sub_lz = {}
    sub_voltages = defaultdict(set)
    for sp in settlement_points:
        sub = sp["SUBSTATION"]
        if sub not in already_matched:
            sub_lz[sub] = sp["SETTLEMENT_LOAD_ZONE"]
            v = sp.get("VOLTAGE_LEVEL", "")
            if v:
                try:
                    sub_voltages[sub].add(float(v))
                except ValueError:
                    pass

    # Build OSM blocking index by first 3 chars of canonical name + skeleton
    osm_by_prefix = defaultdict(list)
    osm_by_skeleton = defaultdict(list)
    for osub in osm_subs:
        key = osub["canonical"][:3] if len(osub["canonical"]) >= 3 else osub["canonical"]
        osm_by_prefix[key].append(osub)
        skel = osub["skeleton"][:4] if len(osub["skeleton"]) >= 4 else osub["skeleton"]
        if skel:
            osm_by_skeleton[skel].append(osub)

    matches = {}
    stats = {"high": 0, "medium": 0, "tried": 0}

    for sub in sorted(sub_lz.keys()):
        sub_canonical = canonicalize(sub)
        if not sub_canonical or len(sub_canonical) < 3:
            continue

        lz = sub_lz[sub]

        # Blocking: prefix + skeleton
        prefix_key = sub_canonical[:3]
        skel_key = consonant_skeleton(sub)[:4]
        candidates = list(osm_by_prefix.get(prefix_key, []))
        for osub in osm_by_skeleton.get(skel_key, []):
            if osub not in candidates:
                candidates.append(osub)

        best_score = 0
        best_osub = None

        for osub in candidates:
            raw = ensemble_score(sub_canonical, osub["canonical"])
            score = validate_match(sub_canonical, osub["canonical"], raw)
            if score <= 0:
                continue

            # Load zone geographic check — penalize if outside expected zone
            if not point_in_lz(osub["lat"], osub["lon"], lz):
                score *= 0.7  # Significant penalty

            # Voltage consistency bonus
            if osub["voltage_kv"] and sub_voltages.get(sub):
                osm_v = osub["voltage_kv"]
                ercot_vs = sub_voltages[sub]
                if any(abs(osm_v - ev) < 15 for ev in ercot_vs):
                    score = min(100, score * 1.05)

            if score > best_score:
                best_score = score
                best_osub = osub

        stats["tried"] += 1

        if best_score >= THRESHOLD_MEDIUM and best_osub is not None:
            conf = classify_confidence(best_score)
            if conf == "low":
                continue
            stats[conf] += 1
            matches[sub] = {
                "lat": best_osub["lat"],
                "lon": best_osub["lon"],
                "source": "osm",
                "confidence": conf,
                "score": round(best_score, 1),
                "matched_name": best_osub["name"],
                "osm_id": best_osub["osm_id"],
                "matched_via": sub_canonical,
            }

    total = stats["high"] + stats["medium"]
    print(f"  Substations tried: {stats['tried']}")
    print(f"  High confidence (≥{THRESHOLD_HIGH}): {stats['high']}")
    print(f"  Medium confidence ({THRESHOLD_MEDIUM}-{THRESHOLD_HIGH}): {stats['medium']}")
    print(f"  Total accepted: {total}")
    print()

    return matches


# ---------------------------------------------------------------------------
# Pass 3: Topology propagation + load zone centroid fallback
# ---------------------------------------------------------------------------

def run_pass3(settlement_points, already_matched):
    """Propagate coordinates via NODE_NAME siblings and LZ centroids."""
    print("=" * 60)
    print("PASS 3: Topology Propagation + Load Zone Centroid Fallback")
    print("=" * 60)

    # Group substations by NODE_NAME
    node_to_subs = defaultdict(set)
    sub_to_nodes = defaultdict(set)
    sub_lz = {}
    for sp in settlement_points:
        node = sp["NODE_NAME"]
        sub = sp["SUBSTATION"]
        node_to_subs[node].add(sub)
        sub_to_nodes[sub].add(node)
        sub_lz[sub] = sp["SETTLEMENT_LOAD_ZONE"]

    all_subs = set(sp["SUBSTATION"] for sp in settlement_points)
    unmatched = all_subs - set(already_matched.keys())

    # Propagation: if any substation sharing a NODE_NAME is matched, use its coords
    propagated = {}
    for sub in sorted(unmatched):
        for node in sub_to_nodes.get(sub, set()):
            for sibling in node_to_subs.get(node, set()):
                if sibling in already_matched:
                    m = already_matched[sibling]
                    propagated[sub] = {
                        "lat": m["lat"],
                        "lon": m["lon"],
                        "source": "propagated",
                        "confidence": "low",
                        "score": 0,
                        "propagated_from": sibling,
                    }
                    break
            if sub in propagated:
                break

    still_unmatched = unmatched - set(propagated.keys())

    # Load zone centroid fallback
    lz_centroids = {
        "LZ_WEST":    (31.0, -102.5),
        "LZ_NORTH":   (33.5, -97.0),
        "LZ_HOUSTON": (29.8, -95.3),
        "LZ_SOUTH":   (29.0, -98.0),
    }

    centroid_matches = {}
    for sub in still_unmatched:
        lz = sub_lz.get(sub, "")
        if lz in lz_centroids:
            lat, lon = lz_centroids[lz]
            centroid_matches[sub] = {
                "lat": lat,
                "lon": lon,
                "source": "lz_centroid",
                "confidence": "none",
                "score": 0,
            }

    print(f"  Propagated from siblings: {len(propagated)}")
    print(f"  Load zone centroid fallback: {len(centroid_matches)}")
    print(f"  Still unmatched: {len(still_unmatched) - len(centroid_matches)}")
    print()

    return propagated, centroid_matches


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_results(all_matches, settlement_points, output_dir):
    """Save matched substations as CSV and GeoJSON."""
    os.makedirs(output_dir, exist_ok=True)

    # Enrich with load zone info
    sub_lz = {}
    sub_voltages = defaultdict(set)
    for sp in settlement_points:
        sub = sp["SUBSTATION"]
        sub_lz[sub] = sp["SETTLEMENT_LOAD_ZONE"]
        v = sp.get("VOLTAGE_LEVEL", "")
        if v:
            try:
                sub_voltages[sub].add(float(v))
            except ValueError:
                pass

    # CSV
    csv_path = os.path.join(output_dir, "texas_matched_substations.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ercot_substation", "lat", "lon", "match_source", "confidence",
            "score", "matched_name", "load_zone", "max_voltage_kv",
            "eia_plant_code", "osm_id", "propagated_from",
        ])
        for sub, m in sorted(all_matches.items()):
            voltages = sub_voltages.get(sub, set())
            max_v = max(voltages) if voltages else ""
            writer.writerow([
                sub,
                round(m["lat"], 6),
                round(m["lon"], 6),
                m["source"],
                m["confidence"],
                m.get("score", ""),
                m.get("matched_name", ""),
                sub_lz.get(sub, ""),
                max_v,
                m.get("eia_plant_code", ""),
                m.get("osm_id", ""),
                m.get("propagated_from", ""),
            ])
    print(f"Saved CSV: {csv_path}")

    # GeoJSON
    features = []
    for sub, m in all_matches.items():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [m["lon"], m["lat"]]},
            "properties": {
                "ercot_substation": sub,
                "match_source": m["source"],
                "confidence": m["confidence"],
                "score": m.get("score", 0),
                "matched_name": m.get("matched_name", ""),
                "load_zone": sub_lz.get(sub, ""),
            },
        })
    geojson_path = os.path.join(output_dir, "texas_matched_substations.geojson")
    with open(geojson_path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)
    print(f"Saved GeoJSON: {geojson_path}")


def generate_report(all_matches, total_subs, settlement_points, output_dir):
    """Generate the match report."""
    os.makedirs(output_dir, exist_ok=True)

    # Stats by source
    by_source = defaultdict(int)
    by_confidence = defaultdict(int)
    by_source_conf = defaultdict(lambda: defaultdict(int))
    by_lz_source = defaultdict(lambda: defaultdict(int))

    sub_lz = {}
    for sp in settlement_points:
        sub_lz[sp["SUBSTATION"]] = sp["SETTLEMENT_LOAD_ZONE"]

    for sub, m in all_matches.items():
        by_source[m["source"]] += 1
        by_confidence[m["confidence"]] += 1
        by_source_conf[m["source"]][m["confidence"]] += 1
        lz = sub_lz.get(sub, "unknown")
        by_lz_source[lz][m["source"]] += 1

    # Count high-quality matches (eia860 + osm, confidence >= medium)
    hq = sum(1 for m in all_matches.values()
             if m["source"] in ("eia860", "osm") and m["confidence"] in ("high", "medium"))

    report_path = os.path.join(output_dir, "report.md")
    with open(report_path, "w") as f:
        f.write("# First Pass: ERCOT Node Matching Report\n\n")

        # Executive summary
        f.write("## Executive Summary\n\n")
        f.write(f"Attempted to geolocate **{total_subs}** unique ERCOT substations ")
        f.write(f"from the Settlement Point to Electrical Bus mapping.\n\n")
        f.write(f"- **{by_source.get('eia860', 0)}** matched via EIA-860 plant names (Pass 1)\n")
        f.write(f"- **{by_source.get('osm', 0)}** matched via OSM substation names (Pass 2)\n")
        f.write(f"- **{by_source.get('propagated', 0)}** propagated from matched siblings (Pass 3)\n")
        f.write(f"- **{by_source.get('lz_centroid', 0)}** assigned load zone centroid (fallback)\n")
        total_matched = len(all_matches)
        pct = 100 * total_matched / total_subs if total_subs else 0
        f.write(f"\n**Total geolocated: {total_matched}/{total_subs} ({pct:.1f}%)**\n\n")
        f.write(f"**High-quality matches (EIA-860 + OSM, confidence ≥ medium): {hq}** ")
        hq_pct = 100 * hq / total_subs if total_subs else 0
        f.write(f"({hq_pct:.1f}% of total substations)\n\n")

        # Confidence breakdown
        f.write("## Confidence Breakdown\n\n")
        f.write("| Confidence | Count | % of Total |\n")
        f.write("|---|---|---|\n")
        for conf in ["high", "medium", "low", "none"]:
            c = by_confidence.get(conf, 0)
            p = 100 * c / total_subs if total_subs else 0
            f.write(f"| {conf} | {c} | {p:.1f}% |\n")
        f.write("\n")

        # By source and confidence
        f.write("## Match Source × Confidence\n\n")
        f.write("| Source | High | Medium | Low | None | Total |\n")
        f.write("|---|---|---|---|---|---|\n")
        for src in ["eia860", "osm", "propagated", "lz_centroid"]:
            sc = by_source_conf[src]
            total_src = sum(sc.values())
            f.write(f"| {src} | {sc.get('high', 0)} | {sc.get('medium', 0)} | "
                    f"{sc.get('low', 0)} | {sc.get('none', 0)} | {total_src} |\n")
        f.write("\n")

        # By load zone
        f.write("## Matches by Load Zone\n\n")
        f.write("| Load Zone | EIA-860 | OSM | Propagated | Centroid | Total |\n")
        f.write("|---|---|---|---|---|---|\n")
        for lz in sorted(by_lz_source.keys()):
            ls = by_lz_source[lz]
            total_lz = sum(ls.values())
            f.write(f"| {lz} | {ls.get('eia860', 0)} | {ls.get('osm', 0)} | "
                    f"{ls.get('propagated', 0)} | {ls.get('lz_centroid', 0)} | {total_lz} |\n")
        f.write("\n")

        # Sample matches by source
        f.write("## Sample Matches\n\n")
        for src in ["eia860", "osm"]:
            f.write(f"### {src.upper()} matches (top 20 by score)\n\n")
            f.write("| ERCOT Sub | Matched Name | Score | Confidence |\n")
            f.write("|---|---|---|---|\n")
            src_matches = [(sub, m) for sub, m in all_matches.items() if m["source"] == src]
            src_matches.sort(key=lambda x: x[1].get("score", 0), reverse=True)
            for sub, m in src_matches[:20]:
                f.write(f"| {sub} | {m.get('matched_name', '')} | {m.get('score', '')} | {m['confidence']} |\n")
            f.write("\n")

        # Worst accepted matches (lowest scores) for review
        f.write("### Lowest-scoring accepted matches (for manual review)\n\n")
        f.write("| ERCOT Sub | Source | Matched Name | Score | Confidence |\n")
        f.write("|---|---|---|---|---|\n")
        scored = [(sub, m) for sub, m in all_matches.items()
                  if m["source"] in ("eia860", "osm") and m.get("score", 0) > 0]
        scored.sort(key=lambda x: x[1]["score"])
        for sub, m in scored[:20]:
            f.write(f"| {sub} | {m['source']} | {m.get('matched_name', '')} | "
                    f"{m.get('score', '')} | {m['confidence']} |\n")
        f.write("\n")

    print(f"Saved report: {report_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading data...\n")

    settlement_points = load_settlement_points()
    resource_nodes = load_resource_node_to_unit()
    eia_plants = load_eia_plants()
    osm_subs = load_osm_substations()

    all_subs = set(sp["SUBSTATION"] for sp in settlement_points)
    total_subs = len(all_subs)

    print(f"ERCOT unique substations: {total_subs}")
    print(f"EIA-860 ERCOT plants: {len(eia_plants)}")
    print(f"OSM named substations: {len(osm_subs)}")
    print()

    # Pass 1
    pass1_matches = run_pass1(settlement_points, resource_nodes, eia_plants)

    # Pass 2
    pass2_matches = run_pass2(settlement_points, osm_subs, pass1_matches)

    # Merge pass 1 + 2
    combined = dict(pass1_matches)
    combined.update(pass2_matches)

    # Pass 3
    propagated, centroids = run_pass3(settlement_points, combined)
    combined.update(propagated)
    combined.update(centroids)

    # Summary
    print("=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    by_source = defaultdict(int)
    for m in combined.values():
        by_source[m["source"]] += 1
    for src in ["eia860", "osm", "propagated", "lz_centroid"]:
        print(f"  {src:>15s}: {by_source.get(src, 0)}")
    print(f"  {'TOTAL':>15s}: {len(combined)}/{total_subs} ({100*len(combined)/total_subs:.1f}%)")
    print()

    # Export
    export_results(combined, settlement_points, OUTPUT_DIR)
    generate_report(combined, total_subs, settlement_points, OUTPUT_DIR)


if __name__ == "__main__":
    main()
