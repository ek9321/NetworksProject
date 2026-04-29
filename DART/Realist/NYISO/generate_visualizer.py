"""
Generate a self-contained HTML visualizer for the NYISO grid.

Node set: OSM physical substations >= 115 kV that are within 500 m of a
transmission line endpoint AND inside NYISO territory.
Colored by voltage tier.

Reads:
  Realist/NYISO/grid_data/ny_substations.geojson   — OSM substation geometries
  Realist/NYISO/grid_data/ny_hv_lines.geojson       — OSM HV line geometries
  Realist/NYISO/grid_data/nyiso_zones.geojson        — NYISO zone polygons (9 zones, A-K)

Writes:
  Realist/NYISO/ny_grid_visualizer.html
"""

import json
import math
import os
from collections import defaultdict, deque

from shapely.geometry import shape, Point

NYISO_DIR  = os.path.dirname(os.path.abspath(__file__))
OSM_SUBS   = os.path.join(NYISO_DIR, "grid_data", "ny_substations.geojson")
LINES      = os.path.join(NYISO_DIR, "grid_data", "ny_hv_lines.geojson")
ZONES      = os.path.join(NYISO_DIR, "grid_data", "nyiso_zones.geojson")
OUT        = os.path.join(NYISO_DIR, "ny_grid_visualizer.html")

# ---------------------------------------------------------------------------
# NYISO zone polygons
# ---------------------------------------------------------------------------

# Zone display colours — 9 visible zones (H/I merged into G at polygon level)
ZONE_COLORS = {
    'A': '#f87171',   # West
    'B': '#fb923c',   # Genesee
    'C': '#fbbf24',   # Central
    'D': '#34d399',   # North
    'E': '#4ade80',   # Mohawk Valley
    'F': '#60a5fa',   # Capital
    'G': '#a78bfa',   # Hudson Valley (covers G/H/I)
    'J': '#f472b6',   # New York City
    'K': '#38bdf8',   # Long Island
}


def load_zones():
    """
    Returns:
      zone_features : list of raw GeoJSON features (for HTML embedding)
      nyiso_union   : shapely geometry — union of all zones (for PIP filtering)
    """
    with open(ZONES, encoding='utf-8') as f:
        data = json.load(f)

    zone_features = data['features']
    geoms = [shape(feat['geometry']) for feat in zone_features]

    from shapely.ops import unary_union
    # buffer(0) repairs self-intersections introduced by simplification
    geoms = [g.buffer(0) for g in geoms]
    nyiso_union = unary_union(geoms)

    names = [f"{f['properties'].get('zone_letter', '?')} ({f['properties'].get('zone_name', '?')})"
             for f in zone_features]
    print(f"  Loaded {len(zone_features)} NYISO zones: {names}")
    print(f"  Union bbox: {tuple(round(x, 2) for x in nyiso_union.bounds)}")
    return zone_features, nyiso_union


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def in_ny_bounds(lon, lat):
    return 40.4 <= lat <= 45.1 and -80.0 <= lon <= -71.8


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
# Load HV line features (>= 115 kV, inside NYISO territory)
# ---------------------------------------------------------------------------

def load_line_features(nyiso_union):
    """
    Keep lines >= 115 kV where at least one endpoint is inside NYISO territory.
    Uses a cheap bbox pre-check before the shapely PIP test.
    """
    print("  Loading HV line features...")
    with open(LINES, encoding='utf-8') as f:
        data = json.load(f)

    bounds = nyiso_union.bounds   # (minx, miny, maxx, maxy)

    def in_nyiso_bbox(lon, lat):
        return bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]

    valid = []
    skipped = 0
    for feat in data['features']:
        kv = feat['properties'].get('voltage_kv') or 0
        if kv < 115:
            continue
        coords = feat['geometry']['coordinates']
        if len(coords) < 2:
            continue
        lon0, lat0 = coords[0]
        lon1, lat1 = coords[-1]
        # Quick bbox gate, then exact PIP on whichever endpoint passes bbox
        in0 = in_nyiso_bbox(lon0, lat0) and nyiso_union.contains(Point(lon0, lat0))
        in1 = in_nyiso_bbox(lon1, lat1) and nyiso_union.contains(Point(lon1, lat1))
        if not (in0 or in1):
            skipped += 1
            continue
        valid.append(feat)

    print(f"  Valid HV line features: {len(valid)}  (dropped {skipped} outside NYISO)")
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

def load_nodes(ep_grid, nyiso_union):
    """
    Load OSM physical substations >= 115 kV that are:
      - within 500 m of a transmission line endpoint
      - inside NYISO territory
    """
    with open(OSM_SUBS, encoding='utf-8') as f:
        data = json.load(f)

    CONNECT_KM = 0.5   # must be this close to a line endpoint
    bounds = nyiso_union.bounds

    nodes = []
    skipped_kv    = 0
    skipped_conn  = 0
    skipped_nyiso = 0
    for feat in data['features']:
        props = feat['properties']
        kv = props.get('voltage_kv') or 0
        if kv < 115:
            skipped_kv += 1
            continue

        lon, lat = feat['geometry']['coordinates']

        # Cheap bbox gate before shapely PIP
        if not (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]):
            skipped_nyiso += 1
            continue
        if not nyiso_union.contains(Point(lon, lat)):
            skipped_nyiso += 1
            continue

        d = nearest_in_grid(lat, lon, ep_grid, CONNECT_KM)
        if d > CONNECT_KM:
            skipped_conn += 1
            continue

        osm_id = props['osm_id']
        name   = (props.get('name') or '').strip()
        op     = (props.get('operator') or '').strip()
        stype  = (props.get('substation_type') or '').strip()

        nodes.append({
            'i':     len(nodes),
            'lat':   round(lat, 5),
            'lon':   round(lon, 5),
            'id':    str(osm_id),
            'name':  name,
            'kv':    kv,
            'op':    op,
            'stype': stype,
        })

    print(f"  OSM subs (raw): {len(nodes)} kept, {skipped_kv} dropped (<115 kV), "
          f"{skipped_nyiso} dropped (outside NYISO), {skipped_conn} dropped (no line within {CONNECT_KM} km)")

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
    return nodes


# ---------------------------------------------------------------------------
# Zone assignment via point-in-polygon
# ---------------------------------------------------------------------------

def assign_zones(nodes, zone_features):
    """Assign each node a zone letter via point-in-polygon against zone polygons."""
    zone_shapes = []
    for feat in zone_features:
        letter = feat['properties'].get('zone_letter', '?')
        geom = shape(feat['geometry']).buffer(0)
        zone_shapes.append((letter, geom))

    assigned = 0
    for n in nodes:
        pt = Point(n['lon'], n['lat'])
        n['zone'] = ''
        for letter, geom in zone_shapes:
            if geom.contains(pt):
                n['zone'] = letter
                assigned += 1
                break

    print(f"  Zone assignment: {assigned}/{len(nodes)} nodes assigned a zone")


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
            if not in_ny_bounds(lon, lat):
                continue
            matched = None
            for c in clusters:
                if abs(c[0] - lat) > 0.01 or abs(c[1] - lon) > 0.01:
                    continue
                if haversine(lat, lon, c[0], c[1]) <= cluster_r:
                    matched = c
                    break
            if matched:
                n = matched[2]
                matched[0] = (matched[0] * n + lat) / (n + 1)
                matched[1] = (matched[1] * n + lon) / (n + 1)
                matched[2] += 1
                matched[3] = max(matched[3], kv)
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

    Non-substation junctions with degree >= 3 are treated as "split nodes" --
    real physical branch points (T-junctions, tap points).  They become stop
    nodes in the BFS alongside substation junctions so that a T-shaped
    corridor A->X->{B,C} produces edges A-X, X-B, X-C rather than the
    spurious A-B, A-C that BFS-contraction alone would give.

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

    # Snap junctions -> nearest OSM substation (strict snap_km radius)
    junc_to_node = {}
    for i, c in enumerate(clusters):
        n, _ = nearest_node(c[0], c[1], node_grid, snap_km)
        if n:
            junc_to_node[i] = n['i']

    sub_juncs = set(junc_to_node.keys())

    # Step 3: Detect split junctions -- degree >= 3, not snapped to any substation
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
# Process line geometries and build simplified graph edges
# ---------------------------------------------------------------------------

def process_lines(features, nodes):
    """
    Returns (lines_high, lines_mid_hi, lines_mid_lo, edges, split_nodes).

    Voltage tiers:  high >= 345 kV  |  mid-high 200-344 kV  |  mid-low 115-199 kV
    Step 2: Separate HV (>=345 kV, SNAP_KM=0.45) and MV (115-344 kV,
    SNAP_KM=0.15) passes to avoid cross-contamination.
    Step 3: Split nodes (T-junctions) detected per pass.
    Step 4: Self-loop and <300 m edges dropped.
    """
    # --- Visual line geometry split into 3 tiers ---
    lines_high   = []   # >= 345 kV      (full simplified geometry)
    lines_mid_hi = []   # 200-344 kV     (endpoints only)
    lines_mid_lo = []   # 115-199 kV     (endpoints only)
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
    mv_feats = [f for f in features
                if 115 <= (f['properties'].get('voltage_kv') or 0) < 345]
    print(f"  HV features (>=345 kV): {len(hv_feats)},  MV features (115-344 kV): {len(mv_feats)}")

    node_grid = build_node_grid(nodes)

    # HV pass: wide snap (450 m) to capture compensation substation corridors, 150 m junction clustering
    hv_edges, hv_splits = _graph_pass(
        hv_feats, nodes, node_grid,
        snap_km=0.45, cluster_r=0.15,
        base_split_idx=len(nodes),
    )
    # MV pass: tighter snap (150 m), 100 m junction clustering
    mv_edges, mv_splits = _graph_pass(
        mv_feats, nodes, node_grid,
        snap_km=0.15, cluster_r=0.10,
        base_split_idx=len(nodes) + len(hv_splits),
    )
    print(f"  HV junctions->edges: {len(hv_edges)}, split pts: {len(hv_splits)}")
    print(f"  MV junctions->edges: {len(mv_edges)}, split pts: {len(mv_splits)}")

    all_edges   = hv_edges + mv_edges
    split_nodes = hv_splits + mv_splits

    # Build coordinate lookup (substations + split nodes) for distance filter
    idx_coords = {n['i']: (n['lat'], n['lon']) for n in nodes}
    for sn in split_nodes:
        idx_coords[sn['i']] = (sn['lat'], sn['lon'])

    # Step 4: Drop self-loops and edges shorter than 300 m
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
        if haversine(la, loa, lb, lob) < 0.3:
            dropped_short += 1
            continue
        edges.append(e)

    print(f"  Post-filter: {len(edges)} edges kept  "
          f"(dropped {dropped_loop} self-loops, {dropped_short} <300 m)")
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
  <title>NYISO Transmission Grid</title>
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

    /* --- Panel shell --- */
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

    /* --- Sticky header --- */
    .p-head {
      position: sticky; top: 0; z-index: 2;
      padding: 14px 16px 10px;
      background: rgba(10,15,30,0.98);
      border-bottom: 1px solid rgba(148,163,184,0.08);
    }
    .p-title { font-size: 13px; font-weight: 700; color: #f1f5f9; letter-spacing: 0.01em; }
    .p-sub   { font-size: 11px; color: #475569; margin-top: 2px; line-height: 1.4; }

    /* --- Accordion --- */
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
      content: '>';
      font-size: 15px; line-height: 1;
      color: #334155;
      transition: transform 0.18s;
      display: inline-block;
      transform: rotate(90deg);
    }
    details[open] summary::after { transform: rotate(270deg); }
    .s-body { padding: 2px 16px 13px; }

    /* --- Sub-labels inside sections --- */
    .sub-lbl {
      font-size: 10px; font-weight: 600;
      color: #2d3f55;
      text-transform: uppercase; letter-spacing: 0.09em;
      margin: 8px 0 6px;
    }
    .sub-lbl:first-child { margin-top: 0; }
    .divider { border: none; border-top: 1px solid rgba(148,163,184,0.07); margin: 10px 0; }

    /* --- Toggle rows --- */
    .tog {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 7px; cursor: pointer;
    }
    .tog:last-child { margin-bottom: 0; }
    .tog-lbl {
      display: flex; align-items: center; gap: 7px;
      color: #cbd5e1; user-select: none;
    }

    /* --- Toggle switch --- */
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

    /* --- Swatches --- */
    .dot  { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .lsw  { width: 16px; height: 3px; border-radius: 2px; flex-shrink: 0; }
    .dsw  { width: 16px; height: 0; border-top: 2px dashed; flex-shrink: 0; }
    .bsw  {
      width: 13px; height: 9px;
      border: 1.5px solid; border-radius: 2px;
      flex-shrink: 0; background: rgba(148,163,184,0.1);
    }

    /* --- Tool buttons --- */
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

    /* --- Stats bar --- */
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

    /* --- Leaflet popup --- */
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
    .bg-high { background: rgba(168,85,247,0.18); color: #c084fc; }
    .bg-mid  { background: rgba(59,130,246,0.18); color: #60a5fa; }
    .bg-low  { background: rgba(6,182,212,0.18);  color: #22d3ee; }
    .pm  { display: grid; grid-template-columns: auto 1fr; gap: 3px 9px; font-size: 12px; }
    .mk  { color: #475569; white-space: nowrap; }
    .mv  { color: #cbd5e1; word-break: break-word; }

    /* --- Zone labels --- */
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
    <div class="p-title">NYISO Transmission Grid</div>
    <div class="p-sub" style="color:#334155;font-size:10px;margin-top:1px;">Dartboard Project</div>
    <div class="p-sub" id="subtitle">Loading...</div>
  </div>

  <!-- -- Lines -- -->
  <details open>
    <summary>Lines</summary>
    <div class="s-body">
      <div class="tog" onclick="document.getElementById('togLH').click()">
        <span class="tog-lbl"><span class="lsw" style="background:#a855f7"></span>High  >= 345 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togLH" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togLM').click()">
        <span class="tog-lbl"><span class="lsw" style="background:#3b82f6"></span>Mid  230 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togLM"><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togLL').click()">
        <span class="tog-lbl"><span class="lsw" style="background:#06b6d4"></span>Sub  115+ kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togLL"><span class="tr"></span><span class="th"></span></label>
      </div>
    </div>
  </details>

  <!-- -- Simplified Graph -- -->
  <details>
    <summary>Simplified Graph</summary>
    <div class="s-body">
      <div class="tog" onclick="document.getElementById('togEH').click()">
        <span class="tog-lbl"><span class="dsw" style="border-color:#a855f7"></span>High  >= 345 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togEH"><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togEM').click()">
        <span class="tog-lbl"><span class="dsw" style="border-color:#3b82f6"></span>Mid  230 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togEM"><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togEL').click()">
        <span class="tog-lbl"><span class="dsw" style="border-color:#06b6d4"></span>Sub  115+ kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togEL"><span class="tr"></span><span class="th"></span></label>
      </div>
    </div>
  </details>

  <!-- -- Nodes -- -->
  <details open>
    <summary>Nodes</summary>
    <div class="s-body">

      <div class="sub-lbl">Voltage tier</div>
      <div class="tog" onclick="document.getElementById('togNH').click()">
        <span class="tog-lbl"><span class="dot" style="background:#a855f7"></span>High  >= 345 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togNH" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togNM').click()">
        <span class="tog-lbl"><span class="dot" style="background:#3b82f6"></span>Mid  230 kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togNM" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togNL').click()">
        <span class="tog-lbl"><span class="dot" style="background:#06b6d4"></span>Sub  115+ kV</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togNL" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div class="tog" onclick="document.getElementById('togSP').click()">
        <span class="tog-lbl"><span class="dot" style="background:#475569"></span>Split points</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togSP"><span class="tr"></span><span class="th"></span></label>
      </div>
    </div>
  </details>

  <!-- -- Map -- -->
  <details open>
    <summary>Map</summary>
    <div class="s-body">
      <div class="tog" onclick="document.getElementById('togZones').click()">
        <span class="tog-lbl"><span class="bsw" style="border-color:#94a3b8"></span>NYISO zones</span>
        <label class="sw" onclick="event.stopPropagation()"><input type="checkbox" id="togZones" checked><span class="tr"></span><span class="th"></span></label>
      </div>
      <div style="margin-top:9px;display:grid;grid-template-columns:1fr 1fr;gap:4px 8px;font-size:12px;color:#64748b">
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#f87171"></span>A West</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#fb923c"></span>B Genesee</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#fbbf24"></span>C Central</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#34d399"></span>D North</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#4ade80"></span>E Mohawk V.</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#60a5fa"></span>F Capital</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#a78bfa"></span>G Hud. Val.</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#f472b6"></span>J NYC</span>
        <span style="display:flex;align-items:center;gap:5px"><span class="dot" style="background:#38bdf8"></span>K Long Isl.</span>
      </div>
    </div>
  </details>

  <!-- -- Information -- -->
  <details>
    <summary>Information</summary>
    <div class="s-body" style="font-size:11px; line-height:1.75; color:#94a3b8;">
      <p style="margin:0 0 8px;">NYISO transmission grid map built from OpenStreetMap data. Shows substations and transmission lines >= 115 kV within NYISO territory.</p>
      <div class="sub-lbl" style="margin-top:4px;">Voltage tiers</div>
      <p style="margin:0 0 8px;"><span style="color:#a855f7">High</span> = 345+ kV (EHV backbone). <span style="color:#3b82f6">Mid</span> = 200-344 kV (mostly 230 kV). <span style="color:#06b6d4">Sub</span> = 115-199 kV (sub-transmission).</p>
      <div class="sub-lbl" style="margin-top:4px;">Lines &amp; graph</div>
      <p style="margin:0;">Solid lines are OSM HV transmission geometry >= 115 kV. Dashed lines are inferred bus-to-bus connectivity from endpoint clustering.</p>
    </div>
  </details>

  <!-- -- Tools -- -->
  <details>
    <summary>Tools</summary>
    <div class="s-body">
      <button class="tbtn" onclick="zoomToNYISO()">Zoom to NYISO</button>
      <button class="tbtn" id="btnIso" onclick="toggleIsolated()">Show isolated nodes only</button>
    </div>
  </details>
</div>

<div id="statsbar">
  <span><span class="sn" id="st-nodes">-</span> subs</span>
  <span><span class="sn" id="st-lines">-</span> lines</span>
  <span><span class="sn" id="st-edges">-</span> graph edges</span>
</div>

<script>
// ============================================================
// Data
// ============================================================
const NODES      = __NODES__;
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
const KV_COLOR = kv => {
  if (kv >= 345) return '#a855f7';
  if (kv >= 200) return '#3b82f6';
  return '#06b6d4';
};

const NYISO_BOUNDS = [[40.4, -80.0], [45.1, -71.8]];

// Zone colors by letter
const ZONE_COLOR = {
  A: '#f87171', B: '#fb923c', C: '#fbbf24', D: '#34d399',
  E: '#4ade80', F: '#60a5fa', G: '#a78bfa', J: '#f472b6', K: '#38bdf8',
};

// ============================================================
// Map & renderer
// ============================================================
const map = L.map('map', { center: [42.5,-75.5], zoom: 7, zoomControl: false, preferCanvas: true });
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  { attribution: 'OpenStreetMap contributors, CARTO', subdomains: 'abcd', maxZoom: 19 }
).addTo(map);
L.control.zoom({ position: 'topleft' }).addTo(map);
const renderer = L.canvas({ padding: 0.5 });

// ============================================================
// Layer groups
// ============================================================
const layerZones     = L.layerGroup().addTo(map);
// Nodes -- by voltage tier
const layerNHigh      = L.layerGroup().addTo(map);
const layerNMidHi     = L.layerGroup().addTo(map);
const layerNMidLo     = L.layerGroup().addTo(map);
const layerSplits     = L.layerGroup();             // off by default
// Lines -- by voltage tier (high on, mid-hi/mid-lo off -- too dense)
const layerLinesHigh  = L.layerGroup().addTo(map);
const layerLinesMidHi = L.layerGroup();
const layerLinesMidLo = L.layerGroup();
// Simplified graph edges -- all off by default
const layerEdgesHigh  = L.layerGroup();
const layerEdgesMidHi = L.layerGroup();
const layerEdgesMidLo = L.layerGroup();

// ============================================================
// Zone boundaries
// ============================================================
L.geoJSON(ZONES, {
  style: f => {
    const c = f.properties.color || '#94a3b8';
    return { color: c, weight: 1.5, opacity: 0.65, fillColor: c, fillOpacity: 0.05, dashArray: '6 4' };
  },
  onEachFeature: (f, l) => {
    const letter = f.properties.zone_letter || '';
    const name = f.properties.zone_name || '';
    const label = letter ? `${letter} ${name}` : name;
    if (label) l.bindTooltip(label, { permanent: true, direction: 'center', className: 'zone-label', interactive: false });
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
function nodeColor(n) {
  return KV_COLOR(n.kv);
}
function nodeStyle(n) {
  if (n.split) {
    return { renderer, radius: 2, fillColor: KV_COLOR(n.kv), color: 'rgba(0,0,0,0)', weight: 0, fillOpacity: 0.45, opacity: 0 };
  }
  const col = nodeColor(n);
  return { renderer, radius: nodeRadius(n.kv), fillColor: col,
           color: 'rgba(0,0,0,0.3)', weight: 0.7, fillOpacity: 0.75, opacity: 0.9 };
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
let isoOnly = false;

// Pre-compute which nodes have at least one graph edge
const connectedSet = new Set();
for (const e of [...EDGES_HIGH, ...EDGES_MID_HI, ...EDGES_MID_LO]) {
  connectedSet.add(e.a);
  connectedSet.add(e.b);
}

function applyNodeFilters() {
  for (const {m, n} of allMarkers) {
    const hidden = isoOnly && connectedSet.has(n.i);
    m.setStyle({
      fillOpacity: hidden ? 0 : 0.75,
      opacity:     hidden ? 0 : 0.9,
    });
  }
}

// ============================================================
// Popup builder
// ============================================================
function kvTierLabel(kv) {
  if (kv >= 345) return 'high';
  if (kv >= 200) return 'mid';
  return 'low';
}

function makePopup(n) {
  let rows = '';
  const add = (k, v) => { if (v) rows += `<span class="mk">${k}</span><span class="mv">${v}</span>`; };
  add('Voltage', n.kv ? `${n.kv} kV` : '');
  if (n.zone) add('Zone', n.zone);
  if (n.op)   add('Operator', n.op);
  if (n.stype) add('Type', n.stype);
  const disp = n.name || `OSM ${n.id}`;
  const tier = kvTierLabel(n.kv);
  return `<div class="pi">
    <div class="pid">OSM ${n.id}</div>
    <div class="pnm">${disp}</div>
    <div class="pbg bg-${tier}">${n.kv} kV</div>
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
    if (n.name) {
      m.on('mouseover', function() {
        const parts = [n.name, `${n.kv} kV`];
        if (n.zone) parts.push(`Zone ${n.zone}`);
        this.bindTooltip(parts.join('  |  '), { sticky: true, className: 'lmp-tip' }).openTooltip();
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

// ============================================================
// Toggle wiring -- Lines
// ============================================================
document.getElementById('togLH').addEventListener('change', e => setLayer(layerLinesHigh,  e.target.checked));
document.getElementById('togLM').addEventListener('change', e => setLayer(layerLinesMidHi, e.target.checked));
document.getElementById('togLL').addEventListener('change', e => setLayer(layerLinesMidLo, e.target.checked));

// ============================================================
// Toggle wiring -- Simplified graph
// ============================================================
document.getElementById('togEH').addEventListener('change', e => setLayer(layerEdgesHigh,  e.target.checked));
document.getElementById('togEM').addEventListener('change', e => setLayer(layerEdgesMidHi, e.target.checked));
document.getElementById('togEL').addEventListener('change', e => setLayer(layerEdgesMidLo, e.target.checked));

// ============================================================
// Toggle wiring -- Node voltage tiers
// ============================================================
document.getElementById('togNH').addEventListener('change', e => setLayer(layerNHigh,   e.target.checked));
document.getElementById('togNM').addEventListener('change', e => setLayer(layerNMidHi,  e.target.checked));
document.getElementById('togNL').addEventListener('change', e => setLayer(layerNMidLo,  e.target.checked));
document.getElementById('togSP').addEventListener('change', e => setLayer(layerSplits,  e.target.checked));

// ============================================================
// Map elements
// ============================================================
document.getElementById('togZones').addEventListener('change', e => setLayer(layerZones, e.target.checked));

// ============================================================
// Tools
// ============================================================
function zoomToNYISO() {
  map.fitBounds(NYISO_BOUNDS, { padding: [20, 20] });
}

function toggleIsolated() {
  isoOnly = !isoOnly;
  const btn = document.getElementById('btnIso');
  btn.textContent = isoOnly ? 'Show all nodes' : 'Show isolated nodes only';
  btn.classList.toggle('active', isoOnly);
  applyNodeFilters();
}

// ============================================================
// Stats bar
// ============================================================
const substations = NODES.filter(n => !n.split);
const splits      = NODES.filter(n =>  n.split);
const totalLines  = LINES_HIGH.length + LINES_MID_HI.length + LINES_MID_LO.length;
const totalEdges  = EDGES_HIGH.length + EDGES_MID_HI.length + EDGES_MID_LO.length;

document.getElementById('st-nodes').textContent = substations.length.toLocaleString();
document.getElementById('st-lines').textContent = totalLines.toLocaleString();
document.getElementById('st-edges').textContent = totalEdges.toLocaleString();
document.getElementById('subtitle').textContent =
  `${substations.length.toLocaleString()} subs + ${splits.length.toLocaleString()} split pts`;

</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading NYISO zone boundaries...")
    zone_features, nyiso_union = load_zones()

    print("Loading HV line features...")
    features = load_line_features(nyiso_union)

    print("Building line endpoint grid...")
    ep_grid = build_ep_grid(features)

    print("Loading OSM substations...")
    nodes = load_nodes(ep_grid, nyiso_union)
    print(f"  {len(nodes)} nodes loaded")

    print("Assigning zones to nodes...")
    assign_zones(nodes, zone_features)

    print("Processing lines and building graph edges...")
    lines_high, lines_mid_hi, lines_mid_lo, edges, split_nodes = process_lines(features, nodes)

    # Split edges by voltage tier for per-tier simplified graph toggles
    edges_high   = [e for e in edges if e['kv'] >= 345]
    edges_mid_hi = [e for e in edges if 200 <= e['kv'] < 345]
    edges_mid_lo = [e for e in edges if 115 <= e['kv'] < 200]

    print("Serialising data...")
    all_node_dicts = (
        [{'i': n['i'], 'lat': n['lat'], 'lon': n['lon'],
          'id': n['id'], 'name': n['name'], 'kv': n['kv'],
          'is_split': False, 'zone': n.get('zone', ''),
          'op': n['op'], 'stype': n['stype']}
         for n in nodes]
    )
    all_node_dicts = list(all_node_dicts) + [
        {'i': sn['i'], 'lat': sn['lat'], 'lon': sn['lon'],
         'id': '', 'name': '', 'kv': sn['kv'],
         'is_split': True, 'split': True}
        for sn in split_nodes
    ]
    nodes_js         = json.dumps(all_node_dicts,   separators=(',', ':'))
    lines_high_js    = json.dumps(lines_high,        separators=(',', ':'))
    lines_mid_hi_js  = json.dumps(lines_mid_hi,      separators=(',', ':'))
    lines_mid_lo_js  = json.dumps(lines_mid_lo,      separators=(',', ':'))
    edges_high_js    = json.dumps(edges_high,         separators=(',', ':'))
    edges_mid_hi_js  = json.dumps(edges_mid_hi,       separators=(',', ':'))
    edges_mid_lo_js  = json.dumps(edges_mid_lo,       separators=(',', ':'))

    # Annotate zones with display colour and embed
    for feat in zone_features:
        letter = feat['properties'].get('zone_letter', '')
        feat['properties']['color'] = ZONE_COLORS.get(letter, '#94a3b8')
    zones_js = json.dumps({'type': 'FeatureCollection', 'features': zone_features},
                          separators=(',', ':'))

    print(f"  Nodes: {len(nodes_js)//1024} KB  "
          f"Lines H/MH/ML: {len(lines_high_js)//1024}/{len(lines_mid_hi_js)//1024}/{len(lines_mid_lo_js)//1024} KB  "
          f"Edges H/MH/ML: {len(edges_high_js)//1024}/{len(edges_mid_hi_js)//1024}/{len(edges_mid_lo_js)//1024} KB")

    html = HTML_TEMPLATE
    html = html.replace('__NODES__',        nodes_js)
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
    print(f"Substations: {len(nodes)}, Split nodes: {len(split_nodes)}, Edges: {len(edges)}  (HV snap 0.45 km)")
    print("Done.")


if __name__ == '__main__':
    main()
