#!/usr/bin/env python3
"""
Dartboard Pipeline - Master Runner

This script runs the complete synthetic grid topology generation pipeline.
Each phase can also be run independently by executing the phase file directly.

Usage:
    python run_pipeline.py              # Run full pipeline
    python run_pipeline.py --skip       # Skip phases with existing outputs
    python run_pipeline.py --phase 3    # Run only phase 3
    python run_pipeline.py --from 4     # Run from phase 4 onwards
    python run_pipeline.py --to 5       # Run up to phase 5
    python run_pipeline.py --list       # List all phases

Individual phases can be run with:
    python -m pipeline.phase1_goldbook
    python -m pipeline.phase2_census
    etc.
"""

import argparse
import sys
import time

from pipeline import config
from pipeline import phase1_goldbook
from pipeline import phase2_census
from pipeline import phase3_clustering
from pipeline import phase4_topology
from pipeline import phase5_pruning
from pipeline import phase6_generation
from pipeline import phase7_voltage


PHASES = [
    (1, "Gold Book Extraction", phase1_goldbook),
    (2, "Census Data Processing", phase2_census),
    (3, "Clustering into Substations", phase3_clustering),
    (4, "Initial Topology Generation", phase4_topology),
    (5, "Topology Pruning (Birchfield RNG)", phase5_pruning),
    (6, "Generation Integration", phase6_generation),
    (7, "Voltage Assignment", phase7_voltage),
]


def list_phases():
    """Print list of all phases."""
    print("\nAvailable Pipeline Phases:")
    print("-" * 50)
    for num, name, _ in PHASES:
        print(f"  Phase {num}: {name}")
    print()


def run_pipeline(start_phase=1, end_phase=7, single_phase=None, skip_existing=False):
    """Run the pipeline (or part of it)."""
    
    print("=" * 60)
    print("Dartboard Pipeline - Synthetic Grid Topology Generator")
    print("=" * 60)
    
    config.ensure_directories()
    
    start_time = time.time()
    
    for num, name, module in PHASES:
        if single_phase is not None:
            if num != single_phase:
                continue
        else:
            if num < start_phase or num > end_phase:
                continue
        
        try:
            module.run(skip_if_exists=skip_existing)
        except FileNotFoundError as e:
            print(f"\nERROR in Phase {num}: {e}")
            print("Aborting pipeline.")
            sys.exit(1)
        except Exception as e:
            print(f"\nERROR in Phase {num}: {e}")
            raise
    
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"Pipeline Complete! Total time: {elapsed:.1f}s")
    print(f"Output directory: {config.OUTPUT_DIR}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Run the Dartboard synthetic grid topology pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--list", action="store_true", help="List all phases and exit")
    parser.add_argument("--phase", type=int, metavar="N", help="Run only phase N")
    parser.add_argument("--from", dest="start", type=int, default=1, metavar="N", help="Start from phase N")
    parser.add_argument("--to", dest="end", type=int, default=7, metavar="N", help="Run up to phase N")
    parser.add_argument("--skip", action="store_true", help="Skip phases with existing outputs")
    
    args = parser.parse_args()
    
    if args.list:
        list_phases()
        return
    
    run_pipeline(
        start_phase=args.start,
        end_phase=args.end,
        single_phase=args.phase,
        skip_existing=args.skip
    )


if __name__ == "__main__":
    main()
