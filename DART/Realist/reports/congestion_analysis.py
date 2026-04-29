"""
ERCOT LMP Congestion Analysis
==============================
Loads 30 days of hourly SCED LMPs, joins to matched substation coordinates,
and produces a congestion report with figures.

Usage (from project root):
    python3 Realist/reports/congestion_analysis.py

Requires:
    Realist/reports/data/lmp_history.csv    (from fetch_lmp_history.py)
    Realist/grid_data/matching_results/texas_matched_substations_v6.csv

Outputs:
    Realist/reports/figures/fig_01_system_spread.png
    Realist/reports/figures/fig_02_mean_lmp_map.png
    Realist/reports/figures/fig_03_volatility_map.png
    Realist/reports/figures/fig_04_congestion_proxy_map.png
    Realist/reports/figures/fig_05_temporal_heatmap.png
    Realist/reports/figures/fig_06_price_duration_curves.png
    Realist/reports/figures/fig_07_zone_boxplots.png
    Realist/reports/figures/fig_08_correlation_clusters.png
    Realist/reports/ERCOT_Congestion_Analysis.md
"""

import csv
import math
import os
from collections import defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import matplotlib.ticker as mticker
import numpy as np
from scipy.cluster import hierarchy
from scipy.spatial.distance import squareform

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
REALIST      = os.path.dirname(SCRIPT_DIR)

LMP_CSV      = os.path.join(SCRIPT_DIR, "data",    "lmp_history.csv")
MATCH_CSV    = os.path.join(REALIST,    "grid_data", "matching_results",
                             "texas_matched_substations_v6.csv")
FIG_DIR      = os.path.join(SCRIPT_DIR, "figures")
REPORT_PATH  = os.path.join(SCRIPT_DIR, "ERCOT_Congestion_Analysis.md")

SP_DIR       = os.path.join(REALIST, "grid_data", "SP_List_EB_Mapping")
RN_TO_UNIT_CSV = os.path.join(SP_DIR, "Resource_Node_to_Unit_01292026_104938.csv")
SP_CSV         = os.path.join(SP_DIR, "Settlement_Points_01292026_104938.csv")

os.makedirs(FIG_DIR, exist_ok=True)

ZONE_COLORS = {
    "LZ_WEST":    "#fb923c",
    "LZ_NORTH":   "#60a5fa",
    "LZ_HOUSTON": "#f87171",
    "LZ_SOUTH":   "#34d399",
}
ZONE_ORDER = ["LZ_WEST", "LZ_NORTH", "LZ_HOUSTON", "LZ_SOUTH"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _save(fig, name):
    path = os.path.join(FIG_DIR, name)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {name}")
    return name


def setup_map_ax(ax, lons, lats, pad=1.0):
    """Set equal-aspect geographic extent from data bounds."""
    ax.set_xlim(min(lons) - pad, max(lons) + pad)
    ax.set_ylim(min(lats) - pad, max(lats) + pad)
    mid_lat = (min(lats) + max(lats)) / 2
    ax.set_aspect(1.0 / math.cos(math.radians(mid_lat)))
    ax.set_xlabel("Longitude", fontsize=8)
    ax.set_ylabel("Latitude",  fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.15)


# ── 1. Load data ──────────────────────────────────────────────────────────────

def load_lmp_history():
    """
    Returns:
      hours      : sorted list of hour strings "YYYY-MM-DDTHH"
      sp_lmp     : {settlement_point: {hour: lmp}}
      lz_lmp     : {load_zone: {hour: lmp}}
      hub_lmp    : {hub: {hour: lmp}}
    """
    sp_lmp  = defaultdict(dict)
    lz_lmp  = defaultdict(dict)
    hub_lmp = defaultdict(dict)

    print(f"Loading {LMP_CSV} …")
    with open(LMP_CSV) as f:
        for row in csv.DictReader(f):
            h  = row["hour"]
            sp = row["settlement_point"]
            v  = float(row["lmp"])
            t  = row["sp_type"]
            if t == "load_zone":
                lz_lmp[sp][h]  = v
            elif t == "hub":
                hub_lmp[sp][h] = v
            else:
                sp_lmp[sp][h]  = v

    hours = sorted({h for d in sp_lmp.values() for h in d}
                 | {h for d in lz_lmp.values()  for h in d})
    print(f"  {len(hours)} hours, {len(sp_lmp)} resource nodes, "
          f"{len(lz_lmp)} load zones, {len(hub_lmp)} hubs")
    return hours, sp_lmp, lz_lmp, hub_lmp


def build_rn_to_substation():
    """
    Map each ERCOT resource-node name → canonical ERCOT substation abbreviation.

    Primary source:   Resource_Node_to_Unit  (RESOURCE_NODE → UNIT_SUBSTATION)
    Fallback source:  Settlement_Points      (RESOURCE_NODE → SUBSTATION)
    """
    mapping = {}
    if os.path.exists(RN_TO_UNIT_CSV):
        with open(RN_TO_UNIT_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rn  = row["RESOURCE_NODE"].strip()
                sub = row["UNIT_SUBSTATION"].strip()
                if rn and sub:
                    mapping[rn] = sub
    if os.path.exists(SP_CSV):
        with open(SP_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rn  = row.get("RESOURCE_NODE", "").strip()
                sub = row.get("SUBSTATION", "").strip()
                if rn and sub and rn not in mapping:
                    mapping[rn] = sub
    print(f"  Mapped {len(mapping)} resource nodes to substations")
    return mapping


def load_matched_substations():
    """
    Returns {ercot_name: {lat, lon, load_zone, confidence, match_source}}
    """
    subs = {}
    with open(MATCH_CSV) as f:
        for row in csv.DictReader(f):
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (ValueError, KeyError):
                continue
            subs[row["ercot_substation"]] = {
                "lat":        lat,
                "lon":        lon,
                "load_zone":  row.get("load_zone", ""),
                "confidence": row.get("confidence", ""),
                "src":        row.get("match_source", ""),
            }
    print(f"  {len(subs)} matched ERCOT substations")
    return subs


def join_lmp_to_coords(sp_lmp, matched_subs, hours, rn_to_sub):
    """
    For each ERCOT substation that has both LMP history AND coordinates,
    compute per-hour timeseries and summary stats.

    Uses the Resource_Node_to_Unit mapping (rn_to_sub) to map each settlement
    point to its canonical ERCOT substation abbreviation, then averages prices
    across all settlement points at the same substation per hour.

    Returns list of dicts, one per matched substation, with:
      name, lat, lon, load_zone, confidence, src,
      mean_lmp, std_lmp, min_lmp, max_lmp,
      ts: {hour: lmp}   (only hours where data exists)
    """
    # Group settlement points by substation
    sub_to_sps = defaultdict(list)
    for sp in sp_lmp:
        sub = rn_to_sub.get(sp)
        if sub:
            sub_to_sps[sub].append(sp)

    nodes = []
    for name, meta in matched_subs.items():
        sps = sub_to_sps.get(name)
        if not sps:
            continue
        # Average prices across all settlement points at this substation, per hour
        ts = {}
        for h in hours:
            prices = [sp_lmp[sp][h] for sp in sps if h in sp_lmp[sp]]
            if prices:
                ts[h] = sum(prices) / len(prices)
        vals = [ts[h] for h in hours if h in ts]
        if len(vals) < 24:   # need at least one day of data
            continue
        nodes.append({
            "name":       name,
            "sp":         sps[0],
            "lat":        meta["lat"],
            "lon":        meta["lon"],
            "load_zone":  meta["load_zone"],
            "confidence": meta["confidence"],
            "src":        meta["src"],
            "mean_lmp":   float(np.mean(vals)),
            "std_lmp":    float(np.std(vals)),
            "min_lmp":    float(np.min(vals)),
            "max_lmp":    float(np.max(vals)),
            "ts":         ts,
            "vals":       vals,
        })
    print(f"  {len(nodes)} nodes with LMP history + coordinates")
    return nodes


# ── 2. System-level spread time series ───────────────────────────────────────

def fig_system_spread(hours, sp_lmp, lz_lmp):
    """
    Per-hour: (max LMP − min LMP) across all resource nodes = congestion pressure.
    Also plot load zone prices as reference lines.
    """
    spreads, means, maxs, mins = [], [], [], []
    lz_series = {lz: [] for lz in ZONE_ORDER}

    for h in hours:
        vals = [v for sp in sp_lmp.values() if h in sp for v in [sp[h]]]
        if not vals:
            spreads.append(np.nan); means.append(np.nan)
            maxs.append(np.nan);   mins.append(np.nan)
        else:
            spreads.append(max(vals) - min(vals))
            means.append(np.mean(vals))
            maxs.append(np.max(vals))
            mins.append(np.min(vals))
        for lz in ZONE_ORDER:
            lz_series[lz].append(lz_lmp.get(lz, {}).get(h, np.nan))

    x = np.arange(len(hours))
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # Top: LMP spread
    ax1.fill_between(x, 0, spreads, alpha=0.35, color="#ef4444", label="Max−Min spread")
    ax1.plot(x, spreads, color="#ef4444", linewidth=0.6, alpha=0.7)
    ax1.axhline(np.nanmean(spreads), color="#991b1b", linestyle="--",
                linewidth=1, label=f"Mean spread ${np.nanmean(spreads):.1f}")
    ax1.set_ylabel("LMP Spread ($/MWh)", fontsize=9)
    ax1.set_title("ERCOT System-Wide LMP Spread (30-Day Hourly)", fontsize=12)
    ax1.legend(fontsize=8); ax1.grid(True, alpha=0.2)
    ax1.set_ylim(bottom=0)

    # Bottom: load zone prices
    for lz in ZONE_ORDER:
        ax2.plot(x, lz_series[lz], color=ZONE_COLORS[lz],
                 linewidth=0.9, label=lz, alpha=0.85)
    ax2.set_ylabel("Load Zone LMP ($/MWh)", fontsize=9)
    ax2.set_title("Load Zone Prices", fontsize=10)
    ax2.legend(fontsize=8, ncol=4); ax2.grid(True, alpha=0.2)

    # X-axis ticks: one per day
    tick_pos  = [i for i, h in enumerate(hours) if h.endswith("T00")]
    tick_lbl  = [h[:10] for h in hours if h.endswith("T00")]
    ax2.set_xticks(tick_pos)
    ax2.set_xticklabels(tick_lbl, rotation=45, ha="right", fontsize=7)
    ax2.set_xlabel("Date (CPT)", fontsize=9)

    fig.tight_layout()
    return _save(fig, "fig_01_system_spread.png"), float(np.nanmean(spreads))


# ── 3. Mean LMP map ───────────────────────────────────────────────────────────

def fig_mean_lmp_map(nodes):
    lats  = [n["lat"] for n in nodes]
    lons  = [n["lon"] for n in nodes]
    means = [n["mean_lmp"] for n in nodes]

    vmin, vmax = np.percentile(means, 2), np.percentile(means, 98)
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap = cm.RdYlBu_r

    fig, ax = plt.subplots(figsize=(13, 9))
    setup_map_ax(ax, lons, lats)
    sc = ax.scatter(lons, lats, c=means, cmap=cmap, norm=norm,
                    s=18, alpha=0.85, linewidths=0.3, edgecolors="k", zorder=3)
    cbar = plt.colorbar(sc, ax=ax, shrink=0.65)
    cbar.set_label("Mean LMP ($/MWh)", fontsize=9)
    ax.set_title("30-Day Mean LMP by Node Location", fontsize=12)

    # Annotate load zone labels
    for lz, (lon, lat) in {
        "LZ_WEST": (-101.5, 31.5), "LZ_NORTH": (-97.5, 33.8),
        "LZ_HOUSTON": (-95.2, 29.8), "LZ_SOUTH": (-98.3, 27.8),
    }.items():
        ax.text(lon, lat, lz, fontsize=7, color="#374151", ha="center",
                bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=1.5))
    fig.tight_layout()
    return _save(fig, "fig_02_mean_lmp_map.png")


# ── 4. Volatility map ─────────────────────────────────────────────────────────

def fig_volatility_map(nodes):
    lats = [n["lat"] for n in nodes]
    lons = [n["lon"] for n in nodes]
    stds = [n["std_lmp"] for n in nodes]

    vmax = np.percentile(stds, 97)
    norm = mcolors.Normalize(vmin=0, vmax=vmax)
    cmap = cm.plasma

    fig, ax = plt.subplots(figsize=(13, 9))
    setup_map_ax(ax, lons, lats)
    sc = ax.scatter(lons, lats, c=stds, cmap=cmap, norm=norm,
                    s=18, alpha=0.85, linewidths=0.3, edgecolors="k", zorder=3)
    cbar = plt.colorbar(sc, ax=ax, shrink=0.65)
    cbar.set_label("LMP Std Dev ($/MWh)", fontsize=9)
    ax.set_title("30-Day LMP Volatility (Std Dev) by Node", fontsize=12)
    fig.tight_layout()
    return _save(fig, "fig_03_volatility_map.png")


# ── 5. Congestion proxy map ───────────────────────────────────────────────────

def fig_congestion_proxy(nodes, lz_lmp, hours):
    """
    Congestion proxy = node mean LMP − its load zone mean LMP.
    Positive = node is systematically more expensive than its zone
               → likely at the receiving end of a binding constraint.
    Negative = node is systematically cheaper than its zone
               → likely at the sending end (generation-rich, export-limited).
    """
    lz_mean = {lz: np.nanmean([v for v in d.values()]) for lz, d in lz_lmp.items()}

    proxies = []
    valid_nodes = []
    for n in nodes:
        lz = n["load_zone"]
        if lz not in lz_mean:
            continue
        proxies.append(n["mean_lmp"] - lz_mean[lz])
        valid_nodes.append(n)

    if not proxies:
        return None

    lats = [n["lat"] for n in valid_nodes]
    lons = [n["lon"] for n in valid_nodes]

    vlim = np.percentile(np.abs(proxies), 95)
    vlim = max(vlim, 1.0)
    norm = mcolors.TwoSlopeNorm(vmin=-vlim, vcenter=0, vmax=vlim)
    cmap = cm.RdBu_r

    fig, ax = plt.subplots(figsize=(13, 9))
    setup_map_ax(ax, lons, lats)
    sc = ax.scatter(lons, lats, c=proxies, cmap=cmap, norm=norm,
                    s=18, alpha=0.85, linewidths=0.3, edgecolors="k", zorder=3)
    cbar = plt.colorbar(sc, ax=ax, shrink=0.65)
    cbar.set_label("Node LMP − Zone LMP ($/MWh)", fontsize=9)
    ax.set_title(
        "30-Day Congestion Proxy: Node vs. Load Zone Mean LMP\n"
        "Red = above zone avg (import-constrained)  ·  "
        "Blue = below zone avg (export-constrained)",
        fontsize=11,
    )
    fig.tight_layout()

    top_high = sorted(zip(proxies, valid_nodes), key=lambda x: x[0], reverse=True)[:5]
    top_low  = sorted(zip(proxies, valid_nodes), key=lambda x: x[0])[:5]
    return _save(fig, "fig_04_congestion_proxy_map.png"), top_high, top_low, proxies, valid_nodes


# ── 6. Temporal heatmap (hour-of-day × day-of-week) ──────────────────────────

def fig_temporal_heatmap(hours, sp_lmp):
    """Average LMP spread per cell of (hour-of-day × day-of-week)."""
    # Build spread per hour
    spread_by_dow_hod = defaultdict(list)  # key=(dow, hod)
    for h in hours:
        vals = [v for sp in sp_lmp.values() if h in sp for v in [sp[h]]]
        if not vals:
            continue
        spread = max(vals) - min(vals)
        dt  = datetime.strptime(h, "%Y-%m-%dT%H")
        key = (dt.weekday(), dt.hour)
        spread_by_dow_hod[key].append(spread)

    grid = np.full((7, 24), np.nan)
    for (dow, hod), vals in spread_by_dow_hod.items():
        grid[dow, hod] = np.mean(vals)

    fig, ax = plt.subplots(figsize=(14, 5))
    im = ax.imshow(grid, aspect="auto", cmap="YlOrRd",
                   vmin=0, vmax=np.nanpercentile(grid, 97))
    plt.colorbar(im, ax=ax, shrink=0.8, label="Avg LMP Spread ($/MWh)")

    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(24)], rotation=45,
                       ha="right", fontsize=7)
    ax.set_yticks(range(7))
    ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], fontsize=8)
    ax.set_xlabel("Hour of Day (CPT)", fontsize=9)
    ax.set_title("Average LMP Spread by Hour-of-Day × Day-of-Week\n"
                 "(30-day sample  ·  darker = more congestion)", fontsize=11)
    fig.tight_layout()
    return _save(fig, "fig_05_temporal_heatmap.png")


# ── 7. Price duration curves ──────────────────────────────────────────────────

def fig_price_duration(nodes, lz_lmp, hours):
    """
    Price duration curve for each load zone's average node LMP.
    Shows what fraction of hours prices exceed a given level.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Load zone SPP curves
    for lz in ZONE_ORDER:
        vals = sorted([v for v in lz_lmp.get(lz, {}).values() if not np.isnan(v)],
                      reverse=True)
        if not vals:
            continue
        pct = np.linspace(0, 100, len(vals))
        ax.plot(pct, vals, color=ZONE_COLORS[lz], linewidth=2,
                label=lz, zorder=3)

    # Node percentile bands (5th/95th of all resource nodes per hour)
    per_hour_all = {}
    for h in hours:
        vals = [sp["ts"][h] for sp in nodes if h in sp["ts"]]
        if vals:
            per_hour_all[h] = vals

    node_p05 = sorted([np.percentile(v, 5)  for v in per_hour_all.values()], reverse=True)
    node_p95 = sorted([np.percentile(v, 95) for v in per_hour_all.values()], reverse=True)
    n = len(node_p05)
    if n:
        pct = np.linspace(0, 100, n)
        ax.fill_between(pct, node_p05, node_p95, alpha=0.12, color="#6b7280",
                        label="Node 5th–95th pctile band")

    ax.axhline(0, color="black", linewidth=0.6, linestyle="--")
    ax.set_xlabel("% of Hours Exceeding Value", fontsize=9)
    ax.set_ylabel("LMP ($/MWh)", fontsize=9)
    ax.set_title("Price Duration Curves — Load Zones + Node Band (30 days)", fontsize=12)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.2)
    ax.set_xlim(0, 100)
    fig.tight_layout()
    return _save(fig, "fig_06_price_duration_curves.png")


# ── 8. Load zone box plots ────────────────────────────────────────────────────

def fig_zone_boxplots(nodes):
    """Distribution of mean node LMP broken out by load zone."""
    by_zone = defaultdict(list)
    for n in nodes:
        lz = n["load_zone"]
        if lz in ZONE_COLORS:
            by_zone[lz].append(n["mean_lmp"])

    fig, ax = plt.subplots(figsize=(8, 5))
    positions = list(range(len(ZONE_ORDER)))
    bp = ax.boxplot(
        [by_zone.get(lz, []) for lz in ZONE_ORDER],
        positions=positions, widths=0.55, patch_artist=True,
        medianprops=dict(color="black", linewidth=2),
        whiskerprops=dict(linewidth=1.2),
        flierprops=dict(marker=".", markersize=3, alpha=0.5),
    )
    for patch, lz in zip(bp["boxes"], ZONE_ORDER):
        patch.set_facecolor(ZONE_COLORS[lz])
        patch.set_alpha(0.75)

    ax.set_xticks(positions)
    ax.set_xticklabels(ZONE_ORDER, fontsize=9)
    ax.set_ylabel("Mean 30-Day Node LMP ($/MWh)", fontsize=9)
    ax.set_title("Distribution of Node Mean LMPs by Load Zone", fontsize=11)
    ax.grid(True, alpha=0.2, axis="y")
    for i, lz in enumerate(ZONE_ORDER):
        vals = by_zone.get(lz, [])
        if vals:
            ax.text(i, ax.get_ylim()[1] * 0.97,
                    f"n={len(vals)}", ha="center", fontsize=7)
    fig.tight_layout()
    return _save(fig, "fig_07_zone_boxplots.png")


# ── 9. Correlation cluster map ────────────────────────────────────────────────

def fig_correlation_clusters(nodes, hours, max_nodes=80):
    """
    Cluster nodes by the correlation of their hourly LMP timeseries.
    Nodes that move together (corr ≈ 1) are in the same electrical zone.
    Nodes that decorrelate reveal transmission barriers.
    Colors are by cluster assignment on the map.
    """
    # Use the most-covered nodes (most complete timeseries)
    coverage = [(len([h for h in hours if h in n["ts"]]), n) for n in nodes]
    coverage.sort(key=lambda x: x[0], reverse=True)
    sel_nodes = [n for _, n in coverage[:max_nodes]]
    if len(sel_nodes) < 10:
        print("  Not enough nodes for correlation analysis, skipping.")
        return None

    # Build matrix (nodes × hours) for common hours
    common_hours = [h for h in hours if all(h in n["ts"] for n in sel_nodes)]
    if len(common_hours) < 24:
        # Fall back to pairwise available-hours correlation
        common_hours = hours

    mat = np.array([
        [n["ts"].get(h, np.nan) for h in common_hours]
        for n in sel_nodes
    ])

    # Compute correlation matrix, handling NaNs
    valid_mask = ~np.isnan(mat)
    N = len(sel_nodes)
    corr = np.eye(N)
    for i in range(N):
        for j in range(i + 1, N):
            mask = valid_mask[i] & valid_mask[j]
            if mask.sum() < 12:
                corr[i, j] = corr[j, i] = 0.0
                continue
            c = np.corrcoef(mat[i][mask], mat[j][mask])[0, 1]
            corr[i, j] = corr[j, i] = float(np.nan_to_num(c))

    # Hierarchical clustering on distance = 1 − corr
    dist = np.clip(1 - corr, 0, 2)
    np.fill_diagonal(dist, 0)
    try:
        condensed = squareform(dist, checks=False)
        linkage   = hierarchy.ward(condensed)
        n_clusters = 5
        labels    = hierarchy.fcluster(linkage, n_clusters, criterion="maxclust")
    except Exception as e:
        print(f"  Clustering failed: {e}")
        return None

    # ── Dendrogram ────────────────────────────────────────────────────────────
    fig_d, ax_d = plt.subplots(figsize=(14, 5))
    hierarchy.dendrogram(
        linkage, ax=ax_d, leaf_rotation=90, leaf_font_size=5,
        color_threshold=linkage[-n_clusters + 1, 2],
        labels=[n["name"] for n in sel_nodes],
    )
    ax_d.set_title(
        f"LMP Correlation Dendrogram — Top {max_nodes} Nodes\n"
        "(nodes that merge low are electrically close)", fontsize=11)
    ax_d.set_ylabel("Ward Linkage Distance\n(≈ 1 − Pearson correlation)", fontsize=8)
    ax_d.tick_params(axis="x", labelsize=4)
    fig_d.tight_layout()
    dend_name = _save(fig_d, "fig_08a_dendrogram.png")

    # ── Geographic cluster map ─────────────────────────────────────────────────
    cmap_cl  = plt.get_cmap("tab10")
    lats = [n["lat"] for n in sel_nodes]
    lons = [n["lon"] for n in sel_nodes]

    fig_m, ax_m = plt.subplots(figsize=(13, 9))
    setup_map_ax(ax_m, lons, lats)
    for cl in range(1, n_clusters + 1):
        idx  = [i for i, lb in enumerate(labels) if lb == cl]
        clat = [lats[i] for i in idx]
        clon = [lons[i] for i in idx]
        ax_m.scatter(clon, clat, s=22, color=cmap_cl(cl - 1),
                     label=f"Cluster {cl} (n={len(idx)})",
                     alpha=0.85, edgecolors="k", linewidths=0.3, zorder=3)
    ax_m.legend(fontsize=8, loc="upper left")
    ax_m.set_title(
        f"LMP Price Correlation Clusters (k={n_clusters})\n"
        "Nodes in the same cluster co-move in price → few binding constraints between them",
        fontsize=11,
    )
    fig_m.tight_layout()
    map_name = _save(fig_m, "fig_08b_cluster_map.png")

    return dend_name, map_name, labels, sel_nodes, n_clusters


# ── 10. Write report ──────────────────────────────────────────────────────────

def write_report(stats):
    lines = []
    a = lines.append

    a("# ERCOT LMP Congestion Analysis")
    a(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')} CPT  ")
    a(f"**Data window:** {stats['start_hour']} → {stats['end_hour']} (CPT, hourly SCED snapshots)  ")
    a(f"**Nodes with LMP + coordinates:** {stats['n_nodes']}  ")
    a(f"**Total hourly snapshots:** {stats['n_hours']}\n")

    a("---\n")
    a("## Key Findings\n")
    a(f"- **Mean system LMP spread** over the period: **${stats['mean_spread']:.2f}/MWh**  ")
    a(f"  *(spread = max − min LMP across all resource nodes per hour)*\n")
    a("- Load zone price ordering (cheapest → most expensive on average):\n")
    for lz, mean in stats["lz_means"]:
        a(f"  - `{lz}`: ${mean:.2f}/MWh avg\n")

    a("\n### Most Import-Constrained Nodes")
    a("*(mean LMP far above their load zone average — likely at the receiving end "
      "of a binding transmission constraint)*\n")
    a("| Node | Load Zone | Mean LMP | Zone Avg | Congestion Premium |")
    a("|------|-----------|----------|----------|--------------------|")
    for proxy, n in stats.get("top_high", []):
        lz  = n["load_zone"]
        lzm = stats["lz_mean_map"].get(lz, 0)
        a(f"| {n['name']} | {lz} | ${n['mean_lmp']:.2f} | ${lzm:.2f} | +${proxy:.2f} |")

    a("\n### Most Export-Constrained Nodes")
    a("*(mean LMP far below their load zone average — generation that cannot "
      "fully export due to transmission limits)*\n")
    a("| Node | Load Zone | Mean LMP | Zone Avg | Congestion Discount |")
    a("|------|-----------|----------|----------|--------------------|")
    for proxy, n in stats.get("top_low", []):
        lz  = n["load_zone"]
        lzm = stats["lz_mean_map"].get(lz, 0)
        a(f"| {n['name']} | {lz} | ${n['mean_lmp']:.2f} | ${lzm:.2f} | ${proxy:.2f} |")

    a("\n---\n")
    a("## Methodology\n")
    a("### What LMP Spread Tells Us About Line Capacity\n")
    a("In ERCOT's nodal pricing model, the **Locational Marginal Price (LMP)** at each "
      "settlement point is:\n")
    a("```\nLMP = Energy Component + Congestion Component + Loss Component\n```\n")
    a("When a transmission line reaches its thermal limit, the optimal power flow "
      "model assigns a **shadow price** to that constraint. This shadow price flows "
      "directly into the LMPs: nodes on the *import* side of the constraint pay more "
      "(to incentivise demand reduction or local generation), while nodes on the "
      "*export* side receive less (to incentivise more generation or demand increase).\n")
    a("Therefore:\n")
    a("- `LMP(A) − LMP(B) > 0` consistently → the path A→B is likely constrained, "
      "with the line carrying power from cheap B to expensive A\n")
    a("- A **high standard deviation** in `LMP(node)` over time indicates a node "
      "near a constraint that binds intermittently (e.g., only during peak hours "
      "or high-wind periods)\n")
    a("- The **congestion proxy** (`node_mean_LMP − zone_mean_LMP`) isolates the "
      "geographic component from the system-wide energy price\n")
    a("- **Correlation clusters** reveal groups of nodes that are electrically "
      "cohesive — few binding constraints exist *within* a cluster, but the "
      "boundaries between clusters are likely where constraints bind\n")

    a("\n---\n")
    a("## Figures\n")

    figs = [
        ("fig_01_system_spread.png",
         "**Fig 1 — System LMP Spread Time Series.** "
         "Top panel: hourly max−min spread across all resource nodes. "
         "Bottom panel: the four load zone prices. "
         "Spikes correspond to real congestion events; the dashed line is the 30-day mean spread."),
        ("fig_02_mean_lmp_map.png",
         "**Fig 2 — 30-Day Mean LMP by Node.** "
         "Geographic distribution of time-averaged prices. "
         "Red = expensive; blue = cheap. Persistent geographic gradients indicate "
         "recurring transmission barriers."),
        ("fig_03_volatility_map.png",
         "**Fig 3 — LMP Volatility Map (Std Dev).** "
         "High-volatility nodes (bright yellow) are near intermittently-binding "
         "constraints — they swing between cheap and expensive depending on load and dispatch."),
        ("fig_04_congestion_proxy_map.png",
         "**Fig 4 — Congestion Proxy Map.** "
         "Each node's mean LMP minus its load zone's mean LMP. "
         "Red nodes are systematically more expensive than their zone "
         "(import-constrained); blue nodes are systematically cheaper "
         "(export-constrained, typically generation-heavy areas with limited takeaway capacity)."),
        ("fig_05_temporal_heatmap.png",
         "**Fig 5 — Temporal Congestion Heatmap.** "
         "Average LMP spread by hour-of-day and day-of-week. "
         "Darker cells = more congestion. Visible patterns: "
         "afternoon peaks (high load), overnight lows (abundant wind), "
         "and weekday vs. weekend differences."),
        ("fig_06_price_duration_curves.png",
         "**Fig 6 — Price Duration Curves.** "
         "Fraction of hours at or above each price level, by load zone. "
         "The gap between zone curves shows inter-zonal congestion; "
         "the shaded band covers the 5th–95th percentile of all individual node prices."),
        ("fig_07_zone_boxplots.png",
         "**Fig 7 — Node LMP Distribution by Load Zone.** "
         "Spread within each zone shows intra-zonal congestion. "
         "Zones with wide distributions have more internal constraints."),
        ("fig_08a_dendrogram.png",
         "**Fig 8a — LMP Correlation Dendrogram.** "
         "Hierarchical clustering of node price timeseries. "
         "Nodes that merge at low height are highly correlated (electrically close). "
         "Tall merges reveal transmission barriers."),
        ("fig_08b_cluster_map.png",
         "**Fig 8b — LMP Correlation Cluster Map.** "
         "Geographic assignment of the five correlation clusters. "
         "Cluster boundaries approximate the locations of recurring transmission constraints."),
    ]

    for fname, caption in figs:
        a(f"### {fname.replace('_', ' ').replace('.png','').title()}\n")
        a(f"![{fname}](figures/{fname})\n")
        a(f"{caption}\n")

    a("\n---\n")
    a("## Data Provenance\n")
    a("- LMP data: ERCOT Public API, report NP6-788-CD (`lmp_node_zone_hub`), "
      "one SCED interval per hour\n")
    a("- Node coordinates: `grid_data/matching_results/texas_matched_substations_v6.csv`, "
      "OSM + EIA-860 multi-pass fuzzy matching\n")
    a("- Analysis code: `Realist/reports/congestion_analysis.py`\n")
    a("- Raw data cache: `Realist/reports/data/lmp_history.csv`\n")

    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"  Report written: {REPORT_PATH}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("ERCOT LMP Congestion Analysis")
    print("=" * 60)

    print("\n[1/8] Loading LMP history…")
    hours, sp_lmp, lz_lmp, hub_lmp = load_lmp_history()

    print("\n[2/8] Loading matched substations…")
    matched_subs = load_matched_substations()

    print("\n[2b/8] Building resource-node → substation mapping…")
    rn_to_sub = build_rn_to_substation()

    print("\n[3/8] Joining LMPs to coordinates…")
    nodes = join_lmp_to_coords(sp_lmp, matched_subs, hours, rn_to_sub)

    if not nodes:
        print("ERROR: No nodes with both LMP data and coordinates found.")
        return

    # Compute load zone means for report
    lz_means = {lz: float(np.nanmean(list(d.values())))
                 for lz, d in lz_lmp.items() if d}
    lz_means_sorted = sorted(lz_means.items(), key=lambda x: x[1])

    print("\n[4/8] Generating figures…")

    fname01, mean_spread = fig_system_spread(hours, sp_lmp, lz_lmp)
    fname02              = fig_mean_lmp_map(nodes)
    fname03              = fig_volatility_map(nodes)
    cong_result          = fig_congestion_proxy(nodes, lz_lmp, hours)
    fname05              = fig_temporal_heatmap(hours, sp_lmp)

    # Pass nodes with ts dict for price duration
    nodes_with_ts = [n for n in nodes]  # already have .ts
    fname06 = fig_price_duration(nodes_with_ts, lz_lmp, hours)
    fname07 = fig_zone_boxplots(nodes)

    print("\n[5/8] Running correlation clustering (top 80 nodes)…")
    cluster_result = fig_correlation_clusters(nodes, hours, max_nodes=80)

    print("\n[6/8] Writing report…")
    stats = {
        "start_hour":  hours[0]  if hours else "?",
        "end_hour":    hours[-1] if hours else "?",
        "n_nodes":     len(nodes),
        "n_hours":     len(hours),
        "mean_spread": mean_spread,
        "lz_means":    lz_means_sorted,
        "lz_mean_map": lz_means,
    }
    if cong_result:
        _, top_high, top_low, proxies, valid_nodes = cong_result
        stats["top_high"] = top_high
        stats["top_low"]  = top_low

    write_report(stats)

    print("\n" + "=" * 60)
    print("Done.  Output directory:", SCRIPT_DIR)
    print("  Report:  ERCOT_Congestion_Analysis.md")
    print("  Figures: figures/")
    print("=" * 60)


if __name__ == "__main__":
    main()
