from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from scipy.stats import wasserstein_distance

from .network_io import Network, NetworkEdge


@dataclass
class DegreeStats:
    degree_counts: Counter
    mean_degree: float
    max_degree: int


@dataclass
class LengthStats:
    mean_km: float
    median_km: float
    max_km: float


@dataclass
class NetworkStats:
    num_nodes: int
    num_edges: int
    mn_ratio: float
    degree_stats: DegreeStats
    length_stats: LengthStats
    intersection_rate: float
    # Shape metrics
    meshedness: float
    deg1_frac: float
    deg2_frac: float
    deg3plus_frac: float
    degree_entropy: float


def compute_degree_stats(network: Network) -> DegreeStats:
    degree = Counter()
    for edge in network.edges:
        degree[edge.from_id] += 1
        degree[edge.to_id] += 1

    if not degree:
        return DegreeStats(degree_counts=Counter(), mean_degree=0.0, max_degree=0)

    degrees = list(degree.values())
    mean_degree = float(np.mean(degrees))
    max_degree = int(max(degrees))
    return DegreeStats(degree_counts=degree, mean_degree=mean_degree, max_degree=max_degree)


def compute_degree_distribution(network: Network) -> Dict[int, float]:
    """Return {degree: fraction_of_nodes} for degrees 1..max."""
    degree = Counter()
    for edge in network.edges:
        degree[edge.from_id] += 1
        degree[edge.to_id] += 1

    if not degree:
        return {}

    n = len(degree)
    degree_values = Counter(degree.values())
    return {d: count / n for d, count in sorted(degree_values.items())}


def compute_degree_fractions(network: Network) -> Tuple[float, float, float, float]:
    """Return (deg1_frac, deg2_frac, deg3plus_frac, degree_entropy).

    deg1_frac: fraction of nodes with degree 1 (leaf/spur nodes)
    deg2_frac: fraction of nodes with degree 2 (pass-through)
    deg3plus_frac: fraction of nodes with degree >= 3 (branching/mesh)
    degree_entropy: Shannon entropy of degree distribution
    """
    degree = Counter()
    for edge in network.edges:
        degree[edge.from_id] += 1
        degree[edge.to_id] += 1

    if not degree:
        return 0.0, 0.0, 0.0, 0.0

    n = len(degree)
    deg_values = list(degree.values())

    deg1 = sum(1 for d in deg_values if d == 1) / n
    deg2 = sum(1 for d in deg_values if d == 2) / n
    deg3plus = sum(1 for d in deg_values if d >= 3) / n

    # Shannon entropy of degree distribution
    deg_counts = Counter(deg_values)
    probs = np.array([c / n for c in deg_counts.values()], dtype=float)
    entropy = float(-np.sum(probs * np.log2(probs + 1e-12)))

    return deg1, deg2, deg3plus, entropy


def compute_meshedness(network: Network) -> float:
    """Meshedness = (m - n + c) / (2n - 5) for a planar graph.

    Where c = number of connected components.
    Range: 0 = tree (or forest), approaching 1 = maximally planar.
    Uses Euler's formula: independent cycles = m - n + c.
    """
    n = len(network.nodes)
    m = len(network.edges)
    if n < 3:
        return 0.0

    # Count connected components via BFS
    adj: Dict[int, set] = defaultdict(set)
    for edge in network.edges:
        adj[edge.from_id].add(edge.to_id)
        adj[edge.to_id].add(edge.from_id)

    visited = set()
    components = 0
    for node_id in network.nodes:
        if node_id not in visited:
            components += 1
            queue = [node_id]
            visited.add(node_id)
            while queue:
                current = queue.pop()
                for neighbor in adj[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

    independent_cycles = m - n + components
    max_cycles = 2 * n - 5  # max for planar graph
    if max_cycles <= 0:
        return 0.0

    return float(independent_cycles) / float(max_cycles)


def compute_length_histogram_distance(
    lengths_a: List[float],
    lengths_b: List[float],
) -> float:
    """Earth Mover's Distance between two line length distributions.

    Returns a scalar distance (lower = more similar).
    """
    if not lengths_a or not lengths_b:
        return 999.0

    return float(wasserstein_distance(lengths_a, lengths_b))


def compute_category_breakdown(category_list: List[str]) -> Dict[str, float]:
    """Return {category: fraction} from a list of category strings."""
    if not category_list:
        return {}
    counts = Counter(category_list)
    total = len(category_list)
    return {cat: count / total for cat, count in sorted(counts.items())}


def compute_length_stats(network: Network) -> LengthStats:
    if not network.edges:
        return LengthStats(mean_km=0.0, median_km=0.0, max_km=0.0)

    lengths = np.array([e.length_km for e in network.edges], dtype=float)
    return LengthStats(
        mean_km=float(np.mean(lengths)),
        median_km=float(np.median(lengths)),
        max_km=float(np.max(lengths)),
    )


def compute_intersection_rate(network: Network) -> float:
    """Compute fraction of edges that have at least one geometric intersection.

    This is O(E^2) with a cheap bounding-box prefilter; acceptable for one-off
    calibration runs on ~10k lines.
    """
    n_edges = len(network.edges)
    if n_edges <= 1:
        return 0.0

    # Precompute coordinates
    coords: Dict[int, Tuple[float, float]] = network.nodes

    def edge_bbox(e: NetworkEdge) -> Tuple[float, float, float, float]:
        x1, y1 = coords[e.from_id][1], coords[e.from_id][0]
        x2, y2 = coords[e.to_id][1], coords[e.to_id][0]
        return min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)

    bboxes = [edge_bbox(e) for e in network.edges]
    has_intersection = [False] * n_edges

    def ccw(A, B, C):
        return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

    def segments_intersect(p1, p2, p3, p4) -> bool:
        return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)

    for i in range(n_edges):
        if has_intersection[i]:
            continue
        e1 = network.edges[i]
        x1_min, x1_max, y1_min, y1_max = bboxes[i]
        p1 = (coords[e1.from_id][1], coords[e1.from_id][0])
        p2 = (coords[e1.to_id][1], coords[e1.to_id][0])

        for j in range(i + 1, n_edges):
            if has_intersection[j]:
                continue
            e2 = network.edges[j]

            # Skip if they share a node (common endpoint is not a crossing)
            if e1.from_id in (e2.from_id, e2.to_id) or e1.to_id in (e2.from_id, e2.to_id):
                continue

            x2_min, x2_max, y2_min, y2_max = bboxes[j]
            if x1_max < x2_min or x2_max < x1_min or y1_max < y2_min or y2_max < y1_min:
                continue

            q1 = (coords[e2.from_id][1], coords[e2.from_id][0])
            q2 = (coords[e2.to_id][1], coords[e2.to_id][0])

            if segments_intersect(p1, p2, q1, q2):
                has_intersection[i] = True
                has_intersection[j] = True

    intersecting_edges = sum(1 for flag in has_intersection if flag)
    return float(intersecting_edges) / float(n_edges)


def compute_network_stats(network: Network) -> NetworkStats:
    degree_stats = compute_degree_stats(network)
    length_stats = compute_length_stats(network)
    intersection_rate = compute_intersection_rate(network)

    num_nodes = len(network.nodes)
    num_edges = len(network.edges)
    mn_ratio = float(num_edges) / float(num_nodes) if num_nodes > 0 else 0.0

    meshedness = compute_meshedness(network)
    deg1_frac, deg2_frac, deg3plus_frac, degree_entropy = compute_degree_fractions(network)

    return NetworkStats(
        num_nodes=num_nodes,
        num_edges=num_edges,
        mn_ratio=mn_ratio,
        degree_stats=degree_stats,
        length_stats=length_stats,
        intersection_rate=intersection_rate,
        meshedness=meshedness,
        deg1_frac=deg1_frac,
        deg2_frac=deg2_frac,
        deg3plus_frac=deg3plus_frac,
        degree_entropy=degree_entropy,
    )
