"""
Voltage partition and bus creation.

Assigns nominal voltage buses to each substation, creates internal transformers,
and attaches loads/generators to appropriate buses.

Algorithm:
  1. Load all substations (Type A, B, g) with their loads and generators
  2. Compute selection scores = max(load, generation)
  3. Select substations for high-voltage buses via weighted sampling
  4. Create buses at appropriate voltage levels per substation
  5. Create internal transformers connecting voltage levels
  6. Attach loads to lowest voltage, generators to highest voltage
  7. Output buses, transformers, and substation metadata

Reference: Birchfield et al. - voltage partitioning stage.
"""

import csv
import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class Substation:
    """A substation with load and/or generation."""
    substation_id: int
    lat: float
    lng: float
    mw_load: float
    assigned_generator_ids: list[str]
    total_gen_mw: float
    substation_type: str  # 'A', 'B', or 'g'
    has_high_voltage: dict[int, bool]  # voltage_kv -> bool


@dataclass
class Bus:
    """A bus at a specific voltage level within a substation."""
    bus_id: int
    substation_id: int
    voltage_kv: int
    role: str  # 'load', 'generator', or 'transmission'
    connected_load_mw: float
    connected_generator_ids: list[str]


@dataclass
class Transformer:
    """An internal transformer connecting buses within a substation."""
    transformer_id: int
    substation_id: int
    from_bus_id: int
    to_bus_id: int
    from_kv: int
    to_kv: int
    rating_mva: float


def load_all_substations(
    substations_csv: str,
    type_b_assignments_csv: str,
    type_g_substations_csv: str,
) -> list[Substation]:
    """Load all substations (Type A, B, g) with their metadata.

    Args:
        substations_csv: Path to load substations (Type A+B)
        type_b_assignments_csv: Path to Type B generator assignments
        type_g_substations_csv: Path to Type-g generator-only substations

    Returns:
        List of Substation instances
    """
    substations = []
    substation_id = 1

    # Load Type B assignments into a lookup
    type_b_lookup = {}
    with open(type_b_assignments_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bus_id = int(row['bus_id'])
            gen_ids = row['generator_ids'].split(';') if row['generator_ids'] else []
            gen_mw = float(row['assigned_gen_mw'])
            type_b_lookup[bus_id] = (gen_ids, gen_mw)

    # Load Type A+B substations
    with open(substations_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bus_id = int(row['bus_id'])
            mw_load = float(row['mw_load'])

            # Check if this is Type B
            if bus_id in type_b_lookup:
                gen_ids, gen_mw = type_b_lookup[bus_id]
                sub_type = 'B'
            else:
                gen_ids, gen_mw = [], 0.0
                sub_type = 'A'

            substations.append(Substation(
                substation_id=substation_id,
                lat=float(row['lat']),
                lng=float(row['lng']),
                mw_load=mw_load,
                assigned_generator_ids=gen_ids,
                total_gen_mw=gen_mw,
                substation_type=sub_type,
                has_high_voltage={},
            ))
            substation_id += 1

    # Load Type-g substations (generator-only)
    with open(type_g_substations_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            gen_ids = row['generator_ids'].split(';') if row['generator_ids'] else []
            gen_mw = float(row['total_capacity_mw'])

            substations.append(Substation(
                substation_id=substation_id,
                lat=float(row['lat']),
                lng=float(row['lng']),
                mw_load=0.0,  # Generator-only, no load
                assigned_generator_ids=gen_ids,
                total_gen_mw=gen_mw,
                substation_type='g',
                has_high_voltage={},
            ))
            substation_id += 1

    return substations


def select_high_voltage_substations(
    substations: list[Substation],
    voltage_levels: list[int],
    pct_with_high_voltage: dict[int, float],
    random_seed: int,
    verbose: bool = False,
) -> None:
    """Select substations to receive high-voltage buses.

    Modifies substations in-place by setting has_high_voltage flags.

    Args:
        substations: List of Substation instances
        voltage_levels: Voltage levels in descending order (e.g., [345, 115])
        pct_with_high_voltage: Fraction of substations per voltage level
        random_seed: Random seed for reproducibility
        verbose: If True, print progress
    """
    rng = np.random.default_rng(random_seed)

    # All substations get the lowest voltage
    lowest_voltage = voltage_levels[-1]
    for sub in substations:
        sub.has_high_voltage[lowest_voltage] = True

    if verbose:
        print(f"  All {len(substations)} substations get {lowest_voltage} kV (base level)")

    # Process higher voltages from highest to lowest (excluding lowest)
    for voltage_kv in voltage_levels[:-1]:
        target_pct = pct_with_high_voltage.get(voltage_kv, 0.0)
        if target_pct <= 0:
            continue

        target_num = max(1, round(target_pct * len(substations)))

        # Compute selection scores = max(load, generation)
        # Exclude zero-score substations (unless we need more)
        scores = []
        eligible_subs = []

        for sub in substations:
            score = max(sub.mw_load, sub.total_gen_mw)
            if score > 0:
                scores.append(score)
                eligible_subs.append(sub)

        if len(eligible_subs) < target_num:
            # Not enough non-zero substations, include all
            if verbose:
                print(f"  WARNING: Only {len(eligible_subs)} non-zero substations "
                      f"for {target_num} target at {voltage_kv} kV")
            target_num = len(eligible_subs)

        if target_num == 0 or len(eligible_subs) == 0:
            if verbose:
                print(f"  No substations selected for {voltage_kv} kV")
            continue

        # Normalize to probabilities
        scores_array = np.array(scores)
        probs = scores_array / scores_array.sum()

        # Weighted sampling without replacement
        indices = rng.choice(len(eligible_subs), size=target_num, replace=False, p=probs)

        selected_subs = [eligible_subs[i] for i in indices]
        for sub in selected_subs:
            sub.has_high_voltage[voltage_kv] = True

        if verbose:
            print(f"  Selected {len(selected_subs)} substations for {voltage_kv} kV "
                  f"({target_pct*100:.1f}% of {len(substations)})")


def create_buses_and_transformers(
    substations: list[Substation],
    voltage_levels: list[int],
) -> tuple[list[Bus], list[Transformer]]:
    """Create buses and internal transformers for all substations.

    Args:
        substations: List of Substation instances with voltage assignments
        voltage_levels: Voltage levels in descending order

    Returns:
        Tuple of (buses, transformers)
    """
    buses = []
    transformers = []
    bus_id = 1
    transformer_id = 1

    for sub in substations:
        # Determine which voltage levels this substation has
        has_voltages = sorted(
            [v for v in voltage_levels if sub.has_high_voltage.get(v, False)],
            reverse=True  # Highest to lowest
        )

        if not has_voltages:
            # Should not happen, but handle gracefully
            has_voltages = [voltage_levels[-1]]  # At least lowest voltage

        # Create buses at each voltage level
        sub_buses = {}  # voltage_kv -> Bus

        for voltage_kv in has_voltages:
            # Determine role
            if voltage_kv == has_voltages[0]:  # Highest voltage
                role = 'generator'
                gen_ids = sub.assigned_generator_ids
                load_mw = 0.0
            elif voltage_kv == has_voltages[-1]:  # Lowest voltage
                role = 'load'
                gen_ids = []
                load_mw = sub.mw_load
            else:  # Intermediate
                role = 'transmission'
                gen_ids = []
                load_mw = 0.0

            bus = Bus(
                bus_id=bus_id,
                substation_id=sub.substation_id,
                voltage_kv=voltage_kv,
                role=role,
                connected_load_mw=load_mw,
                connected_generator_ids=gen_ids,
            )
            buses.append(bus)
            sub_buses[voltage_kv] = bus
            bus_id += 1

        # If single bus, it gets both load and generation
        if len(has_voltages) == 1:
            single_bus = sub_buses[has_voltages[0]]
            single_bus.connected_load_mw = sub.mw_load
            single_bus.connected_generator_ids = sub.assigned_generator_ids
            if sub.mw_load > 0 and sub.assigned_generator_ids:
                single_bus.role = 'load_and_generator'
            elif sub.mw_load > 0:
                single_bus.role = 'load'
            elif sub.assigned_generator_ids:
                single_bus.role = 'generator'

        # Create transformers between adjacent voltage levels
        if len(has_voltages) > 1:
            for i in range(len(has_voltages) - 1):
                from_kv = has_voltages[i]      # Higher voltage
                to_kv = has_voltages[i + 1]    # Lower voltage

                from_bus = sub_buses[from_kv]
                to_bus = sub_buses[to_kv]

                # Rating heuristic: 1.2 × (generation + load), minimum 50 MVA
                total_power = sub.total_gen_mw + sub.mw_load
                rating_mva = max(total_power * 1.2, 50.0)

                transformer = Transformer(
                    transformer_id=transformer_id,
                    substation_id=sub.substation_id,
                    from_bus_id=from_bus.bus_id,
                    to_bus_id=to_bus.bus_id,
                    from_kv=from_kv,
                    to_kv=to_kv,
                    rating_mva=rating_mva,
                )
                transformers.append(transformer)
                transformer_id += 1

    return buses, transformers


def voltage_partition(
    substations_csv: str,
    type_b_assignments_csv: str,
    type_g_substations_csv: str,
    voltage_levels: list[int],
    pct_with_high_voltage: dict[int, float],
    random_seed: int = 42,
    verbose: bool = False,
) -> tuple[list[Substation], list[Bus], list[Transformer], dict]:
    """Execute voltage partition algorithm.

    Args:
        substations_csv: Path to load substations CSV
        type_b_assignments_csv: Path to Type B assignments CSV
        type_g_substations_csv: Path to Type-g substations CSV
        voltage_levels: Voltage levels in descending order (e.g., [345, 115])
        pct_with_high_voltage: Fraction per voltage level
        random_seed: Random seed for reproducibility
        verbose: If True, print progress

    Returns:
        Tuple of (substations, buses, transformers, summary_dict)
    """
    if verbose:
        print(f"Voltage partition: {len(voltage_levels)} voltage levels")
        print(f"  Levels: {voltage_levels}")

    # 1. Load all substations
    if verbose:
        print("\nLoading substations...")

    substations = load_all_substations(
        substations_csv,
        type_b_assignments_csv,
        type_g_substations_csv
    )

    if verbose:
        type_counts = {'A': 0, 'B': 0, 'g': 0}
        for sub in substations:
            type_counts[sub.substation_type] += 1

        print(f"  Loaded {len(substations)} substations:")
        print(f"    Type A (load-only): {type_counts['A']}")
        print(f"    Type B (load+gen): {type_counts['B']}")
        print(f"    Type g (gen-only): {type_counts['g']}")

    # 2. Select high-voltage substations
    if verbose:
        print("\nSelecting high-voltage substations...")

    select_high_voltage_substations(
        substations,
        voltage_levels,
        pct_with_high_voltage,
        random_seed,
        verbose
    )

    # 3. Create buses and transformers
    if verbose:
        print("\nCreating buses and transformers...")

    buses, transformers = create_buses_and_transformers(
        substations,
        voltage_levels
    )

    if verbose:
        print(f"  Created {len(buses)} buses")
        print(f"  Created {len(transformers)} transformers")

    # 4. Create summary
    summary = {
        'total_substations': len(substations),
        'total_buses': len(buses),
        'total_transformers': len(transformers),
        'voltage_levels': voltage_levels,
    }

    # Calculate actual percentages for each voltage
    for voltage_kv in voltage_levels[:-1]:
        count = sum(1 for sub in substations if sub.has_high_voltage.get(voltage_kv, False))
        actual_pct = count / len(substations) if len(substations) > 0 else 0.0
        requested_pct = pct_with_high_voltage.get(voltage_kv, 0.0)

        summary[f'requested_pct_{voltage_kv}kv'] = requested_pct
        summary[f'actual_pct_{voltage_kv}kv'] = actual_pct
        summary[f'count_{voltage_kv}kv'] = count

    return substations, buses, transformers, summary
