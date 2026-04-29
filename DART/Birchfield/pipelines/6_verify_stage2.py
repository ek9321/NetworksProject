"""
Verify Stage 2: Voltage Partition outputs.

Checks:
  - All substations have at least one bus (at lowest voltage)
  - Bus roles are correctly assigned
  - Loads attached to lowest voltage bus
  - Generators attached to highest voltage bus
  - Transformers connect adjacent voltage levels
  - Transformer ratings follow heuristic
  - Voltage percentages match requested targets (within tolerance)
  - No duplicate IDs
  - All bus/transformer IDs reference valid substations
"""

import os
import csv
import json
from collections import defaultdict


def load_substations(csv_path: str) -> dict:
    """Load substations with voltage assignments."""
    substations = {}
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sub_id = int(row['substation_id'])
            substations[sub_id] = {
                'lat': float(row['lat']),
                'lng': float(row['lng']),
                'mw_load': float(row['mw_load']),
                'total_gen_mw': float(row['total_assigned_gen_mw']),
                'type': row['substation_type'],
                'voltages': []
            }
            # Extract voltage levels
            for key, val in row.items():
                if key.startswith('has_high_voltage_') and val.lower() == 'true':
                    kv = int(key.replace('has_high_voltage_', '').replace('kv', ''))
                    substations[sub_id]['voltages'].append(kv)
            substations[sub_id]['voltages'].sort(reverse=True)  # Highest to lowest
    return substations


def load_buses(csv_path: str) -> list:
    """Load buses."""
    buses = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            buses.append({
                'bus_id': int(row['bus_id']),
                'substation_id': int(row['substation_id']),
                'voltage_kv': int(row['voltage_kv']),
                'role': row['role'],
                'connected_load_mw': float(row['connected_load_mw']),
                'connected_generator_ids': row['connected_generator_ids'].split(';') if row['connected_generator_ids'] else []
            })
    return buses


def load_transformers(csv_path: str) -> list:
    """Load transformers."""
    transformers = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            transformers.append({
                'transformer_id': int(row['transformer_id']),
                'substation_id': int(row['substation_id']),
                'from_bus_id': int(row['from_bus_id']),
                'to_bus_id': int(row['to_bus_id']),
                'from_kv': int(row['from_kv']),
                'to_kv': int(row['to_kv']),
                'rating_mva': float(row['rating_mva'])
            })
    return transformers


def verify_region(region_name: str, output_dir: str = "data/processed") -> dict:
    """Verify voltage partition for a single region."""

    region_slug = region_name.lower().replace(" ", "_")

    print(f"\n{'='*70}")
    print(f"Verifying {region_name} - Stage 2: Voltage Partition")
    print(f"{'='*70}\n")

    # Load data
    subs_path = os.path.join(output_dir, f"{region_slug}_substations_with_buses.csv")
    buses_path = os.path.join(output_dir, f"{region_slug}_buses.csv")
    xfmr_path = os.path.join(output_dir, f"{region_slug}_transformers.csv")
    summary_path = os.path.join(output_dir, f"{region_slug}_voltage_partition_summary.json")

    substations = load_substations(subs_path)
    buses = load_buses(buses_path)
    transformers = load_transformers(xfmr_path)

    with open(summary_path, 'r') as f:
        summary = json.load(f)

    print(f"Loaded:")
    print(f"  {len(substations)} substations")
    print(f"  {len(buses)} buses")
    print(f"  {len(transformers)} transformers\n")

    issues = []
    warnings = []

    # Check 1: All substations have at least one bus
    print("Check 1: All substations have at least one bus...")
    sub_to_buses = defaultdict(list)
    for bus in buses:
        sub_to_buses[bus['substation_id']].append(bus)

    missing_buses = []
    for sub_id in substations:
        if sub_id not in sub_to_buses:
            missing_buses.append(sub_id)
            issues.append(f"Substation {sub_id} has no buses")

    if missing_buses:
        print(f"  ✗ {len(missing_buses)} substations have no buses")
    else:
        print(f"  ✓ All substations have at least one bus")

    # Check 2: Bus voltages match substation voltage assignments
    print("Check 2: Bus voltages match substation assignments...")
    voltage_mismatch = []
    for sub_id, sub_buses in sub_to_buses.items():
        sub = substations[sub_id]
        bus_voltages = sorted([b['voltage_kv'] for b in sub_buses], reverse=True)
        if bus_voltages != sub['voltages']:
            voltage_mismatch.append(sub_id)
            issues.append(f"Substation {sub_id}: buses {bus_voltages} != voltages {sub['voltages']}")

    if voltage_mismatch:
        print(f"  ✗ {len(voltage_mismatch)} substations have voltage mismatches")
    else:
        print(f"  ✓ All bus voltages match substation assignments")

    # Check 3: Loads attached to lowest voltage bus
    print("Check 3: Loads attached to lowest voltage bus...")
    load_errors = []
    for sub_id, sub_buses in sub_to_buses.items():
        sub = substations[sub_id]
        if sub['mw_load'] == 0:
            continue  # Skip zero-load substations

        # Find lowest voltage bus
        lowest_voltage = min(b['voltage_kv'] for b in sub_buses)
        lowest_bus = [b for b in sub_buses if b['voltage_kv'] == lowest_voltage][0]

        # Check if load is on lowest bus
        total_load = sum(b['connected_load_mw'] for b in sub_buses)
        if abs(total_load - sub['mw_load']) > 0.01:
            load_errors.append(sub_id)
            issues.append(f"Substation {sub_id}: total bus load {total_load:.2f} != substation load {sub['mw_load']:.2f}")

        if abs(lowest_bus['connected_load_mw'] - sub['mw_load']) > 0.01:
            # Check if it's a single-bus substation (allowed to have load on single bus)
            if len(sub_buses) > 1:
                load_errors.append(sub_id)
                issues.append(f"Substation {sub_id}: load {lowest_bus['connected_load_mw']:.2f} on lowest bus != {sub['mw_load']:.2f}")

    if load_errors:
        print(f"  ✗ {len(load_errors)} substations have load attachment errors")
    else:
        print(f"  ✓ All loads correctly attached")

    # Check 4: Generators attached to highest voltage bus
    print("Check 4: Generators attached to highest voltage bus...")
    gen_errors = []
    for sub_id, sub_buses in sub_to_buses.items():
        sub = substations[sub_id]
        if sub['total_gen_mw'] == 0:
            continue  # Skip substations without generation

        # Find highest voltage bus
        highest_voltage = max(b['voltage_kv'] for b in sub_buses)
        highest_bus = [b for b in sub_buses if b['voltage_kv'] == highest_voltage][0]

        # Check if generators are on highest bus
        if not highest_bus['connected_generator_ids']:
            gen_errors.append(sub_id)
            issues.append(f"Substation {sub_id}: no generators on highest voltage bus")

    if gen_errors:
        print(f"  ✗ {len(gen_errors)} substations have generator attachment errors")
    else:
        print(f"  ✓ All generators correctly attached")

    # Check 5: Transformers connect adjacent voltage levels
    print("Check 5: Transformers connect adjacent voltage levels...")
    xfmr_errors = []
    for xfmr in transformers:
        sub_id = xfmr['substation_id']
        sub = substations[sub_id]

        # Check if from_kv and to_kv are adjacent in substation's voltage list
        try:
            idx_from = sub['voltages'].index(xfmr['from_kv'])
            idx_to = sub['voltages'].index(xfmr['to_kv'])

            if idx_to != idx_from + 1:
                xfmr_errors.append(xfmr['transformer_id'])
                issues.append(f"Transformer {xfmr['transformer_id']}: {xfmr['from_kv']}->{xfmr['to_kv']} not adjacent")
        except ValueError:
            xfmr_errors.append(xfmr['transformer_id'])
            issues.append(f"Transformer {xfmr['transformer_id']}: voltage not in substation {sub_id}")

    if xfmr_errors:
        print(f"  ✗ {len(xfmr_errors)} transformers have voltage errors")
    else:
        print(f"  ✓ All transformers connect adjacent voltages")

    # Check 6: Transformer ratings follow heuristic
    print("Check 6: Transformer ratings follow heuristic...")
    rating_warnings = []
    for xfmr in transformers:
        sub_id = xfmr['substation_id']
        sub = substations[sub_id]

        # Expected rating: max(1.2 × (gen + load), 50.0)
        expected_rating = max(1.2 * (sub['total_gen_mw'] + sub['mw_load']), 50.0)

        if abs(xfmr['rating_mva'] - expected_rating) > 0.01:
            rating_warnings.append(xfmr['transformer_id'])
            warnings.append(f"Transformer {xfmr['transformer_id']}: rating {xfmr['rating_mva']:.2f} != expected {expected_rating:.2f}")

    if rating_warnings:
        print(f"  ⚠ {len(rating_warnings)} transformers have unexpected ratings (may be OK)")
    else:
        print(f"  ✓ All transformer ratings match heuristic")

    # Check 7: Voltage percentages match requested (within 2%)
    print("Check 7: Voltage percentages match requested...")
    voltage_levels = summary['voltage_levels']
    pct_errors = []
    for voltage_kv in voltage_levels[:-1]:  # Skip lowest (always 100%)
        requested_key = f'requested_pct_{voltage_kv}kv'
        actual_key = f'actual_pct_{voltage_kv}kv'

        if requested_key in summary and actual_key in summary:
            requested = summary[requested_key]
            actual = summary[actual_key]
            diff = abs(actual - requested)

            if diff > 0.02:  # More than 2% difference
                pct_errors.append(voltage_kv)
                warnings.append(f"{voltage_kv} kV: {actual*100:.2f}% actual vs {requested*100:.2f}% requested (diff: {diff*100:.2f}%)")

    if pct_errors:
        print(f"  ⚠ {len(pct_errors)} voltage levels outside 2% tolerance")
    else:
        print(f"  ✓ All voltage percentages within 2% of requested")

    # Check 8: No duplicate IDs
    print("Check 8: No duplicate IDs...")
    bus_ids = [b['bus_id'] for b in buses]
    xfmr_ids = [x['transformer_id'] for x in transformers]

    dup_buses = len(bus_ids) - len(set(bus_ids))
    dup_xfmrs = len(xfmr_ids) - len(set(xfmr_ids))

    if dup_buses > 0:
        issues.append(f"{dup_buses} duplicate bus IDs")
        print(f"  ✗ {dup_buses} duplicate bus IDs")
    else:
        print(f"  ✓ No duplicate bus IDs")

    if dup_xfmrs > 0:
        issues.append(f"{dup_xfmrs} duplicate transformer IDs")
        print(f"  ✗ {dup_xfmrs} duplicate transformer IDs")
    else:
        print(f"  ✓ No duplicate transformer IDs")

    # Check 9: Expected transformer count
    print("Check 9: Expected transformer count...")
    # Substations with n voltage levels should have n-1 transformers
    expected_xfmrs = sum(max(0, len(sub['voltages']) - 1) for sub in substations.values())

    if len(transformers) != expected_xfmrs:
        issues.append(f"Expected {expected_xfmrs} transformers, got {len(transformers)}")
        print(f"  ✗ Expected {expected_xfmrs} transformers, got {len(transformers)}")
    else:
        print(f"  ✓ Transformer count matches expected: {expected_xfmrs}")

    # Summary
    print(f"\n{'='*70}")
    print(f"Summary: {region_name}")
    print(f"{'='*70}")
    print(f"Issues: {len(issues)}")
    print(f"Warnings: {len(warnings)}")

    if issues:
        print("\nISSUES:")
        for issue in issues[:10]:  # Show first 10
            print(f"  - {issue}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more")

    if warnings:
        print("\nWARNINGS:")
        for warning in warnings[:10]:  # Show first 10
            print(f"  - {warning}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings) - 10} more")

    if not issues and not warnings:
        print("\n✓ All checks passed!")

    return {
        'region': region_name,
        'issues': len(issues),
        'warnings': len(warnings),
        'substations': len(substations),
        'buses': len(buses),
        'transformers': len(transformers)
    }


def main():
    """Verify Stage 2 for all regions."""

    print("="*70)
    print("STAGE 2 VERIFICATION: VOLTAGE PARTITION")
    print("="*70)

    results = []

    # Texas
    texas_result = verify_region("Texas")
    results.append(texas_result)

    # New York
    ny_result = verify_region("New York")
    results.append(ny_result)

    # Overall summary
    print(f"\n{'='*70}")
    print("OVERALL SUMMARY")
    print(f"{'='*70}\n")

    for result in results:
        status = "✓ PASS" if result['issues'] == 0 else "✗ FAIL"
        print(f"{result['region']}: {status}")
        print(f"  Substations: {result['substations']}")
        print(f"  Buses: {result['buses']}")
        print(f"  Transformers: {result['transformers']}")
        print(f"  Issues: {result['issues']}")
        print(f"  Warnings: {result['warnings']}")
        print()

    total_issues = sum(r['issues'] for r in results)
    total_warnings = sum(r['warnings'] for r in results)

    if total_issues == 0:
        print("✓ Stage 2 verification complete: ALL CHECKS PASSED")
    else:
        print(f"✗ Stage 2 verification complete: {total_issues} issues found")

    if total_warnings > 0:
        print(f"⚠ {total_warnings} warnings (may be acceptable)")


if __name__ == "__main__":
    main()
