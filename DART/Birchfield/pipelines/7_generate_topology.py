"""
Pipeline 7: Generate transmission line topology.

Runs the Birchfield algorithm for each region and voltage level,
saving per-voltage line CSVs to data/processed/lines/intermediate/.

Pipeline 8 loads those CSVs for visualization — no recomputation needed.
"""

import os
import sys
import csv
import time
import yaml

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.topology_generation import (
    SubstationNode, LineCandidate, TopologyConfig, generate_topology
)

INTERMEDIATE_DIR = "data/processed/lines/intermediate"


def load_config(config_path: str) -> dict:
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def load_substations(csv_path: str) -> list[SubstationNode]:
    substations = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            has_345kv = row.get('has_high_voltage_345kv', 'False').lower() == 'true'
            has_115kv = row.get('has_high_voltage_115kv', 'True').lower() == 'true'
            substations.append(SubstationNode(
                sub_id=int(row['substation_id']),
                lat=float(row['lat']),
                lng=float(row['lng']),
                mw_load=float(row['mw_load']),
                total_gen_mw=float(row.get('total_assigned_gen_mw', '0')),
                has_345kv=has_345kv,
                has_115kv=has_115kv,
            ))
    return substations


def save_lines_csv(lines: list[LineCandidate], csv_path: str) -> None:
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'from_sub', 'to_sub', 'voltage_kv', 'length_km',
            'category', 'circuits', 'X_pu', 'MVAmax', 'intersects',
        ])
        writer.writeheader()
        for line in lines:
            writer.writerow({
                'from_sub': line.from_sub,
                'to_sub': line.to_sub,
                'voltage_kv': line.voltage_kv,
                'length_km': f'{line.length_km:.3f}',
                'category': line.category,
                'circuits': 1,
                'X_pu': f'{line.X_pu:.6f}',
                'MVAmax': line.MVAmax,
                'intersects': line.intersects,
            })
    print(f"  ✓ Saved {len(lines)} lines → {csv_path}")


def run_region(region_name: str, config_path: str, global_config_path: str) -> None:
    """Generate topology for one region, save per-voltage CSVs."""
    region_slug = region_name.lower().replace(' ', '_')

    print(f"\n{'#'*60}")
    print(f"  {region_name.upper()}")
    print(f"{'#'*60}")

    # Load substations from Stage 2 output
    subs_csv = f"data/processed/{region_slug}_substations_with_buses.csv"
    substations = load_substations(subs_csv)
    n345 = sum(1 for s in substations if s.has_345kv)
    n115 = sum(1 for s in substations if s.has_115kv)
    print(f"Loaded {len(substations)} substations  (345 kV: {n345}, 115 kV: {n115})")

    # Build TopologyConfig from YAML
    region_cfg = load_config(config_path)
    global_cfg = load_config(global_config_path)
    topo = region_cfg.get('topology', {})

    p345 = global_cfg.get('345kV', {})
    p115 = global_cfg.get('138kV', {})  # 138 kV params for 115 kV level

    config = TopologyConfig(
        target_mn_ratio=topo.get('target_mn_ratio', 1.22),
        random_seed=topo.get('random_seed', 42),
        params_345kv={
            'R_per_km': p345.get('R_per_km', 0.0393),
            'X_per_km': p345.get('X_per_km', 0.653),
            'B_per_km': p345.get('B_per_km', 6.02e-06),
            'MVA_limit': p345.get('MVA_limit', 1082),
            'V_base_kV': 345, 'S_base_MVA': 100,
        },
        params_115kv={
            'R_per_km': p115.get('R_per_km', 0.105),
            'X_per_km': p115.get('X_per_km', 0.800),
            'B_per_km': p115.get('B_per_km', 3.28e-06),
            'MVA_limit': p115.get('MVA_limit', 174),
            'V_base_kV': 115, 'S_base_MVA': 100,
        },
    )

    results = {}
    for voltage_kv in (345, 115):
        print(f"\n{'='*60}")
        print(f"Generating {voltage_kv} kV topology...")
        print(f"{'='*60}")
        t0 = time.time()
        lines = generate_topology(substations, voltage_kv, config, verbose=True)
        elapsed = time.time() - t0
        print(f"  ⏱ {elapsed:.1f}s")

        csv_path = os.path.join(
            INTERMEDIATE_DIR, f"{region_slug}_lines_{voltage_kv}kv.csv"
        )
        save_lines_csv(lines, csv_path)

        n = n345 if voltage_kv == 345 else n115
        results[voltage_kv] = (len(lines), n)

    # Print summary for this region
    for v in (345, 115):
        m, n = results[v]
        print(f"  {v} kV: {n} nodes, {m} lines, m/n={m/n:.3f}")


def main():
    print("=" * 60)
    print("STAGE 3: TOPOLOGY GENERATION")
    print("=" * 60)
    print(f"Output directory: {INTERMEDIATE_DIR}")

    global_config = "config/global.yaml"

    regions = [
        ('New York', 'config/new_york.yaml'),
        ('Texas',    'config/texas.yaml'),
    ]

    for region_name, config_path in regions:
        run_region(region_name, config_path, global_config)

    print(f"\n{'='*60}")
    print("✓ All topology generation complete")
    print(f"{'='*60}")
    print(f"\nLine CSVs saved to {INTERMEDIATE_DIR}/")
    print("  Run pipeline 8 to create visualizations (no recomputation).")


if __name__ == "__main__":
    main()
