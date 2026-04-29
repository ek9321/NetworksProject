"""
Generator assignment to substations.

Implements the Birchfield methodology for assigning EIA-860 generators to
a subset of load substations, creating Type B substations (with generation).

Algorithm:
  1. Select Nb = 5.5% of substations using weighted sampling (by load)
  2. For each selected substation:
     - Sample a gen/load ratio using exp(uniform(-1, 1))
     - Calculate target_gen_mw = ratio * substation.mw_load
     - Assign nearby generators until target is met
  3. Track assignments and shortfalls

Reference: Birchfield et al. - standard 5.5% of substations have generation.
"""

import math
import numpy as np
from dataclasses import dataclass
from typing import Optional

from core.graph_types import Bus, GeneratorRecord
from core.load_nodes_clustering import haversine_distance_km


@dataclass
class GeneratorAssignment:
    """Result of assigning generators to a substation.

    Attributes:
        substation: The Bus receiving generation
        target_gen_mw: Target generation capacity (from sampled ratio)
        assigned_generators: List of GeneratorRecord instances assigned
        assigned_gen_mw: Total capacity of assigned generators
        shortfall_mw: Unmet generation target (if any)
        warning: Optional warning message about shortfalls
    """
    substation: Bus
    target_gen_mw: float
    assigned_generators: list[GeneratorRecord]
    assigned_gen_mw: float
    shortfall_mw: float
    warning: Optional[str] = None


def default_gen_load_ratio_sampler(rng: np.random.Generator) -> float:
    """Default sampler for generation/load ratio.

    Samples from exp(uniform(-1, 1)), producing ratios roughly in range [0.37, 2.72].

    Args:
        rng: NumPy random generator (initialized with pipeline random_seed)

    Returns:
        Generation/load ratio (dimensionless)
    """
    u = rng.uniform(-1.0, 1.0)
    return math.exp(u)


def select_substations_with_generation(
    substations: list[Bus],
    n_b: int,
    random_seed: int,
) -> list[Bus]:
    """Select Nb substations to have generation using weighted sampling.

    Probability of selection is proportional to substation load (MW).
    Uses deterministic weighted sampling without replacement.

    Args:
        substations: List of Bus instances with mw_load populated
        n_b: Number of substations to select for generation
        random_seed: Random seed for reproducibility

    Returns:
        List of selected Bus instances (exactly n_b)

    Raises:
        ValueError: If fewer than n_b substations have positive load
    """
    # Filter to substations with positive load
    eligible = [bus for bus in substations if bus.mw_load > 0]

    if len(eligible) < n_b:
        raise ValueError(
            f"Cannot select {n_b} substations for generation: "
            f"only {len(eligible)} substations have positive load"
        )

    # Extract loads and normalize to probabilities
    loads = np.array([bus.mw_load for bus in eligible])
    probs = loads / loads.sum()

    # Deterministic weighted sampling
    rng = np.random.default_rng(random_seed)
    indices = rng.choice(len(eligible), size=n_b, replace=False, p=probs)

    selected = [eligible[i] for i in indices]
    return selected


def find_candidate_generators(
    substation: Bus,
    generators: list[GeneratorRecord],
    max_distance_km: Optional[float] = None,
) -> list[tuple[float, GeneratorRecord]]:
    """Find candidate generators for a substation, sorted by distance.

    Args:
        substation: Bus instance seeking generation
        generators: List of available GeneratorRecord instances
        max_distance_km: Maximum assignment radius in km (None = unlimited)

    Returns:
        List of (distance_km, generator) tuples, sorted by:
          1. Distance (ascending)
          2. Nameplate capacity (descending)
          3. Generator ID (ascending)
    """
    candidates = []

    for gen in generators:
        # Compute Haversine distance
        distance = haversine_distance_km(
            substation.lat, substation.lng,
            gen.lat, gen.lon
        )

        # Apply distance filter if specified
        if max_distance_km is not None and distance > max_distance_km:
            continue

        candidates.append((distance, gen))

    # Sort by distance (asc), capacity (desc), ID (asc)
    candidates.sort(key=lambda x: (
        x[0],                           # distance ascending
        -x[1].nameplate_capacity_mw,    # capacity descending
        x[1].generator_id                # ID ascending
    ))

    return candidates


def assign_generators_to_substation(
    substation: Bus,
    target_gen_mw: float,
    available_generators: list[GeneratorRecord],
    max_distance_km: Optional[float] = None,
) -> GeneratorAssignment:
    """Assign generators to a substation to meet target capacity.

    Args:
        substation: Bus receiving generation
        target_gen_mw: Target generation capacity
        available_generators: Pool of unassigned generators
        max_distance_km: Maximum assignment radius (None = unlimited)

    Returns:
        GeneratorAssignment with assigned generators and metrics
    """
    # Find and sort candidates
    candidates = find_candidate_generators(
        substation,
        available_generators,
        max_distance_km
    )

    # Assign generators until target is met
    assigned = []
    assigned_mw = 0.0

    for distance, gen in candidates:
        if assigned_mw >= target_gen_mw:
            break

        assigned.append(gen)
        assigned_mw += gen.nameplate_capacity_mw

        # Remove from available pool
        available_generators.remove(gen)

    # Calculate shortfall
    shortfall_mw = max(0.0, target_gen_mw - assigned_mw)

    # Generate warning if shortfall exists
    warning = None
    if shortfall_mw > 0.1:  # Ignore negligible shortfalls
        warning = (
            f"Substation {substation.bus_id} ({substation.sub_name}): "
            f"target {target_gen_mw:.1f} MW, assigned {assigned_mw:.1f} MW, "
            f"shortfall {shortfall_mw:.1f} MW"
        )

    return GeneratorAssignment(
        substation=substation,
        target_gen_mw=target_gen_mw,
        assigned_generators=assigned,
        assigned_gen_mw=assigned_mw,
        shortfall_mw=shortfall_mw,
        warning=warning,
    )


def assign_generators_to_substations(
    substations: list[Bus],
    generators: list[GeneratorRecord],
    fraction_with_generation: float = 0.055,  # 5.5% per Birchfield
    random_seed: int = 42,
    gen_load_ratio_sampler=None,
    max_distance_km: Optional[float] = None,
    verbose: bool = False,
) -> tuple[list[GeneratorAssignment], dict]:
    """Assign EIA generators to a subset of substations.

    Implements the Birchfield methodology:
      1. Select Nb = fraction_with_generation × N substations (weighted by load)
      2. For each selected substation, sample target gen/load ratio
      3. Assign generators by proximity until target is met

    Args:
        substations: List of Bus instances from load clustering
        generators: List of GeneratorRecord instances from EIA-860
        fraction_with_generation: Fraction of substations with generation (default 5.5%)
        random_seed: Random seed for reproducibility
        gen_load_ratio_sampler: Function(rng) -> ratio (default: exp(uniform(-1,1)))
        max_distance_km: Maximum assignment radius in km (None = unlimited)
        verbose: If True, print progress updates

    Returns:
        Tuple of (assignments, summary_dict)
          - assignments: List of GeneratorAssignment instances
          - summary_dict: Summary statistics and warnings

    Raises:
        ValueError: If inputs are invalid
    """
    # Validate inputs
    if not substations:
        raise ValueError("substations cannot be empty")

    if not generators:
        raise ValueError("generators cannot be empty")

    # Filter generators to valid entries (positive capacity, valid coordinates)
    valid_generators = [
        g for g in generators
        if g.nameplate_capacity_mw > 0
        and g.lat is not None
        and g.lon is not None
    ]

    if not valid_generators:
        raise ValueError("No valid generators with positive capacity and coordinates")

    if verbose:
        print(f"Generator assignment: {len(substations)} substations, "
              f"{len(valid_generators)} valid generators")
        print(f"  Filtering: {len(generators) - len(valid_generators)} "
              f"generators excluded (zero capacity or missing coords)")

    # Create working copy of generators (will be modified during assignment)
    available_generators = valid_generators.copy()

    # Determine number of substations with generation
    n_b = max(1, int(len(substations) * fraction_with_generation))

    if verbose:
        print(f"  Selecting Nb = {n_b} substations for generation "
              f"({fraction_with_generation*100:.1f}% of {len(substations)})")

    # Select substations for generation
    selected_substations = select_substations_with_generation(
        substations,
        n_b,
        random_seed
    )

    # Initialize RNG for sampling
    rng = np.random.default_rng(random_seed)

    # Use default sampler if not provided
    if gen_load_ratio_sampler is None:
        gen_load_ratio_sampler = default_gen_load_ratio_sampler

    # Assign generators to each selected substation
    assignments = []
    total_target_mw = 0.0
    total_assigned_mw = 0.0
    total_shortfall_mw = 0.0
    warnings = []

    for i, substation in enumerate(selected_substations):
        # Sample generation/load ratio
        ratio = gen_load_ratio_sampler(rng)
        target_gen_mw = ratio * substation.mw_load

        # Assign generators
        assignment = assign_generators_to_substation(
            substation,
            target_gen_mw,
            available_generators,
            max_distance_km
        )

        assignments.append(assignment)

        # Accumulate statistics
        total_target_mw += assignment.target_gen_mw
        total_assigned_mw += assignment.assigned_gen_mw
        total_shortfall_mw += assignment.shortfall_mw

        if assignment.warning:
            warnings.append(assignment.warning)

        if verbose and (i + 1) % 10 == 0:
            print(f"  Progress: {i + 1}/{n_b} substations assigned")

    if verbose:
        print(f"\nAssignment complete:")
        print(f"  Substations with generation: {len(assignments)}")
        print(f"  Total generators assigned: "
              f"{sum(len(a.assigned_generators) for a in assignments)}")
        print(f"  Target capacity: {total_target_mw:.1f} MW")
        print(f"  Assigned capacity: {total_assigned_mw:.1f} MW")
        print(f"  Shortfall: {total_shortfall_mw:.1f} MW")
        if warnings:
            print(f"  Warnings: {len(warnings)}")

    # Create summary
    summary = {
        "total_substations": len(substations),
        "total_requested_n_b": n_b,
        "total_selected": len(assignments),
        "total_assigned_generators": sum(len(a.assigned_generators) for a in assignments),
        "total_target_gen_mw": float(total_target_mw),
        "total_assigned_gen_mw": float(total_assigned_mw),
        "total_shortfall_mw": float(total_shortfall_mw),
        "fraction_with_generation": fraction_with_generation,
        "random_seed": random_seed,
        "warnings": warnings,
    }

    return assignments, summary
