"""
Generate a self-contained HTML visualizer for the ERCOT grid.

Node set: OSM physical substations >= 138 kV that are within 500 m of a
transmission line endpoint AND inside ERCOT territory.
Colored by ERCOT settlement-point match quality.

Reads:
  Realist/grid_data/texas_substations.geojson                 — OSM substation geometries
  Realist/grid_data/texas_hv_lines.geojson                    — OSM HV line geometries
  Realist/grid_data/texas_plants.geojson                      — OSM power plant geometries
  Realist/grid_data/ercot_zones.geojson                       — ERCOT zone polygons (4 zones)
  Realist/grid_data/matching_results/texas_matched_substations_v6.csv — ERCOT→OSM match results
  Birchfield/data/eia8602023/3_1_Generator_Y2023.xlsx         — EIA-860 generator capacity

Writes:
  Realist/grid_visualizer_v2.html

V2 fixes applied (from audit3_24_26.md):
  Fix 1: MV snap radius 150 m → 400 m (recover orphaned 138 kV substations)
  Fix 2: Nearest-match clustering (eliminate order-dependent topology)
  Fix 4: Post-merge split point cleanup (contract degree-2, remove degree-0/1)
  Fix 5: Cross-voltage validation (reclassify mismatched edge kV)
  Fix 6: Smarter 300 m filter (keep short edges between two substations)
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
OUT        = os.path.join(REALIST, "grid_visualizer_v2.html")

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


# ---------------------------------------------------------------------------
# Load HV line features (>= 115 kV, inside Texas)
# ---------------------------------------------------------------------------

def load_line_features(ercot_union):
    """
    Keep lines >= 115 kV where at least one endpoint is inside ERCOT territory.
    Uses a cheap bbox pre-check before the shapely PIP test.
    """
    print("  Loading HV line features…")
    with open(LINES, encoding='utf-8') as f:
        data = json.load(f)

    bounds = ercot_union.bounds   # (minx, miny, maxx, maxy)

    def in_ercot_bbox(lon, lat):
        return bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]

    valid = []
    skipped = 0
    for feat in data['features']:
        kv = feat['properties'].get('voltage_kv') or 0
        if kv < 138:
            continue
        coords = feat['geometry']['coordinates']
        if len(coords) < 2:
            continue
        lon0, lat0 = coords[0]
        lon1, lat1 = coords[-1]
        # Quick bbox gate, then exact PIP on whichever endpoint passes bbox
        in0 = in_ercot_bbox(lon0, lat0) and ercot_union.contains(Point(lon0, lat0))
        in1 = in_ercot_bbox(lon1, lat1) and ercot_union.contains(Point(lon1, lat1))
        if not (in0 or in1):
            skipped += 1
            continue
        valid.append(feat)

    print(f"  Valid HV line features: {len(valid)}  (dropped {skipped} outside ERCOT)")
    return valid


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
# Load OSM substations (node set)
# ---------------------------------------------------------------------------

def load_nodes(ep_grid, ercot_lookup, ercot_union):
    """
    Load OSM physical substations >= 115 kV that are:
      - within 500 m of a transmission line endpoint
      - inside ERCOT territory
    Attach ERCOT match data where available.
    """
    with open(OSM_SUBS, encoding='utf-8') as f:
        data = json.load(f)

    CONNECT_KM = 0.5   # must be this close to a line endpoint
    bounds = ercot_union.bounds

    nodes = []
    skipped_kv    = 0
    skipped_conn  = 0
    skipped_ercot = 0
    for feat in data['features']:
        props = feat['properties']
        kv = props.get('voltage_kv') or 0
        if kv < 138:
            skipped_kv += 1
            continue

        lon, lat = feat['geometry']['coordinates']

        # Cheap bbox gate before shapely PIP
        if not (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]):
            skipped_ercot += 1
            continue
        if not ercot_union.contains(Point(lon, lat)):
            skipped_ercot += 1
            continue

        d = nearest_in_grid(lat, lon, ep_grid, CONNECT_KM)
        if d > CONNECT_KM:
            skipped_conn += 1
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

    print(f"  OSM subs (raw): {len(nodes)} kept, {skipped_kv} dropped (<138 kV), {skipped_ercot} dropped (outside ERCOT), {skipped_conn} dropped (no line within {CONNECT_KM} km)")

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

NODE_GRID = 0.15   # degrees per cell (~17 km)


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
# Junction clustering (merge nearby line endpoints into junctions)
# ---------------------------------------------------------------------------

CLUSTER_GRID = 0.05
CLUSTER_R    = 0.15   # km


def cluster_endpoints(features, cluster_r=CLUSTER_R):
    clusters = []
    for feat in features:
        coords = feat['geometry']['coordinates']
        kv = feat['properties'].get('voltage_kv') or 0
        for lon, lat in (coords[0], coords[-1]):
            if not in_texas_bounds(lon, lat):
                continue
            # Fix 2: find NEAREST cluster within radius, not first
            best_c = None
            best_d = cluster_r + 0.001
            for c in clusters:
                if abs(c[0] - lat) > 0.01 or abs(c[1] - lon) > 0.01:
                    continue
                d = haversine(lat, lon, c[0], c[1])
                if d <= cluster_r and d < best_d:
                    best_d = d
                    best_c = c
            if best_c is not None:
                n = best_c[2]
                best_c[0] = (best_c[0] * n + lat) / (n + 1)
                best_c[1] = (best_c[1] * n + lon) / (n + 1)
                best_c[2] += 1
                best_c[3] = max(best_c[3], kv)
            else:
                clusters.append([lat, lon, 1, kv])
    return clusters


def build_cluster_grid(clusters):
    g = defaultdict(list)
    for i, c in enumerate(clusters):
        k = (round(c[0] / CLUSTER_GRID), round(c[1] / CLUSTER_GRID))
        g[k].append((i, c))
    return g


def find_cluster(lat, lon, cgrid, max_km=0.3):
    k0 = (round(lat / CLUSTER_GRID), round(lon / CLUSTER_GRID))
    best_d, best_i = float('inf'), None
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            for i, c in cgrid.get((k0[0]+dr, k0[1]+dc), []):
                d = haversine(lat, lon, c[0], c[1])
                if d < best_d:
                    best_d, best_i = d, i
    return best_i if best_d <= max_km else None


# ---------------------------------------------------------------------------
# Graph pass helper: junction clustering + BFS contraction for one voltage tier
# ---------------------------------------------------------------------------

def _graph_pass(features, nodes, node_grid, snap_km, cluster_r, base_split_idx):
    """
    Run junction clustering + BFS graph contraction for one voltage tier.

    Non-substation junctions with degree >= 3 are treated as "split nodes" —
    real physical branch points (T-junctions, tap points).  They become stop
    nodes in the BFS alongside substation junctions so that a T-shaped
    corridor A→X→{B,C} produces edges A–X, X–B, X–C rather than the
    spurious A–B, A–C that BFS-contraction alone would give.

    Returns (edges_list, split_nodes_list).
    split_node indices start at base_split_idx.
    """
    if not features:
        return [], []

    clusters = cluster_endpoints(features, cluster_r)
    if not clusters:
        return [], []
    cgrid = build_cluster_grid(clusters)

    # Build junction adjacency from individual line endpoints
    junc_edges = set()
    for feat in features:
        coords = feat['geometry']['coordinates']
        kv = int(feat['properties'].get('voltage_kv') or 0)
        lon0, lat0 = coords[0]
        lon1, lat1 = coords[-1]
        j0 = find_cluster(lat0, lon0, cgrid)
        j1 = find_cluster(lat1, lon1, cgrid)
        if j0 is not None and j1 is not None and j0 != j1:
            junc_edges.add((min(j0, j1), max(j0, j1), kv))

    jadj = defaultdict(set)
    jkv  = {}
    for j0, j1, kv in junc_edges:
        jadj[j0].add(j1)
        jadj[j1].add(j0)
        key = (min(j0, j1), max(j0, j1))
        jkv[key] = max(jkv.get(key, 0), kv)

    # Snap junctions → nearest OSM substation (strict snap_km radius)
    junc_to_node = {}
    for i, c in enumerate(clusters):
        n, _ = nearest_node(c[0], c[1], node_grid, snap_km)
        if n:
            junc_to_node[i] = n['i']

    sub_juncs = set(junc_to_node.keys())

    # Step 3: Detect split junctions — degree >= 3, not snapped to any substation
    split_juncs = {j for j, nbrs in jadj.items()
                   if len(nbrs) >= 3 and j not in sub_juncs}

    # Assign output indices and build split node objects
    junc_to_split = {}
    split_nodes = []
    for j in sorted(split_juncs):   # sorted for determinism
        c = clusters[j]
        split_i = base_split_idx + len(split_nodes)
        junc_to_split[j] = split_i
        max_kv = max((jkv.get((min(j, nb), max(j, nb)), 0) for nb in jadj[j]), default=0)
        split_nodes.append({
            'i':     split_i,
            'lat':   round(c[0], 5),
            'lon':   round(c[1], 5),
            'kv':    max_kv,
            'split': True,
        })

    # Combined stop set (substations + split points) and index map
    stop_set = sub_juncs | split_juncs
    junc_to_idx = {}
    junc_to_idx.update(junc_to_node)
    junc_to_idx.update(junc_to_split)

    # BFS from every stop junction; stop at other stop-set junctions
    edges_set = set()
    for start_j in stop_set:
        start_idx = junc_to_idx[start_j]
        visited = {start_j}
        queue = deque([(start_j, 0)])   # (junction_id, max_kv_along_path)
        while queue:
            curr_j, path_kv = queue.popleft()
            for next_j in jadj[curr_j]:
                if next_j in visited:
                    continue
                visited.add(next_j)
                seg_kv = jkv.get((min(curr_j, next_j), max(curr_j, next_j)), 0)
                new_kv = max(path_kv, seg_kv)
                if next_j in stop_set:
                    end_idx = junc_to_idx[next_j]
                    if start_idx != end_idx:
                        a, b = min(start_idx, end_idx), max(start_idx, end_idx)
                        edges_set.add((a, b, new_kv))
                else:
                    queue.append((next_j, new_kv))

    edges = [{'a': a, 'b': b, 'kv': kv} for a, b, kv in edges_set]
    return edges, split_nodes


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
# Process line geometries and build simplified graph edges
# ---------------------------------------------------------------------------

def process_lines(features, nodes):
    """
    Returns (lines_high, lines_mid_hi, lines_mid_lo, edges, split_nodes).

    Voltage tiers:  high >= 345 kV  |  mid-high 200–344 kV  |  mid-low 138–199 kV
    Step 2: Separate HV (>=345 kV, SNAP_KM=0.45) and MV (138–344 kV,
    SNAP_KM=0.15) passes to avoid cross-contamination.
    Step 3: Split nodes (T-junctions) detected per pass.
    Step 4: Self-loop and <300 m edges dropped.
    """
    # --- Visual line geometry split into 3 tiers ---
    lines_high   = []   # >= 345 kV      (full simplified geometry)
    lines_mid_hi = []   # 200–344 kV     (endpoints only)
    lines_mid_lo = []   # 138–199 kV     (endpoints only)
    for feat in features:
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
        else:
            pts = [[round(lat0, 4), round(lon0, 4)],
                   [round(lat1, 4), round(lon1, 4)]]
            lines_mid_lo.append({'kv': kv, 'pts': pts})

    # --- Separate feature sets by voltage tier ---
    hv_feats = [f for f in features if (f['properties'].get('voltage_kv') or 0) >= 345]
    mv_feats  = [f for f in features
                 if 138 <= (f['properties'].get('voltage_kv') or 0) < 345]
    print(f"  HV features (≥345 kV): {len(hv_feats)},  MV features (138–344 kV): {len(mv_feats)}")

    node_grid = build_node_grid(nodes)

    # HV pass: wide snap (450 m) to capture compensation substation corridors, 150 m junction clustering
    hv_edges, hv_splits = _graph_pass(
        hv_feats, nodes, node_grid,
        snap_km=0.45, cluster_r=0.15,
        base_split_idx=len(nodes),
    )
    # MV pass: Fix 1 — wider snap (400 m) to capture urban 138 kV substations
    mv_edges, mv_splits = _graph_pass(
        mv_feats, nodes, node_grid,
        snap_km=0.40, cluster_r=0.10,
        base_split_idx=len(nodes) + len(hv_splits),
    )
    print(f"  HV junctions→edges: {len(hv_edges)}, split pts: {len(hv_splits)}")
    print(f"  MV junctions→edges: {len(mv_edges)}, split pts: {len(mv_splits)}")

    all_edges   = hv_edges + mv_edges
    split_nodes = hv_splits + mv_splits
    print(f"  Pre-cleanup: {len(all_edges)} edges, {len(split_nodes)} split nodes")

    # Build coordinate lookup (substations + split nodes) for distance filter
    idx_coords = {n['i']: (n['lat'], n['lon']) for n in nodes}
    for sn in split_nodes:
        idx_coords[sn['i']] = (sn['lat'], sn['lon'])

    # ---------------------------------------------------------------
    # Fix 4: Clean up phantom split points after HV/MV merge
    #   - Degree-2 splits: contract (merge two edges into one)
    #   - Degree-0/1 splits: remove node + edges
    #   Iterative: chained degree-2 splits need multiple passes.
    # ---------------------------------------------------------------
    split_ids = {sn['i'] for sn in split_nodes}
    total_removed = 0
    total_contracted = 0
    pass_num = 0

    while True:
        pass_num += 1
        # Build adjacency from current edges
        adj = defaultdict(list)
        for ei, e in enumerate(all_edges):
            adj[e['a']].append((e['b'], ei))
            adj[e['b']].append((e['a'], ei))

        remove_edges = set()
        new_edges = []
        remove_splits = set()

        for sn in [s for s in split_nodes if s['i'] in split_ids]:
            sid = sn['i']
            neighbors = adj.get(sid, [])
            deg = len(neighbors)

            if deg == 0:
                remove_splits.add(sid)
            elif deg == 1:
                for _, ei in neighbors:
                    remove_edges.add(ei)
                remove_splits.add(sid)
            elif deg == 2:
                n1, ei1 = neighbors[0]
                n2, ei2 = neighbors[1]
                # Only contract if neither neighbor is also being removed
                # (prevents broken edges in chained degree-2 splits)
                if n1 not in remove_splits and n2 not in remove_splits:
                    remove_edges.add(ei1)
                    remove_edges.add(ei2)
                    remove_splits.add(sid)
                    kv = max(all_edges[ei1].get('kv', 0), all_edges[ei2].get('kv', 0))
                    new_edges.append({'a': min(n1, n2), 'b': max(n1, n2), 'kv': kv})

        if not remove_splits:
            break

        total_removed += len(remove_splits)
        total_contracted += len(new_edges)
        all_edges = [e for ei, e in enumerate(all_edges) if ei not in remove_edges]
        all_edges.extend(new_edges)
        split_nodes = [sn for sn in split_nodes if sn['i'] not in remove_splits]
        split_ids = {sn['i'] for sn in split_nodes}

        if pass_num > 20:  # safety valve
            break

    print(f"  Fix 4 split cleanup ({pass_num} passes): removed {total_removed} splits, "
          f"contracted {total_contracted} edges")

    # Renumber split points to be contiguous starting at len(nodes),
    # and remap all edge references. The HTML uses array indexing
    # (NODES[e.a]), so 'i' values must match array positions.
    old_to_new = {}
    for new_offset, sn in enumerate(split_nodes):
        old_i = sn['i']
        new_i = len(nodes) + new_offset
        old_to_new[old_i] = new_i
        sn['i'] = new_i
    # Substations keep their original indices (0..len(nodes)-1)
    for n in nodes:
        old_to_new[n['i']] = n['i']
    # Remap edges
    for e in all_edges:
        e['a'] = old_to_new.get(e['a'], e['a'])
        e['b'] = old_to_new.get(e['b'], e['b'])
    split_ids = {sn['i'] for sn in split_nodes}

    print(f"  After cleanup: {len(all_edges)} edges, {len(split_nodes)} split nodes")

    # ---------------------------------------------------------------
    # Fix 5: Cross-voltage validation
    #   Reclassify edges where kV doesn't match both endpoint voltages.
    #   Only for edges between two non-split substations.
    # ---------------------------------------------------------------
    node_kv = {n['i']: n['kv'] for n in nodes}
    for sn in split_nodes:
        node_kv[sn['i']] = sn['kv']

    n_reclassed = 0
    for e in all_edges:
        a_id, b_id = e['a'], e['b']
        # Skip if either endpoint is a split point (kv inherited, not authoritative)
        if a_id in split_ids or b_id in split_ids:
            continue
        kv_a = node_kv.get(a_id, 0)
        kv_b = node_kv.get(b_id, 0)
        if kv_a == 0 or kv_b == 0:
            continue
        max_node_kv = max(kv_a, kv_b)
        min_node_kv = min(kv_a, kv_b)
        edge_kv = e['kv']
        # Both nodes < 345 but edge >= 345 → downgrade
        if max_node_kv < 345 and edge_kv >= 345:
            e['kv'] = int(max_node_kv)
            n_reclassed += 1
        # Both nodes >= 345 but edge < 345 → upgrade
        elif min_node_kv >= 345 and edge_kv < 345:
            e['kv'] = int(max_node_kv)
            n_reclassed += 1
    print(f"  Fix 5 cross-voltage: reclassified {n_reclassed} edges")

    # ---------------------------------------------------------------
    # Fix 6: Smarter 300 m filter + self-loop removal
    #   Keep edges < 300 m if BOTH endpoints are substations.
    #   Only drop short edges involving split points.
    # ---------------------------------------------------------------
    edges = []
    dropped_loop = 0
    dropped_short = 0
    for e in all_edges:
        a, b = e['a'], e['b']
        if a == b:
            dropped_loop += 1
            continue
        la, loa = idx_coords.get(a, (0, 0))
        lb, lob = idx_coords.get(b, (0, 0))
        dist = haversine(la, loa, lb, lob)
        # Keep short edges between two substations (real bus-section ties)
        a_is_split = a in split_ids
        b_is_split = b in split_ids
        if dist < 0.3 and (a_is_split or b_is_split):
            dropped_short += 1
            continue
        edges.append(e)

    print(f"  Post-filter: {len(edges)} edges kept  "
          f"(dropped {dropped_loop} self-loops, {dropped_short} <300 m split edges)")

    # ---------------------------------------------------------------
    # Fix 8: Edge-splice — connect low-degree substations to nearby
    # graph edges they clearly belong on.
    #
    # Many substations sit right next to a transmission corridor but
    # weren't connected because the OSM line endpoint was outside the
    # snap radius. Instead of widening the snap (which causes cross-
    # contamination in dense areas), we splice the substation into the
    # nearest passing edge: edge A→B becomes A→S + S→B.
    #
    # Only applied to substations with degree 0 or 1 (orphaned or
    # pendant). The splice distance threshold is generous (2 km) since
    # we're matching substations to corridors, not endpoints.
    # ---------------------------------------------------------------
    SPLICE_MAX_KM = 2.0           # max perpendicular distance from substation to edge
    SPLICE_MAX_OFFSET_RATIO = 0.3 # splice distance must be < 30% of edge length
    SPLICE_T_MIN = 0.1            # projection must be away from endpoints
    SPLICE_T_MAX = 0.9            # (endpoint connections handled by normal snap)

    # Rebuild idx_coords after renumbering (needed for distance calculations)
    idx_coords = {n['i']: (n['lat'], n['lon']) for n in nodes}
    for sn in split_nodes:
        idx_coords[sn['i']] = (sn['lat'], sn['lon'])

    # Build current degree count
    node_degree = defaultdict(int)
    for e in edges:
        node_degree[e['a']] += 1
        node_degree[e['b']] += 1

    # Find low-degree substations (not split points) eligible for splicing
    splice_candidates = []
    for n in nodes:
        deg = node_degree.get(n['i'], 0)
        if deg <= 1:
            splice_candidates.append(n)

    print(f"  Fix 8 edge-splice: {len(splice_candidates)} low-degree substations (deg 0-1)")

    # For each candidate, find the nearest edge (by point-to-segment distance)
    def point_to_segment_km(plat, plon, alat, alon, blat, blon):
        """Approximate distance from point P to segment A-B in km."""
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

    # Build spatial grid of edge midpoints for fast lookup
    EDGE_GRID = 0.05
    edge_grid = defaultdict(list)
    for ei, e in enumerate(edges):
        a_lat, a_lon = idx_coords.get(e['a'], (0, 0))
        b_lat, b_lon = idx_coords.get(e['b'], (0, 0))
        mid_lat = (a_lat + b_lat) / 2
        mid_lon = (a_lon + b_lon) / 2
        k = (int(mid_lat / EDGE_GRID), int(mid_lon / EDGE_GRID))
        edge_grid[k].append(ei)

    n_spliced = 0
    edges_to_remove = set()
    edges_to_add = []

    for n in splice_candidates:
        nlat, nlon = n['lat'], n['lon']
        nid = n['i']
        k = (int(nlat / EDGE_GRID), int(nlon / EDGE_GRID))

        best_dist = SPLICE_MAX_KM + 0.001
        best_ei = None
        best_t = 0.0

        # Determine substation voltage tier for matching
        node_kv_tier = 345 if n['kv'] >= 345 else 138

        for dr in range(-1, 2):
            for dc in range(-1, 2):
                for ei in edge_grid.get((k[0] + dr, k[1] + dc), []):
                    e = edges[ei]
                    # Don't splice into an edge we already connected to
                    if e['a'] == nid or e['b'] == nid:
                        continue
                    # Only splice into edges at the same voltage tier
                    edge_kv_tier = 345 if e.get('kv', 0) >= 345 else 138
                    if edge_kv_tier != node_kv_tier:
                        continue
                    a_lat, a_lon = idx_coords.get(e['a'], (0, 0))
                    b_lat, b_lon = idx_coords.get(e['b'], (0, 0))
                    if a_lat == 0 and a_lon == 0:
                        continue  # missing coordinates
                    edge_len = haversine(a_lat, a_lon, b_lat, b_lon)
                    if edge_len < 0.5:
                        continue  # too short to splice into
                    dist, t = point_to_segment_km(nlat, nlon, a_lat, a_lon, b_lat, b_lon)
                    # Principled checks:
                    # 1. Perpendicular distance within threshold
                    if dist > SPLICE_MAX_KM:
                        continue
                    # 2. Offset ratio: splice distance small relative to edge length
                    #    (prevents splicing into distant backbone lines)
                    if dist / edge_len > SPLICE_MAX_OFFSET_RATIO:
                        continue
                    # 3. Projection away from endpoints (endpoint snap handles those)
                    if t < SPLICE_T_MIN or t > SPLICE_T_MAX:
                        continue
                    if dist < best_dist:
                        best_dist = dist
                        best_ei = ei
                        best_t = t

        if best_ei is not None and best_dist <= SPLICE_MAX_KM:
            e = edges[best_ei]
            kv = e['kv']
            a_id, b_id = e['a'], e['b']

            # Don't splice if already connected to either endpoint
            if nid == a_id or nid == b_id:
                continue

            # Replace edge A→B with A→N + N→B
            edges_to_remove.add(best_ei)
            edges_to_add.append({'a': min(a_id, nid), 'b': max(a_id, nid), 'kv': kv})
            edges_to_add.append({'a': min(nid, b_id), 'b': max(nid, b_id), 'kv': kv})
            n_spliced += 1

    # Apply splices
    edges = [e for ei, e in enumerate(edges) if ei not in edges_to_remove]
    edges.extend(edges_to_add)

    print(f"  Spliced {n_spliced} substations into nearby edges "
          f"(edges: {len(edges_to_remove)} removed, {len(edges_to_add)} added, "
          f"net +{len(edges_to_add) - len(edges_to_remove)})")

    print(f"  Lines  high: {len(lines_high)}, mid-high: {len(lines_mid_hi)}, mid-low: {len(lines_mid_lo)}")
    print(f"  Graph edges: {len(edges)}, Split nodes: {len(split_nodes)}")
    return lines_high, lines_mid_hi, lines_mid_lo, edges, split_nodes


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
    .pbg { display: inline-block; font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; padding: 2px 7px; border-radius: 5px; margin-bottom: 9px; }
    .bg-high      { background: rgba(34,197,94,0.18);  color: #4ade80; }
    .bg-medium    { background: rgba(245,158,11,0.18); color: #fbbf24; }
    .bg-low       { background: rgba(249,115,22,0.18); color: #fb923c; }
    .bg-none      { background: rgba(107,114,128,0.18);color: #9ca3af; }
    .bg-unmatched { background: rgba(96,165,250,0.18); color: #93c5fd; }
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

  <!-- ── Lines ── -->
  <details open>
    <summary>Lines</summary>
    <div class="s-body">
      <div class="tog" onclick="document.getElementById('togLH').click()">
        <span class="tog-lbl"><span class="lsw" style="background:#a855f7"></span>High  ≥ 345 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togLH" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togLM').click()">
        <span class="tog-lbl"><span class="lsw" style="background:#3b82f6"></span>Mid  230 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togLM"><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togLL').click()">
        <span class="tog-lbl"><span class="lsw" style="background:#06b6d4"></span>Sub  138 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togLL"><span class="tr"></span><span class="th"></span></label>
      </div>
    </div>
  </details>

  <!-- ── Simplified Graph ── -->
  <details>
    <summary>Simplified Graph</summary>
    <div class="s-body">
      <div class="tog" onclick="document.getElementById('togEH').click()">
        <span class="tog-lbl"><span class="dsw" style="border-color:#a855f7"></span>High  ≥ 345 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togEH"><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togEM').click()">
        <span class="tog-lbl"><span class="dsw" style="border-color:#3b82f6"></span>Mid  230 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togEM"><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togEL').click()">
        <span class="tog-lbl"><span class="dsw" style="border-color:#06b6d4"></span>Sub  138 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togEL"><span class="tr"></span><span class="th"></span></label>
      </div>
    </div>
  </details>

  <!-- ── Nodes ── -->
  <details open>
    <summary>Nodes</summary>
    <div class="s-body">

      <div class="sub-lbl">Voltage tier</div>
      <div class="tog" onclick="document.getElementById('togNH').click()">
        <span class="tog-lbl"><span class="dot" style="background:#a855f7"></span>High  ≥ 345 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togNH" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togNM').click()">
        <span class="tog-lbl"><span class="dot" style="background:#3b82f6"></span>Mid  230 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togNM" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togNL').click()">
        <span class="tog-lbl"><span class="dot" style="background:#06b6d4"></span>Sub  138 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togNL" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togSP').click()">
        <span class="tog-lbl"><span class="dot" style="background:#475569"></span>Split points</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togSP"><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togPL').click()">
        <span class="tog-lbl"><span class="dot" style="background:#f97316;border:2px solid #fff;box-sizing:border-box"></span>Power plants</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togPL" checked><span class="tr"></span><span class="th"></span></label>
      </div>

      <hr class="divider">

      <div class="sub-lbl">Match quality filter</div>
      <div class="tog" onclick="document.getElementById('togQH').click()">
        <span class="tog-lbl"><span class="dot" style="background:#22c55e"></span>High confidence</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togQH" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togQM').click()">
        <span class="tog-lbl"><span class="dot" style="background:#f59e0b"></span>Medium confidence</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togQM" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togQL').click()">
        <span class="tog-lbl"><span class="dot" style="background:#f97316"></span>Low confidence</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togQL" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togQU').click()">
        <span class="tog-lbl"><span class="dot" style="background:#60a5fa"></span>Unmatched (OSM only)</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togQU" checked><span class="tr"></span><span class="th"></span></label>
      </div>

      <hr class="divider">

      <div class="sub-lbl">Colour by</div>
      <label class="rad"><input type="radio" name="colorBy" value="quality" checked> Match quality</label>
      <label class="rad"><input type="radio" name="colorBy" value="voltage"> Voltage level</label>
      <label class="rad"><input type="radio" name="colorBy" value="lmp"> LMP price</label>

      <hr class="divider">

      <div class="tog" onclick="document.getElementById('togLmpOnly').click()">
        <span class="tog-lbl">LMP nodes only</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togLmpOnly"><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togGenOnly').click()">
        <span class="tog-lbl">EIA-860 generators only</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togGenOnly"><span class="tr"></span><span class="th"></span></label>
      </div>
    </div>
  </details>

  <!-- ── Map ── -->
  <details open>
    <summary>Map</summary>
    <div class="s-body">
      <div class="tog" onclick="document.getElementById('togZones').click()">
        <span class="tog-lbl"><span class="bsw" style="border-color:#94a3b8"></span>ERCOT zones</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togZones" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div style="margin-top:9px;display:grid;grid-template-columns:1fr 1fr;gap:4px 8px;font-size:12px;color:#64748b">
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#f87171"></span>Houston</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#60a5fa"></span>North</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#34d399"></span>South</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#fb923c"></span>West</span>
      </div>
    </div>
  </details>

  <!-- ── Information ── -->
  <details>
    <summary>Information</summary>
    <div class="s-body" style="font-size:11px; line-height:1.75; color:#94a3b8;">
      <p style="margin:0 0 8px;">Real-time ERCOT transmission grid map. LMP prices refresh every 15 minutes from the ERCOT Public API.</p>
      <div class="sub-lbl" style="margin-top:4px;">What is a match?</div>
      <p style="margin:0 0 8px;">ERCOT prices energy at ~4,900 named settlement points. Each is matched to a physical substation in OpenStreetMap using name similarity and geographic proximity. <span style="color:#34d399">High</span> / <span style="color:#f59e0b">medium</span> confidence matches are verified by multiple signals. <span style="color:#f97316">Low</span> confidence is name-only and may be imprecise. <span style="color:#60a5fa">Unmatched</span> substations have an OSM location but no ERCOT settlement point assigned.</p>
      <div class="sub-lbl" style="margin-top:4px;">LMP colour mode</div>
      <p style="margin:0 0 8px;"><span style="color:#6496d2">Blue</span> = below median price · <span style="color:#dc4444">Red</span> = above median. Scale is 5th–95th percentile of live prices. Hover any node to see its exact LMP. Dark grey nodes have no price data.</p>
      <div class="sub-lbl" style="margin-top:4px;">Lines &amp; graph</div>
      <p style="margin:0;">Solid lines are OSM HV transmission geometry ≥ 115 kV. Dashed lines are inferred bus-to-bus connectivity from endpoint clustering.</p>
    </div>
  </details>

  <!-- ── Tools ── -->
  <details>
    <summary>Tools</summary>
    <div class="s-body">
      <button class="tbtn" onclick="zoomToERCOT()">↩  Zoom to ERCOT</button>
      <button class="tbtn" id="btnIso" onclick="toggleIsolated()">◎  Show isolated nodes only</button>
    </div>
  </details>
</div>

<div id="statsbar">
  <span><span class="sn" id="st-nodes">–</span> subs</span>
  <span><span class="sn" id="st-match">–</span> matched</span>
  <span><span class="sn" id="st-lines">–</span> lines</span>
  <span><span class="sn" id="st-edges">–</span> graph edges</span>
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
const EDGES_HIGH   = __EDGES_HIGH__;
const EDGES_MID_HI = __EDGES_MID_HI__;
const EDGES_MID_LO = __EDGES_MID_LO__;
const ZONES      = __ZONES__;

// ============================================================
// Color constants  (3-tier: high / mid-high / mid-low)
// ============================================================
const CONF_COLOR = {
  high:      '#22c55e',
  medium:    '#f59e0b',
  low:       '#f97316',
  none:      '#6b7280',
  unmatched: '#60a5fa',
};

const KV_COLOR = kv => {
  if (kv >= 345) return '#a855f7';
  if (kv >= 200) return '#3b82f6';
  return '#06b6d4';
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

const SOURCE_LABEL = {
  osm:                  'OSM (pass 2)',
  eia860:               'EIA-860 (pass 1)',
  gnis:                 'USGS GNIS (pass 8)',
  mora_eia860:          'MORA → EIA-860 (pass 6)',
  mora_osm:             'MORA → OSM (pass 4)',
  mora_ix_queue:        'MORA → IX Queue (pass 7)',
  mora_county_centroid: 'MORA county centroid (pass 5)',
  hv_endpoint:          'HV endpoint (pass 9B)',
  hv_osm_345:           '345 kV OSM (pass 9A)',
  cp_osm:               'CenterPoint OSM (pass 10)',
};

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
// Layer groups
// ============================================================
const layerZones     = L.layerGroup().addTo(map);
// Nodes — by voltage tier
const layerNHigh      = L.layerGroup().addTo(map);
const layerNMidHi     = L.layerGroup().addTo(map);
const layerNMidLo     = L.layerGroup().addTo(map);
const layerSplits     = L.layerGroup();             // off by default
// Lines — by voltage tier (high on, mid-hi/mid-lo off — too dense)
const layerLinesHigh  = L.layerGroup().addTo(map);
const layerLinesMidHi = L.layerGroup();
const layerLinesMidLo = L.layerGroup();
// Simplified graph edges — all off by default
const layerEdgesHigh  = L.layerGroup();
const layerEdgesMidHi = L.layerGroup();
const layerEdgesMidLo = L.layerGroup();
// Power plants — on by default
const layerPlants     = L.layerGroup().addTo(map);

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
let colorMode    = 'quality'; // 'quality' | 'voltage' | 'lmp'
let lmpData      = null;
let lmpMap       = {};       // base settlement-point name → price
let lmpScale     = null;     // { lo, mid, hi } percentile anchors
const allMarkers = [];

// ── LMP colour scale ─────────────────────────────────────────
function buildLmpScale(priceMap) {
  const prices = Object.values(priceMap).filter(v => typeof v === 'number');
  if (!prices.length) return null;
  prices.sort((a, b) => a - b);
  const n = prices.length;
  return {
    lo:  prices[Math.floor(n * 0.05)],
    mid: prices[Math.floor(n * 0.50)],
    hi:  prices[Math.floor(n * 0.95)],
  };
}

// 3-stop gradient: blue (0,100,210) → white (255,255,255) → red (220,30,30)
function lmpColor(price) {
  if (!lmpScale) return '#94a3b8';
  const { lo, mid, hi } = lmpScale;
  let t, r, g, b;
  if (price <= mid) {
    t = Math.max(0, Math.min(1, (price - lo) / Math.max(mid - lo, 0.01)));
    r = Math.round(0   + 255 * t);
    g = Math.round(100 + 155 * t);
    b = Math.round(210 +  45 * t);
  } else {
    t = Math.max(0, Math.min(1, (price - mid) / Math.max(hi - mid, 0.01)));
    r = Math.round(255 - 35  * t);
    g = Math.round(255 - 225 * t);
    b = Math.round(255 - 225 * t);
  }
  return `rgb(${r},${g},${b})`;
}

function nodeColorLmp(n) {
  if (!n.ercot) return '#475569';
  const price = lmpMap[n.ercot];
  if (price === undefined) return '#475569';
  return lmpColor(price);
}

function nodeRadius(kv) {
  if (kv >= 345) return 5.5;
  if (kv >= 200) return 3.5;
  return 2.5;
}
function baseFillOp(n) {
  return (n.conf === 'low' || n.conf === 'unmatched') ? 0.5 : 0.82;
}
function nodeColor(n) {
  if (colorMode === 'voltage') return KV_COLOR(n.kv);
  if (colorMode === 'lmp')     return nodeColorLmp(n);
  return CONF_COLOR[n.conf] || '#60a5fa';
}
function nodeStyle(n) {
  if (n.split) {
    return { renderer, radius: 2, fillColor: KV_COLOR(n.kv), color: 'rgba(0,0,0,0)', weight: 0, fillOpacity: 0.45, opacity: 0 };
  }
  const col = nodeColor(n);
  return { renderer, radius: nodeRadius(n.kv), fillColor: col,
           color: 'rgba(0,0,0,0.3)', weight: 0.7, fillOpacity: baseFillOp(n), opacity: 0.9 };
}
function nodeTierLayer(n) {
  if (n.split)     return layerSplits;
  if (n.kv >= 345) return layerNHigh;
  if (n.kv >= 200) return layerNMidHi;
  return layerNMidLo;
}

// ============================================================
// Node filters (opacity-based, independent of tier layers)
// ============================================================
const hiddenConf = new Set();
let   isoOnly    = false;
let   lmpOnly    = false;
let   genOnly    = false;

// Pre-compute which nodes have at least one graph edge
const connectedSet = new Set();
for (const e of [...EDGES_HIGH, ...EDGES_MID_HI, ...EDGES_MID_LO]) {
  connectedSet.add(e.a);
  connectedSet.add(e.b);
}

function applyNodeFilters() {
  for (const {m, n} of allMarkers) {
    const hidden = hiddenConf.has(n.conf)
      || (isoOnly && connectedSet.has(n.i))
      || (lmpOnly && lmpMap[n.ercot] === undefined)
      || (genOnly && !n.mw);
    m.setStyle({
      fillOpacity: hidden ? 0 : baseFillOp(n),
      opacity:     hidden ? 0 : 0.9,
    });
  }
}

// ============================================================
// Popup builder
// ============================================================
function makePopup(n) {
  const src = SOURCE_LABEL[n.src] || n.src || '';
  let rows = '';
  const add = (k, v) => { if (v) rows += `<span class="mk">${k}</span><span class="mv">${v}</span>`; };
  if (n.ercot)  add('ERCOT node',   n.ercot);
  if (n.ercot && lmpMap[n.ercot] !== undefined) add('LMP', `$${lmpMap[n.ercot].toFixed(2)}/MWh`);
  if (src)      add('Match source', src);
  add('Voltage', n.kv ? `${n.kv} kV` : '');
  if (n.lz)     add('Load zone',    `LZ_${n.lz}`);
  if (n.mw)     add('Gen capacity', `${n.mw} MW${n.tech ? ' · ' + n.tech : ''}`);
  if (n.op)     add('Operator',     n.op);
  if (n.stype)  add('Type',         n.stype);
  if (n.sc)     add('Match score',  n.sc);
  const disp  = n.name || n.ercot || `OSM ${n.id}`;
  const conf  = n.conf === 'unmatched' ? 'unmatched' : n.conf;
  return `<div class="pi">
    <div class="pid">OSM ${n.id}</div>
    <div class="pnm">${disp}</div>
    <div class="pbg bg-${n.conf}">${conf}</div>
    <div class="pm">${rows}</div>
  </div>`;
}

// ============================================================
// Render nodes
// ============================================================
for (const n of NODES) {
  const m = L.circleMarker([n.lat, n.lon], nodeStyle(n));
  if (!n.split) {
    m.bindPopup(makePopup(n), { maxWidth: 310 });
    if (n.ercot || n.mw) {
      m.on('mouseover', function() {
        const parts = [];
        if (n.ercot) parts.push(n.ercot);
        const price = n.ercot ? lmpMap[n.ercot] : undefined;
        if (price !== undefined) parts.push(`$${price.toFixed(2)}/MWh`);
        if (n.mw) parts.push(`${n.mw} MW${n.tech ? ' · ' + n.tech : ''}`);
        this.bindTooltip(parts.join('  ·  '), { sticky: true, className: 'lmp-tip' }).openTooltip();
      });
      m.on('mouseout', function() { this.closeTooltip(); });
    }
    allMarkers.push({m, n});
  } else {
    m.bindTooltip(`${n.kv} kV split point`, { className: 'zone-label' });
  }
  m.addTo(nodeTierLayer(n));
}

// ============================================================
// Render power plants
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
  }).addTo(layerPlants);
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
// Render line geometry
// ============================================================
for (const ln of LINES_HIGH)
  L.polyline(ln.pts, { renderer, color: KV_COLOR(ln.kv), weight: 1.8, opacity: 0.65 }).addTo(layerLinesHigh);
for (const ln of LINES_MID_HI)
  L.polyline(ln.pts, { renderer, color: KV_COLOR(ln.kv), weight: 1.2, opacity: 0.55 }).addTo(layerLinesMidHi);
for (const ln of LINES_MID_LO)
  L.polyline(ln.pts, { renderer, color: KV_COLOR(ln.kv), weight: 0.8, opacity: 0.40 }).addTo(layerLinesMidLo);

// ============================================================
// Render simplified graph edges
// ============================================================
function buildEdgeLayer(edgeList, layer) {
  for (const e of edgeList) {
    const na = NODES[e.a], nb = NODES[e.b];
    if (!na || !nb) continue;
    L.polyline([[na.lat, na.lon],[nb.lat, nb.lon]], {
      renderer, color: KV_COLOR(e.kv),
      weight: e.kv >= 345 ? 1.5 : 0.9, opacity: 0.65, dashArray: '5 4',
    }).addTo(layer);
  }
}
buildEdgeLayer(EDGES_HIGH,   layerEdgesHigh);
buildEdgeLayer(EDGES_MID_HI, layerEdgesMidHi);
buildEdgeLayer(EDGES_MID_LO, layerEdgesMidLo);

// ============================================================
// Helpers
// ============================================================
function setLayer(layer, on) {
  if (on) map.addLayer(layer); else map.removeLayer(layer);
}
function updateNodeColors() {
  for (const {m, n} of allMarkers) m.setStyle({ fillColor: nodeColor(n) });
}

// ============================================================
// Toggle wiring — Lines
// ============================================================
document.getElementById('togLH').addEventListener('change', e => setLayer(layerLinesHigh,  e.target.checked));
document.getElementById('togLM').addEventListener('change', e => setLayer(layerLinesMidHi, e.target.checked));
document.getElementById('togLL').addEventListener('change', e => setLayer(layerLinesMidLo, e.target.checked));

// ============================================================
// Toggle wiring — Simplified graph
// ============================================================
document.getElementById('togEH').addEventListener('change', e => setLayer(layerEdgesHigh,  e.target.checked));
document.getElementById('togEM').addEventListener('change', e => setLayer(layerEdgesMidHi, e.target.checked));
document.getElementById('togEL').addEventListener('change', e => setLayer(layerEdgesMidLo, e.target.checked));

// ============================================================
// Toggle wiring — Node voltage tiers
// ============================================================
document.getElementById('togNH').addEventListener('change', e => setLayer(layerNHigh,   e.target.checked));
document.getElementById('togNM').addEventListener('change', e => setLayer(layerNMidHi,  e.target.checked));
document.getElementById('togNL').addEventListener('change', e => setLayer(layerNMidLo,  e.target.checked));
document.getElementById('togSP').addEventListener('change', e => setLayer(layerSplits,  e.target.checked));
document.getElementById('togPL').addEventListener('change', e => setLayer(layerPlants,  e.target.checked));

// ============================================================
// Toggle wiring — Match quality filter
// ============================================================
function toggleConf(conf, show) {
  if (show) hiddenConf.delete(conf); else hiddenConf.add(conf);
  applyNodeFilters();
}
document.getElementById('togQH').addEventListener('change', e => toggleConf('high',      e.target.checked));
document.getElementById('togQM').addEventListener('change', e => toggleConf('medium',    e.target.checked));
document.getElementById('togQL').addEventListener('change', e => toggleConf('low',       e.target.checked));
document.getElementById('togQU').addEventListener('change', e => toggleConf('unmatched', e.target.checked));

// ============================================================
// Colour by
// ============================================================
document.querySelectorAll('input[name="colorBy"]').forEach(r =>
  r.addEventListener('change', e => { colorMode = e.target.value; updateNodeColors(); })
);
document.getElementById('togLmpOnly').addEventListener('change', e => {
  lmpOnly = e.target.checked;
  applyNodeFilters();
});
document.getElementById('togGenOnly').addEventListener('change', e => {
  genOnly = e.target.checked;
  applyNodeFilters();
});

// ============================================================
// LMP fetch
// ============================================================
fetch('./grid_data/lmp_snapshot.json')
  .then(r => r.json())
  .then(data => {
    lmpData  = data;
    lmpMap   = data.lmp_base || data.lmp || {};
    lmpScale = buildLmpScale(lmpMap);
    if (colorMode === 'lmp') updateNodeColors();
    if (lmpOnly) applyNodeFilters();
  })
  .catch(() => {});

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

function toggleIsolated() {
  isoOnly = !isoOnly;
  const btn = document.getElementById('btnIso');
  btn.textContent = isoOnly ? '◉  Show all nodes' : '◎  Show isolated nodes only';
  btn.classList.toggle('active', isoOnly);
  applyNodeFilters();
}

// ============================================================
// Stats bar
// ============================================================
const substations = NODES.filter(n => !n.split);
const splits      = NODES.filter(n =>  n.split);
const matched     = substations.filter(n => n.conf !== 'unmatched').length;
const totalLines  = LINES_HIGH.length + LINES_MID.length + LINES_LOW.length;
const totalEdges  = EDGES_HIGH.length + EDGES_MID.length + EDGES_LOW.length;

document.getElementById('st-nodes').textContent = substations.length.toLocaleString();
document.getElementById('st-match').textContent = matched.toLocaleString();
document.getElementById('st-lines').textContent = totalLines.toLocaleString();
document.getElementById('st-edges').textContent = totalEdges.toLocaleString();
document.getElementById('subtitle').textContent =
  `${substations.length.toLocaleString()} subs · ${splits.length.toLocaleString()} split pts · ${Math.round(matched/substations.length*100)}% matched`;

</script>
</body>
</html>
"""


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

    print("Loading HV line features…")
    features = load_line_features(ercot_union)

    print("Building line endpoint grid…")
    ep_grid = build_ep_grid(features)

    print("Loading OSM substations…")
    nodes = load_nodes(ep_grid, ercot_lookup, ercot_union)
    print(f"  {len(nodes)} nodes loaded")

    print("Loading OSM power plants…")
    plants = load_plants(ercot_union)

    print("Processing lines and building graph edges…")
    lines_high, lines_mid_hi, lines_mid_lo, edges, split_nodes = process_lines(features, nodes)

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

    print(f"  Nodes: {len(nodes_js)//1024} KB  Plants: {len(plants_js)//1024} KB  "
          f"Lines H/MH/ML: {len(lines_high_js)//1024}/{len(lines_mid_hi_js)//1024}/{len(lines_mid_lo_js)//1024} KB  "
          f"Edges H/MH/ML: {len(edges_high_js)//1024}/{len(edges_mid_hi_js)//1024}/{len(edges_mid_lo_js)//1024} KB")

    html = HTML_TEMPLATE
    html = html.replace('__NODES__',        nodes_js)
    html = html.replace('__PLANTS__',       plants_js)
    html = html.replace('__LINES_HIGH__',   lines_high_js)
    html = html.replace('__LINES_MID_HI__', lines_mid_hi_js)
    html = html.replace('__LINES_MID_LO__', lines_mid_lo_js)
    html = html.replace('__EDGES_HIGH__',   edges_high_js)
    html = html.replace('__EDGES_MID_HI__', edges_mid_hi_js)
    html = html.replace('__EDGES_MID_LO__', edges_mid_lo_js)
    html = html.replace('__ZONES__',        zones_js)

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(html)

    total_kb = len(html) // 1024
    print(f"\nOutput: {OUT}")
    print(f"Total size: {total_kb} KB ({total_kb/1024:.1f} MB)")
    print(f"Substations: {len(nodes)}, Plants: {len(plants)}, Split nodes: {len(split_nodes)}, Edges: {len(edges)}")
    print(f"V2 topology: HV snap 0.45 km, MV snap 0.40 km, nearest-match clustering")
    print("Done.")


if __name__ == "__main__":
    main()
