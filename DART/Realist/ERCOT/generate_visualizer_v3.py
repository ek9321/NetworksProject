"""
Generate a self-contained HTML visualizer for the ERCOT grid.

V3: Geometry-based line splitting (PyPSA-Eur approach).

Instead of only using line endpoints to build topology, V3 checks if each
line's full geometry passes near any substation and splits it there, creating
mesh connections that endpoint-only methods miss.

Reads:
  Realist/grid_data/texas_substations.geojson                 — OSM substation geometries
  Realist/grid_data/texas_hv_lines.geojson                    — OSM HV line geometries
  Realist/grid_data/texas_plants.geojson                      — OSM power plant geometries
  Realist/grid_data/ercot_zones.geojson                       — ERCOT zone polygons (4 zones)
  Realist/grid_data/matching_results/texas_matched_substations_v6.csv — ERCOT→OSM match results
  Birchfield/data/eia8602023/3_1_Generator_Y2023.xlsx         — EIA-860 generator capacity

Writes:
  Realist/grid_visualizer_v3.html

V3 changes vs V2:
  - No endpoint proximity filter on substations (lines may only touch interiors)
  - Geometry-based line splitting replaces junction clustering + BFS contraction
  - Edge-splice (Fix 8) removed — line splitting handles this naturally
  - Junction handling for unsnapped endpoints preserved (degree >= 3 → split nodes)
  - Iterative dead-end pruning added
  - Effective substation-only graph stats reported
"""

import csv
import json
import math
import os
from collections import defaultdict, deque

from shapely.geometry import shape, Point

REALIST    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT       = os.path.dirname(REALIST)
OSM_SUBS   = os.path.join(REALIST, "grid_data", "texas_substations.geojson")
LINES      = os.path.join(REALIST, "grid_data", "texas_hv_lines.geojson")
OSM_PLANTS = os.path.join(REALIST, "grid_data", "texas_plants.geojson")
ZONES      = os.path.join(REALIST, "grid_data", "ercot_zones.geojson")
V5         = os.path.join(REALIST, "grid_data", "matching_results", "texas_matched_substations_v6.csv")
EIA_GEN    = os.path.join(ROOT, "Birchfield", "data", "eia8602023", "3_1_Generator_Y2023.xlsx")
OUT        = os.path.join(REALIST, "grid_visualizer_v3.html")

# ---------------------------------------------------------------------------
# ERCOT zone polygons
# ---------------------------------------------------------------------------

# Zone display colours (fill used both in Python stats and HTML)
ZONE_COLORS = {
    'Houston': '#f87171',
    'North':   '#60a5fa',
    'South':   '#34d399',
    'West':    '#fb923c',
}


def load_zones():
    """
    Returns:
      zone_features : list of raw GeoJSON features (for HTML embedding)
      ercot_union   : shapely geometry — union of all zones (for PIP filtering)
    """
    with open(ZONES, encoding='utf-8') as f:
        data = json.load(f)

    zone_features = data['features']
    geoms = [shape(feat['geometry']) for feat in zone_features]

    from shapely.ops import unary_union
    # buffer(0) repairs self-intersections introduced by simplification
    geoms = [g.buffer(0) for g in geoms]
    ercot_union = unary_union(geoms)

    names = [f['properties'].get('NAME', '?') for f in zone_features]
    print(f"  Loaded {len(zone_features)} ERCOT zones: {names}")
    print(f"  Union bbox: {tuple(round(x, 2) for x in ercot_union.bounds)}")
    return zone_features, ercot_union


# ---------------------------------------------------------------------------
# EIA-860 capacity lookup
# ---------------------------------------------------------------------------

def load_eia_capacity():
    """Returns dict: plant_code (int) -> {mw: float, tech: str}"""
    try:
        import pandas as pd
    except ImportError:
        print("  pandas not available — skipping EIA capacity lookup")
        return {}
    try:
        gen = pd.read_excel(EIA_GEN, sheet_name='Operable', header=1)
    except Exception as e:
        print(f"  EIA-860 load failed: {e}")
        return {}

    cap = {}
    for _, row in gen.iterrows():
        pid = row.get('Plant Code')
        mw  = row.get('Nameplate Capacity (MW)', 0)
        tech = str(row.get('Technology', '') or '').strip()
        if pd.notna(pid) and pd.notna(mw) and mw > 0:
            pid = int(pid)
            if pid not in cap:
                cap[pid] = {'mw': 0.0, 'techs': set()}
            cap[pid]['mw']    += float(mw)
            cap[pid]['techs'].add(tech)

    result = {}
    for pid, v in cap.items():
        techs = v['techs']
        def short(t):
            t = t.lower()
            if 'solar' in t:                   return 'Solar'
            if 'wind' in t:                    return 'Wind'
            if 'gas' in t and 'combined' in t: return 'Gas CC'
            if 'gas' in t:                     return 'Gas CT'
            if 'nuclear' in t:                 return 'Nuclear'
            if 'coal' in t or 'steam' in t:    return 'Coal'
            if 'hydro' in t:                   return 'Hydro'
            if 'batter' in t or 'storage' in t:return 'Storage'
            return 'Other'
        result[pid] = {'mw': round(v['mw'], 0), 'tech': ', '.join(sorted(set(short(t) for t in techs)))}

    print(f"  EIA-860 capacity loaded for {len(result)} plants")
    return result


# ---------------------------------------------------------------------------
# ERCOT→OSM lookup  (osm_id → ERCOT match metadata)
# ---------------------------------------------------------------------------

def build_ercot_lookup(eia_cap):
    """
    Returns dict: osm_id (int) -> {ercot, conf, src, sc, lz, mw, tech}

    Only rows that were directly matched to an OSM substation have osm_id set
    (match_source in: osm, mora_osm, cp_osm, hv_osm_345, mora_ix_queue).
    """
    lookup = {}
    with open(V5, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            raw = row.get('osm_id', '').strip()
            if not raw:
                continue
            try:
                osm_id = int(float(raw))
            except (ValueError, TypeError):
                continue

            gen_mw, gen_tech = '', ''
            eia_raw = row.get('eia_plant_code', '').strip()
            if eia_raw:
                try:
                    pid = int(float(eia_raw))
                    if pid in eia_cap:
                        gen_mw   = str(int(eia_cap[pid]['mw']))
                        gen_tech = eia_cap[pid]['tech']
                except (ValueError, TypeError):
                    pass

            lookup[osm_id] = {
                'ercot': row['ercot_substation'].strip(),
                'conf':  row.get('confidence', 'none'),
                'src':   row.get('match_source', ''),
                'sc':    (row.get('score') or '').strip(),
                'lz':    row.get('load_zone', '').replace('LZ_', ''),
                'mw':    gen_mw,
                'tech':  gen_tech,
            }
    print(f"  ERCOT→OSM lookup: {len(lookup)} entries")
    return lookup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def in_texas_bounds(lon, lat):
    return 25.0 <= lat <= 37.5 and -107.5 <= lon <= -93.0


GRID = 0.05   # ~5.5 km grid cells


def build_grid(points):
    """points: list of (lat, lon, *extra). Returns spatial grid dict."""
    g = defaultdict(list)
    for p in points:
        k = (int(p[0] / GRID), int(p[1] / GRID))
        g[k].append(p)
    return g


def nearest_in_grid(lat, lon, grid, max_km):
    k0 = (int(lat / GRID), int(lon / GRID))
    best = float('inf')
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            for p in grid.get((k0[0]+dr, k0[1]+dc), []):
                d = haversine(lat, lon, p[0], p[1])
                if d < best:
                    best = d
    return best


def point_to_segment_km(plat, plon, alat, alon, blat, blon):
    """Approximate distance from point P to segment A-B in km, plus projection t."""
    # Project P onto line AB using flat-earth approximation (OK for <50 km)
    cos_lat = math.cos(math.radians(plat))
    dx_a = (plon - alon) * cos_lat * 111.32
    dy_a = (plat - alat) * 111.32
    dx_ab = (blon - alon) * cos_lat * 111.32
    dy_ab = (blat - alat) * 111.32
    len_sq = dx_ab * dx_ab + dy_ab * dy_ab
    if len_sq < 1e-10:
        return math.sqrt(dx_a * dx_a + dy_a * dy_a), 0.0
    t = max(0.0, min(1.0, (dx_a * dx_ab + dy_a * dy_ab) / len_sq))
    proj_x = t * dx_ab
    proj_y = t * dy_ab
    dist = math.sqrt((dx_a - proj_x) ** 2 + (dy_a - proj_y) ** 2)
    return dist, t


def snap_voltage(kv):
    """Map voltage to tier for dedup purposes."""
    if kv >= 345:
        return 345
    elif kv >= 200:
        return 230
    else:
        return 138


# ---------------------------------------------------------------------------
# Load line features from OSM GeoJSON
# ---------------------------------------------------------------------------

def load_line_features(ercot_union):
    """
    Load ALL power lines/cables inside ERCOT territory.
    Returns (all_features, hv_features) where hv_features is the >= 138 kV
    subset used for SCED topology building.
    """
    print("  Loading line features…")
    with open(LINES, encoding='utf-8') as f:
        data = json.load(f)

    bounds = ercot_union.bounds   # (minx, miny, maxx, maxy)

    def in_ercot_bbox(lon, lat):
        return bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]

    all_valid = []
    hv_valid = []
    skipped = 0
    for feat in data['features']:
        kv = feat['properties'].get('voltage_kv') or 0
        coords = feat['geometry']['coordinates']
        if len(coords) < 2:
            continue
        lon0, lat0 = coords[0]
        lon1, lat1 = coords[-1]
        in0 = in_ercot_bbox(lon0, lat0) and ercot_union.contains(Point(lon0, lat0))
        in1 = in_ercot_bbox(lon1, lat1) and ercot_union.contains(Point(lon1, lat1))
        if not (in0 or in1):
            skipped += 1
            continue
        all_valid.append(feat)
        if kv >= 138:
            hv_valid.append(feat)

    print(f"  All line features: {len(all_valid)}  (dropped {skipped} outside ERCOT)")
    print(f"  HV subset (>= 138 kV): {len(hv_valid)}  (for SCED topology)")
    return all_valid, hv_valid


def build_ep_grid(features):
    """Build a spatial grid of all line endpoints for fast proximity lookups."""
    pts = []
    for feat in features:
        coords = feat['geometry']['coordinates']
        kv = feat['properties'].get('voltage_kv') or 0
        for lon, lat in (coords[0], coords[-1]):
            pts.append((lat, lon, kv))
    return build_grid(pts)


# ---------------------------------------------------------------------------
# Load OSM substations (node set) — V3: no endpoint proximity filter
# ---------------------------------------------------------------------------

def load_nodes(ercot_lookup, ercot_union):
    """
    Load ALL OSM substations inside ERCOT territory.
    V3: No voltage filter — include 69 kV, 115 kV, and untagged substations.
    These serve as transformer endpoints where HV lines terminate.
    No endpoint proximity filter — substations may be near line interiors.
    """
    with open(OSM_SUBS, encoding='utf-8') as f:
        data = json.load(f)

    bounds = ercot_union.bounds

    nodes = []
    skipped_ercot = 0
    for feat in data['features']:
        props = feat['properties']
        kv = props.get('voltage_kv') or 0

        lon, lat = feat['geometry']['coordinates']

        # Cheap bbox gate before shapely PIP
        if not (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]):
            skipped_ercot += 1
            continue
        if not ercot_union.contains(Point(lon, lat)):
            skipped_ercot += 1
            continue

        osm_id = props['osm_id']
        name   = (props.get('name') or '').strip()
        op     = (props.get('operator') or '').strip()
        stype  = (props.get('substation_type') or '').strip()

        match = ercot_lookup.get(osm_id, {})
        conf  = match.get('conf', 'unmatched') if match else 'unmatched'

        nodes.append({
            'i':     len(nodes),
            'lat':   round(lat, 5),
            'lon':   round(lon, 5),
            'id':    str(osm_id),
            'name':  name,
            'kv':    kv,
            'ercot': match.get('ercot', ''),
            'conf':  conf,
            'src':   match.get('src', ''),
            'sc':    match.get('sc', ''),
            'lz':    match.get('lz', ''),
            'mw':    match.get('mw', ''),
            'tech':  match.get('tech', ''),
            'op':    op,
            'stype': stype,
        })

    print(f"  OSM subs (raw): {len(nodes)} kept (all voltages), "
          f"{skipped_ercot} dropped (outside ERCOT)")

    # Step 1: Deduplicate intra-complex OSM features within 200 m at the same voltage tier.
    # Sort so the "best" representative (named first, then highest osm_id) is seen first.
    DEDUP_KM = 0.2
    nodes_sorted = sorted(nodes, key=lambda n: (1 if n['name'] else 0, int(n['id'])), reverse=True)
    dedup = []
    for node in nodes_sorted:
        kv, lat, lon = node['kv'], node['lat'], node['lon']
        dup = False
        for rep in dedup:
            if rep['kv'] != kv:
                continue
            if abs(rep['lat'] - lat) > 0.003 or abs(rep['lon'] - lon) > 0.003:
                continue
            if haversine(lat, lon, rep['lat'], rep['lon']) <= DEDUP_KM:
                dup = True
                break
        if not dup:
            dedup.append(node)
    for i, n in enumerate(dedup):
        n['i'] = i
    nodes = dedup
    print(f"  After intra-complex dedup: {len(nodes)} nodes ({len(nodes_sorted)-len(nodes)} removed)")

    # Step 2: Cross-voltage merge — collapse substations at different voltage
    # tiers within 300 m into a single bus.  Real transformers are local
    # equipment at one physical location, not branches between distant nodes.
    # Keep the higher-kV node (HV lines snap to it; MV lines also snap by
    # proximity since both passes share the same node set).
    XVOLT_MERGE_KM = 0.30
    merge_grid = defaultdict(list)
    for n in nodes:
        k = (int(n['lat'] / 0.003), int(n['lon'] / 0.003))
        merge_grid[k].append(n)

    absorbed = set()   # indices of nodes merged into a higher-kV neighbor
    for n in nodes:
        if n['i'] in absorbed:
            continue
        lat, lon, kv = n['lat'], n['lon'], n['kv']
        k = (int(lat / 0.003), int(lon / 0.003))
        for di in range(-1, 2):
            for dj in range(-1, 2):
                for m in merge_grid.get((k[0]+di, k[1]+dj), []):
                    if m['i'] == n['i'] or m['i'] in absorbed:
                        continue
                    if m['kv'] == kv:
                        continue  # same voltage — already deduped
                    if haversine(lat, lon, m['lat'], m['lon']) > XVOLT_MERGE_KM:
                        continue
                    # Absorb the lower-kV node into the higher-kV one
                    if m['kv'] > kv:
                        absorbed.add(n['i'])
                        break   # n is absorbed, stop searching
                    else:
                        absorbed.add(m['i'])
            if n['i'] in absorbed:
                break

    nodes = [n for n in nodes if n['i'] not in absorbed]
    for i, n in enumerate(nodes):
        n['i'] = i

    print(f"  Cross-voltage merge (<{XVOLT_MERGE_KM*1000:.0f} m): "
          f"absorbed {len(absorbed)} lower-kV nodes into co-located higher-kV nodes")

    matched = sum(1 for n in nodes if n['conf'] != 'unmatched')
    print(f"  ERCOT-matched: {matched} / {len(nodes)} ({matched/len(nodes)*100:.1f}%)")
    return nodes


# ---------------------------------------------------------------------------
# Spatial grid for fast nearest-node lookup
# ---------------------------------------------------------------------------

NODE_GRID = 0.015   # degrees per cell (~1.7 km) — finer than v2 for segment matching


def build_node_grid(nodes):
    g = defaultdict(list)
    for n in nodes:
        k = (int(n['lat'] / NODE_GRID), int(n['lon'] / NODE_GRID))
        g[k].append(n)
    return g


def nearest_node(lat, lon, grid, max_km):
    k0 = (int(lat / NODE_GRID), int(lon / NODE_GRID))
    best_d, best_n = float('inf'), None
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            for n in grid.get((k0[0]+dr, k0[1]+dc), []):
                d = haversine(lat, lon, n['lat'], n['lon'])
                if d < best_d:
                    best_d, best_n = d, n
    return (best_n, best_d) if best_d <= max_km else (None, None)


# ---------------------------------------------------------------------------
# Simplify line coordinates
# ---------------------------------------------------------------------------

def simplify_coords(coords, max_pts):
    if len(coords) <= max_pts:
        return coords
    stride = max(1, len(coords) // max_pts)
    result = coords[::stride]
    if result[-1] != coords[-1]:
        result = result + [coords[-1]]
    return result


# ---------------------------------------------------------------------------
# Load OSM power plants
# ---------------------------------------------------------------------------

def load_plants(ercot_union):
    """
    Load OSM power=plant features inside ERCOT territory.
    Returns list of dicts with lat, lon, name, fuel, mw, operator.
    Compound fuels (e.g. "solar;battery") are normalised to the first token.
    """
    with open(OSM_PLANTS, encoding='utf-8') as f:
        data = json.load(f)

    bounds = ercot_union.bounds
    plants = []
    skipped = 0
    for feat in data['features']:
        lon, lat = feat['geometry']['coordinates']
        if not (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]):
            skipped += 1
            continue
        if not ercot_union.contains(Point(lon, lat)):
            skipped += 1
            continue
        props = feat['properties']
        # Normalise compound fuels to first token
        fuel_raw = (props.get('fuel') or props.get('plant:source') or '').strip().lower()
        fuel = fuel_raw.split(';')[0].split(',')[0].strip()
        mw = props.get('mw')
        plants.append({
            'lat':  round(lat, 5),
            'lon':  round(lon, 5),
            'name': (props.get('name') or '').strip(),
            'fuel': fuel,
            'mw':   round(mw, 1) if mw is not None else None,
            'op':   (props.get('operator') or '').strip(),
        })

    print(f"  Power plants: {len(plants)} inside ERCOT, {skipped} outside")
    return plants


# ---------------------------------------------------------------------------
# V3: Geometry-based line splitting
# ---------------------------------------------------------------------------

SPLIT_BUFFER_M = 300      # substation footprint + GPS error
SPLIT_BUFFER_KM = SPLIT_BUFFER_M / 1000.0
SPLIT_BUFFER_DEG = 0.004  # ~400m at Texas latitude, conservative envelope

# Endpoint snap radii (GridKit dynamic radius)
MAX_SNAP_KM_HV = 0.50     # >= 345 kV
MAX_SNAP_KM_MV = 0.40     # < 345 kV

# Junction clustering radius
JUNCTION_CLUSTER_R = 0.15  # km


def split_lines_at_substations(features, nodes, node_grid):
    """
    V3 core algorithm: geometry-based line splitting.

    For each line, check if its full geometry passes near any substation.
    Split the line at those points, creating edges between consecutive
    substations along the route.

    Returns (edges, junction_points).
      edges: list of {'a': int, 'b': int, 'kv': int}
      junction_points: list of (lat, lon, kv, line_index) for unsnapped endpoints
    """
    edges = []
    junction_points = []
    partial_connections = []  # (sub_idx, lat, lon, kv, feat_idx) for 1-hit lines

    for feat_idx, feat in enumerate(features):
        kv = int(feat['properties'].get('voltage_kv') or 0)
        coords = feat['geometry']['coordinates']
        if len(coords) < 2:
            continue

        # Compute line length for dynamic snap radius
        line_length_km = 0.0
        for ci in range(len(coords) - 1):
            lon_a, lat_a = coords[ci]
            lon_b, lat_b = coords[ci + 1]
            line_length_km += haversine(lat_a, lon_a, lat_b, lon_b)

        max_snap_km = MAX_SNAP_KM_HV if kv >= 345 else MAX_SNAP_KM_MV

        # --- Find substations this line passes near ---
        # split_hits: list of (cumulative_position, substation_index)
        # cumulative_position is a float in [0, 1] representing position along line
        split_hits = {}  # sub_idx -> (best_position, best_dist)

        cumulative_len = 0.0
        for ci in range(len(coords) - 1):
            lon_a, lat_a = coords[ci]
            lon_b, lat_b = coords[ci + 1]
            seg_len = haversine(lat_a, lon_a, lat_b, lon_b)

            # Search substations near BOTH endpoints of this segment
            checked_subs = set()
            for check_lat, check_lon in ((lat_a, lon_a), (lat_b, lon_b)):
                k0 = (int(check_lat / NODE_GRID), int(check_lon / NODE_GRID))
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        for n in node_grid.get((k0[0]+dr, k0[1]+dc), []):
                            if n['i'] in checked_subs:
                                continue
                            checked_subs.add(n['i'])

                            # Quick bounding box check
                            if (abs(n['lat'] - lat_a) > SPLIT_BUFFER_DEG and
                                abs(n['lat'] - lat_b) > SPLIT_BUFFER_DEG):
                                continue
                            if (abs(n['lon'] - lon_a) > SPLIT_BUFFER_DEG and
                                abs(n['lon'] - lon_b) > SPLIT_BUFFER_DEG):
                                continue

                            # Perpendicular distance from substation to segment
                            dist, t = point_to_segment_km(
                                n['lat'], n['lon'],
                                lat_a, lon_a,
                                lat_b, lon_b
                            )

                            if dist <= SPLIT_BUFFER_KM:
                                # Global position along line
                                if line_length_km > 0:
                                    global_pos = (cumulative_len + t * seg_len) / line_length_km
                                else:
                                    global_pos = 0.0
                                global_pos = max(0.0, min(1.0, global_pos))

                                # Keep closest passage per substation
                                if n['i'] not in split_hits or dist < split_hits[n['i']][1]:
                                    split_hits[n['i']] = (global_pos, dist)

            cumulative_len += seg_len

        # --- Also snap endpoints using dynamic radius ---
        lon0, lat0 = coords[0]
        lon1, lat1 = coords[-1]
        snap_r = min(max_snap_km, line_length_km / 3) if line_length_km > 0 else max_snap_km

        ep0_node, ep0_dist = nearest_node(lat0, lon0, node_grid, snap_r)
        if ep0_node is not None and ep0_node['i'] not in split_hits:
            split_hits[ep0_node['i']] = (0.0, ep0_dist)
        elif ep0_node is not None and ep0_node['i'] in split_hits:
            # Endpoint is closer to position 0.0 — update if position makes sense
            if split_hits[ep0_node['i']][0] > 0.5:
                split_hits[ep0_node['i']] = (0.0, ep0_dist)

        ep1_node, ep1_dist = nearest_node(lat1, lon1, node_grid, snap_r)
        if ep1_node is not None and ep1_node['i'] not in split_hits:
            split_hits[ep1_node['i']] = (1.0, ep1_dist)
        elif ep1_node is not None and ep1_node['i'] in split_hits:
            if split_hits[ep1_node['i']][0] < 0.5:
                split_hits[ep1_node['i']] = (1.0, ep1_dist)

        # --- Sort hits by position along line ---
        sorted_hits = sorted(split_hits.items(), key=lambda x: x[1][0])
        # sorted_hits: list of (sub_idx, (position, dist))

        if len(sorted_hits) >= 2:
            # Create edges between consecutive substations along the route
            for hi in range(len(sorted_hits) - 1):
                sub_a = sorted_hits[hi][0]
                sub_b = sorted_hits[hi + 1][0]
                if sub_a != sub_b:
                    edges.append({'a': sub_a, 'b': sub_b, 'kv': kv})
        elif len(sorted_hits) == 1:
            # Only one substation found — track the other endpoint as junction
            # AND record a partial connection so junction handling can link them
            sub_idx = sorted_hits[0][0]
            pos = sorted_hits[0][1][0]
            if pos < 0.5:
                junction_points.append((lat1, lon1, kv, feat_idx))
                partial_connections.append((sub_idx, lat1, lon1, kv, feat_idx))
            else:
                junction_points.append((lat0, lon0, kv, feat_idx))
                partial_connections.append((sub_idx, lat0, lon0, kv, feat_idx))
        else:
            # No substations found — track both endpoints as junctions
            junction_points.append((lat0, lon0, kv, feat_idx))
            junction_points.append((lat1, lon1, kv, feat_idx))

    n_two_plus = sum(1 for h in [None] if len(edges) > 0)  # placeholder
    print(f"  Line splitting: {len(edges)} raw edges from {len(features)} lines, "
          f"{len(junction_points)} junction points, "
          f"{len(partial_connections)} partial connections (1-hit lines)")
    return edges, junction_points, partial_connections


# ---------------------------------------------------------------------------
# Junction handling (unsnapped endpoints)
# ---------------------------------------------------------------------------

def handle_junctions(junction_points, raw_edges, partial_connections, features, nodes, node_grid):
    """
    Process unsnapped junction endpoints using v2-style clustering + BFS.

    Also resolves partial_connections: 1-hit lines where one endpoint
    hit a substation but the other didn't. For each partial connection,
    find which junction cluster the unsnapped endpoint belongs to, and
    if that cluster snaps to a substation (or is a split point), create
    an edge connecting them.

    Returns (edges, split_nodes).
    """
    if not junction_points:
        return raw_edges, []

    # --- Step 1: Cluster junction points ---
    clusters = []  # each: [lat, lon, count, max_kv, set_of_feat_indices]
    junc_map = {}  # (feat_idx, endpoint_id) → cluster_idx

    for jp_idx, (lat, lon, kv, feat_idx) in enumerate(junction_points):
        if not in_texas_bounds(lon, lat):
            continue
        best_c = None
        best_ci = None
        best_d = JUNCTION_CLUSTER_R + 0.001
        for ci, c in enumerate(clusters):
            if abs(c[0] - lat) > 0.01 or abs(c[1] - lon) > 0.01:
                continue
            d = haversine(lat, lon, c[0], c[1])
            if d <= JUNCTION_CLUSTER_R and d < best_d:
                best_d = d
                best_c = c
                best_ci = ci
        if best_c is not None:
            n = best_c[2]
            best_c[0] = (best_c[0] * n + lat) / (n + 1)
            best_c[1] = (best_c[1] * n + lon) / (n + 1)
            best_c[2] += 1
            best_c[3] = max(best_c[3], kv)
            best_c[4].add(feat_idx)
            junc_map[jp_idx] = best_ci
        else:
            junc_map[jp_idx] = len(clusters)
            clusters.append([lat, lon, 1, kv, {feat_idx}])

    # --- Step 2: Snap clusters to nearest substations ---
    cluster_to_node = {}  # cluster_idx → node['i']
    for ci, c in enumerate(clusters):
        snap_r = MAX_SNAP_KM_MV if c[3] < 345 else MAX_SNAP_KM_HV
        n, _ = nearest_node(c[0], c[1], node_grid, snap_r)
        if n is not None:
            cluster_to_node[ci] = n['i']

    sub_clusters = set(cluster_to_node.keys())

    # --- Step 3: Build junction adjacency from line features ---
    # For each junction point, we know which feat_idx it came from and which
    # cluster it belongs to. Build edges between clusters from the same line.
    #
    # We need to reconstruct which endpoint each junction_point represents.
    # In split_lines_at_substations, junction points are emitted for line
    # endpoints that didn't snap. Each line has at most 2 endpoints.
    # Group junction points by feat_idx.
    feat_juncs = defaultdict(list)  # feat_idx → list of cluster_idx
    for jp_idx, (lat, lon, kv, feat_idx) in enumerate(junction_points):
        ci = junc_map.get(jp_idx)
        if ci is not None:
            feat_juncs[feat_idx].append(ci)

    # Also add cluster connections from lines that had geometry-split edges
    # (one endpoint may be a junction while the other snapped to a substation).
    # We already have those edges in raw_edges, so no need to duplicate.

    junc_edges = set()  # (min(c1, c2), max(c1, c2), kv)
    junc_kv = {}
    jadj = defaultdict(set)
    for feat_idx, cis in feat_juncs.items():
        kv = int(features[feat_idx]['properties'].get('voltage_kv') or 0)
        # Remove duplicates (same cluster from both endpoints of same line)
        unique_cis = list(dict.fromkeys(cis))
        for i in range(len(unique_cis)):
            for j in range(i + 1, len(unique_cis)):
                c1, c2 = unique_cis[i], unique_cis[j]
                if c1 != c2:
                    key = (min(c1, c2), max(c1, c2))
                    junc_edges.add((*key, kv))
                    junc_kv[key] = max(junc_kv.get(key, 0), kv)
                    jadj[c1].add(c2)
                    jadj[c2].add(c1)

    # --- Step 4: Detect split points (degree >= 3, not snapped to substation) ---
    split_clusters = {ci for ci, nbrs in jadj.items()
                      if len(nbrs) >= 3 and ci not in sub_clusters}

    split_nodes = []
    base_idx = len(nodes)
    cluster_to_split = {}

    for ci in sorted(split_clusters):
        c = clusters[ci]
        split_i = base_idx + len(split_nodes)
        cluster_to_split[ci] = split_i
        split_nodes.append({
            'i':     split_i,
            'lat':   round(c[0], 5),
            'lon':   round(c[1], 5),
            'kv':    c[3],
            'split': True,
        })

    # --- Step 5: BFS contraction from stop nodes ---
    stop_set = sub_clusters | split_clusters
    cluster_to_idx = {}
    cluster_to_idx.update(cluster_to_node)
    cluster_to_idx.update(cluster_to_split)

    bfs_edges = set()
    for start_c in stop_set:
        start_idx = cluster_to_idx[start_c]
        visited = {start_c}
        queue = deque([(start_c, 0)])
        while queue:
            curr_c, path_kv = queue.popleft()
            for next_c in jadj[curr_c]:
                if next_c in visited:
                    continue
                visited.add(next_c)
                key = (min(curr_c, next_c), max(curr_c, next_c))
                seg_kv = junc_kv.get(key, 0)
                new_kv = max(path_kv, seg_kv)
                if next_c in stop_set:
                    end_idx = cluster_to_idx[next_c]
                    if start_idx != end_idx:
                        a, b = min(start_idx, end_idx), max(start_idx, end_idx)
                        bfs_edges.add((a, b, new_kv))
                else:
                    queue.append((next_c, new_kv))

    junction_edge_list = [{'a': a, 'b': b, 'kv': kv} for a, b, kv in bfs_edges]

    # --- Step 6: Resolve partial connections (1-hit lines) ---
    # For each 1-hit line, one endpoint hit a substation but the other didn't.
    # Find the nearest substation to the unsnapped endpoint (wider 1 km radius)
    # and create an edge connecting them.
    PARTIAL_SNAP_KM = 1.0  # wider than normal snap — we know one end connects
    partial_edge_list = []
    n_partial_resolved = 0
    for sub_idx, jp_lat, jp_lon, kv, feat_idx in partial_connections:
        # First try: find via cluster → substation mapping
        target_idx = None
        best_ci = None
        best_d = JUNCTION_CLUSTER_R + 0.5
        for ci, c in enumerate(clusters):
            if abs(c[0] - jp_lat) > 0.01 or abs(c[1] - jp_lon) > 0.01:
                continue
            d = haversine(jp_lat, jp_lon, c[0], c[1])
            if d < best_d:
                best_d = d
                best_ci = ci

        if best_ci is not None:
            if best_ci in cluster_to_node:
                target_idx = cluster_to_node[best_ci]
            elif best_ci in cluster_to_split:
                target_idx = cluster_to_split[best_ci]

        # Second try: direct nearest-substation lookup with wider radius
        if target_idx is None:
            n_near, d_near = nearest_node(jp_lat, jp_lon, node_grid, PARTIAL_SNAP_KM)
            if n_near is not None:
                target_idx = n_near['i']

        if target_idx is not None and target_idx != sub_idx:
            a, b = min(sub_idx, target_idx), max(sub_idx, target_idx)
            partial_edge_list.append({'a': a, 'b': b, 'kv': kv})
            n_partial_resolved += 1

    print(f"  Junction handling: {len(clusters)} clusters, "
          f"{len(sub_clusters)} snapped to substations, "
          f"{len(split_nodes)} split-point nodes (degree >= 3), "
          f"{len(junction_edge_list)} BFS edges, "
          f"{n_partial_resolved} partial connections resolved")

    # Combine geometry-split edges with junction BFS edges and partial edges
    all_edges = raw_edges + junction_edge_list + partial_edge_list
    return all_edges, split_nodes


# ---------------------------------------------------------------------------
# Dead-end pruning
# ---------------------------------------------------------------------------

def prune_dead_ends(edges, nodes, split_nodes):
    """
    Iterative dead-end pruning: remove degree-1 nodes that have no generation
    and are not ERCOT-matched.

    A substation "has generation" if it has a non-empty 'mw' field or a
    non-empty 'ercot' match.
    """
    # ALL substations are protected — they represent real physical locations.
    # Only split points (synthetic T-junctions) are eligible for pruning.
    # Generation assignment happens later in build_gen_table.py using MORA data,
    # so we can't know here which substations have generators.
    protected = {n['i'] for n in nodes}
    split_ids = {sn['i'] for sn in split_nodes}

    total_pruned_nodes = 0
    total_pruned_edges = 0
    iteration = 0

    while True:
        iteration += 1
        changed = False

        # Compute node degrees from edges
        node_degree = defaultdict(int)
        node_edges = defaultdict(list)
        for ei, e in enumerate(edges):
            node_degree[e['a']] += 1
            node_degree[e['b']] += 1
            node_edges[e['a']].append(ei)
            node_edges[e['b']].append(ei)

        remove_edges = set()
        remove_nodes = set()

        # Check all nodes with degree 1
        all_node_ids = set()
        for n in nodes:
            all_node_ids.add(n['i'])
        for sn in split_nodes:
            all_node_ids.add(sn['i'])

        for nid in all_node_ids:
            if nid in remove_nodes:
                continue
            if node_degree.get(nid, 0) != 1:
                continue
            if nid in protected:
                continue
            # Remove this dead-end node and its single edge
            for ei in node_edges.get(nid, []):
                remove_edges.add(ei)
            remove_nodes.add(nid)
            changed = True

        if not changed or iteration > 50:
            break

        edges = [e for ei, e in enumerate(edges) if ei not in remove_edges]
        split_nodes = [sn for sn in split_nodes if sn['i'] not in remove_nodes]
        split_ids -= remove_nodes
        total_pruned_nodes += len(remove_nodes)
        total_pruned_edges += len(remove_edges)

    print(f"  Dead-end pruning ({iteration} iterations): removed {total_pruned_nodes} nodes, "
          f"{total_pruned_edges} edges")
    return edges, split_nodes


# ---------------------------------------------------------------------------
# Effective graph stats
# ---------------------------------------------------------------------------

def compute_effective_stats(edges, nodes, split_nodes):
    """
    Compute substation-only graph stats by contracting through split-point chains.
    """
    split_ids = {sn['i'] for sn in split_nodes}
    sub_ids = {n['i'] for n in nodes}

    # Raw stats (including split points)
    all_node_ids = set()
    raw_degree = defaultdict(int)
    for e in edges:
        all_node_ids.add(e['a'])
        all_node_ids.add(e['b'])
        raw_degree[e['a']] += 1
        raw_degree[e['b']] += 1

    raw_nodes = len(all_node_ids)
    raw_edges = len(edges)
    raw_mean_deg = sum(raw_degree.values()) / max(len(raw_degree), 1)

    # Count bridges in raw graph
    raw_bridges = _count_bridges(edges, all_node_ids)
    raw_bridge_ratio = raw_bridges / max(raw_edges, 1)

    print(f"  Raw graph: {raw_nodes} nodes, {raw_edges} edges, "
          f"mean degree {raw_mean_deg:.2f}, {raw_bridges} bridges ({raw_bridge_ratio:.1%})")

    # Effective stats: contract through split points to get substation-only graph
    # Build adjacency
    adj = defaultdict(set)
    adj_kv = {}
    for e in edges:
        adj[e['a']].add(e['b'])
        adj[e['b']].add(e['a'])
        key = (min(e['a'], e['b']), max(e['a'], e['b']))
        adj_kv[key] = e['kv']

    # BFS from each substation through split points to find connected substations
    eff_edges_set = set()
    for start in sub_ids:
        if start not in adj:
            continue
        # BFS through split points
        visited = {start}
        queue = deque()
        for nb in adj[start]:
            queue.append((nb, adj_kv.get((min(start, nb), max(start, nb)), 138)))
            visited.add(nb)

        while queue:
            curr, path_kv = queue.popleft()
            if curr in sub_ids:
                # Reached another substation
                a, b = min(start, curr), max(start, curr)
                eff_edges_set.add((a, b, path_kv))
            elif curr in split_ids:
                # Continue through split point
                for nb in adj[curr]:
                    if nb not in visited:
                        visited.add(nb)
                        seg_kv = adj_kv.get((min(curr, nb), max(curr, nb)), 138)
                        queue.append((nb, max(path_kv, seg_kv)))

    eff_degree = defaultdict(int)
    for a, b, kv in eff_edges_set:
        eff_degree[a] += 1
        eff_degree[b] += 1

    eff_nodes = len(eff_degree)
    eff_edges = len(eff_edges_set)
    eff_mean_deg = sum(eff_degree.values()) / max(eff_nodes, 1)
    eff_edge_node_ratio = eff_edges / max(eff_nodes, 1)

    # Count bridges in effective graph
    eff_node_set = set()
    eff_edge_list = []
    for a, b, kv in eff_edges_set:
        eff_node_set.add(a)
        eff_node_set.add(b)
        eff_edge_list.append({'a': a, 'b': b, 'kv': kv})
    eff_bridges = _count_bridges(eff_edge_list, eff_node_set)
    eff_bridge_ratio = eff_bridges / max(eff_edges, 1)

    print(f"  Effective substation graph: {eff_nodes} nodes, {eff_edges} edges, "
          f"E/N ratio {eff_edge_node_ratio:.2f}, mean degree {eff_mean_deg:.2f}, "
          f"{eff_bridges} bridges ({eff_bridge_ratio:.1%})")


def _count_bridges(edges, node_set):
    """Count bridges using Tarjan's algorithm."""
    adj = defaultdict(list)
    for e in edges:
        adj[e['a']].append(e['b'])
        adj[e['b']].append(e['a'])

    disc = {}
    low = {}
    timer = [0]
    bridges = [0]

    def dfs(u, parent):
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        for v in adj[u]:
            if v not in disc:
                dfs(v, u)
                low[u] = min(low[u], low[v])
                if low[v] > disc[u]:
                    bridges[0] += 1
            elif v != parent:
                low[u] = min(low[u], disc[v])

    # Use iterative DFS to avoid recursion limit
    import sys
    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, len(node_set) + 100))

    for node in node_set:
        if node not in disc:
            dfs(node, -1)

    sys.setrecursionlimit(old_limit)
    return bridges[0]


# ---------------------------------------------------------------------------
# Process line geometries and build graph edges — V3 Route Walking
# ---------------------------------------------------------------------------

ROUTE_SPLIT_BUFFER_KM = 0.50   # 500m: substation footprint + GPS error
ROUTE_SNAP_KM = 0.50          # substation snap radius (all voltages)
# Junction clustering: use EXACT coordinate matching (OSM ways share nodes
# at exactly the same coordinates). Small tolerance for floating point.
EXACT_MATCH_DEG = 0.000005     # ~0.5m — effectively exact


def _presplit_ways_at_substations(features, nodes):
    """
    PyPSA-Eur style: for each way, check if its geometry passes within
    500m of any substation. If so, insert the substation as an intermediate
    point, effectively splitting the way into sub-ways.

    This modifies the features list in-place by replacing ways that have
    intermediate substations with multiple shorter sub-ways.

    Returns the new features list (possibly longer than input).
    """
    # Build spatial grid of substations for fast lookup
    SUB_CELL = 0.01  # ~1.1 km cells
    sub_grid = defaultdict(list)
    for n in nodes:
        gk = (int(n['lat'] / SUB_CELL), int(n['lon'] / SUB_CELL))
        sub_grid[gk].append(n)

    new_features = []
    n_split = 0
    n_ways_split = 0

    for feat in features:
        coords = feat['geometry']['coordinates']
        kv = feat['properties'].get('voltage_kv', 0)
        if len(coords) < 2 or kv < 138:
            new_features.append(feat)
            continue

        # Find substations along the interior of this way (not at endpoints)
        # For each segment, check if any substation is within 500m
        hits = []  # (segment_index, t, substation_node)
        ep0 = (coords[0][1], coords[0][0])   # (lat, lon) of first endpoint
        ep1 = (coords[-1][1], coords[-1][0])  # (lat, lon) of last endpoint

        for ci in range(len(coords) - 1):
            lon_a, lat_a = coords[ci]
            lon_b, lat_b = coords[ci + 1]

            # Search substations near this segment
            checked = set()
            for clat, clon in ((lat_a, lon_a), (lat_b, lon_b)):
                gk = (int(clat / SUB_CELL), int(clon / SUB_CELL))
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        for n in sub_grid.get((gk[0]+di, gk[1]+dj), []):
                            if n['i'] in checked:
                                continue
                            checked.add(n['i'])

                            # Skip if substation is at either endpoint of the WAY
                            d_ep0 = haversine(n['lat'], n['lon'], ep0[0], ep0[1])
                            d_ep1 = haversine(n['lat'], n['lon'], ep1[0], ep1[1])
                            if d_ep0 < ROUTE_SPLIT_BUFFER_KM or d_ep1 < ROUTE_SPLIT_BUFFER_KM:
                                continue

                            dist, t = point_to_segment_km(
                                n['lat'], n['lon'],
                                lat_a, lon_a, lat_b, lon_b
                            )
                            if dist <= ROUTE_SPLIT_BUFFER_KM and 0.02 < t < 0.98:
                                hits.append((ci, t, n))

        if not hits:
            # No intermediate substations — keep way as-is
            new_features.append(feat)
            continue

        # Deduplicate: one substation per segment, keep closest
        best_per_seg = {}
        for seg_i, t, n in hits:
            key = (seg_i, n['i'])
            if key not in best_per_seg:
                best_per_seg[key] = (seg_i, t, n)

        # Sort all hits by (segment_index, t) for sequential splitting
        sorted_hits = sorted(best_per_seg.values(), key=lambda x: (x[0], x[1]))

        # Deduplicate by substation ID (keep first occurrence)
        seen_subs = set()
        unique_hits = []
        for seg_i, t, n in sorted_hits:
            if n['i'] not in seen_subs:
                seen_subs.add(n['i'])
                unique_hits.append((seg_i, t, n))

        # Split the coordinate list at each hit point
        # Insert the substation's lon/lat at the split point
        split_points = []  # (coord_index_after_insert, substation)
        for seg_i, t, n in unique_hits:
            # Interpolate position along segment
            lon_a, lat_a = coords[seg_i]
            lon_b, lat_b = coords[seg_i + 1]
            split_lon = lon_a + t * (lon_b - lon_a)
            split_lat = lat_a + t * (lat_b - lat_a)
            split_points.append((seg_i, t, split_lon, split_lat, n))

        # Build sub-ways by splitting coords at each split point
        # Work backwards to preserve indices
        sub_coords_list = []
        remaining_coords = list(coords)
        offset = 0

        # Sort split points by global position
        # (segment index, then t within segment)
        for sp_idx, (seg_i, t, sp_lon, sp_lat, n) in enumerate(split_points):
            actual_idx = seg_i + offset
            # Coords before the split: start to split point
            pre = remaining_coords[:actual_idx + 1] + [[sp_lon, sp_lat]]
            # Coords after the split: split point to end
            remaining_coords = [[sp_lon, sp_lat]] + remaining_coords[actual_idx + 1:]
            sub_coords_list.append(pre)
            offset = 0  # remaining_coords is now relative

        sub_coords_list.append(remaining_coords)

        # Create sub-features
        n_ways_split += 1
        for sub_coords in sub_coords_list:
            if len(sub_coords) >= 2:
                sub_feat = {
                    'geometry': {'type': 'LineString', 'coordinates': sub_coords},
                    'properties': dict(feat['properties']),
                }
                new_features.append(sub_feat)
                n_split += 1

    print(f"  Pre-split: {n_ways_split} ways split at {n_split - n_ways_split} intermediate substations, "
          f"{len(new_features)} total sub-ways (was {len(features)})")
    return new_features


def _build_topology(features, nodes, node_grid):
    """
    V3 core: exact-coordinate topology on pre-split ways.

    OSM ways that meet share exact endpoint coordinates (same OSM node).
    We use exact matching (not proximity clustering) to build the junction graph.
    Then snap junctions to substations and BFS-contract through non-substation junctions.

    Returns (edges, split_nodes).
    """
    # --- Step 1: Build junction graph from exact endpoint coordinates ---
    # OSM ways share nodes — endpoints at exactly the same coordinate connect.
    # Use a fine grid (0.5m tolerance) for effectively exact matching.
    coord_to_junc = {}  # (rounded_lat, rounded_lon) → junction_id
    clusters = []  # [lat, lon, count, max_kv]

    def coord_key(lat, lon):
        # Round to ~0.5m precision for exact matching
        return (round(lat / EXACT_MATCH_DEG) , round(lon / EXACT_MATCH_DEG))

    def find_or_create_junction(lat, lon, kv):
        ck = coord_key(lat, lon)
        if ck in coord_to_junc:
            ci = coord_to_junc[ck]
            clusters[ci][3] = max(clusters[ci][3], kv)
            clusters[ci][2] += 1
            return ci
        else:
            ci = len(clusters)
            clusters.append([lat, lon, 1, kv])
            coord_to_junc[ck] = ci
            return ci

    junc_edges = set()
    junc_route_km = {}
    for feat in features:
        coords = feat['geometry']['coordinates']
        kv = int(feat['properties'].get('voltage_kv') or 0)
        if len(coords) < 2 or kv < 138:
            continue
        lon0, lat0 = coords[0]
        lon1, lat1 = coords[-1]
        if not in_texas_bounds(lon0, lat0) and not in_texas_bounds(lon1, lat1):
            continue
        j0 = find_or_create_junction(lat0, lon0, kv)
        j1 = find_or_create_junction(lat1, lon1, kv)
        if j0 != j1:
            junc_edges.add((min(j0, j1), max(j0, j1), kv))
            route_km = 0.0
            for ci in range(len(coords) - 1):
                route_km += haversine(coords[ci][1], coords[ci][0],
                                      coords[ci+1][1], coords[ci+1][0])
            key = (min(j0, j1), max(j0, j1))
            junc_route_km[key] = max(junc_route_km.get(key, 0), route_km)

    print(f"  Topology: {len(clusters)} junctions (exact coord match), {len(junc_edges)} junction edges")

    # --- Step 2: Build adjacency ---
    jadj = defaultdict(set)
    jkv = {}
    for j0, j1, kv in junc_edges:
        jadj[j0].add(j1)
        jadj[j1].add(j0)
        key = (min(j0, j1), max(j0, j1))
        jkv[key] = max(jkv.get(key, 0), kv)

    # --- Step 3: Snap junctions to substations ---
    junc_to_node = {}
    for ci, c in enumerate(clusters):
        n, _ = nearest_node(c[0], c[1], node_grid, ROUTE_SNAP_KM)
        if n is not None:
            junc_to_node[ci] = n['i']

    sub_juncs = set(junc_to_node.keys())
    print(f"  Junctions snapped to substations: {len(sub_juncs)} / {len(clusters)}")

    # --- Step 4: Split junctions (degree >= 3, not snapped) ---
    split_juncs = {j for j, nbrs in jadj.items()
                   if len(nbrs) >= 3 and j not in sub_juncs}

    split_nodes = []
    base_split_idx = len(nodes)
    junc_to_split = {}
    for j in sorted(split_juncs):
        c = clusters[j]
        split_i = base_split_idx + len(split_nodes)
        junc_to_split[j] = split_i
        split_nodes.append({
            'i': split_i,
            'lat': round(c[0], 5),
            'lon': round(c[1], 5),
            'kv': c[3],
            'split': True,
        })

    stop_set = sub_juncs | split_juncs
    junc_to_idx = {}
    junc_to_idx.update(junc_to_node)
    junc_to_idx.update(junc_to_split)

    print(f"  Stop nodes: {len(sub_juncs)} subs + {len(split_juncs)} splits = {len(stop_set)}")

    # --- Step 5: BFS contraction — accumulate route distance ---
    edges_dict = {}  # (a, b) → {'kv': int, 'km': float}
    for start_j in stop_set:
        start_idx = junc_to_idx[start_j]
        visited = {start_j}
        queue = deque([(start_j, 0, 0.0)])  # (junction, max_kv, accumulated_km)
        while queue:
            curr_j, path_kv, path_km = queue.popleft()
            for next_j in jadj[curr_j]:
                if next_j in visited:
                    continue
                visited.add(next_j)
                seg_key = (min(curr_j, next_j), max(curr_j, next_j))
                seg_kv = jkv.get(seg_key, 0)
                seg_km = junc_route_km.get(seg_key, 0.1)
                new_kv = max(path_kv, seg_kv)
                new_km = path_km + seg_km
                if next_j in stop_set:
                    end_idx = junc_to_idx[next_j]
                    if start_idx != end_idx:
                        a, b = min(start_idx, end_idx), max(start_idx, end_idx)
                        # Keep the shortest route if multiple BFS paths find the same edge
                        if (a, b) not in edges_dict or new_km < edges_dict[(a, b)]['km']:
                            edges_dict[(a, b)] = {'kv': new_kv, 'km': round(new_km, 3)}
                else:
                    queue.append((next_j, new_kv, new_km))

    edges = [{'a': a, 'b': b, 'kv': d['kv'], 'km': d['km']} for (a, b), d in edges_dict.items()]

    # Report route distance vs straight-line distance
    total_route = sum(e['km'] for e in edges)
    total_straight = 0
    node_by_i = {n['i']: n for n in nodes}
    for sn in split_nodes:
        node_by_i[sn['i']] = sn
    for e in edges:
        na = node_by_i.get(e['a'])
        nb = node_by_i.get(e['b'])
        if na and nb:
            total_straight += haversine(na['lat'], na['lon'], nb['lat'], nb['lon'])
    print(f"  BFS produced {len(edges)} edges")
    print(f"  Route distance: {total_route:,.0f} km vs straight-line: {total_straight:,.0f} km "
          f"(ratio {total_route/max(total_straight,1):.2f})")
    return edges, split_nodes


def process_lines(all_features, hv_features, nodes):
    """
    V3: Route-walking topology extraction.

    all_features: every OSM line/cable (for visual rendering)
    hv_features:  >= 138 kV subset (for SCED topology building)

    Returns (lines_high, lines_mid_hi, lines_mid_lo, lines_low, edges, split_nodes).
    """
    # --- Visual line geometry split into 4 tiers ---
    lines_high   = []   # >= 345 kV
    lines_mid_hi = []   # 200-344 kV
    lines_mid_lo = []   # 138-199 kV (SCED threshold)
    lines_low    = []   # < 138 kV (OSM-only visual, not in SCED)
    for feat in all_features:
        kv = int(feat['properties'].get('voltage_kv') or 0)
        coords = feat['geometry']['coordinates']
        lon0, lat0 = coords[0]
        lon1, lat1 = coords[-1]
        if kv >= 345:
            simp = simplify_coords(coords, 8)
            pts  = [[round(c[1], 4), round(c[0], 4)] for c in simp]
            lines_high.append({'kv': kv, 'pts': pts})
        elif kv >= 200:
            pts = [[round(lat0, 4), round(lon0, 4)],
                   [round(lat1, 4), round(lon1, 4)]]
            lines_mid_hi.append({'kv': kv, 'pts': pts})
        elif kv >= 138:
            pts = [[round(lat0, 4), round(lon0, 4)],
                   [round(lat1, 4), round(lon1, 4)]]
            lines_mid_lo.append({'kv': kv, 'pts': pts})
        else:
            pts = [[round(lat0, 4), round(lon0, 4)],
                   [round(lat1, 4), round(lon1, 4)]]
            lines_low.append({'kv': kv, 'pts': pts})

    # --- Build topology from HV features only (>= 138 kV) ---
    node_grid = build_node_grid(nodes)

    # Step 1: Pre-split ways where their geometry passes over substations
    split_features = _presplit_ways_at_substations(hv_features, nodes)

    # Step 2: Build topology on the now-split ways (endpoint clustering + BFS)
    edges, split_nodes = _build_topology(split_features, nodes, node_grid)

    # --- Cleanup ---
    # Self-loop removal
    pre = len(edges)
    edges = [e for e in edges if e['a'] != e['b']]
    dropped_loops = pre - len(edges)

    # Dedup by (min(a,b), max(a,b), tier)
    seen = set()
    deduped = []
    for e in edges:
        key = (min(e['a'], e['b']), max(e['a'], e['b']), snap_voltage(e['kv']))
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    dropped_dup = len(edges) - len(deduped)
    edges = deduped
    print(f"  Cleanup: dropped {dropped_loops} self-loops, {dropped_dup} duplicate edges")

    # Cross-voltage validation
    split_ids = {sn['i'] for sn in split_nodes}
    node_kv = {n['i']: n['kv'] for n in nodes}
    for sn in split_nodes:
        node_kv[sn['i']] = sn['kv']

    n_reclassed = 0
    for e in edges:
        a_id, b_id = e['a'], e['b']
        if a_id in split_ids or b_id in split_ids:
            continue
        kv_a = node_kv.get(a_id, 0)
        kv_b = node_kv.get(b_id, 0)
        if kv_a == 0 or kv_b == 0:
            continue
        max_node_kv = max(kv_a, kv_b)
        min_node_kv = min(kv_a, kv_b)
        edge_kv = e['kv']
        if max_node_kv < 345 and edge_kv >= 345:
            e['kv'] = int(max_node_kv)
            n_reclassed += 1
        elif min_node_kv >= 345 and edge_kv < 345:
            e['kv'] = int(max_node_kv)
            n_reclassed += 1
    print(f"  Cross-voltage validation: reclassified {n_reclassed} edges")

    # Dead-end pruning (split points only — substations are protected)
    edges, split_nodes = prune_dead_ends(edges, nodes, split_nodes)

    # Renumber split nodes contiguously
    old_to_new = {}
    for new_offset, sn in enumerate(split_nodes):
        old_i = sn['i']
        new_i = len(nodes) + new_offset
        old_to_new[old_i] = new_i
        sn['i'] = new_i
    for n in nodes:
        old_to_new[n['i']] = n['i']
    for e in edges:
        e['a'] = old_to_new.get(e['a'], e['a'])
        e['b'] = old_to_new.get(e['b'], e['b'])

    # Stats
    print(f"  Lines  high: {len(lines_high)}, mid-high: {len(lines_mid_hi)}, "
          f"mid-low: {len(lines_mid_lo)}, low: {len(lines_low)}")
    print(f"  Graph edges: {len(edges)}, Split nodes: {len(split_nodes)}")
    compute_effective_stats(edges, nodes, split_nodes)

    return lines_high, lines_mid_hi, lines_mid_lo, lines_low, edges, split_nodes


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ERCOT Transmission Grid</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      overflow: hidden;
      background: #0f172a;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    }
    #map { width: 100vw; height: 100vh; }

    /* ─── Panel shell ─── */
    #panel {
      position: fixed;
      top: 14px; right: 14px;
      z-index: 1000;
      width: 268px;
      max-height: calc(100vh - 28px);
      overflow-y: auto;
      background: rgba(10,15,30,0.95);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(148,163,184,0.11);
      border-radius: 14px;
      color: #e2e8f0;
      font-size: 13px;
      box-shadow: 0 20px 48px -8px rgba(0,0,0,0.65), 0 0 0 1px rgba(255,255,255,0.03);
      scrollbar-width: thin;
      scrollbar-color: #1e293b transparent;
    }
    #panel::-webkit-scrollbar { width: 3px; }
    #panel::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 2px; }

    /* ─── Sticky header ─── */
    .p-head {
      position: sticky; top: 0; z-index: 2;
      padding: 14px 16px 10px;
      background: rgba(10,15,30,0.98);
      border-bottom: 1px solid rgba(148,163,184,0.08);
    }
    .p-title { font-size: 13px; font-weight: 700; color: #f1f5f9; letter-spacing: 0.01em; }
    .p-sub   { font-size: 11px; color: #475569; margin-top: 2px; line-height: 1.4; }

    /* ─── Accordion ─── */
    details { border-bottom: 1px solid rgba(148,163,184,0.07); }
    details:last-child { border-bottom: none; }
    summary {
      list-style: none;
      display: flex; align-items: center; justify-content: space-between;
      padding: 9px 16px;
      cursor: pointer; user-select: none;
      font-size: 10px; font-weight: 700;
      color: #475569;
      text-transform: uppercase; letter-spacing: 0.1em;
    }
    summary:hover { color: #94a3b8; }
    summary::-webkit-details-marker { display: none; }
    summary::after {
      content: '›';
      font-size: 15px; line-height: 1;
      color: #334155;
      transition: transform 0.18s;
      display: inline-block;
      transform: rotate(90deg);
    }
    details[open] summary::after { transform: rotate(270deg); }
    .s-body { padding: 2px 16px 13px; }

    /* ─── Sub-labels inside sections ─── */
    .sub-lbl {
      font-size: 10px; font-weight: 600;
      color: #2d3f55;
      text-transform: uppercase; letter-spacing: 0.09em;
      margin: 8px 0 6px;
    }
    .sub-lbl:first-child { margin-top: 0; }
    .divider { border: none; border-top: 1px solid rgba(148,163,184,0.07); margin: 10px 0; }

    /* ─── Toggle rows ─── */
    .tog {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 7px; cursor: pointer;
    }
    .tog:last-child { margin-bottom: 0; }
    .tog-lbl {
      display: flex; align-items: center; gap: 7px;
      color: #cbd5e1; user-select: none;
    }

    /* ─── Toggle switch ─── */
    .sw { position: relative; width: 30px; height: 16px; flex-shrink: 0; }
    .sw input { opacity: 0; width: 0; height: 0; }
    .tr {
      position: absolute; inset: 0;
      background: #1e293b; border: 1px solid #2d3f55;
      border-radius: 8px;
      transition: background 0.15s, border-color 0.15s;
    }
    .sw input:checked ~ .tr { background: #4f46e5; border-color: #4f46e5; }
    .th {
      position: absolute; top: 2px; left: 2px;
      width: 10px; height: 10px;
      background: #475569; border-radius: 50%;
      transition: left 0.15s, background 0.15s;
    }
    .sw input:checked ~ .th { left: 16px; background: #fff; }

    /* ─── Swatches ─── */
    .dot  { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .lsw  { width: 16px; height: 3px; border-radius: 2px; flex-shrink: 0; }
    .dsw  { width: 16px; height: 0; border-top: 2px dashed; flex-shrink: 0; }
    .bsw  {
      width: 13px; height: 9px;
      border: 1.5px solid; border-radius: 2px;
      flex-shrink: 0; background: rgba(148,163,184,0.1);
    }

    /* ─── Radio rows ─── */
    .rad {
      display: flex; align-items: center; gap: 7px;
      margin-bottom: 6px; cursor: pointer; color: #cbd5e1;
    }
    .rad:last-child { margin-bottom: 0; }
    .rad input { accent-color: #4f46e5; cursor: pointer; }

    /* ─── Tool buttons ─── */
    .tbtn {
      display: block; width: 100%;
      padding: 6px 10px; margin-bottom: 6px;
      background: rgba(79,70,229,0.10);
      border: 1px solid rgba(79,70,229,0.22);
      border-radius: 7px;
      color: #a5b4fc; font-size: 12px;
      cursor: pointer; text-align: left;
      transition: background 0.15s, border-color 0.15s;
    }
    .tbtn:last-child { margin-bottom: 0; }
    .tbtn:hover { background: rgba(79,70,229,0.20); border-color: rgba(79,70,229,0.40); }
    .tbtn.active { background: rgba(79,70,229,0.28); border-color: rgba(99,102,241,0.55); color: #c7d2fe; }

    /* ─── Stats bar ─── */
    #statsbar {
      position: fixed; bottom: 14px; left: 50%;
      transform: translateX(-50%);
      z-index: 1000;
      background: rgba(10,15,30,0.88);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border: 1px solid rgba(148,163,184,0.09);
      border-radius: 20px; padding: 6px 16px;
      color: #475569; font-size: 12px;
      display: flex; gap: 16px; align-items: center;
      pointer-events: none;
    }
    .sn { color: #e2e8f0; font-weight: 600; }

    /* ─── Leaflet popup ─── */
    .leaflet-popup-content-wrapper {
      background: rgba(10,15,30,0.97) !important;
      border: 1px solid rgba(148,163,184,0.14) !important;
      border-radius: 12px !important; color: #e2e8f0 !important;
      box-shadow: 0 12px 32px rgba(0,0,0,0.55) !important; padding: 0 !important;
    }
    .leaflet-popup-content { margin: 0 !important; }
    .leaflet-popup-tip { background: rgba(10,15,30,0.97) !important; }
    .leaflet-popup-close-button { color: #64748b !important; top: 10px !important; right: 12px !important; }
    .pi  { padding: 13px 15px; min-width: 210px; max-width: 295px; }
    .pid { font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.07em; text-transform: uppercase; margin-bottom: 2px; }
    .pnm { font-size: 14px; font-weight: 600; color: #f1f5f9; margin-bottom: 8px; line-height: 1.3; }
    .pm  { display: grid; grid-template-columns: auto 1fr; gap: 3px 9px; font-size: 12px; }
    .mk  { color: #475569; white-space: nowrap; }
    .mv  { color: #cbd5e1; word-break: break-word; }

    /* ─── Zone labels ─── */
    .zone-label {
      background: transparent !important; border: none !important;
      box-shadow: none !important;
      font-size: 12px; font-weight: 700;
      color: rgba(255,255,255,0.28);
      letter-spacing: 0.08em; text-transform: uppercase; pointer-events: none;
    }
    .leaflet-tooltip.zone-label::before { display: none; }

    .lmp-tip {
      background: rgba(15,23,42,0.92) !important; border: 1px solid rgba(148,163,184,0.2) !important;
      box-shadow: none !important; color: #e2e8f0; font-size: 11px;
      font-family: monospace; padding: 3px 8px !important; border-radius: 4px; white-space: nowrap;
    }
    .lmp-tip::before { display: none !important; }

    .leaflet-attribution-flag { display: none !important; }
    .leaflet-control-attribution { background: rgba(10,15,30,0.7) !important; color: #334155 !important; font-size: 10px !important; }
    .leaflet-control-attribution a { color: #475569 !important; }
  </style>
</head>
<body>
<div id="map"></div>

<div id="panel">
  <div class="p-head">
    <div class="p-title">ERCOT Transmission Grid</div>
    <div class="p-sub" style="color:#334155;font-size:10px;margin-top:1px;">© Emmett Souder</div>
    <div class="p-sub" id="subtitle">Loading…</div>
  </div>

  <!-- ── Layers ── -->
  <details open>
    <summary>Layers</summary>
    <div class="s-body">
      <div class="tog" onclick="document.getElementById('togOSM').click()">
        <span class="tog-lbl"><span class="lsw" style="background:#a855f7"></span>OSM Raw Data</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togOSM" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togSCED').click()">
        <span class="tog-lbl"><span class="dsw" style="border-color:#22c55e"></span>SCED Network</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togSCED" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togGenSnap').click()">
        <span class="tog-lbl"><span class="lsw" style="background:#fbbf24"></span>Gen → Bus Snap</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togGenSnap"><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togSCEDResults').click()">
        <span class="tog-lbl"><span class="lsw" style="background:#ef4444"></span>SCED Results</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togSCEDResults"><span class="tr"></span><span class="th"></span></label>
      </div>
    </div>
  </details>

  <!-- ── Map ── -->
  <details open>
    <summary>Map</summary>
    <div class="s-body">
      <div class="tog" onclick="document.getElementById('togZones').click()">
        <span class="tog-lbl"><span class="bsw" style="border-color:#94a3b8"></span>ERCOT zones</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togZones"><span class="tr"></span><span class="th"></span></label>
      </div>
      <div style="margin-top:9px;display:grid;grid-template-columns:1fr 1fr;gap:4px 8px;font-size:12px;color:#64748b">
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#f87171"></span>Houston</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#60a5fa"></span>North</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#34d399"></span>South</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#fb923c"></span>West</span>
      </div>
    </div>
  </details>

  <!-- ── Color by ── -->
  <details>
    <summary>Color by</summary>
    <div class="s-body">
      <div class="rad"><label><input type="radio" name="colorMode" value="kv" checked onchange="recolorNodes()"> Voltage tier</label></div>
      <div class="rad"><label><input type="radio" name="colorMode" value="gen" onchange="recolorNodes()"> Generator type</label></div>
      <div id="gen-legend" style="display:none;margin-top:8px">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px 8px;font-size:11px;color:#64748b">
          <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#22d3ee"></span>Wind</span>
          <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#fbbf24"></span>Solar</span>
          <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#f97316"></span>Gas</span>
          <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#78716c"></span>Coal</span>
          <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#c084fc"></span>Nuclear</span>
          <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#334155"></span>No gen</span>
        </div>
      </div>
    </div>
  </details>

  <!-- ── Tools ── -->
  <details>
    <summary>Tools</summary>
    <div class="s-body">
      <button class="tbtn" onclick="zoomToERCOT()">Zoom to ERCOT</button>
    </div>
  </details>
</div>

<div id="statsbar">
  <span>OSM: <span class="sn" id="st-subs">–</span> subs · <span class="sn" id="st-lines">–</span> lines</span>
  <span>SCED: <span class="sn" id="st-sced-nodes">–</span> nodes · <span class="sn" id="st-edges">–</span> edges</span>
</div>

<script>
// ============================================================
// Data
// ============================================================
const NODES      = __NODES__;
const PLANTS     = __PLANTS__;
const LINES_HIGH   = __LINES_HIGH__;
const LINES_MID_HI = __LINES_MID_HI__;
const LINES_MID_LO = __LINES_MID_LO__;
const LINES_LOW    = __LINES_LOW__;
const EDGES_HIGH   = __EDGES_HIGH__;
const EDGES_MID_HI = __EDGES_MID_HI__;
const EDGES_MID_LO = __EDGES_MID_LO__;
const ZONES      = __ZONES__;
const SCED       = __SCED_RESULTS__;

// ============================================================
// Color constants
// ============================================================
const KV_COLOR = kv => {
  if (kv >= 345) return '#a855f7';
  if (kv >= 200) return '#3b82f6';
  if (kv >= 138) return '#06b6d4';
  if (kv >= 69)  return '#64748b';
  return '#475569';
};

const FUEL_COLOR = {
  wind:    '#22d3ee',
  solar:   '#fbbf24',
  gas:     '#f97316',
  coal:    '#78716c',
  nuclear: '#c084fc',
  hydro:   '#60a5fa',
  battery: '#4ade80',
  biomass: '#86efac',
  oil:     '#92400e',
  waste:   '#a3a3a3',
};
const FUEL_DEFAULT = '#94a3b8';

function plantFuelColor(fuel) {
  return FUEL_COLOR[fuel] || FUEL_DEFAULT;
}
function plantRadius(mw) {
  if (!mw) return 5;
  if (mw >= 1000) return 11;
  if (mw >= 500)  return 9;
  if (mw >= 100)  return 7;
  return 5;
}

const ERCOT_BOUNDS = [[25.84, -104.98], [36.06, -94.13]];

// ============================================================
// Map & renderer
// ============================================================
const map = L.map('map', { center: [31.2,-99.3], zoom: 7, zoomControl: false, preferCanvas: true });
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  { attribution: '© OpenStreetMap contributors © CARTO', subdomains: 'abcd', maxZoom: 19 }
).addTo(map);
L.control.zoom({ position: 'topleft' }).addTo(map);
const renderer = L.canvas({ padding: 0.5 });

// ============================================================
// Layer groups — two master groups: OSM raw + SCED network
// ============================================================
const layerZones     = L.layerGroup();              // off by default

// OSM raw data (lines with real geometry, substations, power plants)
const layerOSM       = L.layerGroup().addTo(map);   // on by default

// SCED network (straight-edge simplified graph + SCED nodes)
const layerSCED      = L.layerGroup().addTo(map);   // on by default

// ============================================================
// Zone boundaries
// ============================================================
L.geoJSON(ZONES, {
  style: f => {
    const c = f.properties.color || '#94a3b8';
    return { color: c, weight: 1.5, opacity: 0.65, fillColor: c, fillOpacity: 0.05, dashArray: '6 4' };
  },
  onEachFeature: (f, l) => {
    const n = f.properties.NAME || '';
    if (n) l.bindTooltip(n, { permanent: true, direction: 'center', className: 'zone-label', interactive: false });
  },
}).addTo(layerZones);

// ============================================================
// Node helpers
// ============================================================
const allMarkers = [];

function nodeRadius(kv) {
  if (kv >= 345) return 5.5;
  if (kv >= 200) return 3.5;
  return 2.5;
}

let colorMode = 'kv';

function genColor(n) {
  if (!n.tech) return '#334155';
  const t = n.tech.toLowerCase();
  if (t.includes('wind'))    return '#22d3ee';
  if (t.includes('solar'))   return '#fbbf24';
  if (t.includes('gas'))     return '#f97316';
  if (t.includes('coal'))    return '#78716c';
  if (t.includes('nuclear')) return '#c084fc';
  if (t.includes('hydro'))   return '#60a5fa';
  return '#94a3b8';
}

function nodeColor(n) {
  if (colorMode === 'gen') return genColor(n);
  return KV_COLOR(n.kv);
}

function nodeStyle(n) {
  if (n.split) {
    return { renderer, radius: 2, fillColor: KV_COLOR(n.kv), color: 'rgba(0,0,0,0)', weight: 0, fillOpacity: 0.45, opacity: 0 };
  }
  const col = nodeColor(n);
  return { renderer, radius: nodeRadius(n.kv), fillColor: col,
           color: 'rgba(0,0,0,0.3)', weight: 0.7, fillOpacity: 0.82, opacity: 0.9 };
}

// Pre-compute which nodes have at least one graph edge (SCED network nodes)
const connectedSet = new Set();
for (const e of [...EDGES_HIGH, ...EDGES_MID_HI, ...EDGES_MID_LO]) {
  connectedSet.add(e.a);
  connectedSet.add(e.b);
}

// ============================================================
// Popup builder
// ============================================================
function makePopup(n) {
  let rows = '';
  const add = (k, v) => { if (v) rows += `<span class="mk">${k}</span><span class="mv">${v}</span>`; };
  if (n.ercot)  add('ERCOT node',   n.ercot);
  add('Voltage', n.kv ? `${n.kv} kV` : '');
  if (n.lz)     add('Load zone',    `LZ_${n.lz}`);
  if (n.mw)     add('Gen capacity', `${n.mw} MW${n.tech ? ' · ' + n.tech : ''}`);
  if (n.op)     add('Operator',     n.op);
  if (n.stype)  add('Type',         n.stype);
  add('In SCED', connectedSet.has(n.i) ? 'Yes' : 'No');
  const disp  = n.name || n.ercot || `OSM ${n.id}`;
  return `<div class="pi">
    <div class="pid">OSM ${n.id}</div>
    <div class="pnm">${disp}</div>
    <div class="pm">${rows}</div>
  </div>`;
}

// ============================================================
// Render OSM substations (into OSM layer)
// ============================================================
for (const n of NODES) {
  if (n.split) continue;  // split points only in SCED layer
  const m = L.circleMarker([n.lat, n.lon], nodeStyle(n));
  m.bindPopup(makePopup(n), { maxWidth: 310 });
  if (n.name || n.ercot) {
    const tip = n.name || n.ercot;
    m.bindTooltip(tip, { sticky: true, className: 'lmp-tip' });
  }
  allMarkers.push({m, n});
  m.addTo(layerOSM);
}

// ============================================================
// Render power plants (into OSM layer)
// ============================================================
for (const p of PLANTS) {
  const col = plantFuelColor(p.fuel);
  const m = L.circleMarker([p.lat, p.lon], {
    renderer,
    radius:      plantRadius(p.mw),
    fillColor:   col,
    color:       '#fff',
    weight:      1.5,
    fillOpacity: 0.88,
    opacity:     1,
  }).addTo(layerOSM);
  const capStr = p.mw ? `${p.mw} MW` : 'capacity unknown';
  const fuelStr = p.fuel ? p.fuel.charAt(0).toUpperCase() + p.fuel.slice(1) : 'Unknown';
  const rows = [
    p.name ? `<b>${p.name}</b>` : '<i>Unnamed plant</i>',
    `<span class="mk">Fuel</span><span class="mv">${fuelStr}</span>`,
    `<span class="mk">Capacity</span><span class="mv">${capStr}</span>`,
    p.op ? `<span class="mk">Operator</span><span class="mv">${p.op}</span>` : '',
  ].filter(Boolean).join('');
  m.bindPopup(`<div class="popup-grid">${rows}</div>`, { maxWidth: 280 });
  const tip = [p.name || 'Power Plant', fuelStr, capStr].join('  ·  ');
  m.bindTooltip(tip, { sticky: true, className: 'lmp-tip' });
}

// ============================================================
// Render OSM line geometry (into OSM layer)
// ============================================================
for (const ln of LINES_HIGH)
  L.polyline(ln.pts, { renderer, color: KV_COLOR(ln.kv), weight: 1.8, opacity: 0.65 }).addTo(layerOSM);
for (const ln of LINES_MID_HI)
  L.polyline(ln.pts, { renderer, color: KV_COLOR(ln.kv), weight: 1.2, opacity: 0.55 }).addTo(layerOSM);
for (const ln of LINES_MID_LO)
  L.polyline(ln.pts, { renderer, color: KV_COLOR(ln.kv), weight: 0.8, opacity: 0.40 }).addTo(layerOSM);
for (const ln of LINES_LOW)
  L.polyline(ln.pts, { renderer, color: KV_COLOR(ln.kv), weight: 0.5, opacity: 0.25 }).addTo(layerOSM);

// ============================================================
// Render SCED network: straight edges + SCED nodes (into SCED layer)
// ============================================================
// SCED nodes: render connected substations + split points
const scedMarkers = [];
for (const n of NODES) {
  if (!connectedSet.has(n.i)) continue;
  const col = '#22c55e';  // green for SCED nodes (default)
  const style = n.split
    ? { renderer, radius: 2, fillColor: '#475569', color: 'rgba(0,0,0,0)', weight: 0, fillOpacity: 0.45, opacity: 0 }
    : { renderer, radius: nodeRadius(n.kv), fillColor: col, color: 'rgba(0,0,0,0.3)', weight: 0.7, fillOpacity: 0.82, opacity: 0.9 };
  const m = L.circleMarker([n.lat, n.lon], style);
  if (!n.split) {
    m.bindPopup(makePopup(n), { maxWidth: 310 });
    scedMarkers.push({m, n});
  }
  m.addTo(layerSCED);
}

// SCED edges: straight dashed lines
function buildEdgeLayer(edgeList) {
  for (const e of edgeList) {
    const na = NODES[e.a], nb = NODES[e.b];
    if (!na || !nb) continue;
    L.polyline([[na.lat, na.lon],[nb.lat, nb.lon]], {
      renderer, color: KV_COLOR(e.kv),
      weight: e.kv >= 345 ? 1.5 : 0.9, opacity: 0.65, dashArray: '5 4',
    }).addTo(layerSCED);
  }
}
buildEdgeLayer(EDGES_HIGH);
buildEdgeLayer(EDGES_MID_HI);
buildEdgeLayer(EDGES_MID_LO);

// ============================================================
// Plant-to-substation snap lines (into Gen Snap layer)
// ============================================================
const layerGenSnap = L.layerGroup();   // off by default

// Build spatial index of SCED-connected substations for fast lookup
const scedSubs = NODES.filter(n => !n.split && connectedSet.has(n.i));

function haversineDeg(lat1, lon1, lat2, lon2) {
  const R = 6371, toR = Math.PI / 180;
  const dLat = (lat2 - lat1) * toR, dLon = (lon2 - lon1) * toR;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*toR) * Math.cos(lat2*toR) * Math.sin(dLon/2)**2;
  return R * 2 * Math.asin(Math.sqrt(a));
}

let snappedCount = 0;
const MAX_SNAP_KM = 20;
for (const p of PLANTS) {
  let bestD = Infinity, bestN = null;
  for (const n of scedSubs) {
    // Quick lat/lon filter before haversine (~0.2 deg ≈ 22 km)
    if (Math.abs(n.lat - p.lat) > 0.2 || Math.abs(n.lon - p.lon) > 0.2) continue;
    const d = haversineDeg(p.lat, p.lon, n.lat, n.lon);
    if (d < bestD) { bestD = d; bestN = n; }
  }
  if (bestN && bestD <= MAX_SNAP_KM) {
    snappedCount++;
    const col = bestD < 2 ? '#4ade80' : bestD < 5 ? '#fbbf24' : '#ef4444';
    L.polyline([[p.lat, p.lon], [bestN.lat, bestN.lon]], {
      renderer, color: col, weight: 1.5, opacity: 0.75,
    }).addTo(layerGenSnap);
    // Draw plant marker in this layer too
    const fuelCol = plantFuelColor(p.fuel);
    L.circleMarker([p.lat, p.lon], {
      renderer, radius: plantRadius(p.mw), fillColor: fuelCol,
      color: '#fff', weight: 1.5, fillOpacity: 0.88, opacity: 1,
    }).addTo(layerGenSnap);
  }
}
console.log(`Gen snap: ${snappedCount}/${PLANTS.length} plants snapped to SCED subs (max ${MAX_SNAP_KM} km)`);

// ============================================================
// SCED Results overlay
// ============================================================
const layerSCEDResults = L.layerGroup();  // off by default

if (SCED && SCED.lines) {
  // Index nodes by ID for coordinate lookup
  const nodeIdx = {};
  for (const n of NODES) nodeIdx[n.i] = n;

  // Draw lines colored by utilization: green→yellow→red
  function utilColor(u) {
    if (u >= 0.95) return '#ef4444';  // red — binding
    if (u >= 0.80) return '#f59e0b';  // yellow — stressed
    return '#22c55e';                  // green — loaded but ok
  }
  for (const ln of SCED.lines) {
    const na = nodeIdx[ln.a], nb = nodeIdx[ln.b];
    if (!na || !nb) continue;
    const col = utilColor(ln.u);
    const w = ln.u >= 0.95 ? 3.5 : ln.u >= 0.80 ? 2.5 : 1.5;
    const line = L.polyline([[na.lat, na.lon], [nb.lat, nb.lon]], {
      renderer, color: col, weight: w, opacity: 0.85,
    }).addTo(layerSCEDResults);
    line.bindTooltip(`${ln.a}→${ln.b}  util=${(ln.u*100).toFixed(0)}%  rating=${ln.r} MVA`,
      { sticky: true, className: 'lmp-tip' });
  }

  // Draw nodes with shedding as pulsing red circles
  for (const sn of SCED.nodes) {
    const n = nodeIdx[sn.i];
    if (!n) continue;
    const isShed = Math.abs(sn.s) > 0.1;
    const col = isShed ? '#ef4444' : (sn.l > 500 ? '#f59e0b' : (sn.l < -100 ? '#3b82f6' : '#94a3b8'));
    const r = isShed ? Math.min(12, 4 + Math.abs(sn.s) / 10) : 3;
    const m = L.circleMarker([n.lat, n.lon], {
      renderer, radius: r, fillColor: col,
      color: isShed ? '#fff' : 'rgba(0,0,0,0.3)',
      weight: isShed ? 2 : 0.5,
      fillOpacity: 0.9, opacity: 1,
    }).addTo(layerSCEDResults);
    const name = n.name || n.ercot || `Bus ${sn.i}`;
    const parts = [name];
    if (isShed) parts.push(`SHED ${Math.abs(sn.s).toFixed(1)} MW`);
    parts.push(`LMP $${sn.l.toFixed(0)}/MWh`);
    m.bindTooltip(parts.join('  ·  '), { sticky: true, className: 'lmp-tip' });
  }

  console.log(`SCED overlay: ${SCED.lines.length} lines, ${SCED.nodes.length} nodes`);
}

// ============================================================
// Helpers
// ============================================================
function setLayer(layer, on) {
  if (on) map.addLayer(layer); else map.removeLayer(layer);
}

// ============================================================
// Recolor nodes by color mode
// ============================================================
function recolorNodes() {
  colorMode = document.querySelector('input[name="colorMode"]:checked').value;
  document.getElementById('gen-legend').style.display = colorMode === 'gen' ? '' : 'none';
  // Recolor OSM layer markers
  for (const {m, n} of allMarkers) {
    const col = nodeColor(n);
    m.setStyle({ fillColor: col });
  }
  // Recolor SCED layer markers
  for (const {m, n} of scedMarkers) {
    const col = colorMode === 'gen' ? genColor(n) : '#22c55e';
    m.setStyle({ fillColor: col });
  }
}

// ============================================================
// Toggle wiring — two master layers
// ============================================================
document.getElementById('togOSM').addEventListener('change', e => setLayer(layerOSM, e.target.checked));
document.getElementById('togSCED').addEventListener('change', e => setLayer(layerSCED, e.target.checked));
document.getElementById('togGenSnap').addEventListener('change', e => setLayer(layerGenSnap, e.target.checked));
document.getElementById('togSCEDResults').addEventListener('change', e => setLayer(layerSCEDResults, e.target.checked));

// ============================================================
// Map elements
// ============================================================
document.getElementById('togZones').addEventListener('change', e => setLayer(layerZones, e.target.checked));

// ============================================================
// Tools
// ============================================================
function zoomToERCOT() {
  map.fitBounds(ERCOT_BOUNDS, { padding: [20, 20] });
}

// ============================================================
// Stats bar
// ============================================================
const substations = NODES.filter(n => !n.split);
const totalLines  = LINES_HIGH.length + LINES_MID_HI.length + LINES_MID_LO.length + LINES_LOW.length;
const totalEdges  = EDGES_HIGH.length + EDGES_MID_HI.length + EDGES_MID_LO.length;
const scedNodes   = connectedSet.size;

document.getElementById('st-subs').textContent = substations.length.toLocaleString();
document.getElementById('st-lines').textContent = totalLines.toLocaleString();
document.getElementById('st-sced-nodes').textContent = scedNodes.toLocaleString();
document.getElementById('st-edges').textContent = totalEdges.toLocaleString();
document.getElementById('subtitle').textContent =
  `OSM: ${substations.length.toLocaleString()} subs · SCED: ${scedNodes.toLocaleString()} nodes, ${totalEdges.toLocaleString()} edges`;

</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# SCED results overlay builder
# ---------------------------------------------------------------------------

def _build_sced_overlay(results_dir, nodes, split_nodes):
    """
    Read SCED bus_detail.csv and line_detail.csv, compute steady-state
    (hours 9-23) utilization and shedding, return compact JSON string.
    """
    import csv as _csv
    from collections import defaultdict as _dd

    # Read branch ratings + bus IDs
    branch_file = os.path.join(os.path.dirname(results_dir), 'SourceData', 'branch.csv')
    if not os.path.exists(branch_file):
        # Try pulling from adroit cache
        branch_file = '/tmp/v3r2_branch.csv'
    branches = {}
    with open(branch_file, newline='', encoding='utf-8') as f:
        for row in _csv.DictReader(f):
            branches[row['UID']] = {
                'a': int(row['From Bus']), 'b': int(row['To Bus']),
                'r': float(row['Cont Rating']),
            }

    # Bus name → ID
    bus_file = os.path.join(os.path.dirname(results_dir), 'osm_bus.csv')
    if not os.path.exists(bus_file):
        bus_file = '/tmp/v3r2_osm_bus.csv'
    name_to_id = {}
    with open(bus_file, newline='', encoding='utf-8') as f:
        for row in _csv.DictReader(f):
            name_to_id[row['Bus Name']] = int(row['Bus ID'])

    # Line flows (hours 9-23)
    line_flows = _dd(list)
    with open(os.path.join(results_dir, 'line_detail.csv'), newline='', encoding='utf-8') as f:
        for row in _csv.DictReader(f):
            if int(row['Hour']) >= 9:
                line_flows[row['Line']].append(abs(float(row['Flow'])))

    sced_lines = []
    for uid, flows in line_flows.items():
        if uid not in branches:
            continue
        br = branches[uid]
        mx = max(flows)
        util = mx / br['r'] if br['r'] > 0 else 0
        if util > 0.5:
            sced_lines.append({
                'a': br['a'], 'b': br['b'],
                'u': round(util, 3), 'r': round(br['r']),
            })

    # Bus shedding + LMP (hours 9-23)
    shed_acc = _dd(list)
    lmp_acc = _dd(list)
    with open(os.path.join(results_dir, 'bus_detail.csv'), newline='', encoding='utf-8') as f:
        for row in _csv.DictReader(f):
            if int(row['Hour']) >= 9:
                shed_acc[row['Bus']].append(float(row['Mismatch']))
                lmp_acc[row['Bus']].append(float(row['LMP']))

    sced_nodes = []
    for bus_name in shed_acc:
        bus_id = name_to_id.get(bus_name)
        if bus_id is None:
            continue
        avg_shed = sum(shed_acc[bus_name]) / len(shed_acc[bus_name])
        avg_lmp = sum(lmp_acc[bus_name]) / len(lmp_acc[bus_name])
        if abs(avg_shed) > 0.1 or avg_lmp > 500 or avg_lmp < -100:
            sced_nodes.append({
                'i': bus_id,
                's': round(avg_shed, 1),
                'l': round(avg_lmp, 1),
            })

    print(f"  SCED lines (>50% util): {len(sced_lines)}")
    print(f"  SCED nodes (shed/extreme LMP): {len(sced_nodes)}")
    return json.dumps({'lines': sced_lines, 'nodes': sced_nodes}, separators=(',', ':'))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading ERCOT zone boundaries…")
    zone_features, ercot_union = load_zones()

    print("Loading EIA-860 capacity…")
    eia_cap = load_eia_capacity()

    print("Building ERCOT→OSM lookup…")
    ercot_lookup = build_ercot_lookup(eia_cap)

    print("Loading line features…")
    all_features, hv_features = load_line_features(ercot_union)

    print("Loading OSM substations…")
    nodes = load_nodes(ercot_lookup, ercot_union)
    print(f"  {len(nodes)} nodes loaded")

    print("Loading OSM power plants…")
    plants = load_plants(ercot_union)

    print("Processing lines and building graph edges (V3 geometry splitting)…")
    lines_high, lines_mid_hi, lines_mid_lo, lines_low, edges, split_nodes = \
        process_lines(all_features, hv_features, nodes)

    # Split edges by voltage tier for per-tier simplified graph toggles
    edges_high   = [e for e in edges if e['kv'] >= 345]
    edges_mid_hi = [e for e in edges if 200 <= e['kv'] < 345]
    edges_mid_lo = [e for e in edges if 138 <= e['kv'] < 200]

    print("Serialising data…")
    all_node_dicts = (
        [{'i': n['i'], 'lat': n['lat'], 'lon': n['lon'],
          'id': n['id'], 'name': n['name'], 'kv': n['kv'],
          'ercot': n['ercot'], 'conf': n['conf'], 'src': n['src'],
          'sc': n['sc'], 'lz': n['lz'], 'mw': n['mw'], 'tech': n['tech'],
          'op': n['op'], 'stype': n['stype']}
         for n in nodes]
        +
        [{'i': sn['i'], 'lat': sn['lat'], 'lon': sn['lon'],
          'kv': sn['kv'], 'split': True}
         for sn in split_nodes]
    )
    nodes_js         = json.dumps(all_node_dicts,  separators=(',', ':'))
    lines_high_js    = json.dumps(lines_high,       separators=(',', ':'))
    lines_mid_hi_js  = json.dumps(lines_mid_hi,     separators=(',', ':'))
    lines_mid_lo_js  = json.dumps(lines_mid_lo,     separators=(',', ':'))
    lines_low_js     = json.dumps(lines_low,        separators=(',', ':'))
    edges_high_js    = json.dumps(edges_high,        separators=(',', ':'))
    edges_mid_hi_js  = json.dumps(edges_mid_hi,      separators=(',', ':'))
    edges_mid_lo_js  = json.dumps(edges_mid_lo,      separators=(',', ':'))
    plants_js        = json.dumps(plants,            separators=(',', ':'))

    # Annotate zones with display colour and embed
    for feat in zone_features:
        name = feat['properties'].get('NAME', '')
        feat['properties']['color'] = ZONE_COLORS.get(name, '#94a3b8')
    zones_js = json.dumps({'type': 'FeatureCollection', 'features': zone_features},
                          separators=(',', ':'))

    # Load SCED results if available
    sced_results_file = os.path.join(REALIST, "ERCOT_Calibration_Experiments",
                                     "results", "v3-targeted", "results_v3-targeted")
    sced_js = 'null'
    if os.path.isdir(sced_results_file):
        print("Loading SCED results for overlay…")
        sced_js = _build_sced_overlay(sced_results_file, nodes, split_nodes)
        print(f"  SCED overlay: {len(sced_js)//1024} KB")

    print(f"  Nodes: {len(nodes_js)//1024} KB  Plants: {len(plants_js)//1024} KB  "
          f"Lines H/MH/ML/Lo: {len(lines_high_js)//1024}/{len(lines_mid_hi_js)//1024}/"
          f"{len(lines_mid_lo_js)//1024}/{len(lines_low_js)//1024} KB  "
          f"Edges H/MH/ML: {len(edges_high_js)//1024}/{len(edges_mid_hi_js)//1024}/{len(edges_mid_lo_js)//1024} KB")

    html = HTML_TEMPLATE
    html = html.replace('__NODES__',        nodes_js)
    html = html.replace('__PLANTS__',       plants_js)
    html = html.replace('__LINES_HIGH__',   lines_high_js)
    html = html.replace('__LINES_MID_HI__', lines_mid_hi_js)
    html = html.replace('__LINES_MID_LO__', lines_mid_lo_js)
    html = html.replace('__LINES_LOW__',    lines_low_js)
    html = html.replace('__EDGES_HIGH__',   edges_high_js)
    html = html.replace('__EDGES_MID_HI__', edges_mid_hi_js)
    html = html.replace('__EDGES_MID_LO__', edges_mid_lo_js)
    html = html.replace('__ZONES__',        zones_js)
    html = html.replace('__SCED_RESULTS__', sced_js)

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html)

    total_kb = len(html) // 1024
    print(f"\nOutput: {OUT}")
    print(f"Total size: {total_kb} KB ({total_kb/1024:.1f} MB)")
    print(f"Substations: {len(nodes)}, Plants: {len(plants)}, Split nodes: {len(split_nodes)}, Edges: {len(edges)}")
    print(f"OSM lines: {len(all_features)} total, {len(hv_features)} HV (>= 138 kV)")
    print("Done.")


if __name__ == "__main__":
    main()
