"""Run Dartboard topology generation on Texas-7k buses at full nodal resolution.

This script does NOT modify existing pipelines. It builds SubstationNode objects
from the Texas-7k bus.csv file and uses the existing TopologyGenerator to
construct 345 kV and 115 kV (≈138 kV) networks, saving line CSVs under
Calibration/outputs/ for calibration experiments.
"""

from __future__ import annotations

import os
import csv
from typing import List

from core.topology_generation import TopologyConfig, TopologyGenerator
from .network_io import build_texas7k_substation_nodes_for_topology


REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "Calibration", "outputs")


def _ensure_output_dir() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _save_lines_csv(label: str, voltage_kv: int, lines) -> None:
    path = os.path.join(OUTPUT_DIR, f"texas7k_{label}_lines_{voltage_kv}kv.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "from_sub",
            "to_sub",
            "voltage_kv",
            "length_km",
            "category",
            "circuits",
            "X_pu",
            "MVAmax",
            "intersects",
        ])
        for line in lines:
            writer.writerow([
                line.from_sub,
                line.to_sub,
                line.voltage_kv,
                line.length_km,
                line.category,
                1,
                line.X_pu,
                line.MVAmax,
                line.intersects,
            ])


def main() -> None:
    _ensure_output_dir()

    substations = build_texas7k_substation_nodes_for_topology()

    # Calibrated parameters from audit: mn=1.55 matches Texas-7k 345 kV (1.552),
    # w_intersect=25 avoids over-penalizing corridor-forming long lines.
    config = TopologyConfig(
        target_mn_ratio=1.55,
        w_intersect=25,
    )

    for voltage in (345, 115):
        gen = TopologyGenerator(substations=substations, voltage_kv=voltage, config=config, verbose=True)
        lines = gen.run()
        _save_lines_csv("dartboard", voltage, lines)


if __name__ == "__main__":
    main()
