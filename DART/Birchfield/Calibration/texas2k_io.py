"""Load Texas2k_series2025 data for use with TopologyGenerator and network metrics.

Parses:
  - AUX file: substations (lat/lng), buses (NomkV, SubNumber)
  - RAW file: loads (PL), generators (PG), branches (line data)

Produces:
  - SubstationNode list compatible with TopologyGenerator
  - Network objects (reference topology) for metric comparison
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from core.topology_generation import SubstationNode
from .network_io import Network, NetworkEdge

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
CASE_DIR = os.path.join(
    REPO_ROOT, "Texas2k_series2025", "Texas2k_series25_case1_summerpeak"
)
AUX_FILE = os.path.join(CASE_DIR, "Texas2k_series25_case1_summerpeak.AUX")
RAW_FILE = os.path.join(CASE_DIR, "Texas2k_series25_case1_summerpeak.RAW")


# ── AUX Parsers ──────────────────────────────────────────────────────────

def _parse_aux_substations(aux_path: str) -> Dict[int, Tuple[str, float, float]]:
    """Parse Substation block → {number: (name, lat, lng)}."""
    subs: Dict[int, Tuple[str, float, float]] = {}
    in_block = False
    with open(aux_path, "r") as f:
        for line in f:
            s = line.strip()
            if s.startswith("Substation ("):
                in_block = True
                continue
            if in_block and s == "{":
                continue
            if in_block and s == "}":
                break
            if not in_block:
                continue
            tokens = re.findall(r'"[^"]*"|\S+', s)
            if len(tokens) < 5:
                continue
            try:
                num = int(tokens[0])
                name = tokens[1].strip('"')
                lat = float(tokens[3])
                lng = float(tokens[4])
                subs[num] = (name, lat, lng)
            except (ValueError, IndexError):
                continue
    return subs


def _parse_aux_buses(aux_path: str) -> Dict[int, Tuple[float, int]]:
    """Parse Bus block → {bus_number: (nom_kv, sub_number)}.

    Bus line format (space-separated, with quoted strings):
    Number FixedNumBus SubNodeNum "Name" NomkV ... SubNumber(field 15, 0-indexed) ...
    """
    buses: Dict[int, Tuple[float, int]] = {}
    in_block = False
    brace_depth = 0
    with open(aux_path, "r") as f:
        for line in f:
            s = line.strip()
            if re.match(r"^Bus \(Number", s):
                in_block = True
                continue
            if in_block and not brace_depth and s == "{":
                brace_depth = 1
                continue
            if in_block and brace_depth and s == "}":
                break
            if not in_block or not brace_depth:
                continue
            if s.startswith("//") or s.startswith("<"):
                continue
            tokens = re.findall(r'"[^"]*"|\S+', s)
            if len(tokens) < 16:
                continue
            try:
                bus_num = int(tokens[0])
                nom_kv = float(tokens[4])
                sub_num = int(tokens[15])
                buses[bus_num] = (nom_kv, sub_num)
            except (ValueError, IndexError):
                continue
    return buses


# ── RAW Parsers ──────────────────────────────────────────────────────────

def _parse_raw_loads(raw_path: str) -> Dict[int, float]:
    """Parse LOAD DATA → {bus_number: total_PL_MW}."""
    loads: Dict[int, float] = defaultdict(float)
    in_section = False
    with open(raw_path, "r") as f:
        for line in f:
            s = line.strip()
            if "BEGIN LOAD DATA" in s:
                in_section = True
                continue
            if "END OF LOAD DATA" in s:
                break
            if not in_section or s.startswith("@") or s.startswith("0 /"):
                continue
            parts = s.split(",")
            if len(parts) < 6:
                continue
            try:
                bus = int(parts[0].strip())
                pl = float(parts[5].strip())
                loads[bus] += pl
            except (ValueError, IndexError):
                continue
    return dict(loads)


def _parse_raw_generators(raw_path: str) -> Dict[int, float]:
    """Parse GENERATOR DATA → {bus_number: total_PG_MW}."""
    gens: Dict[int, float] = defaultdict(float)
    in_section = False
    with open(raw_path, "r") as f:
        for line in f:
            s = line.strip()
            if "BEGIN GENERATOR DATA" in s:
                in_section = True
                continue
            if "END OF GENERATOR DATA" in s:
                break
            if not in_section or s.startswith("@") or s.startswith("0 /"):
                continue
            parts = s.split(",")
            if len(parts) < 3:
                continue
            try:
                bus = int(parts[0].strip())
                pg = float(parts[2].strip())
                gens[bus] += pg
            except (ValueError, IndexError):
                continue
    return dict(gens)


def _parse_raw_branches(raw_path: str) -> List[Tuple[int, int, int]]:
    """Parse BRANCH DATA → [(from_bus, to_bus, status), ...]."""
    branches: List[Tuple[int, int, int]] = []
    in_section = False
    with open(raw_path, "r") as f:
        for line in f:
            s = line.strip()
            if "BEGIN BRANCH DATA" in s:
                in_section = True
                continue
            if "END OF BRANCH DATA" in s:
                break
            if not in_section or s.startswith("@") or s.startswith("0 /"):
                continue
            parts = s.split(",")
            if len(parts) < 3:
                continue
            try:
                from_bus = int(parts[0].strip())
                to_bus = int(parts[1].strip())
                stat = int(parts[23].strip()) if len(parts) > 23 else 1
                branches.append((from_bus, to_bus, stat))
            except (ValueError, IndexError):
                continue
    return branches


# ── Haversine ────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlng = np.radians(lng2 - lng1)
    a = (np.sin(dlat / 2) ** 2 +
         np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) *
         np.sin(dlng / 2) ** 2)
    return float(R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a)))


# ── Public API ───────────────────────────────────────────────────────────

def load_texas2k_substations(hv_class: str = "500kv") -> List[SubstationNode]:
    """Load Texas2k substations as SubstationNode list for TopologyGenerator.

    hv_class controls what gets the has_345kv flag (used by TopologyGenerator
    when voltage_kv=345):
      - "500kv": only subs with buses >= 300 kV get has_345kv (182 subs)
      - "500+230kv": subs with buses >= 200 kV get has_345kv (300 subs)

    has_115kv is always set for subs with buses in [100, 200) kV.

    Load and generation are aggregated per substation from all buses.
    """
    aux_subs = _parse_aux_substations(AUX_FILE)
    aux_buses = _parse_aux_buses(AUX_FILE)
    raw_loads = _parse_raw_loads(RAW_FILE)
    raw_gens = _parse_raw_generators(RAW_FILE)

    # Aggregate per substation
    sub_has_500: Set[int] = set()    # >= 300 kV
    sub_has_230: Set[int] = set()    # 200-299 kV
    sub_has_115: Set[int] = set()    # 100-199 kV
    sub_load: Dict[int, float] = defaultdict(float)
    sub_gen: Dict[int, float] = defaultdict(float)

    for bus_num, (nom_kv, sub_num) in aux_buses.items():
        if nom_kv >= 300:
            sub_has_500.add(sub_num)
        elif nom_kv >= 200:
            sub_has_230.add(sub_num)
        elif nom_kv >= 100:
            sub_has_115.add(sub_num)

        if bus_num in raw_loads:
            sub_load[sub_num] += raw_loads[bus_num]
        if bus_num in raw_gens:
            sub_gen[sub_num] += raw_gens[bus_num]

    # Build SubstationNode list
    nodes: List[SubstationNode] = []
    for sub_num, (name, lat, lng) in aux_subs.items():
        if hv_class == "500kv":
            has_345 = sub_num in sub_has_500
        else:  # "500+230kv"
            has_345 = sub_num in sub_has_500 or sub_num in sub_has_230
        has_115 = sub_num in sub_has_115
        if not has_345 and not has_115:
            continue
        nodes.append(SubstationNode(
            sub_id=sub_num,
            lat=lat,
            lng=lng,
            mw_load=sub_load.get(sub_num, 0.0),
            total_gen_mw=sub_gen.get(sub_num, 0.0),
            has_345kv=has_345,
            has_115kv=has_115,
        ))
    return nodes


def load_texas2k_reference_network(voltage_class: str) -> Network:
    """Load the Texas2k reference topology as a Network for metric comparison.

    voltage_class: "500kv" (>=300), "230kv" (200-299), "115kv" (100-199)
    """
    aux_subs = _parse_aux_substations(AUX_FILE)
    aux_buses = _parse_aux_buses(AUX_FILE)
    raw_branches = _parse_raw_branches(RAW_FILE)

    # Voltage range for this class
    if voltage_class == "500kv":
        kv_min, kv_max = 300.0, 9999.0
    elif voltage_class == "230kv":
        kv_min, kv_max = 200.0, 299.9
    elif voltage_class == "115kv":
        kv_min, kv_max = 100.0, 199.9
    else:
        raise ValueError(f"Unknown voltage_class: {voltage_class}")

    # Bus → (nom_kv, sub_number)
    bus_kv = {b: kv for b, (kv, _) in aux_buses.items()}
    bus_sub = {b: s for b, (_, s) in aux_buses.items()}

    # Sub → (lat, lng)
    sub_coords = {num: (lat, lng) for num, (_, lat, lng) in aux_subs.items()}

    # Filter branches: same-voltage, in-service, different substations
    seen_edges: set = set()
    nodes: Dict[int, Tuple[float, float]] = {}
    edges: List[NetworkEdge] = []

    for from_bus, to_bus, stat in raw_branches:
        if stat != 1:
            continue
        kv_from = bus_kv.get(from_bus, 0)
        kv_to = bus_kv.get(to_bus, 0)
        if abs(kv_from - kv_to) > 1.0:
            continue
        if not (kv_min <= kv_from <= kv_max):
            continue

        sub_from = bus_sub.get(from_bus)
        sub_to = bus_sub.get(to_bus)
        if sub_from is None or sub_to is None or sub_from == sub_to:
            continue

        edge_key = (min(sub_from, sub_to), max(sub_from, sub_to))
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        if sub_from not in sub_coords or sub_to not in sub_coords:
            continue

        lat1, lng1 = sub_coords[sub_from]
        lat2, lng2 = sub_coords[sub_to]
        length = _haversine_km(lat1, lng1, lat2, lng2)

        nodes[sub_from] = sub_coords[sub_from]
        nodes[sub_to] = sub_coords[sub_to]
        edges.append(NetworkEdge(from_id=sub_from, to_id=sub_to, length_km=length))

    return Network(nodes=nodes, edges=edges)
