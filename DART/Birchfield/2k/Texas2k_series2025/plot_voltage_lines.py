"""Parse Texas2k_series2025 PSS/E data and plot transmission lines by voltage level.

Reads:
  - .AUX file for substation coordinates and bus-to-substation mapping
  - .RAW file for branch (line) data and bus voltage levels

Produces:
  - texas2k_voltage_lines.png (all voltage levels on one map)
  - texas2k_voltage_panels.png (one panel per voltage level)
  - texas2k_stats.txt (network statistics by voltage)
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CASE_DIR = os.path.join(SCRIPT_DIR, "Texas2k_series25_case1_summerpeak")
AUX_FILE = os.path.join(CASE_DIR, "Texas2k_series25_case1_summerpeak.AUX")
RAW_FILE = os.path.join(CASE_DIR, "Texas2k_series25_case1_summerpeak.RAW")


# ── Data structures ──────────────────────────────────────────────────────

@dataclass
class Substation:
    number: int
    name: str
    lat: float
    lng: float


@dataclass
class Bus:
    number: int
    name: str
    nom_kv: float
    sub_number: int


@dataclass
class Branch:
    from_bus: int
    to_bus: int
    circuit: str
    status: int  # 1 = in service


# ── Parsers ──────────────────────────────────────────────────────────────

def parse_substations(aux_path: str) -> Dict[int, Substation]:
    """Parse Substation block from PowerWorld AUX file."""
    subs = {}
    in_block = False
    with open(aux_path, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("Substation ("):
                in_block = True
                continue
            if in_block and stripped == "{":
                continue
            if in_block and stripped == "}":
                break
            if not in_block:
                continue

            # Format: Number "Name" "IDExtra" Latitude Longitude ...
            # Use regex to handle quoted strings
            tokens = re.findall(r'"[^"]*"|\S+', stripped)
            if len(tokens) < 5:
                continue
            try:
                num = int(tokens[0])
                name = tokens[1].strip('"')
                lat = float(tokens[3])
                lng = float(tokens[4])
                subs[num] = Substation(number=num, name=name, lat=lat, lng=lng)
            except (ValueError, IndexError):
                continue
    return subs


def parse_buses(aux_path: str) -> Dict[int, Bus]:
    """Parse Bus block from PowerWorld AUX file."""
    buses = {}
    in_block = False
    brace_depth = 0
    with open(aux_path, "r") as f:
        for line in f:
            stripped = line.strip()
            # Look for Bus ( block - but not RatingSetNameBus etc.
            if re.match(r'^Bus \(Number', stripped):
                in_block = True
                continue
            if in_block and not brace_depth and stripped == "{":
                brace_depth = 1
                continue
            if in_block and brace_depth and stripped == "}":
                break
            if not in_block or not brace_depth:
                continue
            if stripped.startswith("//") or stripped.startswith("<"):
                continue

            # Format: Number FixedNumBus SubNodeNum "Name" NomkV ... SubNumber ...
            tokens = re.findall(r'"[^"]*"|\S+', stripped)
            if len(tokens) < 16:
                continue
            try:
                bus_num = int(tokens[0])
                name = tokens[3].strip('"')
                nom_kv = float(tokens[4])
                sub_num = int(tokens[15])
                buses[bus_num] = Bus(number=bus_num, name=name,
                                     nom_kv=nom_kv, sub_number=sub_num)
            except (ValueError, IndexError):
                continue
    return buses


def parse_branches_raw(raw_path: str) -> List[Branch]:
    """Parse branch data from PSS/E RAW file."""
    branches = []
    in_branch = False
    with open(raw_path, "r") as f:
        for line in f:
            stripped = line.strip()
            if "END OF GENERATOR DATA, BEGIN BRANCH DATA" in stripped:
                in_branch = True
                continue
            if "END OF BRANCH DATA" in stripped:
                break
            if not in_branch:
                continue
            if stripped.startswith("@") or stripped.startswith("0 /"):
                continue

            parts = stripped.split(",")
            if len(parts) < 3:
                continue
            try:
                from_bus = int(parts[0].strip())
                to_bus = int(parts[1].strip())
                circuit = parts[2].strip().strip("'").strip()
                # STAT field is at index 25 in v35 format
                # Simpler: find STAT - it's after the rates
                # In the data, STAT appears to be the field after the last rate
                # Let's just count: I,J,CKT,R,X,B,NAME,RATE1-12,GI,BI,GJ,BJ,STAT
                # = 0,1,2,3,4,5,6,7-18,19,20,21,22,23
                stat = int(parts[23].strip()) if len(parts) > 23 else 1
                branches.append(Branch(from_bus=from_bus, to_bus=to_bus,
                                       circuit=circuit, status=stat))
            except (ValueError, IndexError):
                continue
    return branches


def parse_transformers_raw(raw_path: str) -> List[Tuple[int, int, int]]:
    """Parse transformer data from PSS/E RAW file.

    Returns list of (from_bus, to_bus, status) tuples.
    Transformers connect different voltage levels at the same substation.
    """
    xfmrs = []
    in_xfmr = False
    line_count = 0
    current_record: List[str] = []

    with open(raw_path, "r") as f:
        for line in f:
            stripped = line.strip()
            if "BEGIN TRANSFORMER DATA" in stripped:
                in_xfmr = True
                continue
            if "END OF TRANSFORMER DATA" in stripped:
                break
            if not in_xfmr:
                continue
            if stripped.startswith("@") or stripped.startswith("0 /"):
                continue

            current_record.append(stripped)
            line_count += 1

            # 2-winding transformer: 4 data lines, 3-winding: 5 lines
            # First line has I, J, K - if K=0, it's 2-winding (4 lines)
            if line_count == 1:
                parts = stripped.split(",")
                if len(parts) >= 4:
                    try:
                        k = int(parts[2].strip())
                    except ValueError:
                        k = 0
                    num_lines = 5 if k != 0 else 4
                else:
                    num_lines = 4

            if line_count >= num_lines:
                # Parse first line for I, J, STAT
                parts = current_record[0].split(",")
                try:
                    from_bus = int(parts[0].strip())
                    to_bus = int(parts[1].strip())
                    stat = int(parts[11].strip()) if len(parts) > 11 else 1
                    xfmrs.append((from_bus, to_bus, stat))
                except (ValueError, IndexError):
                    pass
                current_record = []
                line_count = 0

    return xfmrs


# ── Analysis ─────────────────────────────────────────────────────────────

def classify_voltage(kv: float) -> Optional[str]:
    """Map nominal kV to a voltage class label."""
    if kv >= 300:
        return "345 kV"
    elif kv >= 200:
        return "230 kV"
    elif kv >= 100:
        return "115 kV"
    elif kv >= 60:
        return "69 kV"
    else:
        return None  # distribution level, skip


def compute_line_length_km(lat1: float, lng1: float,
                           lat2: float, lng2: float) -> float:
    """Haversine distance in km."""
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlng = np.radians(lng2 - lng1)
    a = (np.sin(dlat / 2) ** 2 +
         np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) *
         np.sin(dlng / 2) ** 2)
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


# ── Visualization ────────────────────────────────────────────────────────

VOLTAGE_COLORS = {
    "345 kV": "#e74c3c",   # red
    "230 kV": "#e67e22",   # orange
    "115 kV": "#2980b9",   # blue
    "69 kV":  "#27ae60",   # green
}

VOLTAGE_ORDER = ["345 kV", "230 kV", "115 kV", "69 kV"]


def main():
    print("Parsing AUX substations...")
    subs = parse_substations(AUX_FILE)
    print(f"  Found {len(subs)} substations")

    print("Parsing AUX buses...")
    buses = parse_buses(AUX_FILE)
    print(f"  Found {len(buses)} buses")

    print("Parsing RAW branches...")
    branches = parse_branches_raw(RAW_FILE)
    print(f"  Found {len(branches)} branches")

    print("Parsing RAW transformers...")
    xfmrs = parse_transformers_raw(RAW_FILE)
    print(f"  Found {len(xfmrs)} transformers")

    # Build bus→substation coordinate lookup
    bus_coords: Dict[int, Tuple[float, float]] = {}
    bus_voltage: Dict[int, float] = {}
    for bus in buses.values():
        if bus.sub_number in subs:
            s = subs[bus.sub_number]
            bus_coords[bus.number] = (s.lat, s.lng)
        bus_voltage[bus.number] = bus.nom_kv

    # Voltage distribution of buses
    print("\nBus voltage distribution:")
    kv_counts = Counter(b.nom_kv for b in buses.values())
    for kv in sorted(kv_counts.keys(), reverse=True):
        print(f"  {kv:8.1f} kV: {kv_counts[kv]:4d} buses")

    # Group branches by voltage class (use the higher voltage of the two endpoints)
    # Only include same-voltage branches (branches between different voltages are transformers)
    lines_by_voltage: Dict[str, List[Tuple[int, int, float]]] = defaultdict(list)
    skipped = 0
    seen_edges: Dict[str, set] = defaultdict(set)

    for br in branches:
        if br.status != 1:
            continue
        if br.from_bus not in bus_voltage or br.to_bus not in bus_voltage:
            skipped += 1
            continue
        if br.from_bus not in bus_coords or br.to_bus not in bus_coords:
            skipped += 1
            continue

        kv_from = bus_voltage[br.from_bus]
        kv_to = bus_voltage[br.to_bus]

        # For same-voltage branches → transmission lines
        # For different-voltage → transformer (skip for line plotting)
        if abs(kv_from - kv_to) > 1.0:
            continue

        vclass = classify_voltage(kv_from)
        if vclass is None:
            continue

        # Map to substations for deduplication
        sub_from = buses[br.from_bus].sub_number
        sub_to = buses[br.to_bus].sub_number
        if sub_from == sub_to:
            continue  # internal substation connection

        edge_key = (min(sub_from, sub_to), max(sub_from, sub_to))
        if edge_key in seen_edges[vclass]:
            continue  # parallel circuit
        seen_edges[vclass].add(edge_key)

        lat1, lng1 = bus_coords[br.from_bus]
        lat2, lng2 = bus_coords[br.to_bus]
        length = compute_line_length_km(lat1, lng1, lat2, lng2)
        lines_by_voltage[vclass].append((br.from_bus, br.to_bus, length))

    # Print statistics
    stats_lines = []
    stats_lines.append("=" * 70)
    stats_lines.append("Texas2k_series2025 Network Statistics")
    stats_lines.append("=" * 70)

    for vclass in VOLTAGE_ORDER:
        edges = lines_by_voltage.get(vclass, [])
        if not edges:
            continue

        # Count unique substations at this voltage
        sub_ids = set()
        for from_bus, to_bus, _ in edges:
            sub_ids.add(buses[from_bus].sub_number)
            sub_ids.add(buses[to_bus].sub_number)

        n_nodes = len(sub_ids)
        n_edges = len(edges)
        mn_ratio = n_edges / n_nodes if n_nodes > 0 else 0
        lengths = [l for _, _, l in edges]

        # Degree distribution
        degree = Counter()
        for from_bus, to_bus, _ in edges:
            degree[buses[from_bus].sub_number] += 1
            degree[buses[to_bus].sub_number] += 1
        deg_vals = list(degree.values())
        deg1_frac = sum(1 for d in deg_vals if d == 1) / len(deg_vals) if deg_vals else 0
        deg3plus_frac = sum(1 for d in deg_vals if d >= 3) / len(deg_vals) if deg_vals else 0
        mean_deg = np.mean(deg_vals) if deg_vals else 0

        # Meshedness
        meshedness = (n_edges - n_nodes + 1) / (2 * n_nodes - 5) if n_nodes > 2 else 0

        stats_lines.append(f"\n{vclass}")
        stats_lines.append(f"  Substations: {n_nodes}")
        stats_lines.append(f"  Unique lines: {n_edges}")
        stats_lines.append(f"  m/n ratio: {mn_ratio:.3f}")
        stats_lines.append(f"  Mean degree: {mean_deg:.2f}")
        stats_lines.append(f"  Meshedness: {meshedness:.3f}")
        stats_lines.append(f"  deg1 fraction: {deg1_frac:.3f} ({deg1_frac*100:.1f}%)")
        stats_lines.append(f"  deg3+ fraction: {deg3plus_frac:.3f} ({deg3plus_frac*100:.1f}%)")
        stats_lines.append(f"  Line lengths: mean={np.mean(lengths):.1f} km, "
                          f"median={np.median(lengths):.1f} km, "
                          f"min={np.min(lengths):.1f} km, max={np.max(lengths):.1f} km")

    stats_text = "\n".join(stats_lines)
    print(stats_text)

    stats_path = os.path.join(SCRIPT_DIR, "texas2k_stats.txt")
    with open(stats_path, "w") as f:
        f.write(stats_text + "\n")
    print(f"\nSaved stats to {stats_path}")

    # ── Plot 1: All voltages on one map ──────────────────────────────────
    print("\nPlotting combined voltage map...")

    # Compute bounds from all substations
    all_lats = [s.lat for s in subs.values()]
    all_lngs = [s.lng for s in subs.values()]
    lat_pad = (max(all_lats) - min(all_lats)) * 0.03
    lng_pad = (max(all_lngs) - min(all_lngs)) * 0.03
    bounds = {
        "lat_min": min(all_lats) - lat_pad,
        "lat_max": max(all_lats) + lat_pad,
        "lng_min": min(all_lngs) - lng_pad,
        "lng_max": max(all_lngs) + lng_pad,
    }

    fig, ax = plt.subplots(figsize=(14, 10))

    # Draw lines by voltage (lower voltages first so higher voltages are on top)
    for vclass in reversed(VOLTAGE_ORDER):
        edges = lines_by_voltage.get(vclass, [])
        if not edges:
            continue
        color = VOLTAGE_COLORS[vclass]
        lw = {"345 kV": 1.2, "230 kV": 0.9, "115 kV": 0.5, "69 kV": 0.3}[vclass]
        alpha = {"345 kV": 0.8, "230 kV": 0.7, "115 kV": 0.5, "69 kV": 0.4}[vclass]

        for from_bus, to_bus, _ in edges:
            lat1, lng1 = bus_coords[from_bus]
            lat2, lng2 = bus_coords[to_bus]
            ax.plot([lng1, lng2], [lat1, lat2],
                    color=color, linewidth=lw, alpha=alpha, zorder=2)

        # Add to legend
        ax.plot([], [], color=color, linewidth=lw * 2,
                label=f"{vclass} ({len(edges)} lines)")

    # Draw substations
    sub_lats = [s.lat for s in subs.values()]
    sub_lngs = [s.lng for s in subs.values()]
    ax.scatter(sub_lngs, sub_lats, c="#555", s=2, alpha=0.4, zorder=3)

    ax.set_xlim(bounds["lng_min"], bounds["lng_max"])
    ax.set_ylim(bounds["lat_min"], bounds["lat_max"])
    mean_lat = np.mean(ax.get_ylim())
    ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
    ax.set_xlabel("Longitude", fontsize=10)
    ax.set_ylabel("Latitude", fontsize=10)
    ax.set_title("Texas2k_series2025 — Transmission Lines by Voltage Level",
                 fontsize=14, fontweight="bold")
    ax.legend(loc="upper left", fontsize=10, framealpha=0.9)
    ax.grid(True, linestyle=":", alpha=0.25)

    out_path = os.path.join(SCRIPT_DIR, "texas2k_voltage_lines.png")
    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out_path}")

    # ── Plot 2: Per-voltage panels ───────────────────────────────────────
    print("Plotting per-voltage panels...")

    active_voltages = [v for v in VOLTAGE_ORDER if lines_by_voltage.get(v)]
    n_panels = len(active_voltages)
    if n_panels == 0:
        print("No voltage lines to plot!")
        return

    ncols = min(n_panels, 2)
    nrows = (n_panels + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(9 * ncols, 7 * nrows),
                              squeeze=False)

    for idx, vclass in enumerate(active_voltages):
        row, col = divmod(idx, ncols)
        ax = axes[row][col]
        edges = lines_by_voltage[vclass]
        color = VOLTAGE_COLORS[vclass]

        # Draw lines
        for from_bus, to_bus, _ in edges:
            lat1, lng1 = bus_coords[from_bus]
            lat2, lng2 = bus_coords[to_bus]
            ax.plot([lng1, lng2], [lat1, lat2],
                    color=color, linewidth=0.6, alpha=0.6, zorder=2)

        # Draw nodes at this voltage
        sub_ids = set()
        for from_bus, to_bus, _ in edges:
            sub_ids.add(buses[from_bus].sub_number)
            sub_ids.add(buses[to_bus].sub_number)

        node_lats = [subs[s].lat for s in sub_ids if s in subs]
        node_lngs = [subs[s].lng for s in sub_ids if s in subs]
        ax.scatter(node_lngs, node_lats, c=color, s=4, alpha=0.7,
                   edgecolors="none", zorder=3)

        # Compute stats for annotation
        degree = Counter()
        for from_bus, to_bus, _ in edges:
            degree[buses[from_bus].sub_number] += 1
            degree[buses[to_bus].sub_number] += 1
        deg_vals = list(degree.values())
        n_nodes = len(sub_ids)
        n_edges = len(edges)
        mn = n_edges / n_nodes if n_nodes else 0
        mean_deg = np.mean(deg_vals) if deg_vals else 0
        deg1_f = sum(1 for d in deg_vals if d == 1) / len(deg_vals) if deg_vals else 0
        deg3_f = sum(1 for d in deg_vals if d >= 3) / len(deg_vals) if deg_vals else 0
        lengths = [l for _, _, l in edges]
        mesh = (n_edges - n_nodes + 1) / (2 * n_nodes - 5) if n_nodes > 2 else 0

        info = (f"n={n_nodes}  m={n_edges}  m/n={mn:.3f}\n"
                f"<deg>={mean_deg:.2f}  mesh={mesh:.3f}\n"
                f"d1%={deg1_f*100:.1f}  d3+%={deg3_f*100:.1f}\n"
                f"<len>={np.mean(lengths):.1f} km")
        ax.text(0.02, 0.98, info, transform=ax.transAxes,
                fontsize=9, fontfamily="monospace", verticalalignment="top",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                          edgecolor="#999", alpha=0.85))

        ax.set_xlim(bounds["lng_min"], bounds["lng_max"])
        ax.set_ylim(bounds["lat_min"], bounds["lat_max"])
        ax.set_aspect(1.0 / np.cos(np.radians(mean_lat)))
        ax.set_title(f"{vclass} ({n_nodes} subs, {n_edges} lines)",
                     fontsize=12, fontweight="bold", color=color)
        ax.grid(True, linestyle=":", alpha=0.25)
        ax.tick_params(labelsize=8)

    # Hide empty panels
    for idx in range(len(active_voltages), nrows * ncols):
        row, col = divmod(idx, ncols)
        axes[row][col].set_visible(False)

    fig.suptitle("Texas2k_series2025 — Per-Voltage Topology",
                 fontsize=15, fontweight="bold", y=1.01)
    fig.tight_layout()
    out_path = os.path.join(SCRIPT_DIR, "texas2k_voltage_panels.png")
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out_path}")

    # ── Plot 3: Degree distribution by voltage ───────────────────────────
    print("Plotting degree distributions...")

    fig, axes = plt.subplots(1, len(active_voltages),
                              figsize=(5 * len(active_voltages), 4),
                              squeeze=False)

    for idx, vclass in enumerate(active_voltages):
        ax = axes[0][idx]
        edges = lines_by_voltage[vclass]
        color = VOLTAGE_COLORS[vclass]

        degree = Counter()
        for from_bus, to_bus, _ in edges:
            degree[buses[from_bus].sub_number] += 1
            degree[buses[to_bus].sub_number] += 1

        deg_counts = Counter(degree.values())
        max_deg = max(deg_counts.keys())
        degs = list(range(1, max_deg + 1))
        fracs = [deg_counts.get(d, 0) / len(degree) for d in degs]

        ax.bar(degs, fracs, color=color, alpha=0.8, edgecolor="white")
        ax.set_xlabel("Degree", fontsize=10)
        ax.set_ylabel("Fraction", fontsize=10)
        ax.set_title(f"{vclass}", fontsize=11, fontweight="bold", color=color)
        ax.set_xticks(degs)
        ax.grid(axis="y", linestyle=":", alpha=0.3)

    fig.suptitle("Texas2k — Degree Distribution by Voltage",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    out_path = os.path.join(SCRIPT_DIR, "texas2k_degree_dist.png")
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
