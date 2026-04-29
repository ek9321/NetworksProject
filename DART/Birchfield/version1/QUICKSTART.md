# Quick Start Guide

Get up and running in 5 minutes!

## Step 1: Open in VS Code
```bash
cd /path/to/IW
code .
```

## Step 2: Activate the Python Environment
```bash
# Use the existing conda environment:
source .conda/bin/activate

# Or create a new one:
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Step 3: Run the Pipeline
```bash
# Run full pipeline
python run_pipeline.py

# Or run with caching (faster re-runs)
python run_pipeline.py --skip
```

## Step 4: Check Outputs
- Intermediate data: `output/intermediate/`
- Visualizations: `output/visualizations/`

---

## Running Individual Phases

```bash
# List all phases
python run_pipeline.py --list

# Run a specific phase
python run_pipeline.py --phase 3

# Run from phase 4 onwards
python run_pipeline.py --from 4

# Run phases directly
python -m pipeline.phase2_census
```

---

## Required Input Files

Make sure these are in the project root:
- `GoldBook.pdf` - NY ISO Gold Book
- `2020_Gaz_zcta_national 2 (1).txt` - Census Gazetteer
- `eia8602023/` - EIA-860 data folder with Excel files

---

## Common Issues

**"python: command not found"**
→ Try `python3` instead of `python`

**"No module named 'pdfplumber'"**
→ Activate the environment: `source .conda/bin/activate`

**"Run Phase X first: file not found"**
→ Phases must run in order. Use `python run_pipeline.py` to run all, or `--from N` to start from phase N

**"Census API request failed"**
→ Check internet connection. The Census API is required for Phase 2

**VS Code doesn't recognize Python**
→ Press `Ctrl+Shift+P`, type "Python: Select Interpreter", choose the one in `venv/`

---

Need more help? See the full [README.md](README.md) for detailed instructions.
