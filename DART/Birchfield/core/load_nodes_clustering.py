"""
Population-weighted geographic clustering of load nodes.

This module implements hierarchical agglomerative clustering of postal code
(ZCTA) data into a fixed number of load substations, following the methodology
described in LoadNodesClusteringPlan.md.

The clustering algorithm:
  1. Initializes one cluster per postal code
  2. Caches cluster-to-cluster distances
  3. Iteratively merges the closest pair of clusters
  4. Uses weighted-average distance updates for efficiency (O(1) per pair)
  5. Enforces a maximum population constraint per cluster
  6. Stops when exactly N_target clusters remain

Output is an intermediate cluster representation. Conversion to Bus objects
and assignment of global identifiers is handled by pipeline orchestration code.
"""

from dataclasses import dataclass
import math
import heapq

from core.graph_types import LoadNode


@dataclass
class PostalCode:
    """A postal code (ZCTA) member of a cluster.

    Attributes:
        zcta: ZIP Code Tabulation Area identifier
        lat: Latitude in degrees
        lon: Longitude in degrees
        population: Population count
    """
    zcta: str
    lat: float
    lon: float
    population: int


@dataclass
class Cluster:
    """An intermediate cluster representation during hierarchical clustering.

    Attributes:
        cluster_id: Unique integer identifier for this cluster
        members: Set of PostalCode instances in this cluster
        total_population: Sum of populations of all members
        cluster_lat: Population-weighted average latitude (degrees)
        cluster_lon: Population-weighted average longitude (degrees)
    """
    cluster_id: int
    members: list[PostalCode]
    total_population: int
    cluster_lat: float
    cluster_lon: float


def haversine_distance_km(lat1: float, lon1: float,
                          lat2: float, lon2: float) -> float:
    """Compute Haversine distance between two points on Earth.

    Uses the Haversine formula on a spherical Earth model.

    Args:
        lat1: Latitude of first point (degrees)
        lon1: Longitude of first point (degrees)
        lat2: Latitude of second point (degrees)
        lon2: Longitude of second point (degrees)

    Returns:
        Distance in kilometers (double precision)
    """
    # Earth radius in kilometers
    R = 6371.0

    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.asin(math.sqrt(a))

    distance = R * c
    return distance


def cluster_to_cluster_distance(c1: Cluster, c2: Cluster) -> float:
    """Compute population-weighted distance between two clusters.

    For every postal code m1 in cluster c1 and every postal code m2 in
    cluster c2:
      1. Compute the Haversine distance (km) between m1 and m2
      2. Multiply by (population of m1 + population of m2)

    The cluster-to-cluster distance is the sum of all such weighted distances
    divided by the sum of all weights.

    Args:
        c1: First cluster
        c2: Second cluster

    Returns:
        Population-weighted average distance in kilometers
    """
    total_weighted_distance = 0.0
    total_weight = 0.0

    for m1 in c1.members:
        for m2 in c2.members:
            # Compute Haversine distance between m1 and m2
            distance = haversine_distance_km(m1.lat, m1.lon, m2.lat, m2.lon)

            # Weight is sum of populations
            weight = m1.population + m2.population

            # Accumulate weighted distance
            total_weighted_distance += distance * weight
            total_weight += weight

    # Return weighted average
    if total_weight == 0.0:
        return 0.0

    return total_weighted_distance / total_weight


def compute_cluster_location(members: list[PostalCode]) -> tuple[float, float]:
    """Compute population-weighted average location of cluster members.

    Args:
        members: List of PostalCode instances

    Returns:
        Tuple of (weighted_avg_lat, weighted_avg_lon) in degrees
    """
    if not members:
        return (0.0, 0.0)

    total_population = sum(m.population for m in members)

    if total_population == 0:
        # Unweighted average if all populations are zero
        avg_lat = sum(m.lat for m in members) / len(members)
        avg_lon = sum(m.lon for m in members) / len(members)
        return (avg_lat, avg_lon)

    weighted_lat = sum(m.lat * m.population for m in members) / total_population
    weighted_lon = sum(m.lon * m.population for m in members) / total_population

    return (weighted_lat, weighted_lon)


def merge_clusters(c1: Cluster, c2: Cluster, new_id: int) -> Cluster:
    """Merge two clusters into a new cluster.

    Args:
        c1: First cluster
        c2: Second cluster
        new_id: Cluster ID for the merged cluster

    Returns:
        New Cluster instance with combined members and updated location
    """
    # Combine members
    merged_members = c1.members + c2.members

    # Compute new population
    merged_population = c1.total_population + c2.total_population

    # Compute new population-weighted location
    merged_lat, merged_lon = compute_cluster_location(merged_members)

    return Cluster(
        cluster_id=new_id,
        members=merged_members,
        total_population=merged_population,
        cluster_lat=merged_lat,
        cluster_lon=merged_lon,
    )


def cluster_load_nodes(load_nodes: list[LoadNode], n_target: int,
                       verbose: bool = False) -> list[Cluster]:
    """Cluster load nodes into n_target geographic clusters.

    Implements hierarchical agglomerative clustering with:
      - Population-weighted Haversine distance metric
      - Maximum cluster population constraint (3 × avg_population per cluster)
      - Deterministic tie-breaking by population and cluster ID
      - Cached distances with weighted-average updates (efficient)
      - Priority queue for finding minimum distance pairs

    Args:
        load_nodes: List of LoadNode instances (from Census data)
        n_target: Target number of clusters
        verbose: If True, print progress updates during clustering

    Returns:
        List of Cluster instances (exactly n_target clusters)

    Raises:
        ValueError: If load_nodes is empty or n_target is invalid
    """
    if not load_nodes:
        raise ValueError("load_nodes cannot be empty")

    if n_target < 1:
        raise ValueError(f"n_target must be at least 1, got {n_target}")

    if n_target > len(load_nodes):
        raise ValueError(
            f"n_target ({n_target}) cannot exceed number of load nodes "
            f"({len(load_nodes)})"
        )

    # Step 1: Initialization
    # Create one cluster per postal code
    clusters = {}  # cluster_id -> Cluster
    next_cluster_id = 0

    for node in load_nodes:
        postal = PostalCode(
            zcta=node.zcta,
            lat=node.lat,
            lon=node.lon,
            population=node.population,
        )

        cluster = Cluster(
            cluster_id=next_cluster_id,
            members=[postal],
            total_population=node.population,
            cluster_lat=node.lat,
            cluster_lon=node.lon,
        )
        clusters[next_cluster_id] = cluster
        next_cluster_id += 1

    # Compute total population
    total_population = sum(c.total_population for c in clusters.values())

    # Initialize max_cluster_population
    max_cluster_population = 3.0 * (total_population / n_target)

    # Cache cluster-to-cluster distances
    # Key: (min_id, max_id), Value: distance
    distance_cache = {}

    # Initialize distance cache for all pairs
    cluster_ids = list(clusters.keys())
    for i in range(len(cluster_ids)):
        for j in range(i + 1, len(cluster_ids)):
            id1, id2 = cluster_ids[i], cluster_ids[j]
            c1, c2 = clusters[id1], clusters[id2]
            dist = cluster_to_cluster_distance(c1, c2)
            distance_cache[(id1, id2)] = dist

    # Priority queue: (distance, combined_pop, min_id, max_id)
    # This allows deterministic tie-breaking
    heap = []
    for (id1, id2), dist in distance_cache.items():
        c1, c2 = clusters[id1], clusters[id2]
        combined_pop = c1.total_population + c2.total_population
        heapq.heappush(heap, (dist, combined_pop, id1, id2))

    # Step 2: Iterative merging
    total_merges = len(clusters) - n_target
    merge_count = 0

    if verbose:
        print(f"Starting clustering: {len(clusters)} clusters → {n_target} clusters")
        print(f"Total merges needed: {total_merges}")
        print(f"Initial cache size: {len(distance_cache)} distances")

    while len(clusters) > n_target:
        # Find the next valid merge using the priority queue
        merged = False

        while heap and not merged:
            dist, combined_pop, id1, id2 = heapq.heappop(heap)

            # Check if both clusters still exist
            if id1 not in clusters or id2 not in clusters:
                continue

            # Check population constraint
            if combined_pop > max_cluster_population:
                # Try to increase max and continue searching
                continue

            # Valid merge found
            c1, c2 = clusters[id1], clusters[id2]

            # Merge the clusters
            merged_cluster = merge_clusters(c1, c2, next_cluster_id)
            merged_id = next_cluster_id
            next_cluster_id += 1

            # Remove old clusters
            del clusters[id1]
            del clusters[id2]

            # Add merged cluster
            clusters[merged_id] = merged_cluster

            # Update distance cache using weighted-average formula
            # For each remaining cluster C:
            #   distance(M, C) = (pop_A × dist(A,C) + pop_B × dist(B,C)) / (pop_A + pop_B)
            remaining_ids = [cid for cid in clusters.keys() if cid != merged_id]

            for other_id in remaining_ids:
                other = clusters[other_id]

                # Get cached distances to old clusters
                key1 = (min(id1, other_id), max(id1, other_id))
                key2 = (min(id2, other_id), max(id2, other_id))

                dist1 = distance_cache.get(key1, 0.0)
                dist2 = distance_cache.get(key2, 0.0)

                # Weighted-average update formula
                pop_a = c1.total_population
                pop_b = c2.total_population

                if pop_a + pop_b > 0:
                    new_dist = (pop_a * dist1 + pop_b * dist2) / (pop_a + pop_b)
                else:
                    # If both populations are zero, use simple average
                    new_dist = (dist1 + dist2) / 2.0

                # Cache the new distance
                new_key = (min(merged_id, other_id), max(merged_id, other_id))
                distance_cache[new_key] = new_dist

                # Add to priority queue
                combined = merged_cluster.total_population + other.total_population
                heapq.heappush(heap, (
                    new_dist,
                    combined,
                    min(merged_id, other_id),
                    max(merged_id, other_id)
                ))

            # Remove old distances from cache (for memory efficiency)
            keys_to_remove = []
            for key in distance_cache:
                if id1 in key or id2 in key:
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del distance_cache[key]

            merged = True
            merge_count += 1

            if verbose and (merge_count % 50 == 0 or merge_count == total_merges):
                percent = (merge_count / total_merges) * 100
                print(f"  Progress: {merge_count}/{total_merges} merges "
                      f"({percent:.1f}%) - {len(clusters)} clusters remaining")

        # If no valid merge was found, increase max_cluster_population
        if not merged:
            max_cluster_population *= 1.1
            if verbose:
                print(f"  No valid pairs, increasing max population to "
                      f"{max_cluster_population:.0f}")

            # Re-add all pairs to heap with new constraint
            heap = []
            cluster_ids = list(clusters.keys())
            for i in range(len(cluster_ids)):
                for j in range(i + 1, len(cluster_ids)):
                    id1, id2 = cluster_ids[i], cluster_ids[j]
                    key = (id1, id2)
                    if key in distance_cache:
                        dist = distance_cache[key]
                        c1, c2 = clusters[id1], clusters[id2]
                        combined = c1.total_population + c2.total_population
                        heapq.heappush(heap, (dist, combined, id1, id2))

    # Step 3: Termination
    # Return exactly n_target clusters
    return list(clusters.values())
