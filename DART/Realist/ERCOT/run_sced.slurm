#!/bin/bash
#SBATCH --job-name=dartboard-sced
#SBATCH --output=/scratch/network/js0735/dartboard/logs/%x_%j.out
#SBATCH --error=/scratch/network/js0735/dartboard/logs/%x_%j.err
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --partition=all
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=js0735@princeton.edu

# ---------------------------------------------------------------------------
# Dartboard DC-SCED job — Princeton Adroit cluster
#
# Uses the vatic-test conda env (/home/js0735/.conda/envs/vatic-test) which
# has vatic installed as a package (with models.py) and Gurobi licensed.
#
# Submit from laptop (after ControlMaster is open):
#   ssh adroit "sbatch /scratch/network/js0735/dartboard/run_sced.slurm"
#
# Compute nodes have no internet — install packages from login node only.
# ---------------------------------------------------------------------------

SCRATCH=/scratch/network/js0735/dartboard
ENV=/home/js0735/.conda/envs/vatic-test

mkdir -p $SCRATCH/logs

module purge
module load anaconda3/2024.10 gurobi/11.0.3

export DARTBOARD_SCRATCH=$SCRATCH
export GRB_LICENSE_FILE=/usr/licensed/gurobi/license/gurobi.lic

echo "Starting SCED run at $(date)"
echo "Node: $(hostname)"
echo "CPUs: $SLURM_CPUS_PER_TASK  Mem: $SLURM_MEM_PER_NODE MB"
echo "Env:  $ENV"

$ENV/bin/python $SCRATCH/run_sced.py

echo "Finished at $(date)"
