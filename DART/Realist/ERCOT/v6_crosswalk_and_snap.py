"""
Pass V6: Crosswalk + strict OSM snap-attach for trusted non-OSM matches.

Implements two steps:
1) Build an ERCOT crosswalk table:
   Resource Node -> Substation -> NODE_NAME/ELECTRICAL_BUS/HUB/LZ -> matched location/OSM node.
2) Expand dashboard-usable coverage by strict coordinate snapping for trusted matches:
   - candidates: match_source in {eia860, mora_eia860}, confidence in {high, medium}, no osm_id
   - nearest OSM substation (>=115 kV) in same ERCOT load zone
   - auto-accept if distance <= 1.0 km
   - review queue if 1.0 < distance <= 2.0 km

Outputs:
  OIM/FirstPass/texas_matched_substations_v6.csv
  OIM/FirstPass/texas_matched_substations_v6_snap_review.csv
  data/processed/ercot_crosswalk_v1.csv
  ERCOT/v6_matching_report.md
  ERCOT/v6_coverage_delta_report.md
"""

from __future__ import annotations

import csv
import json
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List

from shapely.geometry import Point, shape


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

V5_CSV = os.path.join(ROOT, "OIM", "FirstPass", "texas_matched_substations_v5.csv")
V6_CSV = os.path.join(ROOT, "OIM", "FirstPass", "texas_matched_substations_v6.csv")
REVIEW_CSV = os.path.join(ROOT, "OIM", "FirstPass", "texas_matched_substations_v6_snap_review.csv")

SP_CSV = os.path.join(ROOT, "SP_List_EB_Mapping", "Settlement_Points_01292026_104938.csv")
RNU_CSV = os.path.join(ROOT, "SP_List_EB_Mapping", "Resource_Node_to_Unit_01292026_104938.csv")

OSM_SUBS_GEOJSON = os.path.join(ROOT, "OIM", "data", "texas_substations.geojson")
ERCOT_ZONES_GEOJSON = os.path.join(ROOT, "OIM", "data", "ercot_zones.geojson")
LMP_SNAPSHOT_CSV = os.path.join(ROOT, "OIM", "data", "lmp_test.csv")

CROSSWALK_CSV = os.path.join(ROOT, "data", "processed", "ercot_crosswalk_v1.csv")
MATCH_REPORT_MD = os.path.join(ROOT, "ERCOT", "v6_matching_report.md")
COVERAGE_REPORT_MD = os.path.join(ROOT, "ERCOT", "v6_coverage_delta_report.md")

TRUSTED_SOURCES = {"eia860", "mora_eia860"}
AUTO_MAX_KM = 1.0
REVIEW_MAX_KM = 2.0


@dataclass
class OsmNode:
    osm_id: str
    name: str
    lat: float
    lon: float
    kv: float
    lz: str


LZ_NAME_TO_CODE = {
    "Houston": "LZ_HOUSTON",
    "North": "LZ_NORTH",
    "South": "LZ_SOUTH",
    "West": "LZ_WEST",
}


def read_csv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: str, rows: List[dict], fieldnames: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.asin(math.sqrt(a))


def load_zone_polygons() -> Dict[str, object]:
    with open(ERCOT_ZONES_GEOJSON, encoding="utf-8") as f:
        data = json.load(f)

    polygons = {}
    for feat in data["features"]:
        name = feat.get("properties", {}).get("NAME", "").strip()
        lz = LZ_NAME_TO_CODE.get(name)
        if not lz:
            continue
        # Repair occasional self-intersections from simplified polygons.
        polygons[lz] = shape(feat["geometry"]).buffer(0)
    return polygons


def classify_lz(lat: float, lon: float, zone_polys: Dict[str, object]) -> str:
    p = Point(lon, lat)
    for lz, poly in zone_polys.items():
        if poly.contains(p):
            return lz
    return ""


def load_osm_nodes_by_lz(zone_polys: Dict[str, object]) -> Dict[str, List[OsmNode]]:
    with open(OSM_SUBS_GEOJSON, encoding="utf-8") as f:
        data = json.load(f)

    out = defaultdict(list)
    for feat in data["features"]:
        props = feat.get("properties", {})
        kv = props.get("voltage_kv") or 0
        try:
            kv = float(kv)
        except (ValueError, TypeError):
            kv = 0
        if kv < 115:
            continue

        lon, lat = feat["geometry"]["coordinates"]
        lz = classify_lz(lat, lon, zone_polys)
        if not lz:
            continue

        osm_id = str(props.get("osm_id", "")).strip()
        if not osm_id:
            continue

        out[lz].append(
            OsmNode(
                osm_id=osm_id,
                name=str(props.get("name") or "").strip(),
                lat=float(lat),
                lon=float(lon),
                kv=kv,
                lz=lz,
            )
        )
    return out


def nearest_available_osm(
    lat: float,
    lon: float,
    lz: str,
    osm_by_lz: Dict[str, List[OsmNode]],
    used_osm_ids: set,
) -> tuple[OsmNode | None, float]:
    best_node = None
    best_dist = float("inf")

    for node in osm_by_lz.get(lz, []):
        if node.osm_id in used_osm_ids:
            continue
        d = haversine_km(lat, lon, node.lat, node.lon)
        if d < best_dist:
            best_dist = d
            best_node = node

    return best_node, best_dist


def apply_v6_snap(rows_v5: List[dict], osm_by_lz: Dict[str, List[OsmNode]]) -> tuple[List[dict], List[dict], List[dict]]:
    rows_v6 = [dict(r) for r in rows_v5]

    # Existing direct osm bindings are reserved.
    used_osm_ids = {
        str(r.get("osm_id", "")).strip()
        for r in rows_v6
        if str(r.get("osm_id", "")).strip()
    }

    candidate_rows = []
    for idx, row in enumerate(rows_v6):
        src = row.get("match_source", "")
        conf = row.get("confidence", "")
        has_osm = str(row.get("osm_id", "")).strip() != ""
        lz = row.get("load_zone", "")
        if src in TRUSTED_SOURCES and conf in {"high", "medium"} and not has_osm and lz in LZ_NAME_TO_CODE.values():
            candidate_rows.append((idx, row))

    # Deterministic ordering: higher confidence first, then source priority, then score descending.
    conf_rank = {"high": 0, "medium": 1}
    src_rank = {"mora_eia860": 0, "eia860": 1}

    def _score_num(x: str) -> float:
        try:
            return float(x)
        except (ValueError, TypeError):
            return -1.0

    candidate_rows.sort(
        key=lambda t: (
            conf_rank.get(t[1].get("confidence", "medium"), 2),
            src_rank.get(t[1].get("match_source", ""), 9),
            -_score_num(t[1].get("score", "")),
            t[1].get("ercot_substation", ""),
        )
    )

    accepted = []
    review = []

    for idx, row in candidate_rows:
        sub = row.get("ercot_substation", "")
        lz = row.get("load_zone", "")
        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
        except (ValueError, TypeError, KeyError):
            continue

        node, dist_km = nearest_available_osm(lat, lon, lz, osm_by_lz, used_osm_ids)
        if node is None:
            continue

        rec = {
            "ercot_substation": sub,
            "load_zone": lz,
            "original_match_source": row.get("match_source", ""),
            "original_confidence": row.get("confidence", ""),
            "score": row.get("score", ""),
            "lat": row.get("lat", ""),
            "lon": row.get("lon", ""),
            "nearest_osm_id": node.osm_id,
            "nearest_osm_name": node.name,
            "nearest_osm_kv": f"{node.kv:.1f}",
            "distance_km": f"{dist_km:.3f}",
        }

        if dist_km <= AUTO_MAX_KM:
            prev_source = row.get("match_source", "")
            prev_conf = row.get("confidence", "")

            row["original_match_source"] = prev_source
            row["original_confidence"] = prev_conf
            row["match_source"] = f"snap_{prev_source}"
            # Conservative downgrade for snapped attachment.
            row["confidence"] = "medium"
            row["osm_id"] = node.osm_id
            row["snap_distance_km"] = f"{dist_km:.3f}"
            row["snap_status"] = "auto"
            row["snap_rule"] = "same_lz_nearest_osm_le_1km"
            row["snap_candidate_name"] = node.name
            row["snap_candidate_kv"] = f"{node.kv:.1f}"

            used_osm_ids.add(node.osm_id)
            accepted.append(rec)
        elif dist_km <= REVIEW_MAX_KM:
            rec["review_reason"] = "same_lz_nearest_osm_between_1km_and_2km"
            review.append(rec)

    return rows_v6, accepted, review


def unique_join(values: Iterable[str], sep: str = ";") -> str:
    uniq = []
    seen = set()
    for v in values:
        s = str(v or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    return sep.join(uniq)


def load_latest_lmp_resource_nodes() -> tuple[str, set]:
    if not os.path.exists(LMP_SNAPSHOT_CSV):
        return "", set()

    rows = read_csv(LMP_SNAPSHOT_CSV)
    if not rows:
        return "", set()

    latest = max(r.get("SCED Timestamp", "") for r in rows)
    rns = {
        r.get("Location", "")
        for r in rows
        if r.get("SCED Timestamp", "") == latest and r.get("Location Type", "") == "Resource Node"
    }
    return latest, {rn for rn in rns if rn}


def build_crosswalk(rows_v6: List[dict]) -> List[dict]:
    sp_rows = read_csv(SP_CSV)
    rnu_rows = read_csv(RNU_CSV)

    latest_ts, latest_rns = load_latest_lmp_resource_nodes()

    sub_to_match = {r["ercot_substation"]: r for r in rows_v6}

    sp_by_rn = defaultdict(list)
    sp_by_sub = defaultdict(list)
    for sp in sp_rows:
        sub = sp.get("SUBSTATION", "").strip()
        rn = sp.get("RESOURCE_NODE", "").strip()
        if sub:
            sp_by_sub[sub].append(sp)
        if rn:
            sp_by_rn[rn].append(sp)

    # Primary RN -> SUB mapping from RNU, fallback from SP rows.
    rn_to_sub = {}
    for r in rnu_rows:
        rn = r.get("RESOURCE_NODE", "").strip()
        sub = r.get("UNIT_SUBSTATION", "").strip()
        if rn and sub and rn not in rn_to_sub:
            rn_to_sub[rn] = sub

    for rn, sps in sp_by_rn.items():
        if rn in rn_to_sub:
            continue
        sub = next((s.get("SUBSTATION", "").strip() for s in sps if s.get("SUBSTATION", "").strip()), "")
        if sub:
            rn_to_sub[rn] = sub

    all_rns = sorted(set(rn_to_sub.keys()) | set(sp_by_rn.keys()))

    out = []
    for rn in all_rns:
        sub = rn_to_sub.get(rn, "")
        sp_rows_for_rn = sp_by_rn.get(rn, [])

        # If no direct SP rows for RN, backfill from substation rows.
        if not sp_rows_for_rn and sub:
            sp_rows_for_rn = sp_by_sub.get(sub, [])

        match = sub_to_match.get(sub, {})

        out.append(
            {
                "resource_node": rn,
                "substation": sub,
                "node_name": unique_join(s.get("NODE_NAME", "") for s in sp_rows_for_rn),
                "electrical_bus": unique_join(s.get("ELECTRICAL_BUS", "") for s in sp_rows_for_rn),
                "psse_bus_name": unique_join(s.get("PSSE_BUS_NAME", "") for s in sp_rows_for_rn),
                "psse_bus_number": unique_join(s.get("PSSE_BUS_NUMBER", "") for s in sp_rows_for_rn),
                "voltage_level_kv": unique_join(s.get("VOLTAGE_LEVEL", "") for s in sp_rows_for_rn),
                "settlement_load_zone": unique_join(s.get("SETTLEMENT_LOAD_ZONE", "") for s in sp_rows_for_rn),
                "hub_bus_name": unique_join(s.get("HUB_BUS_NAME", "") for s in sp_rows_for_rn),
                "hub": unique_join(s.get("HUB", "") for s in sp_rows_for_rn),
                "lat": match.get("lat", ""),
                "lon": match.get("lon", ""),
                "match_source": match.get("match_source", ""),
                "confidence": match.get("confidence", ""),
                "county_validated": match.get("county_validated", ""),
                "county_dist_km": match.get("county_dist_km", ""),
                "osm_id": match.get("osm_id", ""),
                "snap_distance_km": match.get("snap_distance_km", ""),
                "snap_status": match.get("snap_status", ""),
                "in_latest_lmp_snapshot": "1" if rn in latest_rns else "0",
                "latest_lmp_timestamp": latest_ts,
            }
        )

    return out


def count_with_osm(rows: List[dict]) -> int:
    return sum(1 for r in rows if str(r.get("osm_id", "")).strip())


def lmp_substation_set() -> tuple[str, set]:
    if not os.path.exists(LMP_SNAPSHOT_CSV):
        return "", set()

    lmp_rows = read_csv(LMP_SNAPSHOT_CSV)
    if not lmp_rows:
        return "", set()

    latest = max(r.get("SCED Timestamp", "") for r in lmp_rows)
    latest_rns = {
        r.get("Location", "")
        for r in lmp_rows
        if r.get("SCED Timestamp", "") == latest and r.get("Location Type", "") == "Resource Node"
    }

    rnu = read_csv(RNU_CSV)
    sp = read_csv(SP_CSV)

    rn_to_sub = {}
    for r in rnu:
        rn = r.get("RESOURCE_NODE", "").strip()
        sub = r.get("UNIT_SUBSTATION", "").strip()
        if rn and sub:
            rn_to_sub[rn] = sub

    for s in sp:
        rn = s.get("RESOURCE_NODE", "").strip()
        sub = s.get("SUBSTATION", "").strip()
        if rn and sub and rn not in rn_to_sub:
            rn_to_sub[rn] = sub

    subs = {rn_to_sub[rn] for rn in latest_rns if rn in rn_to_sub}
    return latest, subs


def make_matching_report(rows_v5: List[dict], rows_v6: List[dict], accepted: List[dict], review: List[dict]) -> str:
    c5 = Counter(r.get("match_source", "") for r in rows_v5)
    c6 = Counter(r.get("match_source", "") for r in rows_v6)

    conf5 = Counter(r.get("confidence", "") for r in rows_v5)
    conf6 = Counter(r.get("confidence", "") for r in rows_v6)

    lines = []
    lines.append("# V6 Matching Report")
    lines.append("")
    lines.append(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Input file: `OIM/FirstPass/texas_matched_substations_v5.csv`")
    lines.append(f"- Output file: `OIM/FirstPass/texas_matched_substations_v6.csv`")
    lines.append(f"- Strict auto-accepted snaps (<= {AUTO_MAX_KM:.1f} km): **{len(accepted)}**")
    lines.append(f"- Review queue (>{AUTO_MAX_KM:.1f} and <= {REVIEW_MAX_KM:.1f} km): **{len(review)}**")
    lines.append("")
    lines.append("## Match Source Delta")
    lines.append("")
    lines.append("| Source | V5 | V6 | Delta |")
    lines.append("|---|---|---|---|")
    for src in sorted(set(c5) | set(c6)):
        v5 = c5.get(src, 0)
        v6 = c6.get(src, 0)
        d = v6 - v5
        lines.append(f"| {src} | {v5} | {v6} | {d:+d} |")

    lines.append("")
    lines.append("## Confidence Delta")
    lines.append("")
    lines.append("| Confidence | V5 | V6 | Delta |")
    lines.append("|---|---|---|---|")
    for c in ["high", "medium", "low", "none"]:
        v5 = conf5.get(c, 0)
        v6 = conf6.get(c, 0)
        d = v6 - v5
        lines.append(f"| {c} | {v5} | {v6} | {d:+d} |")

    lines.append("")
    lines.append("## New Auto-Attached OSM Bindings")
    lines.append("")
    lines.append("| Substation | Original Source | Original Conf | New Source | OSM ID | OSM Name | Distance (km) |")
    lines.append("|---|---|---|---|---|---|---|")

    # keep stable readable ordering
    accepted_sorted = sorted(accepted, key=lambda r: float(r["distance_km"]))
    for a in accepted_sorted:
        new_source = f"snap_{a['original_match_source']}"
        lines.append(
            f"| {a['ercot_substation']} | {a['original_match_source']} | {a['original_confidence']} | "
            f"{new_source} | {a['nearest_osm_id']} | {a['nearest_osm_name']} | {a['distance_km']} |"
        )

    lines.append("")
    lines.append("## Review Queue (1-2 km, not applied)")
    lines.append("")
    lines.append("| Substation | Original Source | Original Conf | Nearest OSM ID | OSM Name | Distance (km) |")
    lines.append("|---|---|---|---|---|---|")
    for r in sorted(review, key=lambda x: float(x["distance_km"])):
        lines.append(
            f"| {r['ercot_substation']} | {r['original_match_source']} | {r['original_confidence']} | "
            f"{r['nearest_osm_id']} | {r['nearest_osm_name']} | {r['distance_km']} |"
        )

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Auto-attach candidates were restricted to `eia860` and `mora_eia860` rows with `high/medium` confidence and empty `osm_id`.")
    lines.append("- Nearest-node search was constrained to the same ERCOT load zone polygon.")
    lines.append("- Auto-accepted rows were marked `match_source = snap_<original_source>` and conservatively downgraded to `confidence = medium`.")

    return "\n".join(lines) + "\n"


def make_coverage_report(rows_v5: List[dict], rows_v6: List[dict], crosswalk_rows: List[dict], accepted: List[dict], review: List[dict]) -> str:
    total = len(rows_v5)
    osm5 = count_with_osm(rows_v5)
    osm6 = count_with_osm(rows_v6)

    hq5 = sum(1 for r in rows_v5 if r.get("confidence") in {"high", "medium"})
    hq6 = sum(1 for r in rows_v6 if r.get("confidence") in {"high", "medium"})
    hq_osm5 = sum(
        1
        for r in rows_v5
        if r.get("confidence") in {"high", "medium"} and str(r.get("osm_id", "")).strip()
    )
    hq_osm6 = sum(
        1
        for r in rows_v6
        if r.get("confidence") in {"high", "medium"} and str(r.get("osm_id", "")).strip()
    )

    latest_lmp_ts, lmp_subs = lmp_substation_set()
    v5_by_sub = {r["ercot_substation"]: r for r in rows_v5}
    v6_by_sub = {r["ercot_substation"]: r for r in rows_v6}

    lmp_with_osm5 = sum(1 for s in lmp_subs if str(v5_by_sub.get(s, {}).get("osm_id", "")).strip())
    lmp_with_osm6 = sum(1 for s in lmp_subs if str(v6_by_sub.get(s, {}).get("osm_id", "")).strip())

    lines = []
    lines.append("# V6 Coverage Delta Report")
    lines.append("")
    lines.append(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append("")
    lines.append("## Core Coverage Delta")
    lines.append("")
    lines.append("| Metric | V5 | V6 | Delta |")
    lines.append("|---|---|---|---|")
    lines.append(f"| Total substations | {total} | {len(rows_v6)} | {len(rows_v6)-total:+d} |")
    lines.append(f"| Rows with OSM ID | {osm5} | {osm6} | {osm6-osm5:+d} |")
    lines.append(f"| Rows with OSM ID (%) | {osm5/total*100:.2f}% | {osm6/total*100:.2f}% | {(osm6-osm5)/total*100:+.2f}% |")
    lines.append(f"| High/Medium rows | {hq5} | {hq6} | {hq6-hq5:+d} |")
    lines.append(f"| High/Medium rows with OSM ID | {hq_osm5} | {hq_osm6} | {hq_osm6-hq_osm5:+d} |")
    lines.append("")

    lines.append("## LMP Snapshot Coverage Delta")
    lines.append("")
    lines.append(f"Latest SCED timestamp in `OIM/data/lmp_test.csv`: `{latest_lmp_ts}`")
    lines.append("")
    lines.append("| Metric | V5 | V6 | Delta |")
    lines.append("|---|---|---|---|")
    lines.append(f"| Unique substations represented in latest Resource Node LMP snapshot | {len(lmp_subs)} | {len(lmp_subs)} | +0 |")
    lines.append(f"| Those substations with OSM ID | {lmp_with_osm5} | {lmp_with_osm6} | {lmp_with_osm6-lmp_with_osm5:+d} |")
    lines.append(f"| LMP substation OSM coverage (%) | {lmp_with_osm5/len(lmp_subs)*100:.2f}% | {lmp_with_osm6/len(lmp_subs)*100:.2f}% | {(lmp_with_osm6-lmp_with_osm5)/len(lmp_subs)*100:+.2f}% |")
    lines.append("")

    lines.append("## Step Outputs")
    lines.append("")
    lines.append(f"- Crosswalk rows written: **{len(crosswalk_rows)}** -> `data/processed/ercot_crosswalk_v1.csv`")
    lines.append(f"- Auto-accepted strict snaps: **{len(accepted)}**")
    lines.append(f"- Review queue rows (1-2 km): **{len(review)}** -> `OIM/FirstPass/texas_matched_substations_v6_snap_review.csv`")

    if accepted:
        by_src = Counter(a["original_match_source"] for a in accepted)
        lines.append("")
        lines.append("## Auto-Accepted by Original Source")
        lines.append("")
        lines.append("| Original Source | Count |")
        lines.append("|---|---|")
        for src, n in sorted(by_src.items()):
            lines.append(f"| {src} | {n} |")

    return "\n".join(lines) + "\n"


def main() -> None:
    rows_v5 = read_csv(V5_CSV)

    zone_polys = load_zone_polygons()
    osm_by_lz = load_osm_nodes_by_lz(zone_polys)

    rows_v6, accepted, review = apply_v6_snap(rows_v5, osm_by_lz)

    base_fields = list(rows_v5[0].keys()) if rows_v5 else []
    extra_fields = [
        "original_match_source",
        "original_confidence",
        "snap_distance_km",
        "snap_status",
        "snap_rule",
        "snap_candidate_name",
        "snap_candidate_kv",
    ]
    fieldnames_v6 = base_fields + [f for f in extra_fields if f not in base_fields]
    write_csv(V6_CSV, rows_v6, fieldnames_v6)

    review_fields = [
        "ercot_substation",
        "load_zone",
        "original_match_source",
        "original_confidence",
        "score",
        "lat",
        "lon",
        "nearest_osm_id",
        "nearest_osm_name",
        "nearest_osm_kv",
        "distance_km",
        "review_reason",
    ]
    write_csv(REVIEW_CSV, review, review_fields)

    crosswalk_rows = build_crosswalk(rows_v6)
    crosswalk_fields = [
        "resource_node",
        "substation",
        "node_name",
        "electrical_bus",
        "psse_bus_name",
        "psse_bus_number",
        "voltage_level_kv",
        "settlement_load_zone",
        "hub_bus_name",
        "hub",
        "lat",
        "lon",
        "match_source",
        "confidence",
        "county_validated",
        "county_dist_km",
        "osm_id",
        "snap_distance_km",
        "snap_status",
        "in_latest_lmp_snapshot",
        "latest_lmp_timestamp",
    ]
    write_csv(CROSSWALK_CSV, crosswalk_rows, crosswalk_fields)

    match_md = make_matching_report(rows_v5, rows_v6, accepted, review)
    with open(MATCH_REPORT_MD, "w", encoding="utf-8") as f:
        f.write(match_md)

    cov_md = make_coverage_report(rows_v5, rows_v6, crosswalk_rows, accepted, review)
    with open(COVERAGE_REPORT_MD, "w", encoding="utf-8") as f:
        f.write(cov_md)

    print("V6 complete")
    print(f"  V6 CSV:        {V6_CSV}")
    print(f"  Review CSV:    {REVIEW_CSV}")
    print(f"  Crosswalk CSV: {CROSSWALK_CSV}")
    print(f"  Match report:  {MATCH_REPORT_MD}")
    print(f"  Coverage:      {COVERAGE_REPORT_MD}")


if __name__ == "__main__":
    main()
