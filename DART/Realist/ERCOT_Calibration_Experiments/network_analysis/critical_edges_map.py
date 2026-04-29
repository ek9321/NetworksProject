#!/usr/bin/env python3
"""
Critical Edges Map — ERCOT grid vulnerability analysis.
ORF 387 Networks — Princeton, Spring 2026

Companion visualization to critical_ap_map.png. Highlights:
  (a) Top bridges by population cut — edge removal disconnects a population.
  (b) Top edge betweenness (unweighted) — edges carrying the most shortest-
      path flow through the transmission graph.
  (c) The Morgan Creek ↔ Tonkawa edge (L1605_1612), the WESTEX export
      corridor that is the known SCED-binding constraint on high-wind days.

Reads the edge ranking CSV produced by critical_edges_analysis.py and the
grid topology from grid_visualizer_v3.html.

Output: figures/critical_edges_map.png
"""

import csv
import json
import os
import re
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HTML_PATH = "Realist/grid_visualizer_v3.html"
RANKING_CSV = ("Realist/ERCOT_Calibration_Experiments/network_analysis/"
               "results/critical_edges_ranking.csv")
FIG_DIR = "Realist/ERCOT_Calibration_Experiments/network_analysis/figures"
FIG_OUT = os.path.join(FIG_DIR, "critical_edges_map.png")
os.makedirs(FIG_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Load grid topology (for background edges)
# ---------------------------------------------------------------------------

with open(HTML_PATH) as f:
    content = f.read()

m = re.search(r'(?:const|let|var)\s+NODES\s*=\s*(\[.*?\]);', content, re.DOTALL)
nodes_raw = json.loads(m.group(1))
node_info = {n['i']: n for n in nodes_raw}

edges_by_tier = {}
for varname in ['EDGES_HIGH', 'EDGES_MID_HI', 'EDGES_MID_LO']:
    m2 = re.search(rf'(?:const|let|var)\s+{varname}\s*=\s*(\[.*?\]);',
                   content, re.DOTALL)
    if m2:
        edges_by_tier[varname] = json.loads(m2.group(1))

# ---------------------------------------------------------------------------
# Load edge rankings
# ---------------------------------------------------------------------------

rows = []
with open(RANKING_CSV) as f:
    reader = csv.DictReader(f)
    for r in reader:
        for k in ("a_lat", "a_lon", "b_lat", "b_lon", "eb_unweighted",
                  "eb_popweighted", "bridge_pop_cut"):
            r[k] = float(r[k]) if r[k] else 0.0
        for k in ("is_bridge", "sced_binding", "a_id", "b_id"):
            r[k] = int(r[k])
        rows.append(r)

# Sort views
bridges_sorted = sorted(
    [r for r in rows if r["is_bridge"]],
    key=lambda r: -r["bridge_pop_cut"])

eb_sorted = sorted(rows, key=lambda r: -r["eb_unweighted"])
ebp_sorted = sorted(rows, key=lambda r: -r["eb_popweighted"])

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

fig, ax = plt.subplots(figsize=(14, 11), facecolor='white')
ax.set_facecolor('#f7f7f5')

# Background grid edges (all tiers, muted)
tier_style = {
    'EDGES_HIGH':   dict(color='#b5b5b6', lw=0.50, zorder=1),   # 345 kV
    'EDGES_MID_HI': dict(color='#cfcfcf', lw=0.32, zorder=1),   # 230 kV
    'EDGES_MID_LO': dict(color='#e2e2e2', lw=0.20, zorder=1),   # 138 kV
}
for varname, style in tier_style.items():
    for e in edges_by_tier.get(varname, []):
        ni_a = node_info.get(e['a'], {})
        ni_b = node_info.get(e['b'], {})
        la, lo_a = ni_a.get('lat'), ni_a.get('lon')
        lb, lo_b = ni_b.get('lat'), ni_b.get('lon')
        if la and lb:
            ax.plot([lo_a, lo_b], [la, lb], **style)

# ---------------------------------------------------------------------------
# Overlay: top-15 edge betweenness (blue, thick)
# ---------------------------------------------------------------------------
TOP_EB = 15
eb_max = eb_sorted[0]["eb_unweighted"]

for rank_i, r in enumerate(eb_sorted[:TOP_EB]):
    lw = 1.5 + 3.0 * (r["eb_unweighted"] / eb_max)
    alpha = 0.55 + 0.35 * (r["eb_unweighted"] / eb_max)
    ax.plot([r["a_lon"], r["b_lon"]], [r["a_lat"], r["b_lat"]],
            color='#1f4e79', lw=lw, alpha=alpha, zorder=4,
            solid_capstyle='round')

# ---------------------------------------------------------------------------
# Overlay: top-15 bridges by population cut (red, thick)
# ---------------------------------------------------------------------------
TOP_BR = 15
br_max = bridges_sorted[0]["bridge_pop_cut"] if bridges_sorted else 1.0

for rank_i, r in enumerate(bridges_sorted[:TOP_BR]):
    lw = 1.3 + 2.8 * (r["bridge_pop_cut"] / br_max)
    ax.plot([r["a_lon"], r["b_lon"]], [r["a_lat"], r["b_lat"]],
            color='#b03a2e', lw=lw, alpha=0.92, zorder=5,
            solid_capstyle='round')

# ---------------------------------------------------------------------------
# Mark SCED-binding edge distinctly (gold star overlay + green segment)
# ---------------------------------------------------------------------------
sced_rows = [r for r in rows if r["sced_binding"]]
for r in sced_rows:
    mx, my = 0.5 * (r["a_lon"] + r["b_lon"]), 0.5 * (r["a_lat"] + r["b_lat"])
    ax.plot([r["a_lon"], r["b_lon"]], [r["a_lat"], r["b_lat"]],
            color='#2e8b57', lw=3.2, alpha=0.95, zorder=6,
            solid_capstyle='round')
    ax.scatter(mx, my, marker='*', s=260, color='#f1c40f',
               edgecolors='#7d6608', linewidths=1.2, zorder=9)

# ---------------------------------------------------------------------------
# Endpoint dots for top bridges (small red) + top betweenness (small blue)
# ---------------------------------------------------------------------------
def short(name):
    if not name:
        return ""
    return (name.replace(" Substation", "")
                .replace(" Station", "")
                .replace(" Switching", "")
                .strip())

# Annotate top 5 bridges
for rank_i, r in enumerate(bridges_sorted[:5]):
    mx, my = 0.5 * (r["a_lon"] + r["b_lon"]), 0.5 * (r["a_lat"] + r["b_lat"])
    ax.scatter(mx, my, s=60, color='#b03a2e', edgecolors='white',
               linewidths=1.3, zorder=7)
    ax.text(mx, my, f"B{rank_i+1}", ha='center', va='center',
            fontsize=6.3, fontweight='bold', color='white', zorder=8)

# Annotate top 5 betweenness
for rank_i, r in enumerate(eb_sorted[:5]):
    mx, my = 0.5 * (r["a_lon"] + r["b_lon"]), 0.5 * (r["a_lat"] + r["b_lat"])
    ax.scatter(mx, my, s=60, color='#1f4e79', edgecolors='white',
               linewidths=1.3, zorder=7)
    ax.text(mx, my, f"E{rank_i+1}", ha='center', va='center',
            fontsize=6.3, fontweight='bold', color='white', zorder=8)

# ---------------------------------------------------------------------------
# Callout boxes — bridges table (lower left) & betweenness table (upper right)
# ---------------------------------------------------------------------------

def name_pair(r):
    an = short(r["a_name"]) or "[T-jxn]"
    bn = short(r["b_name"]) or "[T-jxn]"
    return an, bn

bridge_lines = ["TOP BRIDGES  (edge-cut population)",
                "─────────────────────────────────"]
for rank_i, r in enumerate(bridges_sorted[:5]):
    a, b = name_pair(r)
    pop = int(round(r["bridge_pop_cut"]))
    bridge_lines.append(f"B{rank_i+1:<2} {a:<22}↔{b:>22}  {pop:>7,}")

ax.text(-107.0, 26.35, "\n".join(bridge_lines),
        fontsize=6.2, family='monospace', ha='left', va='bottom',
        bbox=dict(boxstyle='round,pad=0.55', facecolor='white',
                  edgecolor='#b03a2e', linewidth=1.4, alpha=0.95),
        zorder=10)

eb_lines = ["TOP EDGE BETWEENNESS  (unweighted)",
            "────────────────────────────────────"]
for rank_i, r in enumerate(eb_sorted[:5]):
    a, b = name_pair(r)
    score = int(round(r["eb_unweighted"]))
    eb_lines.append(f"E{rank_i+1:<2} {a:<22}↔{b:>22}  {score:>9,}")

ax.text(-99.5, 36.6, "\n".join(eb_lines),
        fontsize=6.2, family='monospace', ha='left', va='top',
        bbox=dict(boxstyle='round,pad=0.55', facecolor='white',
                  edgecolor='#1f4e79', linewidth=1.4, alpha=0.95),
        zorder=10)

# Morgan Creek → Tonkawa callout
if sced_rows:
    r = sced_rows[0]
    mx, my = 0.5 * (r["a_lon"] + r["b_lon"]), 0.5 * (r["a_lat"] + r["b_lat"])
    rank_eb = next((i for i, row in enumerate(eb_sorted, 1)
                    if row["a_id"] == r["a_id"] and row["b_id"] == r["b_id"]), None)
    ax.annotate(
        (f"L1605_1612: Morgan Creek ↔ Tonkawa (345 kV)\n"
         f"WESTEX export corridor (SCED binding)\n"
         f"Edge-betweenness rank: #{rank_eb or '?'} of 5,323\n"
         f"→ Cross-validates dispatch model"),
        xy=(mx, my), xytext=(-104.5, 28.7),
        fontsize=6.4, ha='center', va='center',
        color='#1e4620',
        bbox=dict(boxstyle='round,pad=0.45', facecolor='#d4efdf',
                  edgecolor='#2e8b57', linewidth=1.3, alpha=0.95),
        arrowprops=dict(arrowstyle='->', color='#2e8b57', lw=1.2,
                        connectionstyle='arc3,rad=0.20'),
        zorder=11,
    )

# ---------------------------------------------------------------------------
# Regional context annotations
# ---------------------------------------------------------------------------
# NE Texas 345 kV corridor callout (where top 3 betweenness edges live)
ax.annotate(
    "NE Texas 345 kV backbone\n(Singleton–Jewett–Big Brown–Navarro)\n"
    "Single mesh carries Houston↔DFW flow\n→ No redundant east-of-I-45 corridor",
    xy=(-96.1, 31.55),
    xytext=(-94.5, 34.5),
    fontsize=6.2, ha='center', va='center',
    color='#1b2631',
    bbox=dict(boxstyle='round,pad=0.45', facecolor='#d6eaf8',
              edgecolor='#1f4e79', linewidth=1.1, alpha=0.93),
    arrowprops=dict(arrowstyle='->', color='#1f4e79', lw=1.0,
                    connectionstyle='arc3,rad=-0.15'),
    zorder=10,
)

# Horse Hollow / CREZ wind corridor
ax.annotate(
    "Horse Hollow / CREZ wind\n(W–E transfer of West TX wind to load)",
    xy=(-99.50, 32.10),
    xytext=(-102.5, 32.9),
    fontsize=6.2, ha='center', va='center',
    color='#1b2631',
    bbox=dict(boxstyle='round,pad=0.4', facecolor='#d6eaf8',
              edgecolor='#1f4e79', linewidth=1.0, alpha=0.92),
    arrowprops=dict(arrowstyle='->', color='#1f4e79', lw=1.0,
                    connectionstyle='arc3,rad=0.10'),
    zorder=10,
)

# Waco-Temple I-35 bridge corridor
ax.annotate(
    "I-35 bridge cluster\n(Temple–Waco 138 kV — AP map companion)",
    xy=(-97.25, 31.35),
    xytext=(-94.3, 30.1),
    fontsize=6.2, ha='center', va='center',
    color='#512e1a',
    bbox=dict(boxstyle='round,pad=0.4', facecolor='#fadbd8',
              edgecolor='#b03a2e', linewidth=1.0, alpha=0.93),
    arrowprops=dict(arrowstyle='->', color='#b03a2e', lw=1.0,
                    connectionstyle='arc3,rad=-0.18'),
    zorder=10,
)

# ---------------------------------------------------------------------------
# Axes
# ---------------------------------------------------------------------------
ax.set_xlim(-107.2, -93.0)
ax.set_ylim(25.5, 36.9)
ax.set_aspect('equal')

ax.set_xlabel("Longitude", fontsize=9)
ax.set_ylabel("Latitude", fontsize=9)
ax.set_title(
    "ERCOT Grid — Critical Edges by Bridge Population Cut and Betweenness Centrality\n"
    "OSM V3 Topology · 3,786 buses · 5,323 branches  |  "
    "Tarjan bridges + Brandes edge betweenness  |  ORF 387 Networks, Princeton 2026",
    fontsize=10, pad=10,
)

# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------
n_bridges = sum(1 for r in rows if r["is_bridge"])
legend_elements = [
    Line2D([0], [0], color='#b03a2e', lw=3.0,
           label=f'Top-15 bridges by population cut  ({n_bridges} bridges total, 17.2%)'),
    Line2D([0], [0], color='#1f4e79', lw=3.0,
           label='Top-15 edges by Brandes edge betweenness (unweighted)'),
    Line2D([0], [0], color='#2e8b57', lw=3.2,
           label='L1605_1612 Morgan Creek ↔ Tonkawa — known SCED-binding'),
    Line2D([0], [0], marker='*', color='w', markerfacecolor='#f1c40f',
           markeredgecolor='#7d6608', markersize=12,
           label='SCED-binding marker (cross-validation point)'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#b03a2e',
           markeredgecolor='white', markersize=8,
           label='B1–B5 labels: top-5 bridges'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#1f4e79',
           markeredgecolor='white', markersize=8,
           label='E1–E5 labels: top-5 betweenness edges'),
    mpatches.Patch(facecolor='#b5b5b6', label='345 kV backbone'),
    mpatches.Patch(facecolor='#cfcfcf', label='230 kV network'),
    mpatches.Patch(facecolor='#e2e2e2', label='138 kV network'),
]
ax.legend(handles=legend_elements, loc='upper left', fontsize=6.7,
          framealpha=0.93, edgecolor='#bbbbbb',
          title="Critical Edge Metrics", title_fontsize=7.4,
          borderpad=0.75)

# Grid
ax.grid(True, linestyle=':', linewidth=0.3, color='#cccccc', zorder=0)
ax.set_axisbelow(True)

plt.tight_layout()
plt.savefig(FIG_OUT, dpi=200, bbox_inches='tight', facecolor='white')
print(f"Saved: {FIG_OUT}")
