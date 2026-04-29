# CLAUDE.md

Agent instructions for the Dartboard ERCOT project.

---

## What This Project Is

A DC-SCED model of the real ERCOT grid built entirely from public data (OpenStreetMap, ERCOT MORA, EIA-860, SCED disclosure). Active work is in `Realist/`. The `Birchfield/` directory is an archival synthetic grid project — ignore it except for `Birchfield/data/processed/eia860_generators.csv`, which is still used by the Realist pipeline for generator geo-snapping.

---

## How to Operate

**Read first, act second.** This project has a lot of moving parts — three topology versions, 80+ calibration experiments, multiple session logs, and real physics constraints. Before making changes:

1. **Read `README.md`** — the current-state anchor. Model state, known issues, next priorities. Trust it over session logs if they conflict.
2. **Read recent session logs** in `Realist/ERCOT_Calibration_Experiments/session_*.md` — these document what was tried, what worked, what failed, and why. The most recent log picks up where the last session left off.
3. **Read `experiments.md`** — the quick-reference table of all 80+ runs. Understand what's been tried before proposing something new.

These are messy, real-world problems — power systems physics, noisy public data, compensating errors in the model. But they are solvable with patience and methodical iteration. The history shows that every major improvement came from understanding the root cause before writing code.

---

## Code Conventions

- **Clarity over cleverness.** This is a research artifact, not a production system.
- **Implement only what is needed.** Do not add features for convenience.
- **Do not modify unrelated files.** A branch rating fix does not require touching run_sced.py.
- **When ambiguous, stop and ask.** Don't guess at physics or data interpretation.

---

## Key Constraints

**345 kV policy: all at 2400 MVA except WESTEX.** The correct approach (implemented in `build_osm_branch_table.py`) upgrades all 345 kV 1200→2400 MVA EXCEPT L1605_1612 (Morgan Creek→Tonkawa). This preserves the WESTEX export constraint.

**PMax in gen.csv is nameplate capacity.** CF scaling is applied only in `run_sced.py` at dispatch time. Never bake CF into PMax in build scripts.

**Storage elements use the Vatic/Egret storage dict format.** See the storage loading block in `run_sced.py` (Step 4b).

---

## Adroit Cluster

```
SSH alias:    adroit  (Princeton Adroit, adroit.princeton.edu)
Scratch:      /scratch/network/js0735/dartboard/
Conda env:    /home/js0735/.conda/envs/vatic-test
Gurobi:       /usr/licensed/gurobi/license/gurobi.lic
SLURM script: run_sced_array.slurm  (in scratch dir)
```

Results land in: `$SCRATCH/sced_inputs_<TAG>/results_<TAG>/`

---

## Session Logs

Full history in `Realist/ERCOT_Calibration_Experiments/`. Each session log documents: code changes made, experiments run, key findings, and next steps. If starting a new session, read the most recent log to pick up context.

`experiments.md` has the quick-reference table of all runs.
