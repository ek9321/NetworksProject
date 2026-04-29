"""
Pipeline 8: Visualize topology from pre-computed line CSVs.

Reads per-voltage line CSVs from data/processed/lines/intermediate/
(produced by pipeline 7) and substations from data/processed/.
Creates publication-quality map visualizations in data/synthetic/.

No topology recomputation — this is a fast, plot-only pipeline.
"""

import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from matplotlib.collections import LineCollection
from collections import defaultdict

from core.topology_generation import SubstationNode, LineCandidate

INTERMEDIATE_DIR = "data/processed/lines/intermediate"
VIZ_DIR = "data/synthetic"


# ── Data loading ────────────────────────────────────────────

def load_substations(csv_path: str) -> list[SubstationNode]:
    substations = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            has_345kv = row.get('has_high_voltage_345kv', 'False').lower() == 'true'
            has_115kv = row.get('has_high_voltage_115kv', 'True').lower() == 'true'
            substations.append(SubstationNode(
                sub_id=int(row['substation_id']),
                lat=float(row['lat']),
                lng=float(row['lng']),
                mw_load=float(row['mw_load']),
                total_gen_mw=float(row.get('total_assigned_gen_mw', '0')),
                has_345kv=has_345kv,
                has_115kv=has_115kv,
            ))
    return substations


def load_lines(csv_path: str) -> list[LineCandidate]:
    """Load line candidates from a CSV written by pipeline 7."""
    lines = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            lines.append(LineCandidate(
                from_sub=int(row['from_sub']),
                to_sub=int(row['to_sub']),
                voltage_kv=int(row['voltage_kv']),
                length_km=float(row['length_km']),
                category=row['category'],
                X_pu=float(row['X_pu']),
                MVAmax=float(row['MVAmax']),
                intersects=row['intersects'].strip().lower() == 'true',
            ))
    return lines


# ── Visualization helpers ───────────────────────────────────

def make_combined_viz(substations, lines_345, lines_115, region_name, out_path):
    """Combined dual-voltage topology map."""
    fig, ax = plt.subplots(figsize=(14, 16))
    sub_map = {s.sub_id: s for s in substations}

    # 115 kV lines
    segs = [[(sub_map[l.from_sub].lng, sub_map[l.from_sub].lat),
             (sub_map[l.to_sub].lng,   sub_map[l.to_sub].lat)]
            for l in lines_115 if l.from_sub in sub_map and l.to_sub in sub_map]
    if segs:
        ax.add_collection(LineCollection(segs, colors='#7f8c8d',
                                         linewidths=0.4, alpha=0.5, zorder=1))

    # 345 kV lines
    segs = [[(sub_map[l.from_sub].lng, sub_map[l.from_sub].lat),
             (sub_map[l.to_sub].lng,   sub_map[l.to_sub].lat)]
            for l in lines_345 if l.from_sub in sub_map and l.to_sub in sub_map]
    if segs:
        ax.add_collection(LineCollection(segs, colors='#c0392b',
                                         linewidths=1.2, alpha=0.8, zorder=2))

    # Substations
    subs_115_only = [s for s in substations if s.has_115kv and not s.has_345kv]
    subs_345 = [s for s in substations if s.has_345kv]

    ax.scatter([s.lng for s in subs_115_only], [s.lat for s in subs_115_only],
               s=4, c='#3498db', alpha=0.6, edgecolors='none', zorder=3,
               label=f'115 kV substations ({len(subs_115_only)})')
    ax.scatter([s.lng for s in subs_345], [s.lat for s in subs_345],
               s=30, c='#e74c3c', alpha=0.9, edgecolors='black', linewidths=0.3,
               zorder=4, marker='s',
               label=f'345 kV substations ({len(subs_345)})')

    # Stats
    n345, m345 = len(subs_345), len(lines_345)
    n115, m115 = len([s for s in substations if s.has_115kv]), len(lines_115)
    mn345 = m345 / n345 if n345 else 0
    mn115 = m115 / n115 if n115 else 0
    ix345 = sum(1 for l in lines_345 if l.intersects) / m345 * 100 if m345 else 0
    ix115 = sum(1 for l in lines_115 if l.intersects) / m115 * 100 if m115 else 0

    handles, _ = ax.get_legend_handles_labels()
    handles.extend([
        mlines.Line2D([], [], color='#7f8c8d', lw=1.5, label=f'115 kV lines ({m115})'),
        mlines.Line2D([], [], color='#c0392b', lw=2.0, label=f'345 kV lines ({m345})'),
    ])
    ax.legend(handles=handles, loc='lower left', fontsize=9, framealpha=0.9)

    ax.set_xlabel('Longitude', fontsize=11)
    ax.set_ylabel('Latitude', fontsize=11)
    ax.set_title(
        f'{region_name} Synthetic Grid — Birchfield Topology\n'
        f'345 kV: {n345} nodes, {m345} lines (m/n={mn345:.3f})  |  '
        f'115 kV: {n115} nodes, {m115} lines (m/n={mn115:.3f})',
        fontsize=13, fontweight='bold')

    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=':', alpha=0.3)

    if m115:
        stats = (
            f"Category quotas (115 kV):\n"
            f"  MST: {sum(1 for l in lines_115 if l.category=='mst')/m115*100:.0f}%  "
            f"Delaunay: {sum(1 for l in lines_115 if l.category=='delaunay')/m115*100:.0f}%\n"
            f"  2-nbr: {sum(1 for l in lines_115 if l.category=='neighbor_2')/m115*100:.0f}%  "
            f"3-nbr: {sum(1 for l in lines_115 if l.category=='neighbor_3')/m115*100:.0f}%\n"
            f"Intersection rates: 345kV {ix345:.1f}%, 115kV {ix115:.1f}%")
        ax.text(0.98, 0.02, stats, transform=ax.transAxes, fontsize=8,
                va='bottom', ha='right', fontfamily='monospace',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.85))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"  ✓ Saved: {out_path}")


def make_single_voltage_viz(substations, lines, voltage_kv, region_name, out_path):
    """Detailed single-voltage view with category coloring."""
    fig, ax = plt.subplots(figsize=(14, 16))
    sub_map = {s.sub_id: s for s in substations}

    cat_colors = {
        'mst': '#2ecc71', 'delaunay': '#3498db',
        'neighbor_2': '#e67e22', 'neighbor_3': '#9b59b6',
    }
    cat_labels = {
        'mst': 'MST', 'delaunay': 'Delaunay',
        'neighbor_2': '2-neighbor', 'neighbor_3': '3-neighbor',
    }

    # Draw lines by category (back to front)
    for cat in ['neighbor_3', 'neighbor_2', 'delaunay', 'mst']:
        cat_lines = [l for l in lines if l.category == cat]
        if not cat_lines:
            continue
        segs = [[(sub_map[l.from_sub].lng, sub_map[l.from_sub].lat),
                 (sub_map[l.to_sub].lng,   sub_map[l.to_sub].lat)]
                for l in cat_lines if l.from_sub in sub_map and l.to_sub in sub_map]
        lw = 1.0 if cat == 'mst' else 0.6
        alpha = 0.8 if cat == 'mst' else 0.5
        ax.add_collection(LineCollection(segs, colors=cat_colors[cat],
                                         linewidths=lw, alpha=alpha,
                                         zorder=2 if cat == 'mst' else 1))

    # Draw substations
    nodes = [s for s in substations
             if (s.has_345kv if voltage_kv == 345 else s.has_115kv)]
    loads = np.array([max(s.mw_load, 1) for s in nodes])
    sizes = 3 + 25 * (loads / loads.max())
    colors = []
    for s in nodes:
        if s.total_gen_mw > 0 and s.mw_load > 0:
            colors.append('#e74c3c')
        elif s.total_gen_mw > 0:
            colors.append('#f39c12')
        else:
            colors.append('#3498db')
    ax.scatter([s.lng for s in nodes], [s.lat for s in nodes],
               s=sizes, c=colors, alpha=0.7, edgecolors='black',
               linewidths=0.2, zorder=3)

    # Line category legend
    cat_counts = defaultdict(int)
    for l in lines:
        cat_counts[l.category] += 1
    cat_handles = []
    for cat in ['mst', 'delaunay', 'neighbor_2', 'neighbor_3']:
        cnt = cat_counts[cat]
        pct = cnt / len(lines) * 100 if lines else 0
        cat_handles.append(mlines.Line2D(
            [], [], color=cat_colors[cat], lw=2,
            label=f'{cat_labels[cat]}: {cnt} ({pct:.0f}%)'))

    sub_handles = [
        mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#3498db',
                      markersize=6, label='Load only'),
        mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#f39c12',
                      markersize=6, label='Generation only'),
        mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#e74c3c',
                      markersize=6, label='Gen + Load'),
    ]

    leg1 = ax.legend(handles=cat_handles, loc='lower left', fontsize=9,
                     title='Line Category', framealpha=0.9)
    ax.add_artist(leg1)
    ax.legend(handles=sub_handles, loc='upper left', fontsize=9,
              title='Substation Type', framealpha=0.9)

    n = len(nodes)
    m = len(lines)
    mn = m / n if n else 0
    ix = sum(1 for l in lines if l.intersects) / m * 100 if m else 0

    ax.set_xlabel('Longitude', fontsize=11)
    ax.set_ylabel('Latitude', fontsize=11)
    ax.set_title(
        f'{region_name} {voltage_kv} kV Topology — Birchfield Algorithm\n'
        f'{n} substations, {m} lines, m/n = {mn:.3f}, '
        f'intersections = {ix:.1f}%',
        fontsize=13, fontweight='bold')

    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.grid(True, linestyle=':', alpha=0.3)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"  ✓ Saved: {out_path}")


# ── Per-region driver ───────────────────────────────────────

def run_region(region_name: str) -> dict:
    """Load pre-computed lines and create visualizations for one region."""
    slug = region_name.lower().replace(' ', '_')

    print(f"\n{'#'*60}")
    print(f"  {region_name.upper()}")
    print(f"{'#'*60}")

    # Load substations
    subs_csv = f"data/processed/{slug}_substations_with_buses.csv"
    substations = load_substations(subs_csv)
    print(f"Loaded {len(substations)} substations")

    # Load pre-computed lines
    path_345 = os.path.join(INTERMEDIATE_DIR, f"{slug}_lines_345kv.csv")
    path_115 = os.path.join(INTERMEDIATE_DIR, f"{slug}_lines_115kv.csv")

    if not os.path.exists(path_345) or not os.path.exists(path_115):
        print(f"  ✗ Line CSVs not found in {INTERMEDIATE_DIR}/")
        print(f"    Run pipeline 7 first to generate topology.")
        return {}

    lines_345 = load_lines(path_345)
    lines_115 = load_lines(path_115)
    print(f"  345 kV: {len(lines_345)} lines")
    print(f"  115 kV: {len(lines_115)} lines")

    # Copy lines to data/synthetic/ for downstream consumers
    for label, lines in [('345kv', lines_345), ('115kv', lines_115)]:
        dst = os.path.join(VIZ_DIR, f"{slug}_lines_{label}.csv")
        os.makedirs(VIZ_DIR, exist_ok=True)
        with open(os.path.join(INTERMEDIATE_DIR, f"{slug}_lines_{label}.csv")) as src_f:
            with open(dst, 'w') as dst_f:
                dst_f.write(src_f.read())
        print(f"  ✓ Copied → {dst}")

    # Create visualizations
    print(f"\n{'='*60}")
    print(f"Creating {region_name} visualizations...")
    print(f"{'='*60}")

    make_combined_viz(substations, lines_345, lines_115, region_name,
                      os.path.join(VIZ_DIR, f'{slug}_topology_combined.png'))
    make_single_voltage_viz(substations, lines_345, 345, region_name,
                            os.path.join(VIZ_DIR, f'{slug}_topology_345kv.png'))
    make_single_voltage_viz(substations, lines_115, 115, region_name,
                            os.path.join(VIZ_DIR, f'{slug}_topology_115kv.png'))

    n345 = sum(1 for s in substations if s.has_345kv)
    n115 = sum(1 for s in substations if s.has_115kv)
    return {
        345: (len(lines_345), n345),
        115: (len(lines_115), n115),
    }


# ── Main ────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("TOPOLOGY VISUALIZATION (from pre-computed lines)")
    print("=" * 60)
    print(f"Reading lines from: {INTERMEDIATE_DIR}/")
    print(f"Writing plots to:   {VIZ_DIR}/")

    regions = ['New York', 'Texas']
    all_results = {}

    for region_name in regions:
        result = run_region(region_name)
        if result:
            all_results[region_name] = result

    # Summary
    print(f"\n{'='*60}")
    print("✓ ALL VISUALIZATIONS COMPLETE")
    print(f"{'='*60}")
    for region_name, result in all_results.items():
        slug = region_name.lower().replace(' ', '_')
        print(f"\n  {region_name}:")
        for v in (345, 115):
            m, n = result[v]
            print(f"    {v} kV: {n} nodes, {m} lines, m/n={m/n:.3f}")
        print(f"    PNGs: {slug}_topology_{{combined,345kv,115kv}}.png")

    print(f"\nAll outputs in {VIZ_DIR}/")


if __name__ == '__main__':
    main()
