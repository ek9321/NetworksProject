#!/usr/bin/env python3
"""
Dartboard SCED Diagnostic Engine
=================================

Self-contained diagnostic tool for ERCOT SCED experiment results.
Generates a single HTML file with two views:

  MAP        Leaflet map showing all buses (LMP-colored), all lines (utilization),
             zone labels, shedding buses, binding lines. Dropdown to switch experiments.

  SCORECARD  Comparison table of loaded experiments: shed, curtailment, price,
             zone ordering, binding counts. Hourly sparklines for key metrics.

Terminal commands:
  python build_diagnostics.py build                    # 5 most recent, hour 12
  python build_diagnostics.py build --tags A B C       # specific experiments
  python build_diagnostics.py build --hour 14 -n 3     # hour 14, 3 experiments
  python build_diagnostics.py list                     # show all available experiments
  python build_diagnostics.py list --detail            # include per-experiment stats
  python build_diagnostics.py compare                  # terminal comparison table (all)
  python build_diagnostics.py compare --tags A B C     # compare specific experiments

Typical workflow:
  1. Run experiments on adroit, pull results to results/<tag>/
  2. `python build_diagnostics.py list` to see what's available
  3. `python build_diagnostics.py build --tags val-aug20 val-jul23 val-apr13 v3-j17-t135f-r15 v3-nov5`
  4. Open diagnostics.html in browser — use Map tab for geographic view, Scorecard for comparison
  5. To swap an experiment: re-run step 3 with different tags
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
GRID_VIZ = Path(__file__).parent.parent / "grid_visualizer_v3.html"
OUT_PATH = Path(__file__).parent.parent / "diagnostics.html"


# ============================================================
# Data loading
# ============================================================

def extract_topology():
    """Extract bus and line topology from grid_visualizer_v3.html (NODES + SCED_BRANCHES)."""
    if not GRID_VIZ.exists():
        print(f"ERROR: {GRID_VIZ} not found.")
        sys.exit(1)

    print(f"Extracting topology from {GRID_VIZ.name}...")
    html = GRID_VIZ.read_text()

    m_nodes = re.search(r'const NODES\s*=\s*(\[.*?\]);', html, re.DOTALL)
    m_branches = re.search(r'const SCED_BRANCHES\s*=\s*(\[.*?\]);', html, re.DOTALL)
    if not m_nodes or not m_branches:
        print("ERROR: Cannot find NODES or SCED_BRANCHES in grid_visualizer_v3.html")
        sys.exit(1)

    nodes = json.loads(m_nodes.group(1))
    branches = json.loads(m_branches.group(1))

    # Reproduce the same sanitize + unique_name logic as build_osm_bus_table.py
    # so keys match the Bus column in bus_detail.csv exactly.
    def _sanitize(raw, idx):
        if not raw:
            return f"OSM_{idx}"
        cleaned = re.sub(r"[^A-Za-z0-9_]", "_", raw.strip())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned[:48] or f"OSM_{idx}"

    _used = {}
    def _unique(raw, idx):
        base = _sanitize(raw, idx)
        if base not in _used:
            _used[base] = idx
            return base
        return f"{base}_{idx}"

    # bus_by_name: keyed by sanitized unique name (matches Bus column in bus_detail.csv)
    bus_by_name = {}
    for n in sorted(nodes, key=lambda x: x['i']):
        key = _unique(n.get('name', ''), n['i'])
        bus_by_name[key] = {
            'id': n['i'],
            'lat': n['lat'],
            'lng': n['lon'],
            'zone': n.get('lz', '?'),
            'split': n.get('split', False),
        }

    # line_by_uid: keyed by uid (matches Line column in line_detail.csv)
    line_by_uid = {
        b['uid']: {
            'uid': b['uid'],
            'lat1': b['lat1'], 'lng1': b['lng1'],
            'lat2': b['lat2'], 'lng2': b['lng2'],
            'rating': b['r'],
        }
        for b in branches
    }

    print(f"  {len(bus_by_name)} buses, {len(line_by_uid)} lines")
    return bus_by_name, line_by_uid


def load_hourly_summary(tag):
    """Load all rows from hourly_summary.csv. Returns list of dicts with float values."""
    path = RESULTS_DIR / tag / "hourly_summary.csv"
    if not path.exists():
        return []
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            rows.append({
                k: (float(v) if k != "Date" else v)
                for k, v in row.items()
            })
    return rows


def load_zone_lmps_per_hour(tag, bus_zone):
    """Load per-hour zone median LMPs from bus_detail.csv.

    Returns {hour: {zone: median_lmp}} and the W<N hours count.
    """
    path = RESULTS_DIR / tag / "bus_detail.csv"
    if not path.exists():
        return {}, 0

    zone_lmps = defaultdict(lambda: defaultdict(list))
    with open(path) as f:
        for r in csv.DictReader(f):
            z = bus_zone.get(r['Bus'])
            if z:
                zone_lmps[int(r['Hour'])][z].append(float(r['LMP']))

    result = {}
    wn_hours = 0
    for hr in sorted(zone_lmps.keys()):
        hz = {}
        for zone, vals in zone_lmps[hr].items():
            s = sorted(vals)
            mid = len(s) // 2
            hz[zone] = round((s[mid] + s[mid - 1]) / 2, 2) if len(s) % 2 == 0 else round(s[mid], 2)
        result[hr] = hz
        w = hz.get('WEST', 999)
        n = hz.get('NORTH', -999)
        if w < n:
            wn_hours += 1

    return result, wn_hours


def discover_experiments(n=None, requested_tags=None):
    """Return experiment tags sorted by recency (most recent first)."""
    if requested_tags:
        valid = [t for t in requested_tags if (RESULTS_DIR / t / 'hourly_summary.csv').exists()]
        missing = [t for t in requested_tags if t not in valid]
        if missing:
            print(f"  WARNING: not found: {', '.join(missing)}")
        return valid

    dirs = []
    for d in RESULTS_DIR.iterdir():
        if d.is_dir() and (d / 'hourly_summary.csv').exists():
            dirs.append((d.stat().st_mtime, d.name))
    dirs.sort(reverse=True)
    tags = [name for _, name in dirs]
    return tags[:n] if n else tags


def summarize_experiment(rows, wn_hours=None):
    """Compute summary stats from hourly_summary rows."""
    n = len(rows)
    if n == 0:
        return None
    steady = [r for r in rows if r["Hour"] >= 9]
    avail = sum(r["RenewablesAvailable"] for r in rows)
    return {
        "date": rows[0].get("Date", "?"),
        "hours": n,
        "h0_shed": round(rows[0]["LoadShedding"], 1),
        "ss_shed": round(sum(r["LoadShedding"] for r in steady) / max(len(steady), 1), 1),
        "avg_shed": round(sum(r["LoadShedding"] for r in rows) / n, 1),
        "max_shed": round(max(r["LoadShedding"] for r in rows), 1),
        "shed_hours": sum(1 for r in rows if r["LoadShedding"] > 0.1),
        "avg_curt": round(sum(r["RenewablesCurtailment"] for r in rows) / n, 1),
        "renew_pct": round(100 * sum(r["RenewablesUsed"] for r in rows) / avail, 1) if avail else 0,
        "avg_price": round(sum(r["Price"] for r in rows) / n, 2),
        "min_price": round(min(r["Price"] for r in rows), 2),
        "max_price": round(max(r["Price"] for r in rows), 2),
        "demand": round(rows[0]["Demand"], 0),
        "wn_hours": wn_hours,
    }


# ============================================================
# Map snapshot builder (one experiment, one hour)
# ============================================================

def build_snapshot(tag, hour, bus_by_name, line_by_uid):
    """Build full BUSES + LINES + zone stats + summary for one experiment at one hour."""
    rpath = RESULTS_DIR / tag

    # Load LMPs + demand
    bus_data = {}
    with open(rpath / 'bus_detail.csv') as f:
        for r in csv.DictReader(f):
            if int(r['Hour']) == hour:
                bus_data[r['Bus']] = {
                    'demand': float(r['Demand']),
                    'lmp': float(r['LMP']),
                    'mismatch': float(r['Mismatch']),
                }

    # Load flows
    flows = {}
    with open(rpath / 'line_detail.csv') as f:
        for r in csv.DictReader(f):
            if int(r['Hour']) == hour:
                flows[r['Line']] = float(r['Flow'])

    # Load hour summary
    summary = {}
    with open(rpath / 'hourly_summary.csv') as f:
        for r in csv.DictReader(f):
            if int(r['Hour']) == hour:
                summary = {
                    'demand': float(r['Demand']),
                    'shed': float(r['LoadShedding']),
                    'curtailed': float(r['RenewablesCurtailment']),
                    'price': float(r['Price']),
                    'date': r['Date'],
                }
                break

    # Build BUSES array
    buses_out = []
    for name, topo in bus_by_name.items():
        bd = bus_data.get(name)
        if not bd:
            continue
        buses_out.append({
            'id': topo['id'], 'name': name,
            'lat': topo['lat'], 'lng': topo['lng'],
            'zone': topo.get('zone', '?'),
            'demand': round(bd['demand'], 1),
            'lmp': round(bd['lmp'], 2),
            'shedding': bd['mismatch'] > 0.1,
            'split': topo.get('split', False),
        })

    # Build LINES array
    lines_out = []
    n_binding = n_stressed = 0
    for uid, topo in line_by_uid.items():
        flow = flows.get(uid, 0.0)
        rating = topo['rating']
        util = abs(flow) / rating if rating > 0 else 0
        binding = (util >= 0.95 and rating < 999000)
        if binding:
            n_binding += 1
        if 0.50 < util < 0.95 and rating < 999000:
            n_stressed += 1
        lines_out.append({
            'uid': uid,
            'lat1': topo['lat1'], 'lng1': topo['lng1'],
            'lat2': topo['lat2'], 'lng2': topo['lng2'],
            'flow': round(flow, 1),
            'rating': round(rating, 1),
            'util': round(util, 4),
            'binding': binding,
        })

    # Zone LMP stats
    zone_lmps = defaultdict(list)
    for b in buses_out:
        zone_lmps[b['zone']].append(b['lmp'])
    zone_stats = {}
    for zone, vals in zone_lmps.items():
        s = sorted(vals)
        n = len(s)
        zone_stats[zone] = {
            'avg': round(sum(vals) / n, 1), 'med': round(s[n // 2], 1),
            'min': round(s[0], 1), 'max': round(s[-1], 1), 'n': n,
        }

    return {
        'buses': buses_out, 'lines': lines_out, 'zones': zone_stats,
        'summary': summary,
        'counts': {
            'binding': n_binding, 'stressed': n_stressed,
            'shedding': sum(1 for b in buses_out if b['shedding']),
        },
    }


# ============================================================
# HTML generation
# ============================================================

def build_html(snapshots, stats_data, hour):
    """Generate self-contained HTML with Map + Scorecard tabs."""
    tags = list(snapshots.keys())
    options = '\n'.join(f'<option value="{t}">{t}</option>' for t in tags)

    # Embed map data
    map_blocks = []
    for tag, snap in snapshots.items():
        map_blocks.append(
            f'MAP_DATA["{tag}"] = {{\n'
            f'  BUSES: {json.dumps(snap["buses"], separators=(",",":"))},\n'
            f'  LINES: {json.dumps(snap["lines"], separators=(",",":"))},\n'
            f'  zones: {json.dumps(snap["zones"], separators=(",",":"))},\n'
            f'  summary: {json.dumps(snap["summary"], separators=(",",":"))},\n'
            f'  counts: {json.dumps(snap["counts"], separators=(",",":"))}\n'
            f'}};'
        )
    map_data_js = '\n'.join(map_blocks)

    # Embed stats data (small — hourly arrays + summaries + zone LMPs)
    stats_js = json.dumps(stats_data, separators=(',', ':'))

    return f"""<!DOCTYPE html>
<html><head>
<title>Dartboard SCED Diagnostics</title>
<meta charset="utf-8"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; }}

/* --- Tabs --- */
#tab-bar {{ display:flex; background:#0f1923; border-bottom:2px solid #333; padding:0 16px; }}
.tab-btn {{ padding:10px 24px; cursor:pointer; color:#888; font-size:14px; font-weight:600;
  border:none; background:none; border-bottom:3px solid transparent; }}
.tab-btn:hover {{ color:#ccc; }}
.tab-btn.active {{ color:#64ffda; border-bottom-color:#64ffda; }}
.tab-content {{ display:none; }}
.tab-content.active {{ display:block; }}

/* --- Map tab --- */
#map {{ width:100%; height:calc(100vh - 44px); background:#1a1a2e; }}
.info {{ padding:8px 12px; background:rgba(0,0,0,0.85); color:#eee; border-radius:5px; font:13px monospace; max-width:420px; }}
.info h4 {{ margin:0 0 5px; color:#fff; }}
.legend i {{ width:14px; height:14px; float:left; margin-right:6px; opacity:0.8; display:inline-block; }}
#picker {{ position:absolute; top:54px; left:60px; z-index:1000; background:rgba(0,0,0,0.85);
  padding:10px 14px; border-radius:6px; font:14px monospace; color:#eee; }}
#picker select {{ background:#16213e; color:#e0e0e0; border:1px solid #555; padding:4px 8px;
  border-radius:4px; font:13px monospace; margin-left:6px; }}

/* --- Scorecard tab --- */
#scorecard {{ padding: 20px 24px; max-width: 1400px; }}
#scorecard h2 {{ color:#64ffda; margin:20px 0 10px; font-size:16px; }}
table.sc {{ border-collapse:collapse; width:100%; margin:8px 0; background:#0f1923; }}
table.sc th, table.sc td {{ border:1px solid #333; padding:5px 8px; font-size:12px; text-align:right; }}
table.sc th {{ background:#0f3460; color:#64ffda; position:sticky; top:0; text-align:center; }}
table.sc td:first-child {{ text-align:left; font-weight:bold; }}
table.sc tr:hover {{ background:#1a3a5c; }}
.good {{ background:#1b5e20 !important; color:#a5d6a7; }}
.warn {{ background:#e65100 !important; color:#ffcc80; }}
.bad {{ background:#b71c1c !important; color:#ef9a9a; }}
.spark {{ display:inline-block; vertical-align:middle; }}
.zone-pill {{ display:inline-block; padding:2px 6px; border-radius:3px; font-size:11px; margin:1px; }}

/* --- Hourly detail --- */
.hourly-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(600px, 1fr)); gap:16px; }}
.chart-box {{ background:#0f1923; border-radius:8px; padding:12px 16px; }}
.chart-box h3 {{ color:#bb86fc; margin:0 0 8px; font-size:13px; }}
svg.sparkline {{ width:100%; }}
.legend-row {{ display:flex; gap:16px; flex-wrap:wrap; margin:8px 0; font-size:11px; }}
.legend-dot {{ display:inline-block; width:10px; height:3px; border-radius:1px; margin-right:4px; vertical-align:middle; }}
</style>
</head><body>

<!-- Tab bar -->
<div id="tab-bar">
  <button class="tab-btn active" onclick="switchTab('map')">Map</button>
  <button class="tab-btn" onclick="switchTab('scorecard')">Scorecard</button>
</div>

<!-- Map tab -->
<div id="tab-map" class="tab-content active">
  <div id="picker">
    <label>Experiment:
      <select id="exp-select" onchange="switchExperiment()">
        {options}
      </select>
    </label>
  </div>
  <div id="map"></div>
</div>

<!-- Scorecard tab -->
<div id="tab-scorecard" class="tab-content">
  <div id="scorecard"></div>
</div>

<script>
// ============================================================
// Embedded data
// ============================================================
const MAP_DATA = {{}};
{map_data_js}

const STATS = {stats_js};
const HOUR = {hour};

// ============================================================
// Tab switching
// ============================================================
function switchTab(name) {{
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
  if (name === 'map') {{ map.invalidateSize(); }}
  if (name === 'scorecard') {{ buildScorecard(); }}
}}

// ============================================================
// Map
// ============================================================
const map = L.map('map').setView([31.5, -99.0], 6);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '&copy; OSM &copy; CARTO', maxZoom: 18
}}).addTo(map);

let normalLines, bindingLines, sheddingBuses, loadBuses, allBuses, zoneLabels;
let layerControl = null, legendControl = null;

function lmpColor(lmp) {{
  if (lmp > 500) return "#ff0000";
  if (lmp > 50) return "#ff4444";
  if (lmp > 30) return "#ff8800";
  if (lmp > 20) return "#ffcc00";
  if (lmp > 10) return "#44cc44";
  if (lmp > 0) return "#2288ff";
  return "#9944ff";
}}

function flowArrow(lat1, lng1, lat2, lng2, flow, color, layer) {{
  if (Math.abs(flow) < 1) return;
  let fLat=lat1, fLng=lng1, tLat=lat2, tLng=lng2;
  if (flow < 0) {{ fLat=lat2; fLng=lng2; tLat=lat1; tLng=lng1; }}
  const midLat = (fLat + tLat) / 2, midLng = (fLng + tLng) / 2;
  const angle = Math.atan2(tLat - fLat, tLng - fLng) * 180 / Math.PI;
  const sz = Math.min(12, Math.max(6, Math.abs(flow) / 200));
  L.marker([midLat, midLng], {{
    icon: L.divIcon({{
      className: '',
      html: '<div style="font-size:'+sz+'px;color:'+color+';transform:rotate('+(-angle)+'deg);opacity:0.8">&#9654;</div>',
      iconSize: [sz, sz], iconAnchor: [sz/2, sz/2],
    }}),
    interactive: false,
  }}).addTo(layer);
}}

function switchExperiment() {{
  const tag = document.getElementById('exp-select').value;
  const d = MAP_DATA[tag];
  if (!d) return;

  // Remove old layers
  [normalLines, bindingLines, sheddingBuses, loadBuses, allBuses, zoneLabels].forEach(l => {{
    if (l) map.removeLayer(l);
  }});
  if (layerControl) map.removeControl(layerControl);
  if (legendControl) map.removeControl(legendControl);

  normalLines = L.layerGroup();
  bindingLines = L.layerGroup();
  sheddingBuses = L.layerGroup();
  loadBuses = L.layerGroup();
  allBuses = L.layerGroup();
  zoneLabels = L.layerGroup();

  // Lines
  d.LINES.forEach(l => {{
    const ll = [[l.lat1, l.lng1], [l.lat2, l.lng2]];
    let color, weight, opacity;
    if (l.rating >= 999000) {{ color="#555"; weight=0.5; opacity=0.2; }}
    else if (l.binding) {{ color="#ff4444"; weight=3; opacity=0.9; }}
    else if (l.util > 0.8) {{ color="#ff8800"; weight=2; opacity=0.8; }}
    else if (l.util > 0.5) {{ color="#ffaa00"; weight=1.5; opacity=0.7; }}
    else if (l.rating >= 2000) {{ color="#4488ff"; weight=1.5; opacity=0.6; }}
    else if (l.rating >= 900) {{ color="#44aaff"; weight=1; opacity=0.5; }}
    else {{ color="#22cccc"; weight=0.6; opacity=0.3; }}
    const tip = l.uid + "<br>Flow: " + l.flow.toFixed(0) + " / " + l.rating + " MVA (" + (l.util*100).toFixed(1) + "%)";
    const line = L.polyline(ll, {{color, weight, opacity}}).bindPopup(tip);
    const tgt = (l.binding || l.util > 0.8) ? bindingLines : normalLines;
    tgt.addLayer(line);
    if (l.util > 0.3) flowArrow(l.lat1, l.lng1, l.lat2, l.lng2, l.flow, color, tgt);
  }});

  // Buses
  d.BUSES.forEach(b => {{
    if (b.shedding) {{
      const r = Math.min(8, Math.max(3, b.demand / 20));
      const tip = "<b>" + b.name + "</b><br>Zone: " + b.zone + "<br>Demand: " + b.demand + " MW<br>LMP: $" + b.lmp + " (SHEDDING)";
      L.circleMarker([b.lat, b.lng], {{radius: r, color: "#ff0000", fillColor: "#ff0000",
        fillOpacity: 0.9, weight: 2}}).bindPopup(tip).addTo(sheddingBuses);
    }} else if (b.demand > 0) {{
      const c = lmpColor(b.lmp);
      const r = Math.min(6, Math.max(2, Math.sqrt(b.demand) / 5));
      const tip = "<b>" + b.name + "</b><br>Zone: " + b.zone + "<br>Demand: " + b.demand + " MW<br>LMP: $" + b.lmp.toFixed(2) + "/MWh";
      L.circleMarker([b.lat, b.lng], {{radius: r, color: c, fillColor: c,
        fillOpacity: 0.8, weight: 1}}).bindPopup(tip).addTo(loadBuses);
    }} else {{
      const c = lmpColor(b.lmp);
      const tip = "<b>" + b.name + "</b><br>Zone: " + b.zone + "<br>LMP: $" + b.lmp.toFixed(2) + "/MWh";
      L.circleMarker([b.lat, b.lng], {{radius: 1.5, color: c, fillColor: c,
        fillOpacity: 0.4, weight: 0.5}}).bindPopup(tip).addTo(allBuses);
    }}
  }});

  // Zone labels
  const zoneCenters = {{"WEST":[31.5,-101.5],"NORTH":[33,-97],"SOUTH":[29,-98],"HOUSTON":[29.8,-95.5]}};
  Object.entries(d.zones).forEach(([z, s]) => {{
    const pos = zoneCenters[z] || [31,-98];
    const icon = L.divIcon({{
      className: "",
      html: '<div style="background:rgba(0,0,0,0.75);color:#eee;padding:6px 10px;border-radius:5px;font:bold 13px monospace;white-space:nowrap;border:1px solid '+lmpColor(s.med)+'">' +
        z+'<br>Med: $'+s.med+'<br>Avg: $'+s.avg+'<br>n='+s.n+'</div>',
      iconSize: [0,0]
    }});
    L.marker(pos, {{icon}}).addTo(zoneLabels);
  }});

  normalLines.addTo(map);
  bindingLines.addTo(map);
  sheddingBuses.addTo(map);
  loadBuses.addTo(map);
  zoneLabels.addTo(map);

  layerControl = L.control.layers(null, {{
    "Normal lines": normalLines,
    "Binding/stressed lines": bindingLines,
    "Shedding buses (red)": sheddingBuses,
    "Load buses (by LMP)": loadBuses,
    "All buses (by LMP)": allBuses,
    "Zone labels": zoneLabels,
  }}, {{collapsed: false}}).addTo(map);

  // Legend
  const sm = d.summary, ct = d.counts;
  const zoneOrder = ["WEST","NORTH","SOUTH","HOUSTON"];
  const zoneStr = zoneOrder.filter(z => d.zones[z]).map(z => z+" $"+d.zones[z].med).join(" &lt; ");

  legendControl = L.control({{position: "bottomright"}});
  legendControl.onAdd = function() {{
    const div = L.DomUtil.create("div", "info legend");
    div.innerHTML = '<h4>'+tag+' &mdash; '+(sm.date||'?')+' h'+HOUR+'</h4>' +
      '<b>'+(sm.demand||0).toLocaleString()+' MW demand &bull; '+(sm.shed||0).toLocaleString()+' MW shed</b><br>' +
      '<b>'+(sm.curtailed||0).toLocaleString()+' MW curtailed &bull; $'+(sm.price||0).toFixed(2)+'/MWh sys</b><br><br>' +
      '<b>Lines:</b><br>' +
      '<i style="background:#ff4444"></i> Binding (&gt;99.99%)<br>' +
      '<i style="background:#ff8800"></i> Near-binding (&gt;80%)<br>' +
      '<i style="background:#ffaa00"></i> Stressed (&gt;50%)<br>' +
      '<i style="background:#4488ff"></i> 345+ kV<br>' +
      '<i style="background:#44aaff"></i> 230 kV<br>' +
      '<i style="background:#22cccc"></i> 138 kV<br>' +
      '<br><b>Buses (LMP):</b><br>' +
      '<i style="background:#ff4444;border-radius:50%"></i> &gt;$50<br>' +
      '<i style="background:#ff8800;border-radius:50%"></i> $30&ndash;50<br>' +
      '<i style="background:#ffcc00;border-radius:50%"></i> $20&ndash;30<br>' +
      '<i style="background:#44cc44;border-radius:50%"></i> $10&ndash;20<br>' +
      '<i style="background:#2288ff;border-radius:50%"></i> $0&ndash;10<br>' +
      '<i style="background:#9944ff;border-radius:50%"></i> Negative<br>' +
      '<br>'+ct.binding+' binding &bull; '+ct.stressed+' stressed &bull; '+ct.shedding+' shedding<br>' +
      zoneStr;
    return div;
  }};
  legendControl.addTo(map);
}}

// Init map
switchExperiment();

// ============================================================
// Scorecard
// ============================================================
const TAG_COLORS = ['#64ffda','#bb86fc','#ff8a65','#4fc3f7','#aed581','#ffb74d','#f48fb1','#80cbc4'];

let scorecardBuilt = false;
function buildScorecard() {{
  if (scorecardBuilt) return;
  scorecardBuilt = true;

  const el = document.getElementById('scorecard');
  const tags = Object.keys(STATS);
  if (tags.length === 0) {{ el.innerHTML = '<p>No stats data.</p>'; return; }}

  let html = '';

  // --- Summary comparison table ---
  html += '<h2>Experiment Comparison</h2>';
  html += '<table class="sc"><tr><th>Experiment</th><th>Date</th><th>Demand<br>MW</th>' +
    '<th>Avg Shed<br>MW</th><th>SS Shed<br>MW</th><th>Max Shed<br>MW</th><th>Shed<br>Hours</th>' +
    '<th>Avg Curt<br>MW</th><th>Renew<br>%</th>' +
    '<th>Avg Price<br>$/MWh</th><th>W&lt;N<br>Hours</th></tr>';

  tags.forEach((tag, i) => {{
    const s = STATS[tag].summary;
    if (!s) return;
    const shedClass = s.avg_shed < 1 ? 'good' : (s.avg_shed < 500 ? 'warn' : 'bad');
    const wnClass = s.wn_hours !== null ? (s.wn_hours >= 18 ? 'good' : (s.wn_hours >= 12 ? 'warn' : 'bad')) : '';
    html += '<tr>' +
      '<td style="color:'+TAG_COLORS[i%TAG_COLORS.length]+'">'+tag+'</td>' +
      '<td>'+s.date+'</td>' +
      '<td>'+fmt(s.demand)+'</td>' +
      '<td class="'+shedClass+'">'+fmt(s.avg_shed)+'</td>' +
      '<td>'+fmt(s.ss_shed)+'</td>' +
      '<td>'+fmt(s.max_shed)+'</td>' +
      '<td>'+(s.shed_hours||0)+'/'+s.hours+'</td>' +
      '<td>'+fmt(s.avg_curt)+'</td>' +
      '<td>'+s.renew_pct+'%</td>' +
      '<td>$'+s.avg_price+'</td>' +
      '<td class="'+wnClass+'">'+(s.wn_hours !== null ? s.wn_hours+'/24' : 'N/A')+'</td>' +
      '</tr>';
  }});
  html += '</table>';

  // --- Zone LMP comparison (at snapshot hour) ---
  html += '<h2>Zone LMPs at Hour '+HOUR+'</h2>';
  html += '<table class="sc"><tr><th>Experiment</th><th>WEST</th><th>NORTH</th><th>SOUTH</th><th>HOUSTON</th><th>W&lt;N?</th></tr>';
  tags.forEach((tag, i) => {{
    const zl = STATS[tag].zone_lmps || {{}};
    const hr = zl[HOUR] || {{}};
    const w = hr.WEST, n = hr.NORTH, s = hr.SOUTH, h = hr.HOUSTON;
    const wn = (w !== undefined && n !== undefined) ? (w < n ? '<span class="good" style="padding:2px 6px;border-radius:3px">YES</span>' : '<span class="bad" style="padding:2px 6px;border-radius:3px">NO</span>') : '?';
    html += '<tr>' +
      '<td style="color:'+TAG_COLORS[i%TAG_COLORS.length]+'">'+tag+'</td>' +
      '<td style="color:'+lmpColor(w||0)+'">$'+(w !== undefined ? w : '?')+'</td>' +
      '<td style="color:'+lmpColor(n||0)+'">$'+(n !== undefined ? n : '?')+'</td>' +
      '<td style="color:'+lmpColor(s||0)+'">$'+(s !== undefined ? s : '?')+'</td>' +
      '<td style="color:'+lmpColor(h||0)+'">$'+(h !== undefined ? h : '?')+'</td>' +
      '<td>'+wn+'</td></tr>';
  }});
  html += '</table>';

  // --- Hourly sparkline charts ---
  html += '<h2>Hourly Profiles (24h)</h2>';
  html += '<div class="legend-row">';
  tags.forEach((tag, i) => {{
    html += '<span><span class="legend-dot" style="background:'+TAG_COLORS[i%TAG_COLORS.length]+'"></span>'+tag+'</span>';
  }});
  html += '</div>';
  html += '<div class="hourly-grid">';

  const metrics = [
    {{ key: 'LoadShedding', label: 'Load Shedding (MW)', warn: 100 }},
    {{ key: 'Price', label: 'System Price ($/MWh)', warn: null }},
    {{ key: 'RenewablesCurtailment', label: 'Renewables Curtailment (MW)', warn: null }},
    {{ key: 'Demand', label: 'Demand (MW)', warn: null }},
  ];

  metrics.forEach(m => {{
    html += '<div class="chart-box"><h3>'+m.label+'</h3>';
    html += buildSparkSVG(tags, m.key, m.warn);
    html += '</div>';
  }});
  html += '</div>';

  el.innerHTML = html;
}}

function fmt(v) {{
  if (v === null || v === undefined) return '?';
  return v.toLocaleString(undefined, {{maximumFractionDigits:1}});
}}

function buildSparkSVG(tags, metricKey, warnLevel) {{
  // Collect all hourly values across experiments to find y range
  let allVals = [];
  const series = [];
  tags.forEach(tag => {{
    const hourly = STATS[tag].hourly || [];
    const vals = hourly.map(h => h[metricKey] || 0);
    series.push(vals);
    allVals = allVals.concat(vals);
  }});

  if (allVals.length === 0) return '<p>No data</p>';

  const yMin = Math.min(0, ...allVals);
  const yMax = Math.max(1, ...allVals) * 1.05;

  const W = 580, H = 120, padL = 50, padR = 10, padT = 5, padB = 20;
  const plotW = W - padL - padR, plotH = H - padT - padB;

  function x(hr) {{ return padL + (hr / 23) * plotW; }}
  function y(v) {{ return padT + plotH - ((v - yMin) / (yMax - yMin)) * plotH; }}

  let svg = '<svg class="sparkline" viewBox="0 0 '+W+' '+H+'" xmlns="http://www.w3.org/2000/svg">';

  // Grid lines + y-axis labels
  const nTicks = 4;
  for (let i = 0; i <= nTicks; i++) {{
    const v = yMin + (yMax - yMin) * i / nTicks;
    const yy = y(v);
    svg += '<line x1="'+padL+'" y1="'+yy+'" x2="'+(W-padR)+'" y2="'+yy+'" stroke="#333" stroke-width="0.5"/>';
    let label = v >= 1000 ? (v/1000).toFixed(1)+'k' : v.toFixed(v < 10 ? 1 : 0);
    svg += '<text x="'+(padL-4)+'" y="'+(yy+3)+'" text-anchor="end" fill="#888" font-size="9">'+label+'</text>';
  }}

  // X-axis labels
  for (let hr = 0; hr <= 23; hr += 4) {{
    svg += '<text x="'+x(hr)+'" y="'+(H-2)+'" text-anchor="middle" fill="#888" font-size="9">'+hr+'</text>';
  }}

  // Warn level
  if (warnLevel !== null) {{
    const yw = y(warnLevel);
    if (yw > padT && yw < padT + plotH) {{
      svg += '<line x1="'+padL+'" y1="'+yw+'" x2="'+(W-padR)+'" y2="'+yw+'" stroke="#ff4444" stroke-width="0.5" stroke-dasharray="4,3" opacity="0.6"/>';
    }}
  }}

  // Hour marker for snapshot hour
  svg += '<line x1="'+x(HOUR)+'" y1="'+padT+'" x2="'+x(HOUR)+'" y2="'+(padT+plotH)+'" stroke="#64ffda" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.5"/>';

  // Data lines
  series.forEach((vals, i) => {{
    if (vals.length === 0) return;
    const color = TAG_COLORS[i % TAG_COLORS.length];
    let path = 'M';
    vals.forEach((v, hr) => {{
      path += (hr > 0 ? ' L' : '') + x(hr).toFixed(1) + ' ' + y(v).toFixed(1);
    }});
    svg += '<path d="'+path+'" fill="none" stroke="'+color+'" stroke-width="2" opacity="0.85"/>';
  }});

  svg += '</svg>';
  return svg;
}}

</script></body></html>"""


# ============================================================
# CLI commands
# ============================================================

def cmd_build(args):
    """Build the diagnostic HTML."""
    print("Extracting topology from sced_diagnostic.html...")
    bus_by_name, line_by_uid = extract_topology()
    print(f"  {len(bus_by_name)} buses, {len(line_by_uid)} lines")

    tags = discover_experiments(args.n, args.tags)
    if not tags:
        print("No experiments found.")
        return

    # Only keep experiments that have bus_detail.csv (needed for map)
    map_tags = [t for t in tags if (RESULTS_DIR / t / 'bus_detail.csv').exists()]
    if not map_tags:
        print("No experiments with bus_detail.csv found (needed for map).")
        return
    print(f"Loading {len(map_tags)} experiments: {', '.join(map_tags)}")

    # Build bus_zone lookup for zone LMP computation
    bus_zone = {name: b.get('zone', '?') for name, b in bus_by_name.items()}

    # Build map snapshots and stats
    snapshots = {}
    stats_data = {}
    for tag in map_tags:
        print(f"  {tag} (hour {args.hour})...")
        snapshots[tag] = build_snapshot(tag, args.hour, bus_by_name, line_by_uid)

        rows = load_hourly_summary(tag)
        zone_lmps, wn_hours = load_zone_lmps_per_hour(tag, bus_zone)
        summary = summarize_experiment(rows, wn_hours)

        stats_data[tag] = {
            'summary': summary,
            'hourly': [{k: v for k, v in r.items() if k != 'Date'} for r in rows],
            'zone_lmps': {str(k): v for k, v in zone_lmps.items()},
        }

    html = build_html(snapshots, stats_data, args.hour)

    with open(OUT_PATH, 'w') as f:
        f.write(html)
    print(f"\nWrote {OUT_PATH} ({len(html)//1024} KB)")
    print(f"Open in browser: file://{OUT_PATH.resolve()}")


def cmd_list(args):
    """List all available experiments."""
    all_tags = discover_experiments()
    if not all_tags:
        print("No experiments found in results/")
        return

    if args.detail:
        # Load summaries for all
        bus_zone = {}
        try:
            bus_by_name, _ = extract_topology()
            bus_zone = {name: b.get('zone', '?') for name, b in bus_by_name.items()}
        except SystemExit:
            pass

        header = f"{'tag':<28} {'date':>10} {'demand':>8} {'avg_shed':>9} {'ss_shed':>9} {'curt':>8} {'price':>8} {'W<N':>5}"
        print(header)
        print("-" * len(header))
        for tag in all_tags:
            rows = load_hourly_summary(tag)
            if not rows:
                continue
            _, wn = load_zone_lmps_per_hour(tag, bus_zone) if bus_zone else ({}, None)
            s = summarize_experiment(rows, wn)
            if not s:
                continue
            wn_str = f"{s['wn_hours']}/24" if s['wn_hours'] is not None else "  ?"
            print(
                f"{tag:<28} {s['date']:>10} {s['demand']:>8,.0f} "
                f"{s['avg_shed']:>9,.1f} {s['ss_shed']:>9,.1f} "
                f"{s['avg_curt']:>8,.0f} ${s['avg_price']:>7.2f} {wn_str:>5}"
            )
    else:
        # Quick list with dates
        for tag in all_tags:
            rows = load_hourly_summary(tag)
            date = rows[0].get('Date', '?') if rows else '?'
            has_bus = (RESULTS_DIR / tag / 'bus_detail.csv').exists()
            marker = " " if has_bus else "*"
            print(f"  {marker} {tag:<28} {date}")
        print(f"\n  {len(all_tags)} experiments (* = no bus_detail.csv, map unavailable)")


def cmd_compare(args):
    """Print terminal comparison table (like compare.py)."""
    tags = discover_experiments(requested_tags=args.tags)
    if not tags:
        print("No experiments found.")
        return

    bus_zone = {}
    try:
        bus_by_name, _ = extract_topology()
        bus_zone = {name: b.get('zone', '?') for name, b in bus_by_name.items()}
    except SystemExit:
        pass

    summaries = []
    for tag in tags:
        rows = load_hourly_summary(tag)
        if not rows:
            continue
        _, wn = load_zone_lmps_per_hour(tag, bus_zone) if bus_zone else ({}, None)
        s = summarize_experiment(rows, wn)
        if s:
            summaries.append((tag, s))

    # Sort by avg shed
    summaries.sort(key=lambda x: x[1]['avg_shed'])

    header = f"{'tag':<28} {'date':>10} {'avg_shed':>9} {'ss_shed':>9} {'max_shed':>9} {'curt':>8} {'price':>8} {'W<N':>5}"
    print(header)
    print("-" * len(header))
    for tag, s in summaries:
        wn_str = f"{s['wn_hours']}/24" if s['wn_hours'] is not None else "  ?"
        print(
            f"{tag:<28} {s['date']:>10} "
            f"{s['avg_shed']:>9,.1f} {s['ss_shed']:>9,.1f} {s['max_shed']:>9,.1f} "
            f"{s['avg_curt']:>8,.0f} ${s['avg_price']:>7.2f} {wn_str:>5}"
        )
    print(f"\n{len(summaries)} experiments (sorted by avg shed)")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Dartboard SCED Diagnostic Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build_diagnostics.py list                         # see all experiments
  python build_diagnostics.py list --detail                # with summary stats
  python build_diagnostics.py compare                      # terminal table, all experiments
  python build_diagnostics.py compare --tags v3-nov5 v3-jan08
  python build_diagnostics.py build                        # 5 most recent → diagnostics.html
  python build_diagnostics.py build --tags A B C D E       # specific experiments
  python build_diagnostics.py build --hour 14 -n 3         # hour 14, 3 experiments
""")
    sub = parser.add_subparsers(dest='command')

    # build
    p_build = sub.add_parser('build', help='Build diagnostics.html')
    p_build.add_argument('--tags', nargs='+', help='Experiment tags to load (default: 5 most recent)')
    p_build.add_argument('--hour', type=int, default=12, help='Map snapshot hour (default: 12)')
    p_build.add_argument('-n', type=int, default=5, help='Number of most recent experiments (default: 5)')

    # list
    p_list = sub.add_parser('list', help='List available experiments')
    p_list.add_argument('--detail', action='store_true', help='Show summary stats for each')

    # compare
    p_compare = sub.add_parser('compare', help='Print comparison table to terminal')
    p_compare.add_argument('--tags', nargs='+', help='Specific experiments to compare (default: all)')

    args = parser.parse_args()

    if args.command == 'build':
        cmd_build(args)
    elif args.command == 'list':
        cmd_list(args)
    elif args.command == 'compare':
        cmd_compare(args)
    else:
        # Default: build (backward compat)
        args.tags = None
        args.hour = 12
        args.n = 5
        cmd_build(args)


if __name__ == "__main__":
    main()
