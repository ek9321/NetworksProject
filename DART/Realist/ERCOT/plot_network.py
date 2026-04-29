#!/usr/bin/env python3
"""
Plot the SCED network: 2,405 buses and ~22,500 branches on a Texas map outline.

Outputs:
  Realist/grid_data/network_plot.png
"""

import math
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.patches as mpatches

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO    = Path(__file__).resolve().parents[2]
DATA    = REPO / "Realist" / "grid_data"
SRC_DIR = DATA / "sced_inputs" / "SourceData"
OUT_PNG = DATA / "network_plot.png"

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
print("Loading bus.csv and branch.csv...")
bus_df = pd.read_csv(SRC_DIR / "bus.csv", dtype=str)
bus_df["lat"] = pd.to_numeric(bus_df["lat"], errors="coerce")
bus_df["lon"] = pd.to_numeric(bus_df["lng"], errors="coerce")
bus_df["kv"]  = pd.to_numeric(bus_df["BaseKV"], errors="coerce")
bus_df["bid"] = pd.to_numeric(bus_df["Bus ID"], errors="coerce")
bus_df = bus_df.dropna(subset=["lat", "lon"])

br_df = pd.read_csv(SRC_DIR / "branch.csv", dtype=str)
br_df["from_bid"] = pd.to_numeric(br_df["From Bus"], errors="coerce")
br_df["to_bid"]   = pd.to_numeric(br_df["To Bus"],   errors="coerce")
br_df["x_pu"]     = pd.to_numeric(br_df["X"],        errors="coerce")
br_df = br_df.dropna(subset=["from_bid", "to_bid"])

print(f"  Buses: {len(bus_df):,}  |  Branches: {len(br_df):,}")

# Build fast bid→(lat, lon) lookup
bid_to_loc = {
    int(row["bid"]): (float(row["lon"]), float(row["lat"]))
    for _, row in bus_df.iterrows()
}

# Separate line branches from transformer branches
line_br  = br_df[~br_df["UID"].str.startswith("XFMR")].copy()
xfmr_br  = br_df[ br_df["UID"].str.startswith("XFMR")].copy()

print(f"  Line branches: {len(line_br):,}  |  Transformer branches: {len(xfmr_br):,}")

# ---------------------------------------------------------------------------
# Zone → colour mapping
# ---------------------------------------------------------------------------
ZONE_COLORS = {
    "NORTH":   "#4e9af1",   # blue
    "HOUSTON": "#f4a261",   # orange
    "SOUTH":   "#2a9d8f",   # teal
    "WEST":    "#e76f51",   # red-orange
}
DEFAULT_COLOR = "#888888"

bus_df["_zone"] = bus_df["Zone"].str.strip().str.upper() if "Zone" in bus_df.columns else ""
bus_df["_color"] = bus_df["_zone"].map(ZONE_COLORS).fillna(DEFAULT_COLOR)

# Voltage → marker size
def kv_size(kv):
    if kv >= 345:
        return 12
    if kv >= 230:
        return 7
    return 4

bus_df["_ms"] = bus_df["kv"].apply(kv_size)

# ---------------------------------------------------------------------------
# Texas approximate bounding box
# ---------------------------------------------------------------------------
LON_MIN, LON_MAX = -107.0, -93.5
LAT_MIN, LAT_MAX =   25.5,  36.8

# Filter buses to Texas bounding box
bus_df = bus_df[
    (bus_df["lon"] >= LON_MIN) & (bus_df["lon"] <= LON_MAX) &
    (bus_df["lat"] >= LAT_MIN) & (bus_df["lat"] <= LAT_MAX)
]

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
print("Rendering plot...")
fig, ax = plt.subplots(figsize=(18, 14), dpi=150)
ax.set_facecolor("#1a1a2e")
fig.patch.set_facecolor("#1a1a2e")

# ── Draw branches (lines first, then transformers) ──────────────────────────

# Use X_pu as a proxy for line length → thin/faint long lines
X_MAX_DRAW = 0.5   # don't draw branches with X > 0.5 (very long/spurious)

print("  Drawing line branches...")
drawn_lines = 0
for _, row in line_br.iterrows():
    a, b, x = int(row["from_bid"]), int(row["to_bid"]), row["x_pu"]
    loc_a = bid_to_loc.get(a)
    loc_b = bid_to_loc.get(b)
    if loc_a is None or loc_b is None:
        continue
    if x > X_MAX_DRAW:
        continue
    # Colour by impedance: low X (short lines) bright, high X dim
    alpha  = max(0.08, 0.45 - x * 0.5)
    lwidth = max(0.15, 0.45 - x * 0.3)
    ax.plot([loc_a[0], loc_b[0]], [loc_a[1], loc_b[1]],
            color="#90caf9", alpha=alpha, linewidth=lwidth, zorder=1)
    drawn_lines += 1

print(f"    Drew {drawn_lines:,} line branches (X <= {X_MAX_DRAW})")

print("  Drawing transformer branches...")
for _, row in xfmr_br.iterrows():
    a, b = int(row["from_bid"]), int(row["to_bid"])
    loc_a = bid_to_loc.get(a)
    loc_b = bid_to_loc.get(b)
    if loc_a is None or loc_b is None:
        continue
    ax.plot([loc_a[0], loc_b[0]], [loc_a[1], loc_b[1]],
            color="#ffd700", alpha=0.6, linewidth=0.8, zorder=2)

# ── Draw buses ──────────────────────────────────────────────────────────────
print("  Drawing buses...")
for _, row in bus_df.iterrows():
    ax.scatter(row["lon"], row["lat"],
               s=row["_ms"], c=row["_color"],
               alpha=0.85, linewidths=0, zorder=3)

# ── Axes and labels ──────────────────────────────────────────────────────────
ax.set_xlim(LON_MIN, LON_MAX)
ax.set_ylim(LAT_MIN, LAT_MAX)
ax.set_xlabel("Longitude", color="white", fontsize=9)
ax.set_ylabel("Latitude",  color="white", fontsize=9)
ax.tick_params(colors="white")
for spine in ax.spines.values():
    spine.set_edgecolor("#444444")

ax.set_title(
    f"ERCOT Transmission Network — {len(bus_df):,} buses · {drawn_lines:,} branches (X ≤ {X_MAX_DRAW} pu)\n"
    f"138 kV+ buses, high/medium geo confidence only",
    color="white", fontsize=12, pad=10
)

# Legend – zones
zone_patches = [
    mpatches.Patch(color=c, label=z) for z, c in ZONE_COLORS.items()
]
# Legend – voltages
ms_legend = [
    mlines.Line2D([], [], color="white", marker="o", markersize=math.sqrt(12),
                  linestyle="None", label="≥ 345 kV"),
    mlines.Line2D([], [], color="white", marker="o", markersize=math.sqrt(7),
                  linestyle="None", label="230 kV"),
    mlines.Line2D([], [], color="white", marker="o", markersize=math.sqrt(4),
                  linestyle="None", label="138 kV"),
]
xfmr_line = mlines.Line2D([], [], color="#ffd700", linewidth=1.5,
                           linestyle="-", label="Transformer")

legend = ax.legend(
    handles=zone_patches + ms_legend + [xfmr_line],
    loc="lower right", framealpha=0.25, facecolor="#1a1a2e",
    labelcolor="white", fontsize=8, title="Zone / Voltage",
    title_fontsize=8
)

# ── Save ────────────────────────────────────────────────────────────────────
plt.tight_layout()
plt.savefig(OUT_PNG, dpi=150, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()

print(f"\nSaved → {OUT_PNG}")
print("Done.")
