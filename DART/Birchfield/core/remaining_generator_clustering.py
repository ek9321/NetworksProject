"""
Clustering of unassigned generators into Type-g substations.

Implements hierarchical agglomerative clustering of remaining generators
(not assigned to Type B substations) into generator-only substations with
fuel-type homogeneity constraints.

Algorithm:
  1. Initialize one cluster per unassigned generator
  2. Merge closest clusters respecting fuel-type constraints
  3. Stop when N_g clusters remain (or earlier if constrained)
  4. Use capacity-weighted centroids for distance computation

Reference: Birchfield et al. - 5% of substations are generator-only (Type g).
"""

from dataclasses import dataclass
import math
from typing import Optional

from core.graph_types import GeneratorRecord
from core.load_nodes_clustering import haversine_distance_km


# Default fuel types that cannot be mixed with others
DEFAULT_EXEMPT_FUEL_TYPES = [
    "NUCLEAR",
    "HYDRO",
    "WIND",
    "SOLAR",
    "OTHER_RENEWABLE",
]


def normalize_fuel_type(energy_source: Optional[str]) -> str:
    """Normalize EIA energy_source_1 codes to standardized fuel types.

    Args:
        energy_source: EIA energy source code (e.g., "NG", "NUC", "SUN")

    Returns:
        Normalized fuel type string
    """
    if not energy_source:
        return "UNKNOWN"

    source = energy_source.upper().strip()

    # Map common EIA codes to standardized fuel types
    fuel_map = {
        # Nuclear
        "NUC": "NUCLEAR",

        # Hydro
        "WAT": "HYDRO",
        "HYC": "HYDRO",

        # Wind
        "WND": "WIND",
        "WDS": "WIND",

        # Solar
        "SUN": "SOLAR",

        # Natural Gas
        "NG": "NATURAL_GAS",

        # Coal
        "BIT": "COAL",
        "SUB": "COAL",
        "LIG": "COAL",
        "WC": "COAL",
        "RC": "COAL",

        # Petroleum
        "DFO": "PETROLEUM",
        "RFO": "PETROLEUM",
        "KER": "PETROLEUM",
        "PC": "PETROLEUM",

        # Other renewables
        "GEO": "OTHER_RENEWABLE",
        "AB": "OTHER_RENEWABLE",
        "BLQ": "OTHER_RENEWABLE",
        "MSW": "OTHER_RENEWABLE",
        "OBS": "OTHER_RENEWABLE",
        "WH": "OTHER_RENEWABLE",
    }

    return fuel_map.get(source, "OTHER")


@dataclass
class GeneratorCluster:
    """A cluster of generators during hierarchical clustering.

    Attributes:
        cluster_id: Unique integer identifier
        generator_ids: List of generator IDs in this cluster
        total_capacity_mw: Sum of nameplate capacities
        centroid_lat: Capacity-weighted average latitude
        centroid_lon: Capacity-weighted average longitude
        fuel_type: Single fuel type or "MIXED"
    """
    cluster_id: int
    generator_ids: list[str]
    total_capacity_mw: float
    centroid_lat: float
    centroid_lon: float
    fuel_type: str


def compute_capacity_weighted_centroid(
    generators: list[tuple[str, float, float, float]]  # (id, lat, lon, capacity)
) -> tuple[float, float]:
    """Compute capacity-weighted centroid of generators.

    Args:
        generators: List of (generator_id, lat, lon, capacity_mw) tuples

    Returns:
        (weighted_lat, weighted_lon) in degrees
    """
    if not generators:
        return (0.0, 0.0)

    total_capacity = sum(cap for _, _, _, cap in generators)

    if total_capacity <= 0:
        # Unweighted average if all capacities are zero
        avg_lat = sum(lat for _, lat, _, _ in generators) / len(generators)
        avg_lon = sum(lon for _, _, lon, _ in generators) / len(generators)
        return (avg_lat, avg_lon)

    weighted_lat = sum(lat * cap for _, lat, _, cap in generators) / total_capacity
    weighted_lon = sum(lon * cap for _, _, lon, cap in generators) / total_capacity

    return (weighted_lat, weighted_lon)


def merge_allowed(
    cluster_a: GeneratorCluster,
    cluster_b: GeneratorCluster,
    enforce_fuel_homogeneity: bool,
    exempt_fuel_types: set[str],
) -> bool:
    """Check if two clusters can be merged given fuel-type constraints.

    Args:
        cluster_a: First cluster
        cluster_b: Second cluster
        enforce_fuel_homogeneity: If True, enforce fuel-type constraints
        exempt_fuel_types: Set of fuel types that cannot be mixed

    Returns:
        True if merge is allowed, False otherwise
    """
    if not enforce_fuel_homogeneity:
        return True

    fuel_a = cluster_a.fuel_type
    fuel_b = cluster_b.fuel_type

    # Same fuel type always allowed
    if fuel_a == fuel_b:
        return True

    # If either cluster is MIXED, mixing is already happening
    if fuel_a == "MIXED" or fuel_b == "MIXED":
        return True

    # Check if either contains an exempt fuel type
    a_is_exempt = fuel_a in exempt_fuel_types
    b_is_exempt = fuel_b in exempt_fuel_types

    # If neither is exempt, mixing is allowed
    if not a_is_exempt and not b_is_exempt:
        return True

    # At least one is exempt, so merge is forbidden
    return False


def merge_clusters(
    cluster_a: GeneratorCluster,
    cluster_b: GeneratorCluster,
    new_id: int,
    generators_lookup: dict[str, tuple[float, float, float]],  # id -> (lat, lon, cap)
) -> GeneratorCluster:
    """Merge two generator clusters.

    Args:
        cluster_a: First cluster
        cluster_b: Second cluster
        new_id: Cluster ID for merged cluster
        generators_lookup: Lookup dict for generator details

    Returns:
        New merged GeneratorCluster
    """
    # Combine generator IDs
    merged_ids = cluster_a.generator_ids + cluster_b.generator_ids

    # Compute new capacity
    merged_capacity = cluster_a.total_capacity_mw + cluster_b.total_capacity_mw

    # Compute capacity-weighted centroid
    all_gens = [(gid, *generators_lookup[gid]) for gid in merged_ids]
    merged_lat, merged_lon = compute_capacity_weighted_centroid(all_gens)

    # Determine fuel type
    if cluster_a.fuel_type == cluster_b.fuel_type:
        merged_fuel = cluster_a.fuel_type
    else:
        merged_fuel = "MIXED"

    return GeneratorCluster(
        cluster_id=new_id,
        generator_ids=merged_ids,
        total_capacity_mw=merged_capacity,
        centroid_lat=merged_lat,
        centroid_lon=merged_lon,
        fuel_type=merged_fuel,
    )


def cluster_remaining_generators(
    generators: list[GeneratorRecord],
    n_g: int,
    enforce_fuel_homogeneity: bool = True,
    exempt_fuel_types: Optional[list[str]] = None,
    random_seed: int = 42,
    verbose: bool = False,
) -> tuple[list[GeneratorCluster], dict]:
    """Cluster unassigned generators into Type-g substations.

    Implements hierarchical agglomerative clustering with fuel-type constraints.

    Args:
        generators: List of unassigned GeneratorRecord instances
        n_g: Target number of Type-g substations
        enforce_fuel_homogeneity: If True, enforce fuel-type mixing constraints
        exempt_fuel_types: Fuel types that cannot be mixed (default: standard list)
        random_seed: Random seed (currently unused, for consistency)
        verbose: If True, print progress updates

    Returns:
        Tuple of (clusters, summary_dict)

    Raises:
        ValueError: If inputs are invalid
    """
    # Validate inputs
    if not generators:
        raise ValueError("generators cannot be empty")

    if n_g <= 0:
        raise ValueError(f"n_g must be positive, got {n_g}")

    # Filter to valid generators
    valid_gens = [
        g for g in generators
        if g.nameplate_capacity_mw > 0
        and g.lat is not None
        and g.lon is not None
    ]

    if not valid_gens:
        raise ValueError("No valid generators with positive capacity and coordinates")

    if verbose:
        print(f"Clustering {len(valid_gens)} unassigned generators → {n_g} Type-g substations")
        if len(valid_gens) != len(generators):
            print(f"  Filtered: {len(generators) - len(valid_gens)} generators excluded")

    # Use default exempt fuel types if not provided
    if exempt_fuel_types is None:
        exempt_fuel_types = DEFAULT_EXEMPT_FUEL_TYPES

    exempt_set = set(exempt_fuel_types)

    # Handle case where N_g >= number of generators
    if n_g >= len(valid_gens):
        if verbose:
            print(f"  N_g >= number of generators, creating one cluster per generator")

        clusters = []
        for i, gen in enumerate(valid_gens, start=1):
            clusters.append(GeneratorCluster(
                cluster_id=i,
                generator_ids=[gen.generator_id],
                total_capacity_mw=gen.nameplate_capacity_mw,
                centroid_lat=gen.lat,
                centroid_lon=gen.lon,
                fuel_type=normalize_fuel_type(gen.energy_source_1),
            ))

        summary = {
            "requested_n_g": n_g,
            "actual_n_g": len(clusters),
            "total_generators_clustered": len(valid_gens),
            "total_capacity_mw": sum(c.total_capacity_mw for c in clusters),
            "num_merges": 0,
            "warnings": [],
        }

        return clusters, summary

    # Build lookup for generator details
    generators_lookup = {
        g.generator_id: (g.lat, g.lon, g.nameplate_capacity_mw)
        for g in valid_gens
    }

    # Step 1: Initialize - one cluster per generator
    clusters = {}
    next_cluster_id = 0

    for gen in valid_gens:
        cluster = GeneratorCluster(
            cluster_id=next_cluster_id,
            generator_ids=[gen.generator_id],
            total_capacity_mw=gen.nameplate_capacity_mw,
            centroid_lat=gen.lat,
            centroid_lon=gen.lon,
            fuel_type=normalize_fuel_type(gen.energy_source_1),
        )
        clusters[next_cluster_id] = cluster
        next_cluster_id += 1

    if verbose:
        print(f"  Initialized {len(clusters)} clusters")
        if enforce_fuel_homogeneity:
            print(f"  Fuel homogeneity enforced, exempt types: {exempt_fuel_types}")

    # Precompute distances between all cluster pairs
    distance_cache = {}
    cluster_ids = list(clusters.keys())

    for i in range(len(cluster_ids)):
        for j in range(i + 1, len(cluster_ids)):
            id1, id2 = cluster_ids[i], cluster_ids[j]
            c1, c2 = clusters[id1], clusters[id2]

            dist = haversine_distance_km(
                c1.centroid_lat, c1.centroid_lon,
                c2.centroid_lat, c2.centroid_lon
            )
            distance_cache[(id1, id2)] = dist

    # Step 2: Agglomerative merging
    merge_count = 0
    warnings = []

    while len(clusters) > n_g:
        # Find all allowed merges
        allowed_pairs = []

        for (id1, id2), dist in distance_cache.items():
            if id1 not in clusters or id2 not in clusters:
                continue

            c1, c2 = clusters[id1], clusters[id2]

            if merge_allowed(c1, c2, enforce_fuel_homogeneity, exempt_set):
                combined_capacity = c1.total_capacity_mw + c2.total_capacity_mw
                allowed_pairs.append((dist, combined_capacity, id1, id2))

        # Check if any merges are possible
        if not allowed_pairs:
            warning = (
                f"Fuel-type constraints prevented reaching requested N_g={n_g}. "
                f"Stopped at {len(clusters)} clusters."
            )
            warnings.append(warning)
            if verbose:
                print(f"  WARNING: {warning}")
            break

        # Sort by distance, capacity, then cluster IDs (deterministic tie-breaking)
        allowed_pairs.sort(key=lambda x: (
            x[0],  # distance ascending
            x[1],  # combined capacity ascending
            min(x[2], x[3]),  # smaller ID
            max(x[2], x[3]),  # larger ID
        ))

        # Merge the best pair
        _, _, id1, id2 = allowed_pairs[0]
        c1, c2 = clusters[id1], clusters[id2]

        merged = merge_clusters(c1, c2, next_cluster_id, generators_lookup)
        next_cluster_id += 1

        # Remove old clusters
        del clusters[id1]
        del clusters[id2]

        # Add merged cluster
        clusters[merged.cluster_id] = merged

        # Update distance cache
        # Remove old distances
        keys_to_remove = [k for k in distance_cache.keys() if id1 in k or id2 in k]
        for key in keys_to_remove:
            del distance_cache[key]

        # Add new distances
        for other_id in clusters.keys():
            if other_id == merged.cluster_id:
                continue

            other = clusters[other_id]
            dist = haversine_distance_km(
                merged.centroid_lat, merged.centroid_lon,
                other.centroid_lat, other.centroid_lon
            )

            key = (min(merged.cluster_id, other_id), max(merged.cluster_id, other_id))
            distance_cache[key] = dist

        merge_count += 1

        if verbose and merge_count % 20 == 0:
            print(f"  Progress: {merge_count} merges, {len(clusters)} clusters remaining")

    if verbose:
        print(f"\nClustering complete:")
        print(f"  Target N_g: {n_g}")
        print(f"  Actual clusters: {len(clusters)}")
        print(f"  Total merges: {merge_count}")
        print(f"  Total capacity: {sum(c.total_capacity_mw for c in clusters.values()):.1f} MW")

    # Create summary
    summary = {
        "requested_n_g": n_g,
        "actual_n_g": len(clusters),
        "total_generators_clustered": len(valid_gens),
        "total_capacity_mw": float(sum(c.total_capacity_mw for c in clusters.values())),
        "num_merges": merge_count,
        "warnings": warnings,
    }

    # Sort clusters by capacity (descending) and return
    sorted_clusters = sorted(clusters.values(),
                            key=lambda c: c.total_capacity_mw,
                            reverse=True)

    return sorted_clusters, summary
