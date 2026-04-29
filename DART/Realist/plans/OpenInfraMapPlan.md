# OpenInfraMap High-Voltage Line Extraction & Visualization Plan

## Objective

Pull high-voltage transmission line geometry from OpenInfraMap (sourced from OpenStreetMap) for the Texas and/or New York regions and plot the results as a geographic map overlay. This provides a real-world reference layer for comparison against Dartboard's synthetic topologies.

---

## Background

[OpenInfraMap](https://openinframap.org/) visualizes global electricity infrastructure using data from [OpenStreetMap](https://www.openstreetmap.org/). Power lines in OSM are tagged with `power=line` and carry a `voltage` tag (in volts). The [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) allows programmatic extraction of these features by geographic area and attribute filters.

Two practical extraction methods exist:

| Method | Pros | Cons |
|---|---|---|
| **Overpass API** (via `requests` + Overpass QL) | No extra dependencies; fine-grained query control; returns GeoJSON directly | Rate-limited; large queries may time out |
| **earth-osm** (PyPSA package) | Handles download, caching, cleaning; CLI + Python API | Heavier dependency; region codes are country-level by default |

**Chosen approach:** Direct Overpass API queries via Python `requests`. This keeps dependencies minimal and allows precise bounding-box + voltage filtering in a single query.

---

## Step 1 — Define Region Bounding Boxes

Use the same region bounds already configured in `config/texas.yaml` and `config/new_york.yaml`. If those configs don't contain explicit lat/lon bounding boxes, define them here:

| Region | South | West | North | East |
|---|---|---|---|---|
| Texas | 25.83 | -106.65 | 36.50 | -93.51 |
| New York | 40.50 | -79.76 | 45.02 | -71.85 |

## Step 2 — Query Overpass API for High-Voltage Lines

Write `OIM/fetch_hv_lines.py` with the following logic:

```
1. Accept region name (texas / new_york) as CLI argument.
2. Look up bounding box for that region.
3. Build an Overpass QL query:
       [out:json][timeout:120];
       (
         way["power"="line"](bbox);
       );
       out body;
       >;
       out skel qt;
   This fetches all power=line ways plus their constituent nodes
   within the bounding box.
4. POST the query to https://overpass-api.de/api/interpreter
5. Parse the JSON response:
       - Build a dict of node_id -> (lat, lon) from elements where type=="node"
       - For each element where type=="way":
           - Extract tags: voltage, cables, operator, name
           - Resolve the node refs to (lat, lon) coordinate lists
6. Filter to high-voltage lines only:
       - Parse the voltage tag (may be semicolon-separated for multi-circuit)
       - Keep lines where max(voltages) >= 69,000 V  (69 kV and above)
       - Classify into voltage tiers:
           - 69–114 kV   (sub-transmission)
           - 115–229 kV  (HV)
           - 230–344 kV  (EHV-1)
           - 345–499 kV  (EHV-2)
           - 500+ kV     (UHV / HVDC)
7. Save results to OIM/data/{region}_hv_lines.geojson as a FeatureCollection
   where each Feature is a LineString with properties:
       voltage_kv, voltage_tier, cables, operator, osm_id
8. Also save a summary CSV: OIM/data/{region}_hv_lines_summary.csv
       columns: osm_id, voltage_kv, voltage_tier, cables, operator, num_nodes
```

### Dependencies

- `requests` (already in environment)
- `json` (stdlib)
- `argparse` (stdlib)

No new packages required for this step.

## Step 3 — Plot the Lines

Write `OIM/plot_hv_lines.py` with the following logic:

```
1. Accept region name as CLI argument.
2. Load OIM/data/{region}_hv_lines.geojson.
3. Create a matplotlib figure with cartopy or plain lat/lon axes.
   (Prefer matplotlib + contextily for basemap tiles, or plain matplotlib
    if keeping dependencies minimal.)
4. For each feature, plot the LineString geometry color-coded by voltage tier:
       - 69–114 kV    → gray,   linewidth=0.5
       - 115–229 kV   → blue,   linewidth=0.8
       - 230–344 kV   → orange, linewidth=1.2
       - 345–499 kV   → red,    linewidth=1.5
       - 500+ kV      → purple, linewidth=2.0
5. Add legend, title ("OpenInfraMap HV Lines — {Region}"), and axis labels.
6. Apply cosine aspect ratio correction (as used elsewhere in Dartboard viz).
7. Save to OIM/output/{region}_hv_lines.png at 300 DPI.
8. Optionally overlay Dartboard synthetic substations from
   data/processed/ for visual comparison.
```

### Dependencies

- `matplotlib` (already in environment)
- `numpy` (already in environment)
- Optional: `contextily` for basemap tiles (would need `pip install contextily`)

## Step 4 — Summary Statistics

Print to console after plotting:

```
Region: Texas
Total HV lines fetched: X
  69–114 kV:   N lines, L total km
  115–229 kV:  N lines, L total km
  230–344 kV:  N lines, L total km
  345–499 kV:  N lines, L total km
  500+ kV:     N lines, L total km
```

Distances computed via Haversine on the node coordinates.

---

## File Structure

```
OIM/
  OpenInfraMapPlan.md          ← this file
  fetch_hv_lines.py            ← Step 2: Overpass query + GeoJSON export
  plot_hv_lines.py             ← Step 3: Visualization
  data/
    texas_hv_lines.geojson     ← fetched line geometry
    texas_hv_lines_summary.csv
    new_york_hv_lines.geojson
    new_york_hv_lines_summary.csv
  output/
    texas_hv_lines.png         ← rendered maps
    new_york_hv_lines.png
```

---

## Potential Issues & Mitigations

| Issue | Mitigation |
|---|---|
| Overpass query times out for Texas (large area) | Split into sub-bounding-boxes (e.g., 4 quadrants) and merge results; deduplicate by OSM way ID |
| Voltage tag missing or malformed | Default to keeping the line but classifying as "unknown"; log warnings |
| Semicolon-separated voltages (multi-circuit) | Split on `;`, parse each as int, take max for classification |
| Rate limiting on Overpass API | Add retry with exponential backoff; cache responses locally |
| Lines crossing region boundary partially included | Accept partial lines; they still show real corridor locations |

---

## Data Licensing

All data from OpenStreetMap is licensed under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/). Any outputs using this data should include attribution: "Data from OpenStreetMap contributors, ODbL."

---

## References

- [OpenInfraMap](https://openinframap.org/) — interactive map of global electricity infrastructure
- [OpenInfraMap About](https://openinframap.org/about) — data sourcing details
- [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) — OSM query API
- [Overpass Turbo](https://overpass-turbo.eu/) — interactive query testing
- [OSM Tag: power=line](https://wiki.openstreetmap.org/wiki/Tag:power=line) — tagging schema
- [earth-osm](https://github.com/pypsa-meets-earth/earth-osm) — alternative Python extraction tool
- [Infrageomatics](https://www.infrageomatics.com/products/osm-export) — commercial OSM infrastructure exports
