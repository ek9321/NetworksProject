# LMP API Pipeline Plan

## How the HTML Currently Works

### The visualizer is entirely self-contained

`grid_visualizer.html` (2.3 MB) contains no runtime HTTP calls and no external data dependencies. It is a static file that works by opening it in a browser. All data — substations, transmission lines, ERCOT zone polygons — is baked directly into the file as inlined JavaScript constants.

### How `generate_visualizer.py` builds the HTML

`Realist/ERCOT/generate_visualizer.py` runs once and emits the HTML. It reads five source files:

| Variable in script | Source file | What it contains |
|---|---|---|
| `OSM_SUBS` | `Realist/grid_data/texas_substations.geojson` | 5,786 OSM physical substations ≥ 115 kV |
| `LINES` | `Realist/grid_data/texas_hv_lines.geojson` | 22,913 OSM HV transmission lines |
| `ZONES` | `Realist/grid_data/ercot_zones.geojson` | 4 ERCOT load zone polygons |
| `V5` | `Realist/grid_data/matching_results/texas_matched_substations_v5.csv` | ERCOT settlement point → OSM substation matches |
| `EIA_GEN` | `Birchfield/data/eia8602023/3_1_Generator_Y2023.xlsx` | EIA-860 generator capacity by plant |

> **Note:** `generate_visualizer.py` still references the old pre-reorganization paths (`OIM/data/...`, `OIM/FirstPass/...`). These need to be updated to the new `Realist/grid_data/...` paths before the script will run correctly.

The script processes these files in Python and writes the HTML with three embedded JavaScript constants:

```
const NODES = [{i, lat, lon, id, name, kv, ercot, conf, src, sc, lz, mw, tech, op, stype}, ...]
const LINES = [{coords: [[lon, lat], ...], kv}, ...]
const ZONES = {type: "FeatureCollection", features: [...]}
```

`NODES` is the most important. Each entry includes the OSM substation's physical location (`lat`, `lon`), voltage level (`kv`), operator (`op`), and — for matched substations — the ERCOT settlement point name (`ercot`), match confidence (`conf`), match source (`src`), and load zone (`lz`). Unmatched substations have `ercot: ""`.

The HTML renders this data with Leaflet.js. Nodes are colored by match quality or voltage tier, toggled via the control panel. No LMP data is currently in the HTML at all.

---

## Where Things Are Stored

```
Realist/
├── grid_data/
│   ├── texas_substations.geojson          ← OSM substations (source for NODES)
│   ├── texas_hv_lines.geojson             ← OSM HV lines (source for LINES)
│   ├── ercot_zones.geojson                ← Zone polygons (source for ZONES)
│   ├── lmp_snapshot.json                  ← Live LMP data (written by GitHub Action)
│   └── matching_results/
│       ├── texas_matched_substations_v5.csv  ← Used by generate_visualizer.py
│       └── texas_matched_substations_v6.csv  ← Newer matching (not yet used)
│
├── ERCOT/
│   ├── generate_visualizer.py             ← Builds the HTML from static sources
│   └── pull_lmp_ercot.py                  ← (to be written) fetches LMPs from ERCOT API
│
└── grid_visualizer.html                   ← Output: self-contained map + live LMP via fetch
```

---

## Why Replace gridstatus with the ERCOT API

The existing `pull_lmp.py` in `OIM/GridStatus/` uses the `gridstatus` library, which wraps the ERCOT API. It requires a Python 3.12 virtual environment, is not compatible with GitHub Actions without extra setup, and produces output only consumed by static PNGs — not the HTML.

The ERCOT Public API is the canonical source. Hitting it directly:
- Runs in any standard Python 3.11+ environment (no special venv)
- Gives us JSON output shaped for the HTML's lookup pattern
- Works inside GitHub Actions with credentials stored as repository secrets

---

## Target Architecture: GitHub Pages + GitHub Actions

The goal is a dashboard hosted at a shareable URL (GitHub Pages) with LMP data that stays fresh automatically (GitHub Actions), requiring no local server to view or share.

```
┌─────────────────────────────────────────────────────────┐
│  GitHub Actions  (runs on schedule, every 15 min)        │
│                                                           │
│  1. Authenticate with ERCOT API                           │
│     (credentials in repository Secrets, never in code)    │
│  2. Fetch np6-788-cd settlement point prices              │
│  3. Write Realist/grid_data/lmp_snapshot.json             │
│  4. git commit + push to main                             │
└────────────────────────┬────────────────────────────────┘
                         │ triggers Pages rebuild
                         ▼
┌─────────────────────────────────────────────────────────┐
│  GitHub Pages  (https://emmettsouder.github.io/Dartboard)│
│                                                           │
│  Serves static files from Realist/ folder:               │
│    grid_visualizer.html   ← inlined substations/lines    │
│    grid_data/lmp_snapshot.json  ← refreshed every 15 min │
└────────────────────────┬────────────────────────────────┘
                         │ browser fetches lmp_snapshot.json
                         ▼
              LMP overlay on interactive map
```

**Why this works for future growth:** The only thing that changes when you want historical data is what the GitHub Action writes and where the HTML fetches from. The static infrastructure layer (substations, lines, zones) stays inlined forever. If LMP history moves to an online database, you swap the `fetch('./grid_data/lmp_snapshot.json')` call in the HTML for a fetch to that external URL — the rest is unchanged.

---

## ERCOT Public API

### Registration

Free. Create an account at [apiexplorer.ercot.com](https://apiexplorer.ercot.com). You will get:
- A username and password
- A **subscription key** from the Products page

Full registration guide: [developer.ercot.com/registration-and-authentication](https://developer.ercot.com/applications/pubapi/user-guide/registration-and-authentication/)

### Authentication

The API uses a B2C token flow. POST to the B2C endpoint with your credentials to get a short-lived ID token:

```python
resp = requests.post(AUTH_URL, data={
    "grant_type": "password",
    "username": os.environ["ERCOT_USERNAME"],
    "password": os.environ["ERCOT_PASSWORD"],
    "client_id": os.environ["ERCOT_CLIENT_ID"],
    "scope": "openid profile",
})
id_token = resp.json()["id_token"]
```

Tokens are valid for **one hour**. Since the GitHub Action runs as a fresh process each time, it just fetches a new token on every run — no caching needed.

### Making a Request

All requests require two headers:

```python
headers = {
    "Authorization": f"Bearer {id_token}",
    "Ocp-Apim-Subscription-Key": os.environ["ERCOT_SUBSCRIPTION_KEY"],
}
BASE = "https://api.ercot.com/api/public-reports"
```

### Relevant LMP Endpoints

| Endpoint | Report ID | Content | Cadence |
|---|---|---|---|
| `np6-788-cd/lmp_node_zone_hub` | NP6-788-CD | LMP by Settlement Point (resource nodes, load zones, hubs) | Every 5 min (per SCED) |
| `np6-905-cd/spp_node_zone_hub` | NP6-905-CD | Settlement Point Price (15-min averages) | Every 15 min |
| `np6-787-cd` | NP6-787-CD | LMP by Electrical Bus (raw bus-level) | Every 5 min |

Use `np6-788-cd`. Settlement point names are already stored in the `ercot` field of each NODES entry, so no secondary lookup is needed.

---

## Implementation Steps

### Step 1: Credentials

Register at apiexplorer.ercot.com and collect:
- `ERCOT_USERNAME`
- `ERCOT_PASSWORD`
- `ERCOT_CLIENT_ID` (from the registration guide)
- `ERCOT_SUBSCRIPTION_KEY`

For local development, store these in `Realist/.env` (add `Realist/.env` to `.gitignore`). The `pull_lmp_ercot.py` script loads them with `python-dotenv`.

For GitHub Actions, add them as **repository secrets** (Settings → Secrets and variables → Actions). They are injected as environment variables at runtime and never appear in any file.

### Step 2: `pull_lmp_ercot.py`

New script at `Realist/ERCOT/pull_lmp_ercot.py`. It should:

1. Authenticate → get `id_token`
2. GET `https://api.ercot.com/api/public-reports/np6-788-cd/lmp_node_zone_hub`
3. Find the latest SCED timestamp in the response
4. Partition records into `lmp` (resource nodes), `hub`, and `zone` buckets
5. Write `Realist/grid_data/lmp_snapshot.json`:

```json
{
  "timestamp": "2026-02-25T14:35:00-06:00",
  "fetched_at": "2026-02-25T20:37:12Z",
  "lmp": {
    "SHILOH_ALL": 41.32,
    "MHOS_ALL":   38.10
  },
  "hub": {
    "HB_BUSAVG":  40.50,
    "HB_NORTH":   39.22,
    "HB_HOUSTON": 43.10,
    "HB_SOUTH":   38.75,
    "HB_WEST":    35.44
  },
  "zone": {
    "LZ_NORTH":   39.80,
    "LZ_HOUSTON": 43.50,
    "LZ_SOUTH":   38.40,
    "LZ_WEST":    35.20
  }
}
```

### Step 3: GitHub Actions workflow

New file at `.github/workflows/refresh_lmp.yml`:

```yaml
name: Refresh LMP snapshot

on:
  schedule:
    - cron: '*/15 * * * *'   # every 15 minutes
  workflow_dispatch:           # allow manual trigger

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install requests python-dotenv

      - name: Fetch LMPs from ERCOT API
        env:
          ERCOT_USERNAME:         ${{ secrets.ERCOT_USERNAME }}
          ERCOT_PASSWORD:         ${{ secrets.ERCOT_PASSWORD }}
          ERCOT_CLIENT_ID:        ${{ secrets.ERCOT_CLIENT_ID }}
          ERCOT_SUBSCRIPTION_KEY: ${{ secrets.ERCOT_SUBSCRIPTION_KEY }}
        run: python Realist/ERCOT/pull_lmp_ercot.py

      - name: Commit updated snapshot
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add Realist/grid_data/lmp_snapshot.json
          git diff --cached --quiet || git commit -m "chore: refresh LMP snapshot"
          git push
```

The `git diff --cached --quiet ||` guard means no commit is made if the data hasn't changed (e.g., outside ERCOT market hours), keeping the commit history clean.

### Step 4: Enable GitHub Pages

In the repository settings (Settings → Pages):
- Source: **Deploy from a branch**
- Branch: `main`
- Folder: `/Realist`

This serves everything under `Realist/` at `https://emmettsouder.github.io/Dartboard/`. The HTML is at `https://emmettsouder.github.io/Dartboard/grid_visualizer.html` and fetches `./grid_data/lmp_snapshot.json` relative to that URL.

### Step 5: Changes to `grid_visualizer.html`

The HTML stays mostly as-is. Two additions:

**a) Fetch LMP snapshot at startup**

```javascript
let lmpMap = {};
let lmpMeta = null;

fetch('./grid_data/lmp_snapshot.json')
  .then(r => r.json())
  .then(data => {
    lmpMeta = data;
    lmpMap  = data.lmp || {};
    applyLmpColors();
    updateLmpPanel(data);
  })
  .catch(() => {
    // No snapshot yet — map still works, just no LMP overlay
  });
```

Note the path is `./grid_data/lmp_snapshot.json`, not `./lmp_snapshot.json`, matching the repo layout and the Pages URL structure.

**b) LMP color mode**

Add "LMP" as a third option in the existing "Colour by" radio group. When active:
- Matched nodes: colored on a diverging scale anchored at `lmpMeta.hub.HB_BUSAVG` (red = above average, blue = below)
- Unmatched nodes: grey
- Panel shows snapshot timestamp + hub and zone prices

**c) Popup addition**

Add an LMP row to the existing node popup (shown only when `lmpMap[node.ercot]` exists).

### Step 6: Fix `generate_visualizer.py` paths

Update the hardcoded input paths to match the reorganized repo:

| Old path | New path |
|---|---|
| `OIM/data/texas_substations.geojson` | `Realist/grid_data/texas_substations.geojson` |
| `OIM/data/texas_hv_lines.geojson` | `Realist/grid_data/texas_hv_lines.geojson` |
| `OIM/data/ercot_zones.geojson` | `Realist/grid_data/ercot_zones.geojson` |
| `OIM/FirstPass/texas_matched_substations_v5.csv` | `Realist/grid_data/matching_results/texas_matched_substations_v6.csv` |
| `data/eia8602023/...` | `Birchfield/data/eia8602023/...` |
| output `grid_visualizer.html` | `Realist/grid_visualizer.html` |

---

## What Gets Matched, What Doesn't

The `ercot` field is populated for roughly 26% of settlement points (the directly matched ones from v5/v6). When LMP mode is active:

- **Matched nodes**: colored by LMP
- **Unmatched nodes** (`ercot == ""`): rendered grey or hidden

Hub and zone price labels can be overlaid at fixed geographic positions as Leaflet tooltips, matching what `plot_lmp_map.py` currently does in the static PNGs.

---

## Future Data Path

The architecture is designed so that adding historical data later requires no structural changes:

1. **Now:** GitHub Action writes `lmp_snapshot.json` (one record, ~15 KB)
2. **Later:** Action writes to an online store (Supabase, S3, etc.) instead, and the HTML fetch URL changes — everything else stays the same
3. **Much later:** Historical time-series explorer could be a second HTML page served from the same Pages URL, fetching from the same online store

No local storage, no server to maintain at any stage.

---

## Summary of New Files

| File | Action |
|---|---|
| `Realist/ERCOT/pull_lmp_ercot.py` | New: authenticates with ERCOT API, writes `lmp_snapshot.json` |
| `Realist/grid_data/lmp_snapshot.json` | New: committed by GitHub Action, fetched by HTML |
| `.github/workflows/refresh_lmp.yml` | New: scheduled action that runs `pull_lmp_ercot.py` and commits |
| `Realist/grid_visualizer.html` | Modify: add fetch for LMP JSON, LMP color mode, popup field |
| `Realist/ERCOT/generate_visualizer.py` | Fix: update file paths for new repo layout |
| `Realist/.env` (gitignored) | New: local dev credentials (never committed) |
