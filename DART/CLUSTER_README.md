# Cluster Setup — Princeton Adroit

How to run Dartboard SCED jobs on the Princeton Adroit HPC cluster.

---

## Starting Claude Code for cluster work

```bash
claude --dangerously-skip-permissions
```

Skips all permission prompts for the session — no interruptions at all.
Use this for cluster work where every command is intentional.

Narrower alternatives:
- `claude -y` — auto-approves prompts but still shows them
- `claude -y --allowedTools "Bash,Write,Edit,Read"` — auto-approve, restricted tool set
- **Shift+Tab** mid-session — toggles auto-accept on/off without restarting

---

## SSH Setup (one-time, already done)

Key pair lives at `~/.ssh/adroit` (ed25519). Config in `~/.ssh/config`:

```
Host adroit
    HostName adroit.princeton.edu
    User js0735
    IdentityFile ~/.ssh/adroit
    AddKeysToAgent yes
    UseKeychain yes
    ControlMaster auto
    ControlPath ~/.ssh/sockets/adroit-%r@%h:%p
    ControlPersist 4h
```

Princeton uses two-factor SSH: key (factor 1) + Duo push (factor 2). Claude Code
cannot handle the Duo push, so **ControlMaster multiplexing is required** — one
authenticated session keeps a socket open that Claude reuses without re-authing.

---

## Opening a session (required before Claude can reach the cluster)

Open a terminal and run:

```bash
ssh adroit
```

Approve the Duo push. Leave the tab open (or just let it idle — socket persists 4 hours).
Claude Code can then run arbitrary SSH/rsync commands against the cluster without prompts.

To explicitly close the socket early:
```bash
ssh -O exit adroit
```

---

## Cluster layout

| Path | What |
|---|---|
| `/scratch/network/js0735/dartboard/` | Project root on cluster |
| `/scratch/network/js0735/dartboard/env/` | Conda environment (Python 3.11) |
| `/scratch/network/js0735/dartboard/sced_inputs/` | Vatic input CSVs (synced from laptop) |
| `/scratch/network/js0735/dartboard/results/` | Vatic output CSVs |
| `/scratch/network/js0735/dartboard/logs/` | SLURM stdout/stderr |
| `/scratch/network/js0735/dartboard/vatic/` | Vatic library |
| `/scratch/network/js0735/dartboard/run_sced.py` | Main simulation script |

Scratch quota: 16 TB available (shared pool). No per-user limit documented; don't
leave large result sets sitting there indefinitely.

---

## Conda environments

**Use `vatic-test` for all SCED runs.** It has vatic installed as a proper package
(including `models.py`) and Gurobi licensed. This is the env the notebook used for v.1.

```
/home/js0735/.conda/envs/vatic-test   ← use this
/scratch/network/js0735/dartboard/env  ← scratch env, not used for SCED
```

Key facts about `vatic-test`:
- Vatic is installed as a Python package — do NOT copy a local `vatic/` directory to
  scratch, it will shadow the installed package and break the import.
- Gurobi is available and licensed (faster than CBC for MIP).
- License file: `/usr/licensed/gurobi/license/gurobi.lic`

To verify the env works:
```bash
ssh adroit "
  /home/js0735/.conda/envs/vatic-test/bin/python -c \
    'from vatic.engines import Simulator; print(\"ok\")'
"
```

To install additional packages into vatic-test (from login node, not compute node):
```bash
ssh adroit "/home/js0735/.conda/envs/vatic-test/bin/pip install <package>"
```

---

## Syncing files from laptop to cluster

Run from the repo root (`~/Desktop/Dartboard`):

```bash
# SCED input tables
rsync -av Realist/grid_data/sced_inputs/ \
  adroit:/scratch/network/js0735/dartboard/sced_inputs/

# Vatic library
rsync -av Realist/vatic/ \
  adroit:/scratch/network/js0735/dartboard/vatic/

# Run script
rsync -av Realist/ERCOT/run_sced.py \
  adroit:/scratch/network/js0735/dartboard/
```

All three in one shot:
```bash
rsync -av Realist/grid_data/sced_inputs/ adroit:/scratch/network/js0735/dartboard/sced_inputs/ && \
rsync -av Realist/vatic/ adroit:/scratch/network/js0735/dartboard/vatic/ && \
rsync -av Realist/ERCOT/run_sced.py adroit:/scratch/network/js0735/dartboard/
```

---

## Submitting a job

The SLURM script is at `Realist/ERCOT/run_sced.slurm` locally and synced to scratch.
`run_sced.py` reads `DARTBOARD_SCRATCH` env var to find inputs when running on the cluster;
the SLURM script sets this automatically. Locally (no env var set) it uses the normal
repo-relative paths.

**Full sync + submit in one shot (Claude Code can do this):**
```bash
rsync -av Realist/grid_data/sced_inputs/ adroit:/scratch/network/js0735/dartboard/sced_inputs/ && \
rsync -av Realist/vatic/ adroit:/scratch/network/js0735/dartboard/vatic/ && \
rsync -av Realist/ERCOT/run_sced.py Realist/ERCOT/run_sced.slurm adroit:/scratch/network/js0735/dartboard/ && \
ssh adroit "sbatch /scratch/network/js0735/dartboard/run_sced.slurm"
```

**Check queue status:**
```bash
ssh adroit "squeue -u js0735"
```

**Watch a running job's log:**
```bash
ssh adroit "tail -f /scratch/network/js0735/dartboard/logs/dartboard-sced_<JOBID>.out"
```

**Cancel a job:**
```bash
ssh adroit "scancel <JOBID>"
```

---

## Pulling results back to laptop

```bash
rsync -av adroit:/scratch/network/js0735/dartboard/results/ \
  Realist/VaticOutputs/cluster_run/
```

---

## SLURM partition summary

| Partition | Time limit | Nodes | Notes |
|---|---|---|---|
| `all` (default) | 7 days | 9 | Use this for SCED runs |
| `gpu` | 7 days | 3 | GPU nodes, not needed for SCED |
| `class` | 4 days | 11 | Teaching partition, avoid |

Current SCED job spec: 4 CPUs, 16 GB RAM, 4 hr wall time. CBC is single-threaded
so extra CPUs mainly help with Python pre/post-processing.

---

## Troubleshooting

**"Permission denied (keyboard-interactive)" from Claude Code**
The ControlMaster socket isn't open. Open a terminal, run `ssh adroit`, approve Duo.

**Job fails immediately (exit code 1)**
Check the `.err` log: `ssh adroit "cat /scratch/network/js0735/dartboard/logs/*.err"`

**CBC not found in environment**
```bash
ssh adroit "conda install -y -p /scratch/network/js0735/dartboard/env -c conda-forge coincbc"
```

**Scratch directory full**
```bash
ssh adroit "du -sh /scratch/network/js0735/dartboard/*"
```
