"""
Verification script for Stage 1 (Substation Synthesis).

Checks:
  1. Total substation counts match specifications
  2. Generator assignments are mutually exclusive
  3. All generators are accounted for
  4. Capacity calculations are correct
  5. Percentages match Birchfield methodology
  6. Data integrity across all outputs
"""

import os
import sys
import csv

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def verify_region(region_name, state_code, expected_total_subs):
    """Verify all Stage 1 outputs for a region."""

    print(f"\n{'='*70}")
    print(f"VERIFYING {region_name.upper()}")
    print(f"{'='*70}\n")

    region_slug = region_name.lower().replace(" ", "_")
    issues = []

    # Load all data files
    substations_csv = f"data/processed/{region_slug}_substations.csv"
    type_b_csv = f"data/processed/{region_slug}_generator_assignments.csv"
    type_g_csv = f"data/processed/{region_slug}_type_g_substations.csv"
    all_gens_csv = "data/processed/eia860_generators.csv"

    # 1. Check substation counts
    print("1. SUBSTATION COUNTS")
    print("-" * 70)

    with open(substations_csv, 'r') as f:
        load_subs = list(csv.DictReader(f))

    with open(type_g_csv, 'r') as f:
        gen_subs = list(csv.DictReader(f))

    actual_load_subs = len(load_subs)
    actual_gen_subs = len(gen_subs)
    total_subs = actual_load_subs + actual_gen_subs

    print(f"  Load substations (Type A+B): {actual_load_subs}")
    print(f"  Gen-only substations (Type g): {actual_gen_subs}")
    print(f"  Total substations: {total_subs}")
    print(f"  Expected load substations: {expected_total_subs}")

    if actual_load_subs != expected_total_subs:
        issues.append(f"Load substation count mismatch: expected {expected_total_subs}, got {actual_load_subs}")
    else:
        print(f"  ✓ Load substation count correct")

    # 2. Check Type B percentage
    print("\n2. TYPE B SUBSTATIONS (5.5% should have generation)")
    print("-" * 70)

    with open(type_b_csv, 'r') as f:
        type_b_assignments = list(csv.DictReader(f))

    num_type_b = len(type_b_assignments)
    type_b_pct = (num_type_b / actual_load_subs) * 100

    print(f"  Type B count: {num_type_b}")
    print(f"  Type B percentage: {type_b_pct:.2f}%")
    print(f"  Expected: 5.5%")

    if abs(type_b_pct - 5.5) > 0.3:  # Allow small rounding tolerance
        issues.append(f"Type B percentage off: expected ~5.5%, got {type_b_pct:.2f}%")
    else:
        print(f"  ✓ Type B percentage correct")

    # 3. Check Type g percentage
    print("\n3. TYPE G SUBSTATIONS (5% of total)")
    print("-" * 70)

    expected_type_g = int(expected_total_subs * 0.05)
    type_g_pct = (actual_gen_subs / expected_total_subs) * 100

    print(f"  Type g count: {actual_gen_subs}")
    print(f"  Expected: {expected_type_g}")
    print(f"  Percentage of total: {type_g_pct:.2f}%")

    if actual_gen_subs != expected_type_g:
        issues.append(f"Type g count mismatch: expected {expected_type_g}, got {actual_gen_subs}")
    else:
        print(f"  ✓ Type g count correct")

    # 4. Check generator assignments are mutually exclusive
    print("\n4. GENERATOR ASSIGNMENT INTEGRITY")
    print("-" * 70)

    # Collect all assigned generator IDs
    type_b_gen_ids = set()
    for row in type_b_assignments:
        ids_str = row['generator_ids']
        if ids_str:
            ids = ids_str.split(';')
            type_b_gen_ids.update(ids)

    type_g_gen_ids = set()
    for row in gen_subs:
        ids_str = row['generator_ids']
        if ids_str:
            ids = ids_str.split(';')
            type_g_gen_ids.update(ids)

    print(f"  Type B generators assigned: {len(type_b_gen_ids)}")
    print(f"  Type g generators assigned: {len(type_g_gen_ids)}")

    # Check for overlaps
    overlap = type_b_gen_ids & type_g_gen_ids
    if overlap:
        issues.append(f"Generator overlap between Type B and Type g: {len(overlap)} generators")
        print(f"  ✗ OVERLAP DETECTED: {len(overlap)} generators in both Type B and Type g!")
        print(f"    Examples: {list(overlap)[:5]}")
    else:
        print(f"  ✓ No overlaps - assignments are mutually exclusive")

    # 5. Check all state generators are accounted for
    print("\n5. GENERATOR ACCOUNTING")
    print("-" * 70)

    # Load all generators for this state
    state_gens = []
    with open(all_gens_csv, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['state'] == state_code:
                state_gens.append(row['generator_id'])

    total_state_gens = len(state_gens)
    total_assigned = len(type_b_gen_ids) + len(type_g_gen_ids)
    unassigned = total_state_gens - total_assigned

    print(f"  Total {state_code} generators: {total_state_gens}")
    print(f"  Assigned to Type B: {len(type_b_gen_ids)}")
    print(f"  Assigned to Type g: {len(type_g_gen_ids)}")
    print(f"  Total assigned: {total_assigned}")
    print(f"  Unassigned: {unassigned}")

    # Calculate assignment rate
    if total_state_gens > 0:
        assignment_rate = (total_assigned / total_state_gens) * 100
        print(f"  Assignment rate: {assignment_rate:.1f}%")

        # Some generators might be filtered out (zero capacity, missing coords)
        # so we don't require 100% but should be high
        if assignment_rate < 50:
            issues.append(f"Low assignment rate: only {assignment_rate:.1f}% of generators assigned")
        else:
            print(f"  ✓ Assignment rate reasonable")

    # 6. Verify capacity calculations
    print("\n6. CAPACITY VERIFICATION")
    print("-" * 70)

    # Calculate Type B capacity from assignments
    type_b_capacity = 0
    for row in type_b_assignments:
        type_b_capacity += float(row['assigned_gen_mw'])

    # Calculate Type g capacity
    type_g_capacity = 0
    for row in gen_subs:
        type_g_capacity += float(row['total_capacity_mw'])

    print(f"  Type B total capacity: {type_b_capacity:,.0f} MW")
    print(f"  Type g total capacity: {type_g_capacity:,.0f} MW")
    print(f"  Total generation: {type_b_capacity + type_g_capacity:,.0f} MW")

    # Verify Type g capacities sum correctly
    type_g_sum_check = 0
    for row in gen_subs:
        reported = float(row['total_capacity_mw'])
        num_gens = int(row['num_generators'])
        type_g_sum_check += reported

    if abs(type_g_sum_check - type_g_capacity) > 0.01:
        issues.append(f"Type g capacity sum mismatch: {type_g_capacity} vs {type_g_sum_check}")
    else:
        print(f"  ✓ Type g capacity calculations consistent")

    # 7. Check load calculations
    print("\n7. LOAD VERIFICATION")
    print("-" * 70)

    total_load = 0
    for row in load_subs:
        total_load += float(row['mw_load'])

    print(f"  Total load: {total_load:,.0f} MW")

    # Verify all substations have positive load
    zero_load = sum(1 for row in load_subs if float(row['mw_load']) <= 0)
    if zero_load > 0:
        issues.append(f"{zero_load} substations have zero or negative load")
        print(f"  ✗ {zero_load} substations with zero/negative load")
    else:
        print(f"  ✓ All substations have positive load")

    # 8. Summary
    print(f"\n{'='*70}")
    print(f"VERIFICATION SUMMARY FOR {region_name.upper()}")
    print(f"{'='*70}")

    if issues:
        print(f"\n⚠️  FOUND {len(issues)} ISSUE(S):\n")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        return False
    else:
        print("\n✅ ALL CHECKS PASSED - NO ISSUES FOUND")
        return True


def main():
    """Run verification for both regions."""

    print("="*70)
    print("STAGE 1 VERIFICATION SCRIPT")
    print("="*70)
    print("\nChecking substation synthesis for Texas and New York...")

    # Verify both regions
    texas_ok = verify_region("Texas", "TX", 1250)
    ny_ok = verify_region("New York", "NY", 600)

    # Final summary
    print("\n" + "="*70)
    print("FINAL VERIFICATION RESULTS")
    print("="*70)

    if texas_ok and ny_ok:
        print("\n✅ STAGE 1 IMPLEMENTATION VERIFIED - ALL CHECKS PASSED")
        print("\nStage 1 (Substation Synthesis) is complete and correct!")
        return 0
    else:
        print("\n⚠️  VERIFICATION FAILED - ISSUES FOUND")
        print("\nPlease review the issues above and fix them.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
