import os
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd

from core.topology_generation import SubstationNode


DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


@dataclass
class NetworkEdge:
    from_id: int
    to_id: int
    length_km: float


@dataclass
class Network:
    nodes: Dict[int, Tuple[float, float]]  # id -> (lat, lng)
    edges: List[NetworkEdge]


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    lat1_rad = np.radians(lat1)
    lat2_rad = np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlng = np.radians(lng2 - lng1)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlng / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return float(R * c)


def load_texas7k_network(
    voltage_filter: Optional[List[float]] = None,
) -> Network:
    """Load Texas-7k bus/branch data as a simple undirected network.

    - Uses vatic/data/grids/Texas-7k/TX_Data/SourceData/{bus,branch}.csv
    - Keeps only rows where Branch Device Type == "Line" and Status == "Closed".
    - If voltage_filter is provided, keeps only edges where BOTH endpoint buses have BaseKV in that list.
    """
    base_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "vatic",
        "data",
        "grids",
        "Texas-7k",
        "TX_Data",
        "SourceData",
    )

    bus_path = os.path.join(base_path, "bus.csv")
    branch_path = os.path.join(base_path, "branch.csv")

    bus_df = pd.read_csv(bus_path)
    branch_df = pd.read_csv(branch_path)

    bus_df = bus_df.rename(columns={"Bus ID": "bus_id"})

    buses = bus_df.set_index("bus_id")

    # Full coordinate lookup (used to build edges, then pruned)
    all_coords: Dict[int, Tuple[float, float]] = {}
    for bus_id, row in buses.iterrows():
        all_coords[int(bus_id)] = (float(row["lat"]), float(row["lng"]))

    # Filter to line branches
    branch_df = branch_df[branch_df["Branch Device Type"] == "Line"]
    branch_df = branch_df[branch_df["Status"] == "Closed"]

    edges: List[NetworkEdge] = []
    connected_ids: set[int] = set()

    for _, row in branch_df.iterrows():
        from_id = int(row["From Bus"])
        to_id = int(row["To Bus"])

        if from_id not in all_coords or to_id not in all_coords:
            continue

        if voltage_filter is not None:
            from_kv = float(buses.loc[from_id, "BaseKV"])
            to_kv = float(buses.loc[to_id, "BaseKV"])
            if from_kv not in voltage_filter or to_kv not in voltage_filter:
                continue

        lat1, lng1 = all_coords[from_id]
        lat2, lng2 = all_coords[to_id]
        length_km = _haversine_km(lat1, lng1, lat2, lng2)
        edges.append(NetworkEdge(from_id=from_id, to_id=to_id, length_km=length_km))
        connected_ids.add(from_id)
        connected_ids.add(to_id)

    # Only include nodes that participate in at least one edge
    nodes: Dict[int, Tuple[float, float]] = {
        nid: all_coords[nid] for nid in connected_ids
    }

    return Network(nodes=nodes, edges=edges)


def load_dartboard_texas_network(voltage_kv: int) -> Network:
    """Load Dartboard synthetic Texas network for a given voltage.

    Uses:
      - data/processed/texas_substations_with_buses.csv for node positions
      - data/synthetic/texas_lines_{voltage}kv.csv for edges and lengths
    """
    substations_path = os.path.join(DATA_ROOT, "processed", "texas_substations_with_buses.csv")
    lines_path = os.path.join(DATA_ROOT, "synthetic", f"texas_lines_{voltage_kv}kv.csv")

    subs_df = pd.read_csv(substations_path)
    lines_df = pd.read_csv(lines_path)

    # Build node map from substation file
    sub_nodes: Dict[int, Tuple[float, float]] = {}
    for _, row in subs_df.iterrows():
        sub_id = int(row["substation_id"])
        sub_nodes[sub_id] = (float(row["lat"]), float(row["lng"]))

    nodes: Dict[int, Tuple[float, float]] = {}
    edges: List[NetworkEdge] = []

    for _, row in lines_df.iterrows():
        from_id = int(row["from_sub"])
        to_id = int(row["to_sub"])

        if from_id not in sub_nodes or to_id not in sub_nodes:
            continue

        nodes[from_id] = sub_nodes[from_id]
        nodes[to_id] = sub_nodes[to_id]

        length_km = float(row["length_km"])
        edges.append(NetworkEdge(from_id=from_id, to_id=to_id, length_km=length_km))

    return Network(nodes=nodes, edges=edges)


def load_calibration_network(voltage_kv: int) -> Network:
    """Load Dartboard-generated topology on Texas-7k buses from Calibration/outputs."""
    repo_root = os.path.dirname(os.path.dirname(__file__))
    lines_path = os.path.join(repo_root, "Calibration", "outputs",
                              f"texas7k_dartboard_lines_{voltage_kv}kv.csv")
    bus_path = os.path.join(
        repo_root, "vatic", "data", "grids", "Texas-7k",
        "TX_Data", "SourceData", "bus.csv",
    )

    bus_df = pd.read_csv(bus_path).rename(columns={"Bus ID": "bus_id"}).set_index("bus_id")
    all_coords: Dict[int, Tuple[float, float]] = {}
    for bus_id, row in bus_df.iterrows():
        all_coords[int(bus_id)] = (float(row["lat"]), float(row["lng"]))

    lines_df = pd.read_csv(lines_path)
    nodes: Dict[int, Tuple[float, float]] = {}
    edges: List[NetworkEdge] = []
    for _, row in lines_df.iterrows():
        from_id = int(row["from_sub"])
        to_id = int(row["to_sub"])
        if from_id in all_coords:
            nodes[from_id] = all_coords[from_id]
        if to_id in all_coords:
            nodes[to_id] = all_coords[to_id]
        edges.append(NetworkEdge(from_id=from_id, to_id=to_id, length_km=float(row["length_km"])))
    return Network(nodes=nodes, edges=edges)


def build_texas7k_substation_nodes_for_topology(
    min_kv_for_345: float = 300.0,
    min_kv_for_115: float = 100.0,
    max_kv_for_115: float = 200.0,
) -> List[SubstationNode]:
    """Build SubstationNode list from Texas-7k bus.csv for use with TopologyGenerator.

    - Marks has_345kv when BaseKV >= min_kv_for_345.
    - Marks has_115kv when min_kv_for_115 <= BaseKV <= max_kv_for_115.
    - Aggregates generator PMax from gen.csv through transformers to HV buses,
      since generators connect at low-voltage buses (13.8–24 kV) in the Texas-7k model.
    """
    from collections import defaultdict

    base_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "vatic",
        "data",
        "grids",
        "Texas-7k",
        "TX_Data",
        "SourceData",
    )
    bus_path = os.path.join(base_path, "bus.csv")
    gen_path = os.path.join(base_path, "gen.csv")
    branch_path = os.path.join(base_path, "branch.csv")

    bus_df = pd.read_csv(bus_path)
    bus_df = bus_df.rename(columns={"Bus ID": "bus_id"})
    bus_kv = bus_df.set_index("bus_id")["BaseKV"].to_dict()

    # --- Aggregate generator PMax to HV buses via transformers ---
    gen_df = pd.read_csv(gen_path)
    branch_df = pd.read_csv(branch_path)
    xfmrs = branch_df[branch_df["Xfrmr"] == "YES"]

    # Build transformer adjacency for BFS
    xfmr_adj: dict[int, set] = defaultdict(set)
    for _, row in xfmrs.iterrows():
        fb, tb = int(row["From Bus"]), int(row["To Bus"])
        xfmr_adj[fb].add(tb)
        xfmr_adj[tb].add(fb)

    def find_hv_bus(start_bus: int) -> Optional[int]:
        """BFS from a low-voltage gen bus through transformers to nearest HV bus."""
        visited = {start_bus}
        queue = [start_bus]
        while queue:
            current = queue.pop(0)
            kv = bus_kv.get(current, 0)
            if kv >= min_kv_for_115 and current != start_bus:
                return current
            for neighbor in xfmr_adj[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return None

    # Map each generator's PMax to its nearest HV bus
    hv_gen: dict[int, float] = defaultdict(float)
    for _, row in gen_df.iterrows():
        bus_id = int(row["Bus ID"])
        pmax = float(row["PMax MW"])
        my_kv = bus_kv.get(bus_id, 0)
        if my_kv >= min_kv_for_115:
            hv_gen[bus_id] += pmax
        else:
            hv_bus = find_hv_bus(bus_id)
            if hv_bus is not None:
                hv_gen[hv_bus] += pmax

    # --- Build SubstationNode list ---
    substations: List[SubstationNode] = []
    for _, row in bus_df.iterrows():
        base_kv = float(row["BaseKV"])
        has_345 = base_kv >= min_kv_for_345
        has_115 = min_kv_for_115 <= base_kv <= max_kv_for_115

        if not has_345 and not has_115:
            continue

        bus_id = int(row["bus_id"])
        sub = SubstationNode(
            sub_id=bus_id,
            lat=float(row["lat"]),
            lng=float(row["lng"]),
            mw_load=0.0 if pd.isna(row.get("MW Load", 0.0)) else float(row["MW Load"]),
            total_gen_mw=hv_gen.get(bus_id, 0.0),
            has_345kv=has_345,
            has_115kv=has_115,
        )
        substations.append(sub)

    return substations
