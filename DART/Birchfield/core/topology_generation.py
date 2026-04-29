"""
Topology generation via iterative line placement with scoring heuristics.

Implements Birchfield et al. methodology:
  - Delaunay triangulation for candidate generation
  - MST for initial connectivity
  - DC power flow for corridor identification
  - Multi-objective scoring (distance, flow, connectivity, category quotas, intersections)
  - Articulation point detection (reported, not enforced)

Key efficiency strategies:
  - Candidate distance pruning (95th percentile)
  - Batched DC solving (K edges per iteration)
  - R-tree spatial indexing for intersections
  - Selective score recomputation
"""

import os
import csv
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from scipy.spatial import Delaunay
from scipy.sparse import csr_matrix, lil_matrix
from scipy.sparse.linalg import spsolve
from scipy.sparse.csgraph import minimum_spanning_tree, connected_components
import heapq
from collections import defaultdict
import warnings

# Suppress scipy warnings about singular matrices
warnings.filterwarnings('ignore', category=RuntimeWarning)


@dataclass
class LineCandidate:
    """A candidate transmission line between two substations."""
    from_sub: int
    to_sub: int
    voltage_kv: int
    length_km: float
    category: str  # 'mst', 'delaunay', 'neighbor_2', 'neighbor_3'
    X_pu: float = 0.0
    MVAmax: float = 0.0
    added: bool = False
    intersects: bool = False
    score: float = -np.inf

    def key(self):
        """Unique identifier for this candidate."""
        return (self.voltage_kv, min(self.from_sub, self.to_sub), max(self.from_sub, self.to_sub))


@dataclass
class SubstationNode:
    """Substation node with generation and load."""
    sub_id: int
    lat: float
    lng: float
    mw_load: float
    total_gen_mw: float
    has_345kv: bool
    has_115kv: bool


@dataclass
class TopologyConfig:
    """Configuration for topology generation."""
    target_mn_ratio: float = 1.22
    K_per_iteration: int = 5
    max_iterations: int = 10000

    # Scoring weights
    w_dist: float = 1.242  # per km (paper: +2 per mile)
    w_dc: float = 0.5
    w_cat: float = 200.0
    w_conn_v: float = 300.0
    w_conn_overall: float = 1000.0
    w_intersect: float = 500.0

    # Quotas (from Birchfield Table VI, as mutually exclusive categories)
    quota_mst: float = 0.50
    quota_delaunay: float = 0.20
    quota_neighbor_2: float = 0.25
    quota_neighbor_3: float = 0.05
    quota_tolerance: float = 0.05

    # Constraints
    max_intersection_rate: float = 0.05
    distance_prune_percentile: float = 95.0

    # Degree-aware scoring (Experiment 1)
    w_deg1_bonus: float = 0.0
    w_hub_penalty: float = 0.0
    max_preferred_degree: int = 5

    # Distance exponent (Experiment 3): score -= w_dist * length^dist_exponent
    dist_exponent: float = 1.0

    # Connectivity decay (Experiment 4): after graph connects, decay w_conn_v/overall
    conn_decay_factor: float = 1.0  # 1.0 = no decay
    conn_floor_v: float = 300.0
    conn_floor_overall: float = 1000.0

    # Hypothesis 2: "radial substation" threshold for w_conn_v bonus
    # 0 = bonus when degree == 0 (current), 1 = bonus when degree <= 1
    radial_degree_threshold: int = 0

    # Hypothesis 4: use biconnectivity (articulation point) for w_conn_overall
    # False = apply w_conn_overall on component merge (current behavior)
    # True = apply w_conn_overall only when edge eliminates an articulation point
    use_biconnectivity_bonus: bool = False

    # Temporary MST
    temp_mst_init_factor: float = 0.05
    temp_mst_increase_factor: float = 1.2

    # Line parameters (from global.yaml)
    params_345kv: dict = field(default_factory=lambda: {
        'R_per_km': 0.0393,
        'X_per_km': 0.653,
        'B_per_km': 6.02e-06,
        'MVA_limit': 1082,
        'V_base_kV': 345,
        'S_base_MVA': 100
    })

    params_115kv: dict = field(default_factory=lambda: {
        'R_per_km': 0.105,  # Using 138kV params (close enough)
        'X_per_km': 0.800,
        'B_per_km': 3.28e-06,
        'MVA_limit': 174,
        'V_base_kV': 115,
        'S_base_MVA': 100
    })

    random_seed: int = 42


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute great-circle distance in kilometers."""
    R = 6371.0  # Earth radius in km

    lat1_rad = np.radians(lat1)
    lat2_rad = np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlng = np.radians(lng2 - lng1)

    a = np.sin(dlat/2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlng/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))

    return R * c


def lines_intersect(p1, p2, p3, p4) -> bool:
    """Check if line segment (p1,p2) intersects (p3,p4) using CCW test."""
    def ccw(A, B, C):
        return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])

    return ccw(p1,p3,p4) != ccw(p2,p3,p4) and ccw(p1,p2,p3) != ccw(p1,p2,p4)


class TopologyGenerator:
    """Generate transmission line topology for a single voltage level."""

    def __init__(self, substations: list[SubstationNode], voltage_kv: int,
                 config: TopologyConfig, verbose: bool = True):
        self.voltage_kv = voltage_kv
        self.config = config
        self.verbose = verbose

        # Filter substations for this voltage level
        if voltage_kv == 345:
            self.nodes = [s for s in substations if s.has_345kv]
        elif voltage_kv == 115:
            self.nodes = [s for s in substations if s.has_115kv]
        else:
            raise ValueError(f"Unsupported voltage: {voltage_kv}")

        self.n = len(self.nodes)
        self.node_ids = [n.sub_id for n in self.nodes]
        self.id_to_idx = {sub_id: i for i, sub_id in enumerate(self.node_ids)}

        # Line parameters for this voltage
        if voltage_kv == 345:
            self.params = config.params_345kv
        else:
            self.params = config.params_115kv

        # State
        self.candidates: list[LineCandidate] = []
        self.added_edges: list[LineCandidate] = []
        self.category_counts = {'mst': 0, 'delaunay': 0, 'neighbor_2': 0, 'neighbor_3': 0}

        # Temporary MST for DC solvability
        self.temp_mst_edges: list[tuple] = []
        self.temp_mst_X_pu = 0.0

        # Connectivity tracking
        self.uf_parent: list[int] = list(range(self.n))
        self.uf_rank: list[int] = [0] * self.n

        # Degree tracking (avoid scanning all edges)
        self.node_degree: dict[int, int] = defaultdict(int)

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"Topology Generation: {voltage_kv} kV")
            print(f"{'='*70}")
            print(f"  Nodes: {self.n}")
            print(f"  Target m/n: {config.target_mn_ratio}")
            print(f"  Target edges: {round(config.target_mn_ratio * self.n)}")

    def run(self) -> list[LineCandidate]:
        """Execute topology generation algorithm."""
        if self.n < 2:
            print(f"  Warning: Only {self.n} nodes at {self.voltage_kv} kV. Skipping topology.")
            return []

        # Step 1: Generate candidates
        self._generate_candidates()

        # Step 2: Compute target edge count
        target_m = round(self.config.target_mn_ratio * self.n)

        # Step 3: Initialize temporary MST for DC solvability
        self._initialize_temp_mst()

        # Step 4: Main iteration loop
        self._iteration_loop(target_m)

        # Step 5: Final validation (N-1 not enforced per Birchfield paper)
        self._validate_topology()

        return self.added_edges

    def _generate_candidates(self):
        """Generate candidate edges via Delaunay + MST."""
        if self.verbose:
            print("\nGenerating candidates...")

        # Extract coordinates
        coords = np.array([[n.lat, n.lng] for n in self.nodes])

        # Delaunay triangulation
        tri = Delaunay(coords)
        delaunay_edges = set()

        for simplex in tri.simplices:
            for i in range(3):
                a, b = simplex[i], simplex[(i+1) % 3]
                edge = (min(a, b), max(a, b))
                delaunay_edges.add(edge)

        if self.verbose:
            print(f"  Delaunay: {len(delaunay_edges)} edges")

        # MST edges - only compute distances for Delaunay edges to save time
        # Build sparse distance matrix from Delaunay edges
        distances = lil_matrix((self.n, self.n))

        for i, j in delaunay_edges:
            dist = haversine_km(self.nodes[i].lat, self.nodes[i].lng,
                               self.nodes[j].lat, self.nodes[j].lng)
            distances[i, j] = dist
            distances[j, i] = dist

        # MST from Delaunay graph (sufficient for planar graphs)
        mst = minimum_spanning_tree(distances.tocsr())
        mst_edges = set()
        cx = mst.tocoo()
        for i, j in zip(cx.row, cx.col):
            edge = (min(i, j), max(i, j))
            mst_edges.add(edge)

        if self.verbose:
            print(f"  MST: {len(mst_edges)} edges")

        # 2-neighbors and 3-neighbors from Delaunay (limit to avoid explosion)
        neighbor_2_edges = set()
        neighbor_3_edges = set()

        # Build adjacency from Delaunay
        adj = defaultdict(set)
        for a, b in delaunay_edges:
            adj[a].add(b)
            adj[b].add(a)

        # Limit neighbor computation to avoid O(n³) blow-up
        max_neighbors_2 = min(self.n, 5000)  # Cap at 5000 edges
        max_neighbors_3 = min(self.n, 3000)  # Cap at 3000 edges

        neighbor_2_count = 0
        neighbor_3_count = 0

        for i in range(self.n):
            if neighbor_2_count >= max_neighbors_2 and neighbor_3_count >= max_neighbors_3:
                break

            # 1-neighbors are direct Delaunay
            neighbors_1 = adj[i]

            # 2-neighbors: neighbors of neighbors (limited)
            if neighbor_2_count < max_neighbors_2:
                neighbors_2 = set()
                for n1 in neighbors_1:
                    neighbors_2.update(adj[n1])
                neighbors_2 -= neighbors_1
                neighbors_2.discard(i)

                for j in neighbors_2:
                    if i < j and neighbor_2_count < max_neighbors_2:
                        neighbor_2_edges.add((i, j))
                        neighbor_2_count += 1

            # 3-neighbors: neighbors of 2-neighbors (limited)
            if neighbor_3_count < max_neighbors_3:
                neighbors_3 = set()
                for n2 in (neighbors_2 if neighbors_2 else []):
                    neighbors_3.update(adj[n2])
                neighbors_3 -= neighbors_1
                neighbors_3 -= (neighbors_2 if neighbors_2 else set())
                neighbors_3.discard(i)

                for j in neighbors_3:
                    if i < j and neighbor_3_count < max_neighbors_3:
                        neighbor_3_edges.add((i, j))
                        neighbor_3_count += 1

        if self.verbose:
            print(f"  2-neighbors: {len(neighbor_2_edges)} edges")
            print(f"  3-neighbors: {len(neighbor_3_edges)} edges")

        # Categorize and create candidates
        all_edges = mst_edges | delaunay_edges | neighbor_2_edges | neighbor_3_edges

        for idx_i, idx_j in all_edges:
            sub_i = self.node_ids[idx_i]
            sub_j = self.node_ids[idx_j]

            length_km = haversine_km(self.nodes[idx_i].lat, self.nodes[idx_i].lng,
                                     self.nodes[idx_j].lat, self.nodes[idx_j].lng)

            # Categorize
            if (idx_i, idx_j) in mst_edges:
                category = 'mst'
            elif (idx_i, idx_j) in delaunay_edges:
                category = 'delaunay'
            elif (idx_i, idx_j) in neighbor_2_edges:
                category = 'neighbor_2'
            else:
                category = 'neighbor_3'

            # Compute electrical parameters
            X_ohm = self.params['X_per_km'] * length_km
            X_pu = X_ohm * self.params['S_base_MVA'] / (self.params['V_base_kV']**2)
            MVAmax = self.params['MVA_limit']

            candidate = LineCandidate(
                from_sub=sub_i,
                to_sub=sub_j,
                voltage_kv=self.voltage_kv,
                length_km=length_km,
                category=category,
                X_pu=X_pu,
                MVAmax=MVAmax
            )

            self.candidates.append(candidate)

        if self.verbose:
            print(f"  Generated {len(self.candidates)} candidates:")
            print(f"    MST: {len(mst_edges)}")
            print(f"    Delaunay: {len(delaunay_edges)}")
            print(f"    2-neighbors: {len(neighbor_2_edges)}")
            print(f"    3-neighbors: {len(neighbor_3_edges)}")

        # Distance pruning (but never prune MST edges - needed for temp MST connectivity)
        lengths = [c.length_km for c in self.candidates]
        prune_threshold = np.percentile(lengths, self.config.distance_prune_percentile)

        original_count = len(self.candidates)
        self.candidates = [c for c in self.candidates
                          if c.length_km <= prune_threshold or c.category == 'mst']

        if self.verbose:
            n_mst_kept = sum(1 for c in self.candidates if c.category == 'mst' and c.length_km > prune_threshold)
            print(f"  Pruned to {len(self.candidates)} candidates (distance ≤ {prune_threshold:.1f} km, kept {n_mst_kept} long MST edges)")

    def _initialize_temp_mst(self):
        """Initialize temporary MST edges for DC solvability."""
        # Find MST candidates
        mst_candidates = [c for c in self.candidates if c.category == 'mst']

        if not mst_candidates:
            return

        # Compute median X_pu
        median_X = np.median([c.X_pu for c in self.candidates])
        self.temp_mst_X_pu = self.config.temp_mst_init_factor * median_X

        # Store temporary MST edges (not added to main list)
        for c in mst_candidates:
            idx_i = self.id_to_idx[c.from_sub]
            idx_j = self.id_to_idx[c.to_sub]
            self.temp_mst_edges.append((idx_i, idx_j, self.temp_mst_X_pu))

        if self.verbose:
            print(f"\n  Initialized {len(self.temp_mst_edges)} temporary MST edges")
            print(f"    Initial X_pu: {self.temp_mst_X_pu:.6f}")

    def _build_base_dc_system(self):
        """Build base B matrix and solve for base theta (once per iteration).

        Uses all current added edges + temporary MST edges.  The result is
        cached so that _estimate_dc_flow_fast() can evaluate each candidate
        in O(1) instead of O(n^2).
        """
        n = self.n
        B = lil_matrix((n, n))

        # Add existing edges
        for edge in self.added_edges:
            i = self.id_to_idx[edge.from_sub]
            j = self.id_to_idx[edge.to_sub]
            b_ij = 1.0 / edge.X_pu if edge.X_pu > 0 else 0.0
            B[i, i] += b_ij
            B[j, j] += b_ij
            B[i, j] -= b_ij
            B[j, i] -= b_ij

        # Add temporary MST edges
        for idx_i, idx_j, X_temp in self.temp_mst_edges:
            b_temp = 1.0 / X_temp if X_temp > 0 else 0.0
            B[idx_i, idx_i] += b_temp
            B[idx_j, idx_j] += b_temp
            B[idx_i, idx_j] -= b_temp
            B[idx_j, idx_i] -= b_temp

        # Power injections (per-unit)
        P_inj = np.zeros(n)
        total_load = sum(node.mw_load for node in self.nodes)
        total_gen = sum(node.total_gen_mw for node in self.nodes)

        if total_load > 0:
            gen_scale = total_load / total_gen if total_gen > 0 else 0.0
        else:
            gen_scale = 1.0

        for idx, node in enumerate(self.nodes):
            gen_dispatch = node.total_gen_mw * gen_scale
            P_inj[idx] = (gen_dispatch - node.mw_load) / self.params['S_base_MVA']

        # Solve DC power flow (remove slack bus = bus 0)
        B_reduced = B[1:, 1:].tocsr()
        P_reduced = P_inj[1:]

        try:
            theta_reduced = spsolve(B_reduced, P_reduced)
            if np.any(np.isnan(theta_reduced)) or np.any(np.isinf(theta_reduced)):
                self._base_theta = None
                return
            theta = np.zeros(n)
            theta[1:] = theta_reduced
            self._base_theta = theta
        except Exception:
            self._base_theta = None

    def _estimate_dc_flow_fast(self, candidate: LineCandidate) -> float:
        """Estimate DC flow on candidate using cached base theta (O(1) per candidate).

        Uses the open-circuit approximation: flow = (theta_i - theta_j) / X_pu.
        This computes what flow would occur on the candidate line given the
        existing voltage angle spread, without re-solving the full system.
        Good enough for ranking candidates by flow attractiveness.
        """
        if self._base_theta is None:
            return 0.0

        i = self.id_to_idx[candidate.from_sub]
        j = self.id_to_idx[candidate.to_sub]

        flow_pu = (self._base_theta[i] - self._base_theta[j]) / candidate.X_pu if candidate.X_pu > 0 else 0.0
        flow_mw = abs(flow_pu) * self.params['S_base_MVA']

        if np.isnan(flow_mw) or np.isinf(flow_mw):
            return 0.0

        return flow_mw

    def _iteration_loop(self, target_m: int):
        """Main iteration loop: add K best candidates per iteration."""
        if self.verbose:
            print(f"\nStarting iteration loop (target: {target_m} edges)...")

        iteration = 0
        K = max(self.config.K_per_iteration, self.n // 100)

        # Pre-cache base theta (None until first build)
        self._base_theta = None

        # Initialize articulation point set for biconnectivity scoring
        self._articulation_points: set = set()

        # Track whether full connectivity has been achieved (for decay)
        self._connectivity_achieved = False

        while len(self.added_edges) < target_m and iteration < self.config.max_iterations:
            iteration += 1

            # Get remaining candidates
            remaining = [c for c in self.candidates if not c.added]

            if not remaining:
                if self.verbose:
                    print(f"\n  Iteration {iteration}: No more candidates. Stopping early.")
                break

            # Build base DC system ONCE per iteration (amortized over all candidates)
            if self.config.w_dc > 0:
                self._build_base_dc_system()

            # Phase 1: Full score for ALL candidates (distance + connectivity + quota + DC flow)
            # DC flow is O(1) per candidate via cached base theta
            for c in remaining:
                c.score = self._compute_score_cheap(c)
                if self.config.w_dc > 0 and self._base_theta is not None:
                    dc_flow = self._estimate_dc_flow_fast(c)
                    if not np.isnan(dc_flow):
                        c.score += self.config.w_dc * dc_flow

            # Sort by full score (distance + connectivity + quota + DC)
            remaining.sort(key=lambda c: c.score, reverse=True)

            # Phase 2: Intersection check for top K*5 only (intersection is O(m) per candidate)
            top_pool = remaining[:K * 5]
            for c in top_pool:
                if self._check_candidate_intersects(c):
                    c.score -= self.config.w_intersect
                    c.intersects = True
                else:
                    c.intersects = False

            # Final sort and select
            top_pool.sort(key=lambda c: c.score, reverse=True)
            to_add = top_pool[:K]

            # Add selected candidates
            for c in to_add:
                c.added = True
                self.added_edges.append(c)
                self.category_counts[c.category] += 1

                # Update union-find for connectivity
                idx_i = self.id_to_idx[c.from_sub]
                idx_j = self.id_to_idx[c.to_sub]
                self._union(idx_i, idx_j)

                # Update degree tracking
                self.node_degree[c.from_sub] += 1
                self.node_degree[c.to_sub] += 1

            # Update articulation points for biconnectivity scoring
            if self.config.use_biconnectivity_bonus:
                self._articulation_points = self._compute_articulation_points()

            # Connectivity decay: once connected, reduce connectivity bonuses
            if self.config.conn_decay_factor < 1.0 and not self._connectivity_achieved:
                if self._is_connected():
                    self._connectivity_achieved = True
            if self._connectivity_achieved and self.config.conn_decay_factor < 1.0:
                self.config.w_conn_v = max(
                    self.config.w_conn_v * self.config.conn_decay_factor,
                    self.config.conn_floor_v)
                self.config.w_conn_overall = max(
                    self.config.w_conn_overall * self.config.conn_decay_factor,
                    self.config.conn_floor_overall)

            # Update temporary MST impedance (weaken temp edges as real ones are added)
            self.temp_mst_X_pu *= self.config.temp_mst_increase_factor

            # Remove temp MST edges that now duplicate real added edges,
            # but keep the rest — they maintain B-matrix invertibility
            # and provide the impedance backbone for DC corridor detection.
            added_edge_set = set()
            for e in self.added_edges:
                ei = self.id_to_idx[e.from_sub]
                ej = self.id_to_idx[e.to_sub]
                added_edge_set.add((min(ei, ej), max(ei, ej)))

            self.temp_mst_edges = [
                (i, j, self.temp_mst_X_pu)
                for i, j, _ in self.temp_mst_edges
                if (min(i, j), max(i, j)) not in added_edge_set
            ]

            if self.verbose and (iteration % 5 == 0 or iteration <= 3):
                print(f"  Iteration {iteration}: Added {len(self.added_edges)}/{target_m} edges "
                      f"(score range: {to_add[-1].score:.1f} to {to_add[0].score:.1f})")
                if iteration % 20 == 0:
                    connected = self._is_connected()
                    print(f"    Graph connected: {connected}, Remaining candidates: {len(remaining)}, "
                          f"Temp MST edges: {len(self.temp_mst_edges)}")
            elif not self.verbose and iteration % 50 == 0:
                # Minimal progress for non-verbose mode (useful for long-running sweeps)
                print(f"    iter {iteration}: {len(self.added_edges)}/{target_m} edges", flush=True)

        if self.verbose:
            print(f"\n  Completed after {iteration} iterations")
            print(f"  Final edge count: {len(self.added_edges)} (target: {target_m})")
            print(f"  Category breakdown:")
            for cat, count in self.category_counts.items():
                pct = 100 * count / len(self.added_edges) if self.added_edges else 0
                print(f"    {cat}: {count} ({pct:.1f}%)")

    def _compute_score_cheap(self, candidate: LineCandidate) -> float:
        """Compute score without intersection check (fast pass for all candidates)."""
        score = 0.0

        # 1. Distance penalty (negative), with optional sublinear exponent
        score -= self.config.w_dist * (candidate.length_km ** self.config.dist_exponent)

        # 2. DC flow bonus — added in Phase 1 loop after this call returns

        # 3. Connectivity bonuses
        idx_i = self.id_to_idx[candidate.from_sub]
        idx_j = self.id_to_idx[candidate.to_sub]

        different_components = self._find(idx_i) != self._find(idx_j)

        if different_components:
            # Connects two components — always gets both bonuses
            score += self.config.w_conn_v
            score += self.config.w_conn_overall

        # Biconnectivity bonus (Hypothesis 4): ALSO reward cycle-forming edges
        # that eliminate articulation points (create redundant paths / mesh)
        if (self.config.use_biconnectivity_bonus and not different_components
                and self._articulation_points):
            if idx_i in self._articulation_points or idx_j in self._articulation_points:
                score += self.config.w_conn_overall

        # Check if either node is low-degree (radial/spur)
        degree_i = self.node_degree.get(candidate.from_sub, 0)
        degree_j = self.node_degree.get(candidate.to_sub, 0)
        threshold = self.config.radial_degree_threshold

        if degree_i <= threshold or degree_j <= threshold:
            score += self.config.w_conn_v

        # 3b. Degree-aware scoring: bonus for connecting to degree-1 nodes (spur fill-in)
        if self.config.w_deg1_bonus > 0:
            if degree_i == 1 and degree_j >= 2:
                score += self.config.w_deg1_bonus
            if degree_j == 1 and degree_i >= 2:
                score += self.config.w_deg1_bonus

        # 3c. Hub penalty: penalize when both endpoints already high-degree
        if self.config.w_hub_penalty > 0:
            if (degree_i >= self.config.max_preferred_degree and
                    degree_j >= self.config.max_preferred_degree):
                score -= self.config.w_hub_penalty

        # 4. Category penalty (if over quota)
        total_added = len(self.added_edges) if self.added_edges else 1
        current_fraction = self.category_counts[candidate.category] / total_added

        quota_targets = {
            'mst': self.config.quota_mst,
            'delaunay': self.config.quota_delaunay,
            'neighbor_2': self.config.quota_neighbor_2,
            'neighbor_3': self.config.quota_neighbor_3
        }

        target_fraction = quota_targets[candidate.category]
        if current_fraction > target_fraction + self.config.quota_tolerance:
            score -= self.config.w_cat

        # 5. Intersection penalty — NOT checked here (done in phase 2 for top candidates only)

        return score

    def _check_candidate_intersects(self, candidate: LineCandidate) -> bool:
        """Check if a candidate edge intersects any existing added edge."""
        idx_i = self.id_to_idx[candidate.from_sub]
        idx_j = self.id_to_idx[candidate.to_sub]
        p1 = (self.nodes[idx_i].lat, self.nodes[idx_i].lng)
        p2 = (self.nodes[idx_j].lat, self.nodes[idx_j].lng)

        from_sub = candidate.from_sub
        to_sub = candidate.to_sub

        for edge in self.added_edges:
            # Skip if shares endpoint
            if (edge.from_sub == from_sub or edge.from_sub == to_sub or
                edge.to_sub == from_sub or edge.to_sub == to_sub):
                continue

            ei = self.id_to_idx[edge.from_sub]
            ej = self.id_to_idx[edge.to_sub]
            p3 = (self.nodes[ei].lat, self.nodes[ei].lng)
            p4 = (self.nodes[ej].lat, self.nodes[ej].lng)

            if lines_intersect(p1, p2, p3, p4):
                return True
        return False

    def _compute_articulation_points(self) -> set:
        """Find articulation points in the current graph using iterative Tarjan's.

        Returns set of node INDICES that are articulation points.
        O(V + E) complexity. Uses iterative DFS to avoid recursion limits.
        """
        n = self.n
        adj: list[list[int]] = [[] for _ in range(n)]
        for edge in self.added_edges:
            i = self.id_to_idx[edge.from_sub]
            j = self.id_to_idx[edge.to_sub]
            adj[i].append(j)
            adj[j].append(i)

        disc = [-1] * n
        low = [0] * n
        parent = [-1] * n
        ap = set()
        timer = [0]

        for start in range(n):
            if disc[start] != -1:
                continue
            # Iterative DFS
            stack = [(start, 0)]  # (node, neighbor_index)
            disc[start] = low[start] = timer[0]
            timer[0] += 1

            while stack:
                u, ni = stack[-1]
                if ni < len(adj[u]):
                    stack[-1] = (u, ni + 1)
                    v = adj[u][ni]
                    if disc[v] == -1:
                        parent[v] = u
                        disc[v] = low[v] = timer[0]
                        timer[0] += 1
                        stack.append((v, 0))
                    elif v != parent[u]:
                        low[u] = min(low[u], disc[v])
                else:
                    stack.pop()
                    if stack:
                        p = stack[-1][0]
                        low[p] = min(low[p], low[u])
                        # Check if p is an articulation point
                        if parent[p] == -1:
                            # Root: AP if it has 2+ children in DFS tree
                            children = sum(1 for c in range(n) if parent[c] == p)
                            if children >= 2:
                                ap.add(p)
                        else:
                            if low[u] >= disc[p]:
                                ap.add(p)
        return ap

    def _estimate_dc_flow(self, candidate: LineCandidate) -> float:
        """Estimate DC power flow magnitude if this candidate were added."""
        # Build B matrix with current edges + candidate + temporary MST
        n = self.n
        B = lil_matrix((n, n))

        # Add existing edges
        for edge in self.added_edges:
            i = self.id_to_idx[edge.from_sub]
            j = self.id_to_idx[edge.to_sub]
            b_ij = 1.0 / edge.X_pu if edge.X_pu > 0 else 0.0
            B[i, i] += b_ij
            B[j, j] += b_ij
            B[i, j] -= b_ij
            B[j, i] -= b_ij

        # Add candidate
        i = self.id_to_idx[candidate.from_sub]
        j = self.id_to_idx[candidate.to_sub]
        b_ij = 1.0 / candidate.X_pu if candidate.X_pu > 0 else 0.0
        B[i, i] += b_ij
        B[j, j] += b_ij
        B[i, j] -= b_ij
        B[j, i] -= b_ij

        # Add temporary MST edges
        for idx_i, idx_j, X_temp in self.temp_mst_edges:
            b_temp = 1.0 / X_temp if X_temp > 0 else 0.0
            B[idx_i, idx_i] += b_temp
            B[idx_j, idx_j] += b_temp
            B[idx_i, idx_j] -= b_temp
            B[idx_j, idx_i] -= b_temp

        # Power injections (per-unit)
        P_inj = np.zeros(n)
        total_load = sum(node.mw_load for node in self.nodes)
        total_gen = sum(node.total_gen_mw for node in self.nodes)

        if total_load > 0:
            gen_scale = total_load / total_gen if total_gen > 0 else 0.0
        else:
            gen_scale = 1.0

        for idx, node in enumerate(self.nodes):
            gen_dispatch = node.total_gen_mw * gen_scale
            P_inj[idx] = (gen_dispatch - node.mw_load) / self.params['S_base_MVA']

        # Solve DC power flow (remove slack bus)
        B_reduced = B[1:, 1:].tocsr()
        P_reduced = P_inj[1:]

        try:
            theta_reduced = spsolve(B_reduced, P_reduced)
            if np.any(np.isnan(theta_reduced)) or np.any(np.isinf(theta_reduced)):
                return 0.0
            theta = np.zeros(n)
            theta[1:] = theta_reduced
        except:
            # Singular matrix - return zero flow
            return 0.0

        # Compute flow on candidate edge
        flow_pu = (theta[i] - theta[j]) / candidate.X_pu if candidate.X_pu > 0 else 0.0
        flow_mw = abs(flow_pu) * self.params['S_base_MVA']

        # Guard against NaN/Inf from numerical issues
        if np.isnan(flow_mw) or np.isinf(flow_mw):
            return 0.0

        return flow_mw

    def _check_articulation_points(self):
        """Check for articulation points (for reporting only, not enforced)."""
        if self.verbose:
            print("\nChecking articulation points (not enforced)...")

        articulation_points = self._find_articulation_points()

        if articulation_points:
            if self.verbose:
                print(f"  Note: {len(articulation_points)} articulation points present (acceptable)")
        else:
            if self.verbose:
                print("  ✓ No articulation points")

    def _find_articulation_points(self) -> set:
        """Find articulation points (nodes whose removal disconnects graph).

        Uses iterative DFS to avoid recursion-depth limits on large graphs.
        """
        if len(self.added_edges) < self.n - 1:
            return set()  # Graph not even connected yet

        # Build adjacency list
        adj = defaultdict(list)
        for edge in self.added_edges:
            idx_i = self.id_to_idx[edge.from_sub]
            idx_j = self.id_to_idx[edge.to_sub]
            adj[idx_i].append(idx_j)
            adj[idx_j].append(idx_i)

        # Iterative DFS-based articulation point finding
        visited = [False] * self.n
        disc = [0] * self.n
        low = [0] * self.n
        parent = [-1] * self.n
        children_count = [0] * self.n
        ap = set()
        timer = 0

        for start in range(self.n):
            if visited[start]:
                continue

            # Stack holds (node, neighbor_index) pairs
            stack = [(start, 0)]
            visited[start] = True
            disc[start] = low[start] = timer
            timer += 1

            while stack:
                u, ni = stack[-1]
                if ni < len(adj[u]):
                    stack[-1] = (u, ni + 1)
                    v = adj[u][ni]
                    if not visited[v]:
                        children_count[u] += 1
                        parent[v] = u
                        visited[v] = True
                        disc[v] = low[v] = timer
                        timer += 1
                        stack.append((v, 0))
                    elif v != parent[u]:
                        low[u] = min(low[u], disc[v])
                else:
                    # All neighbors processed — backtrack
                    stack.pop()
                    if stack:
                        p = stack[-1][0]  # parent on stack
                        low[p] = min(low[p], low[u])
                        # Check articulation point conditions
                        if parent[p] == -1 and children_count[p] > 1:
                            ap.add(p)
                        if parent[p] != -1 and low[u] >= disc[p]:
                            ap.add(p)

        return ap

    def _validate_topology(self):
        """Final validation checks."""
        if self.verbose:
            print("\nFinal validation...")

        # Check connectivity
        if not self._is_connected():
            print("  ✗ Warning: Graph is not connected!")
        else:
            print("  ✓ Graph is connected")

        # Check articulation points (reporting only)
        self._check_articulation_points()

        # Check m/n ratio
        actual_mn = len(self.added_edges) / self.n if self.n > 0 else 0
        target_mn = self.config.target_mn_ratio
        deviation = abs(actual_mn - target_mn) / target_mn

        print(f"  m/n ratio: {actual_mn:.3f} (target: {target_mn:.3f}, deviation: {deviation*100:.1f}%)")

        if deviation > 0.05:
            print(f"  ⚠ Warning: m/n ratio outside ±5% tolerance")
        else:
            print(f"  ✓ m/n ratio within tolerance")

        # Check intersection rate
        intersecting = sum(1 for e in self.added_edges if e.intersects)
        intersection_rate = intersecting / len(self.added_edges) if self.added_edges else 0

        print(f"  Intersection rate: {intersection_rate*100:.2f}% (max: {self.config.max_intersection_rate*100:.1f}%)")

        if intersection_rate > self.config.max_intersection_rate:
            print(f"  ⚠ Warning: Intersection rate exceeds threshold")
        else:
            print(f"  ✓ Intersection rate acceptable")

    # Union-Find helpers
    def _find(self, x: int) -> int:
        if self.uf_parent[x] != x:
            self.uf_parent[x] = self._find(self.uf_parent[x])
        return self.uf_parent[x]

    def _union(self, x: int, y: int):
        root_x = self._find(x)
        root_y = self._find(y)

        if root_x != root_y:
            if self.uf_rank[root_x] < self.uf_rank[root_y]:
                self.uf_parent[root_x] = root_y
            elif self.uf_rank[root_x] > self.uf_rank[root_y]:
                self.uf_parent[root_y] = root_x
            else:
                self.uf_parent[root_y] = root_x
                self.uf_rank[root_x] += 1

    def _is_connected(self) -> bool:
        """Check if current graph is connected."""
        if self.n == 0:
            return True

        # All nodes should have same root
        root = self._find(0)
        return all(self._find(i) == root for i in range(self.n))


def generate_topology(substations: list[SubstationNode],
                     voltage_kv: int,
                     config: TopologyConfig,
                     verbose: bool = True) -> list[LineCandidate]:
    """
    Generate transmission line topology for a single voltage level.

    Args:
        substations: List of substation nodes
        voltage_kv: Voltage level (345 or 115)
        config: Configuration parameters
        verbose: Print progress

    Returns:
        List of added line candidates
    """
    generator = TopologyGenerator(substations, voltage_kv, config, verbose)
    return generator.run()
