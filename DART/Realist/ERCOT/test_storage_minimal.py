#!/usr/bin/env python3
"""
Minimal test: 3-bus, 2-branch, 1-thermal, 1-renewable, 1-storage Egret model.

Tests two scenarios:
  A) Constant load (same value every hour) — should be fast.
  B) Varying load (different each hour) — tests whether storage + varying load causes hang.

If A works but B hangs, confirms the scale-related MIP combinatorial issue.
"""

import time
import sys
sys.path.insert(0, '/Users/emmettsouder/Desktop/Dartboard/Realist')

from egret.data.model_data import ModelData as EgretModel
from egret.models.unit_commitment import solve_unit_commitment, create_tight_unit_commitment_model

NUM_HOURS = 24


def build_model_dict(varying_load=False, include_storage=True):
    """Build an Egret-compatible model dict for a tiny 3-bus system."""

    time_periods = list(range(1, NUM_HOURS + 1))

    # Load profile
    if varying_load:
        # Sinusoidal load: 80 MW base, +/- 30 MW
        import math
        loads = [80 + 30 * math.sin(2 * math.pi * t / 24) for t in range(NUM_HOURS)]
    else:
        loads = [80.0] * NUM_HOURS

    # Wind profile
    if varying_load:
        import math
        wind_maxes = [max(0, 40 * (0.5 + 0.4 * math.cos(2 * math.pi * t / 24))) for t in range(NUM_HOURS)]
    else:
        wind_maxes = [20.0] * NUM_HOURS

    buses = ['Bus1', 'Bus2', 'Bus3']

    model_dict = {
        'system': {
            'time_keys': [str(t) for t in time_periods],
            'time_period_length_minutes': 60,
            'load_mismatch_cost': 10000.0,
            'reserve_shortfall_cost': 1000.0,
            'baseMVA': 1.0,
            'reference_bus': 'Bus1',
            'reference_bus_angle': 0.0,
            'reserve_requirement': {
                'data_type': 'time_series',
                'values': [0.0] * NUM_HOURS,
            },
        },

        'elements': {
            'bus': {
                'Bus1': {'base_kv': 345.0, 'vm': 1.0, 'va': 0.0},
                'Bus2': {'base_kv': 345.0, 'vm': 1.0, 'va': 0.0},
                'Bus3': {'base_kv': 345.0, 'vm': 1.0, 'va': 0.0},
            },

            'load': {
                'Bus1': {
                    'bus': 'Bus1',
                    'in_service': True,
                    'p_load': {
                        'data_type': 'time_series',
                        'values': [l * 0.5 for l in loads],  # 50% of load at Bus1
                    },
                },
                'Bus2': {
                    'bus': 'Bus2',
                    'in_service': True,
                    'p_load': {
                        'data_type': 'time_series',
                        'values': [l * 0.3 for l in loads],  # 30% at Bus2
                    },
                },
                'Bus3': {
                    'bus': 'Bus3',
                    'in_service': True,
                    'p_load': {
                        'data_type': 'time_series',
                        'values': [l * 0.2 for l in loads],  # 20% at Bus3
                    },
                },
            },

            'branch': {
                'Line1_2': {
                    'from_bus': 'Bus1',
                    'to_bus': 'Bus2',
                    'reactance': 0.05,
                    'rating_long_term': 200.0,
                    'rating_short_term': 200.0,
                    'rating_emergency': 200.0,
                    'in_service': True,
                    'branch_type': 'line',
                    'angle_diff_min': -90,
                    'angle_diff_max': 90,
                },
                'Line2_3': {
                    'from_bus': 'Bus2',
                    'to_bus': 'Bus3',
                    'reactance': 0.08,
                    'rating_long_term': 150.0,
                    'rating_short_term': 150.0,
                    'rating_emergency': 150.0,
                    'in_service': True,
                    'branch_type': 'line',
                    'angle_diff_min': -90,
                    'angle_diff_max': 90,
                },
            },

            'generator': {
                'Gas1': {
                    'bus': 'Bus1',
                    'generator_type': 'thermal',
                    'fuel': 'Gas',
                    'fast_start': False,
                    'in_service': True,
                    'zone': 'None',
                    'failure_rate': 0.0,
                    'fixed_commitment': None,

                    'p_min': 10.0,
                    'p_max': 100.0,
                    'ramp_up_60min': 100.0,
                    'ramp_down_60min': 100.0,
                    'startup_capacity': 100.0,
                    'shutdown_capacity': 100.0,
                    'min_up_time': 1,
                    'min_down_time': 1,
                    'initial_status': 24,   # on for 24 hours
                    'initial_p_output': 80.0,
                    'startup_cost': [(1, 500.0)],
                    'shutdown_cost': 0.0,

                    'p_cost': {
                        'data_type': 'cost_curve',
                        'cost_curve_type': 'piecewise',
                        'values': [(10.0, 200.0), (100.0, 2000.0)],
                    },
                },
                'Wind1': {
                    'bus': 'Bus3',
                    'generator_type': 'renewable',
                    'fuel': 'Wind',
                    'in_service': True,
                    'p_min': {
                        'data_type': 'time_series',
                        'values': [0.0] * NUM_HOURS,
                    },
                    'p_max': {
                        'data_type': 'time_series',
                        'values': wind_maxes,
                    },
                },
            },

            'interface': {},
            'zone': {},

            'storage': {},
        },
    }

    if include_storage:
        model_dict['elements']['storage']['BESS1'] = {
            'bus': 'Bus2',
            'min_discharge_rate': 0.0,
            'max_discharge_rate': 25.0,
            'min_charge_rate': 0.0,
            'max_charge_rate': 25.0,
            'energy_capacity': 100.0,        # 4-hour battery
            'initial_state_of_charge': 0.5,   # 50% SOC
            'charge_efficiency': 0.96,
            'discharge_efficiency': 0.96,
            # Egret bug: reads 'discharge_efficienty' (typo, missing 'c')
            'discharge_efficienty': 0.96,
            'initial_status': 1,
            'ramp_up_output_60min': 25.0,
            'ramp_down_output_60min': 25.0,
            'ramp_up_input_60min': 25.0,
            'ramp_down_input_60min': 25.0,
        }

    return model_dict


def run_test(label, varying_load, include_storage, timeout_sec=120):
    """Build model, solve, report."""
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"  varying_load={varying_load}, include_storage={include_storage}")
    print(f"{'='*60}")

    model_dict = build_model_dict(varying_load=varying_load,
                                   include_storage=include_storage)
    md = EgretModel(model_dict)

    print(f"  Buses: {len(model_dict['elements']['bus'])}")
    print(f"  Branches: {len(model_dict['elements']['branch'])}")
    print(f"  Generators: {len(model_dict['elements']['generator'])}")
    print(f"  Storage: {len(model_dict['elements']['storage'])}")

    t0 = time.time()
    print("  Building + solving UC model...")

    try:
        md_results = solve_unit_commitment(
            md,
            'cbc',
            mipgap=0.01,
            timelimit=timeout_sec,
            solver_tee=False,
        )
        elapsed = time.time() - t0
        print(f"  SOLVED in {elapsed:.1f}s")

        # Print storage results
        for s_name, s_data in md_results.elements(element_type='storage'):
            soc_vals = s_data.get('state_of_charge', {}).get('values', [])
            p_dis = s_data.get('p_discharge', {}).get('values', [])
            p_chg = s_data.get('p_charge', {}).get('values', [])
            print(f"    Storage {s_name}:")
            print(f"      SOC:       {[f'{v:.2f}' for v in soc_vals[:6]]}...")
            print(f"      Discharge: {[f'{v:.1f}' for v in p_dis[:6]]}...")
            print(f"      Charge:    {[f'{v:.1f}' for v in p_chg[:6]]}...")

        return True

    except Exception as e:
        elapsed = time.time() - t0
        print(f"  FAILED after {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    # Test A: constant load + storage
    ok_a = run_test("Constant load + storage", varying_load=False, include_storage=True)

    # Test B: varying load + storage
    ok_b = run_test("Varying load + storage", varying_load=True, include_storage=True)

    # Test C: varying load, no storage
    ok_c = run_test("Varying load, no storage", varying_load=True, include_storage=False)

    # Test D: constant load, no storage
    ok_d = run_test("Constant load, no storage", varying_load=False, include_storage=False)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  A) Constant + storage:  {'PASS' if ok_a else 'FAIL'}")
    print(f"  B) Varying + storage:   {'PASS' if ok_b else 'FAIL'}")
    print(f"  C) Varying, no storage: {'PASS' if ok_c else 'FAIL'}")
    print(f"  D) Constant, no storage:{'PASS' if ok_d else 'FAIL'}")
