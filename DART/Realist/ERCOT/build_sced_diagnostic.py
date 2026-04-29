#!/usr/bin/env python3
"""
Build sced_diagnostic.html — Interactive Leaflet map of SCED experiment results.

Generates a self-contained HTML file with a dropdown selector to switch between
experiments. Each experiment shows:
  - Bus circles colored by LMP (blue=cheap → red=expensive)
  - Transmission lines colored by utilization (green→orange→red)
  - Shedding buses highlighted in red
  - Binding lines (>95% utilization) highlighted in red
  - Zone labels with median/average LMP
  - Legend with demand, shedding, curtailment, binding count

Usage:
  python build_sced_diagnostic.py TAG1:HOUR:LABEL TAG2:HOUR:LABEL ...

  Each argument is a colon-separated triple:
    TAG    experiment tag (results directory name)
    HOUR   hour of day to snapshot (0-23)
    LABEL  human-readable label for dropdown

Examples:
  # Quick check of one experiment
  python build_sced_diagnostic.py v3-j17-t135f-r15:14:"Jun 17 — SOLVED"

  # Compare baseline vs upgrade on Aug 20
  python build_sced_diagnostic.py \
    upgr-aug20-t175:17:"Aug 20 T175 (90% shed reduction)" \
    val-aug20:17:"Aug 20 baseline (1,099 MW shed)" \
    v3-j17-t135f-r15:14:"Jun 17 reference (0 shed)"

  # Full validation suite
  python build_sced_diagnostic.py \
    upgr-aug20-t175:17:"Aug 20 T175" \
    v3-j17-t135f-r15:14:"Jun 17 SOLVED" \
    val-mar29:12:"Mar 29 high wind" \
    val-jul23:15:"Jul 23 low wind"

Output:
  Realist/sced_diagnostic.html (~1.3 MB per experiment)

Topology source:
  Bus coordinates and line geometry come from the FIRST experiment's bus.csv
  and branch.csv in the corresponding sced_inputs directory. If a previous
  sced_diagnostic.html exists, its topology is reused for consistency.

Data requirements (per experiment):
  results/<TAG>/bus_detail.csv     — Bus, Hour, Demand, Mismatch, LMP
  results/<TAG>/line_detail.csv    — Line, Hour, Flow
  results/<TAG>/hourly_summary.csv — Hour, various summary columns
"""

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REALIST = SCRIPT_DIR.parent
RESULTS_DIR = REALIST / "ERCOT_Calibration_Experiments" / "results"
OUT_PATH = REALIST / "sced_diagnostic.html"
EXISTING_DIAG = OUT_PATH  # reuse topology from previous build if available


# ---------------------------------------------------------------------------
# Topology extraction
# ---------------------------------------------------------------------------

def load_topology_from_existing():
    """Extract bus/line topology from an existing sced_diagnostic.html."""
    if not EXISTING_DIAG.exists():
        return None, None

    html = EXISTING_DIAG.read_text()
    m = re.search(r'const EXPERIMENTS = (\{)', html)
    if not m:
        return None, None

    start = m.start(1)
    depth = 0
    for i in range(start, len(html)):
        if html[i] == '{':
            depth += 1
        elif html[i] == '}':
            depth -= 1
        if depth == 0:
            break
    exp_json = html[start:i + 1]

    try:
        experiments = json.loads(exp_json)
    except json.JSONDecodeError:
        return None, None

    first_tag = next(iter(experiments))
    buses = experiments[first_tag]['buses']
    lines = experiments[first_tag]['lines']
    return buses, lines


def load_topology_from_csvs(tag):
    """Build topology from SourceData bus.csv and branch.csv."""
    # Try local results first, then sced_inputs directories
    for base in [RESULTS_DIR / tag, REALIST / "grid_data" / f"sced_inputs_{tag}" / "SourceData",
                 REALIST / "grid_data" / "sced_inputs_v3" / "SourceData",
                 REALIST / "grid_data" / "sced_inputs" / "SourceData"]:
        bus_csv = base / "bus.csv"
        branch_csv = base / "branch.csv"
        if bus_csv.exists() and branch_csv.exists():
            break
    else:
        # Try clean-build results as last resort
        bus_csv = RESULTS_DIR / "clean-build" / "bus.csv"
        branch_csv = RESULTS_DIR / "clean-build" / "branch.csv"

    if not bus_csv.exists() or not branch_csv.exists():
        print(f"ERROR: Cannot find bus.csv/branch.csv for topology.")
        print(f"  Tried: {bus_csv}")
        sys.exit(1)

    bus_df = pd.read_csv(bus_csv, dtype=str)
    branch_df = pd.read_csv(branch_csv)

    buses = []
    for _, r in bus_df.iterrows():
        lat = float(r.get('Latitude', r.get('lat', 0)))
        lng = float(r.get('Longitude', r.get('lon', r.get('lng', 0))))
        if lat == 0 and lng == 0:
            continue
        buses.append({
            'id': int(r['Bus ID']),
            'name': r['Bus Name'],
            'lat': round(lat, 5),
            'lng': round(lng, 5),
            'zone': r.get('Zone', ''),
            'split': 'SPL' in str(r.get('Bus Name', '')) or 'OSM_' in str(r.get('Bus Name', '')),
        })

    lines = []
    bus_coords = {int(r['Bus ID']): (float(r.get('Latitude', r.get('lat', 0))),
                                      float(r.get('Longitude', r.get('lon', r.get('lng', 0)))))
                  for _, r in bus_df.iterrows()}
    for _, r in branch_df.iterrows():
        fb, tb = int(r['From Bus']), int(r['To Bus'])
        if fb not in bus_coords or tb not in bus_coords:
            continue
        lat1, lng1 = bus_coords[fb]
        lat2, lng2 = bus_coords[tb]
        lines.append({
            'uid': r['UID'],
            'lat1': round(lat1, 5), 'lng1': round(lng1, 5),
            'lat2': round(lat2, 5), 'lng2': round(lng2, 5),
            'rating': float(r['Cont Rating']),
        })

    return buses, lines


# ---------------------------------------------------------------------------
# Experiment data builder
# ---------------------------------------------------------------------------

def build_experiment(tag, hour, label, topo_buses, topo_lines):
    """Build experiment data dict from results CSVs + topology."""
    result_dir = RESULTS_DIR / tag
    bd_path = result_dir / "bus_detail.csv"
    ld_path = result_dir / "line_detail.csv"
    hs_path = result_dir / "hourly_summary.csv"

    if not bd_path.exists():
        print(f"  WARNING: {bd_path} not found — skipping {tag}")
        return None

    bd = pd.read_csv(bd_path)
    ld = pd.read_csv(ld_path) if ld_path.exists() else pd.DataFrame()
    hs = pd.read_csv(hs_path) if hs_path.exists() else pd.DataFrame()

    # Bus data for this hour
    bh = bd[bd['Hour'] == hour]
    bus_data = {}
    for _, r in bh.iterrows():
        bus_data[r['Bus']] = {
            'demand': round(r['Demand'], 1),
            'lmp': round(r['LMP'], 2),
            'shedding': r['Mismatch'] > 0.1 if 'Mismatch' in r.index else False,
        }

    # Line flows for this hour
    line_data = {}
    if not ld.empty:
        lh = ld[ld['Hour'] == hour]
        for _, r in lh.iterrows():
            line_data[r['Line']] = round(r['Flow'], 1)

    # Build buses array
    buses = []
    for b in topo_buses:
        name = b['name']
        info = bus_data.get(name, {})
        buses.append({
            'id': b['id'], 'name': name,
            'lat': b['lat'], 'lng': b['lng'],
            'zone': b.get('zone', ''),
            'demand': info.get('demand', 0.0),
            'lmp': info.get('lmp', 0.0),
            'shedding': info.get('shedding', False),
            'split': b.get('split', False),
        })

    # Build lines array
    lines = []
    for l in topo_lines:
        uid = l['uid']
        flow = line_data.get(uid, 0.0)
        rating = l.get('rating', 600)
        util = abs(flow) / rating if rating > 0 and rating < 999000 else 0
        lines.append({
            'uid': uid,
            'lat1': l['lat1'], 'lng1': l['lng1'],
            'lat2': l['lat2'], 'lng2': l['lng2'],
            'flow': flow,
            'rating': round(rating, 0),
            'util': round(util, 4),
            'binding': util > 0.95,
        })

    # Summary stats
    demand = round(bh['Demand'].sum(), 0) if not bh.empty else 0
    shed = round(bh['Mismatch'].clip(lower=0).sum(), 1) if 'Mismatch' in bh.columns else 0
    n_binding = sum(1 for l in lines if l['binding'])

    # Curtailment from hourly_summary
    curt = 0
    if not hs.empty:
        hr_row = hs[hs['Hour'] == hour]
        if not hr_row.empty:
            for col in ['Curtailment', 'curtailment', 'Renewables Curtailment']:
                if col in hr_row.columns:
                    curt = round(float(hr_row.iloc[0][col]), 0)
                    break

    # Zone stats
    bus_zone = {b['name']: b.get('zone', '') for b in buses}
    zone_lmps = {}
    for _, r in bh.iterrows():
        z = bus_zone.get(r['Bus'], '?')
        if z and z != '?':
            zone_lmps.setdefault(z, []).append(r['LMP'])

    zone_stats = {}
    for z, lmps in zone_lmps.items():
        if not lmps:
            continue
        lmps_s = sorted(lmps)
        zone_stats[z] = {
            'med': round(lmps_s[len(lmps_s) // 2], 1),
            'avg': round(sum(lmps) / len(lmps), 1),
        }

    return {
        'buses': buses, 'lines': lines,
        'label': label, 'hour': hour,
        'demand': demand, 'shed': shed, 'curt': curt,
        'n_binding': n_binding, 'zone_stats': zone_stats,
    }


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

HTML_BEFORE = """\
<!DOCTYPE html>
<html><head>
<title>Dartboard SCED Diagnostic</title>
<meta charset="utf-8"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body{margin:0}
#map{width:100%;height:100vh;background:#1a1a2e}
.info{padding:8px 12px;background:rgba(0,0,0,0.85);color:#eee;border-radius:5px;font:13px monospace;max-width:450px}
.info h4{margin:0 0 5px;color:#fff}
.legend i{width:14px;height:14px;float:left;margin-right:6px;opacity:0.8;display:inline-block}
#controls{position:absolute;top:10px;left:60px;z-index:1000;background:rgba(0,0,0,0.85);
  padding:10px 15px;border-radius:8px;color:#eee;font:13px monospace}
#controls select{background:#333;color:#eee;border:1px solid #555;padding:4px 8px;border-radius:4px;font:13px monospace;max-width:400px}
</style>
</head><body>
<div id="controls">
  <b>Experiment:</b>
  <select id="exp-select" onchange="loadExperiment()">
__OPTIONS__
  </select>
</div>
<div id="map"></div>
<script>
const EXPERIMENTS = """

HTML_AFTER = """\
;

const map = L.map("map", {preferCanvas: true}).setView([31.0, -97.5], 6);
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
  maxZoom: 19, attribution: "CartoDB"
}).addTo(map);

let normalLines = L.layerGroup().addTo(map);
let bindingLines = L.layerGroup().addTo(map);
let sheddingBuses = L.layerGroup().addTo(map);
let loadBuses = L.layerGroup().addTo(map);
let allBuses = L.layerGroup();
let zoneLabels = L.layerGroup().addTo(map);
let legendCtrl = null;

L.control.layers(null, {
  "Normal lines": normalLines,
  "Binding/stressed": bindingLines,
  "Shedding buses": sheddingBuses,
  "Load buses (LMP)": loadBuses,
  "All buses": allBuses,
  "Zone labels": zoneLabels,
}, {collapsed: false}).addTo(map);

function flowArrow(lat1, lng1, lat2, lng2, flow, color, layer) {
  if (Math.abs(flow) < 1) return;
  // Positive flow = bus1→bus2; negative = bus2→bus1
  let fromLat=lat1, fromLng=lng1, toLat=lat2, toLng=lng2;
  if (flow < 0) { fromLat=lat2; fromLng=lng2; toLat=lat1; toLng=lng1; }
  const midLat = (fromLat + toLat) / 2;
  const midLng = (fromLng + toLng) / 2;
  // ▶ points right (east) at rotate(0). atan2(dLat,dLng) gives math angle
  // from east CCW. CSS rotate is CW, so rotate(-angle) points correctly.
  const dLat = toLat - fromLat;
  const dLng = toLng - fromLng;
  const angle = Math.atan2(dLat, dLng) * 180 / Math.PI;
  const sz = Math.min(12, Math.max(6, Math.abs(flow) / 200));
  L.marker([midLat, midLng], {
    icon: L.divIcon({
      className: '',
      html: '<div style="font-size:'+sz+'px;color:'+color+';transform:rotate('+(-angle)+'deg);opacity:0.8">&#9654;</div>',
      iconSize: [sz, sz], iconAnchor: [sz/2, sz/2],
    }),
    interactive: false,
  }).addTo(layer);
}

function lmpColor(lmp) {
  if (lmp > 500) return "#ff0000";
  if (lmp > 50) return "#ff4444";
  if (lmp > 30) return "#ff8800";
  if (lmp > 20) return "#ffcc00";
  if (lmp > 10) return "#44cc44";
  if (lmp > 0) return "#2288ff";
  return "#9944ff";
}

const ZC = {"WEST":[31.5,-101.5],"NORTH":[33.0,-97.0],"SOUTH":[29.0,-98.0],"HOUSTON":[29.8,-95.5]};

function loadExperiment() {
  const tag = document.getElementById("exp-select").value;
  const exp = EXPERIMENTS[tag];
  if (!exp) return;
  [normalLines,bindingLines,sheddingBuses,loadBuses,allBuses,zoneLabels].forEach(l=>l.clearLayers());

  exp.lines.forEach(l => {
    const ll = [[l.lat1,l.lng1],[l.lat2,l.lng2]];
    let color,weight,opacity;
    if (l.rating>=999000){color="#555";weight=0.5;opacity=0.2;}
    else if (l.binding){color="#ff4444";weight=3;opacity=0.9;}
    else if (l.util>0.8){color="#ff8800";weight=2;opacity=0.8;}
    else if (l.util>0.5){color="#ffaa00";weight=1.5;opacity=0.7;}
    else if (l.rating>=2000){color="#4488ff";weight=1.5;opacity=0.6;}
    else if (l.rating>=900){color="#44aaff";weight=1;opacity=0.5;}
    else {color="#22cccc";weight=0.6;opacity=0.3;}
    const tip=l.uid+"<br>Flow: "+l.flow+" / "+l.rating+" MVA ("+(l.util*100).toFixed(1)+"%)";
    const line=L.polyline(ll,{color,weight,opacity}).bindPopup(tip);
    const targetLayer = (l.binding||l.util>0.8) ? bindingLines : normalLines;
    targetLayer.addLayer(line);
    if (l.util>0.3) flowArrow(l.lat1, l.lng1, l.lat2, l.lng2, l.flow, color, targetLayer);
  });

  exp.buses.forEach(b => {
    if (b.shedding){
      const r=Math.min(8,Math.max(3,b.demand/20));
      L.circleMarker([b.lat,b.lng],{radius:r,color:"#ff0000",fillColor:"#ff0000",fillOpacity:0.9,weight:2})
        .bindPopup("<b>"+b.name+"</b><br>Zone: "+b.zone+"<br>Demand: "+b.demand+" MW<br>LMP: $"+b.lmp+" (SHEDDING)")
        .addTo(sheddingBuses);
    } else if (b.demand>0){
      const c=lmpColor(b.lmp);
      const r=Math.min(6,Math.max(2,Math.sqrt(b.demand)/5));
      L.circleMarker([b.lat,b.lng],{radius:r,color:c,fillColor:c,fillOpacity:0.8,weight:1})
        .bindPopup("<b>"+b.name+"</b><br>Zone: "+b.zone+"<br>Demand: "+b.demand+" MW<br>LMP: $"+b.lmp.toFixed(2)+"/MWh")
        .addTo(loadBuses);
    } else {
      const c=lmpColor(b.lmp);
      L.circleMarker([b.lat,b.lng],{radius:1.5,color:c,fillColor:c,fillOpacity:0.4,weight:0.5})
        .bindPopup(b.name+"<br>Zone: "+b.zone+"<br>LMP: $"+b.lmp.toFixed(2)).addTo(allBuses);
    }
  });

  Object.entries(exp.zone_stats).forEach(([z,s]) => {
    const [lat,lng]=ZC[z]||[31,-98];
    L.marker([lat,lng],{icon:L.divIcon({className:"",
      html:'<div style="background:rgba(0,0,0,0.75);color:#eee;padding:6px 10px;border-radius:5px;font:bold 13px monospace;white-space:nowrap;border:1px solid '+lmpColor(s.med)+'">'+z+'<br>Med: $'+s.med+'<br>Avg: $'+s.avg+'</div>',
      iconSize:[0,0]})}).addTo(zoneLabels);
  });

  if(legendCtrl) map.removeControl(legendCtrl);
  legendCtrl=L.control({position:"bottomright"});
  legendCtrl.onAdd=function(){
    const div=L.DomUtil.create("div","info legend");
    div.innerHTML='<h4>'+exp.label+'</h4>'+
      '<b>'+exp.demand.toLocaleString()+' MW demand</b><br>'+
      '<b>'+exp.shed.toLocaleString()+' MW shed &bull; '+exp.curt.toLocaleString()+' MW curt</b><br>'+
      '<b>'+exp.n_binding+' binding lines (effective ratings)</b><br><br>'+
      '<b>Lines:</b><br>'+
      '<i style="background:#ff4444"></i> Binding (100%)<br>'+
      '<i style="background:#ff8800"></i> Near-binding (&gt;80%)<br>'+
      '<i style="background:#ffaa00"></i> Stressed (&gt;50%)<br>'+
      '<i style="background:#4488ff"></i> 345+ kV<br>'+
      '<i style="background:#22cccc"></i> 138 kV<br>'+
      '<br><b>Buses (LMP):</b><br>'+
      '<i style="background:#ff0000;border-radius:50%"></i> Shedding / &gt;$500<br>'+
      '<i style="background:#ff4444;border-radius:50%"></i> &gt;$50<br>'+
      '<i style="background:#ff8800;border-radius:50%"></i> $30&ndash;50<br>'+
      '<i style="background:#ffcc00;border-radius:50%"></i> $20&ndash;30<br>'+
      '<i style="background:#44cc44;border-radius:50%"></i> $10&ndash;20<br>'+
      '<i style="background:#2288ff;border-radius:50%"></i> $0&ndash;10<br>'+
      '<i style="background:#9944ff;border-radius:50%"></i> Negative<br>';
    return div;
  };
  legendCtrl.addTo(map);
}
loadExperiment();
</script></body></html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build sced_diagnostic.html — interactive SCED experiment map",
        epilog='Example: python build_sced_diagnostic.py upgr-aug20-t175:17:"Aug 20 T175" v3-j17-t135f-r15:14:"Jun 17 ref"',
    )
    parser.add_argument(
        'experiments', nargs='+',
        help='TAG:HOUR:LABEL triples (e.g., v3-j17-t135f-r15:14:"Jun 17 SOLVED")')
    parser.add_argument(
        '-o', '--output', default=str(OUT_PATH),
        help=f'Output path (default: {OUT_PATH})')

    args = parser.parse_args()

    # Parse experiment specs
    specs = []
    for spec in args.experiments:
        parts = spec.split(':', 2)
        if len(parts) < 2:
            print(f"ERROR: Expected TAG:HOUR:LABEL, got '{spec}'")
            sys.exit(1)
        tag = parts[0]
        hour = int(parts[1])
        label = parts[2] if len(parts) > 2 else f"{tag} h{hour}"
        specs.append((tag, hour, label))

    # Load topology
    print("Loading topology...")
    topo_buses, topo_lines = load_topology_from_existing()
    if topo_buses is None:
        print("  No existing sced_diagnostic.html — building from CSVs")
        topo_buses, topo_lines = load_topology_from_csvs(specs[0][0])
    else:
        print(f"  Reusing topology from existing file ({len(topo_buses)} buses, {len(topo_lines)} lines)")

    # Build experiments
    experiments = {}
    for tag, hour, label in specs:
        print(f"  {tag} (hour {hour})...")
        exp = build_experiment(tag, hour, label, topo_buses, topo_lines)
        if exp is not None:
            experiments[tag] = exp

    if not experiments:
        print("ERROR: No valid experiments loaded")
        sys.exit(1)

    # Build HTML
    options = '\n'.join(
        f'    <option value="{tag}">{exp["label"]}</option>'
        for tag, exp in experiments.items()
    )
    html_top = HTML_BEFORE.replace('__OPTIONS__', options)
    experiments_json = json.dumps(experiments, separators=(',', ':'))
    html = html_top + experiments_json + HTML_AFTER

    out_path = Path(args.output)
    out_path.write_text(html)

    print(f"\nWrote {out_path} ({len(html) // 1024} KB)")
    for tag, exp in experiments.items():
        print(f"  {tag}: {exp['label']} — {exp['n_binding']} binding, {exp['shed']} MW shed")


if __name__ == "__main__":
    main()
