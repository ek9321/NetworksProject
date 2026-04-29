#!/usr/bin/env python3
"""
Step 1 — Build bus.csv for DC-SCED Vatic input.

Aggregates ERCOT's 18,989 ELECTRICAL_BUS entries to 7,755 unique PSSE buses.
Multiple ELECTRICAL_BUS entries sharing a PSSE_BUS_NUMBER are variants of the
same physical bus (e.g. COMCHPKW_5, COMCHPKW_5M, COMCHPKW_5N are all the
Comanche Peak 345 kV bus). The DC power flow network is defined at PSSE bus
level; the ELECTRICAL_BUS list is preserved as metadata.

Sources:
  - SP_List_EB_Mapping/Settlement_Points_*.csv   -> PSSE bus name, substation, kV, zone
  - Electrical_Bus_to_Hub_Lists/Full_Electrical_Bus_*.csv  -> full bus catalog
  - Electrical_Bus_to_Hub_Lists/Electrical_BusMap_To_HUB_*.csv -> hub assignment (345 kV only)
  - matching_results/texas_matched_substations_v6.csv -> geographic coordinates

Output: grid_data/sced_inputs/bus.csv
"""

import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "Realist" / "grid_data"
OUT_DIR = DATA / "sced_inputs"
OUT_DIR.mkdir(exist_ok=True)

SP_FILE   = DATA / "SP_List_EB_Mapping" / "Settlement_Points_01292026_104938.csv"
HUB_FILE  = DATA / "Electrical_Bus_to_Hub_Lists" / "Electrical_BusMap_To_HUB_02052026_141606.csv"
FULL_FILE = DATA / "Electrical_Bus_to_Hub_Lists" / "Full_Electrical_Bus_02052026_141606.csv"
V6_FILE   = DATA / "matching_results" / "texas_matched_substations_v6.csv"

# ---------------------------------------------------------------------------
# Zone mapping
# ---------------------------------------------------------------------------
ZONE_SHORT = {
    "LZ_NORTH":   "NORTH",
    "LZ_SOUTH":   "SOUTH",
    "LZ_HOUSTON": "HOUSTON",
    "LZ_WEST":    "WEST",
}
ZONE_NUM = {
    "LZ_NORTH":   1,
    "LZ_SOUTH":   2,
    "LZ_HOUSTON": 3,
    "LZ_WEST":    4,
}
# Fallback coordinates when no v6 match exists for a substation
ZONE_CENTROIDS = {
    "LZ_WEST":    (31.0, -102.5),
    "LZ_NORTH":   (33.5,  -97.0),
    "LZ_HOUSTON": (29.8,  -95.3),
    "LZ_SOUTH":   (29.0,  -98.0),
}
TEXAS_CENTER = (31.0, -100.0)

# ---------------------------------------------------------------------------
# Load inputs
# ---------------------------------------------------------------------------
sp   = pd.read_csv(SP_FILE,   dtype=str)
hub  = pd.read_csv(HUB_FILE,  dtype=str)
full = pd.read_csv(FULL_FILE, dtype=str)
v6   = pd.read_csv(V6_FILE,   dtype=str)

# ---------------------------------------------------------------------------
# 1. Aggregate Settlement_Points to PSSE bus level
#    For each PSSE_BUS_NUMBER keep the first row (PSSE_BUS_NAME, SUBSTATION,
#    VOLTAGE_LEVEL, SETTLEMENT_LOAD_ZONE are consistent within a group).
#    Also collect all ELECTRICAL_BUS and RESOURCE_NODE values as pipe-joined lists.
# ---------------------------------------------------------------------------
sp["RESOURCE_NODE"] = sp["RESOURCE_NODE"].fillna("")

eb_agg = (
    sp.groupby("PSSE_BUS_NUMBER")["ELECTRICAL_BUS"]
    .apply(lambda s: "|".join(s.dropna().unique()))
    .reset_index()
    .rename(columns={"ELECTRICAL_BUS": "electrical_buses"})
)
rn_agg = (
    sp.groupby("PSSE_BUS_NUMBER")["RESOURCE_NODE"]
    .apply(lambda s: "|".join(x for x in s.unique() if x))
    .reset_index()
    .rename(columns={"RESOURCE_NODE": "resource_nodes"})
)

# One canonical row per PSSE bus (first occurrence)
psse = sp.drop_duplicates(subset="PSSE_BUS_NUMBER", keep="first").copy()
psse = psse.merge(eb_agg, on="PSSE_BUS_NUMBER", how="left")
psse = psse.merge(rn_agg, on="PSSE_BUS_NUMBER", how="left")

# ---------------------------------------------------------------------------
# 2. Join hub assignment (345 kV buses only; 870 entries)
#    The hub map matches on ELECTRICAL_BUS, but each PSSE group may contain
#    multiple ELECTRICAL_BUS aliases — only one of which appears in hub map.
#    Fix: join hub map against ALL SP rows first, then aggregate to PSSE level.
# ---------------------------------------------------------------------------
hub = hub.rename(columns={
    "ELECTRICAL_BUS":    "hub_eb",
    "ELECTRICAL_BUS_KV": "hub_kv",
    "HUB_BUS_NAME":      "hub_bus_name",
    "HUB":               "hub",
})
hub_per_psse = (
    sp[["PSSE_BUS_NUMBER", "ELECTRICAL_BUS"]]
    .merge(hub[["hub_eb", "hub_kv", "hub_bus_name", "hub"]],
           left_on="ELECTRICAL_BUS", right_on="hub_eb", how="inner")
    .drop_duplicates(subset="PSSE_BUS_NUMBER", keep="first")
    [["PSSE_BUS_NUMBER", "hub_kv", "hub_bus_name", "hub"]]
)
psse = psse.merge(hub_per_psse, on="PSSE_BUS_NUMBER", how="left")

# ---------------------------------------------------------------------------
# 3. BaseKV: prefer hub_map kV (confirmed accurate for 345 kV tier),
#    then Settlement_Points VOLTAGE_LEVEL, default 138.
# ---------------------------------------------------------------------------
psse["BaseKV"] = pd.to_numeric(
    psse["hub_kv"].fillna(psse["VOLTAGE_LEVEL"]), errors="coerce"
).fillna(138.0)

# ---------------------------------------------------------------------------
# 4. Zone
# ---------------------------------------------------------------------------
psse["Zone"]     = psse["SETTLEMENT_LOAD_ZONE"].map(ZONE_SHORT).fillna("UNKNOWN")
psse["Zone Num"] = psse["SETTLEMENT_LOAD_ZONE"].map(ZONE_NUM).fillna(0).astype(int)
psse["Bus Area"] = psse["Zone Num"]
psse["Sub Area"] = psse["Zone Num"]
psse["Area"]     = psse["Zone"].str.title()

# ---------------------------------------------------------------------------
# 5. Geographic coordinates from v6
#    All 4,953 substations in SP are present in v6 (verified).
#    Join on SUBSTATION == ercot_substation.
# ---------------------------------------------------------------------------
v6_geo = (
    v6[["ercot_substation", "lat", "lon", "confidence"]]
    .drop_duplicates(subset="ercot_substation", keep="first")
    .rename(columns={"lat": "v6_lat", "lon": "v6_lon", "confidence": "geo_confidence"})
)

psse = psse.merge(
    v6_geo, left_on="SUBSTATION", right_on="ercot_substation", how="left"
)

# Convert lat/lon to float (v6 was read as str)
psse["v6_lat"] = pd.to_numeric(psse["v6_lat"], errors="coerce")
psse["v6_lon"] = pd.to_numeric(psse["v6_lon"], errors="coerce")

# Assign final coordinates with fallbacks
def _coords(row):
    if pd.notna(row["v6_lat"]):
        return row["v6_lat"], row["v6_lon"]
    lz = row.get("SETTLEMENT_LOAD_ZONE", "")
    if lz in ZONE_CENTROIDS:
        return ZONE_CENTROIDS[lz]
    return TEXAS_CENTER

coords = psse.apply(_coords, axis=1)
psse["lat"] = [c[0] for c in coords]
psse["lng"] = [c[1] for c in coords]
psse["geo_source"] = psse.apply(
    lambda r: "v6" if pd.notna(r["v6_lat"]) else r.get("SETTLEMENT_LOAD_ZONE", "unknown"),
    axis=1,
)

# ---------------------------------------------------------------------------
# 6. Bus ID — sequential integer (1-based, stable sort by PSSE_BUS_NUMBER)
# ---------------------------------------------------------------------------
psse = psse.sort_values("PSSE_BUS_NUMBER").reset_index(drop=True)
psse["Bus ID"] = psse.index + 1

# ---------------------------------------------------------------------------
# 7. Bus Name, Sub Name, Sub Num
# ---------------------------------------------------------------------------
psse["Bus Name"] = psse["PSSE_BUS_NAME"].fillna(psse["ELECTRICAL_BUS"])
psse["Sub Name"] = psse["SUBSTATION"].fillna(psse["ELECTRICAL_BUS"])

# Sequential Sub Num per unique substation
substations = psse["Sub Name"].unique()
sub_num_map = {s: i + 1 for i, s in enumerate(substations)}
psse["Sub Num"] = psse["Sub Name"].map(sub_num_map)

# ---------------------------------------------------------------------------
# 8. Assemble output in Vatic bus.csv column order
#    Extra traceability columns appended after the standard columns.
# ---------------------------------------------------------------------------
out = pd.DataFrame({
    "Bus ID":              psse["Bus ID"],
    "lat":                 psse["lat"],
    "lng":                 psse["lng"],
    "Zone":                psse["Zone"],
    "Sub Name":            psse["Sub Name"],
    "Bus Name":            psse["Bus Name"],
    "Area":                psse["Area"],
    "BaseKV":              psse["BaseKV"],
    "PU Volt":             1.0,
    "Volt (kV)":           psse["BaseKV"],
    "Angle (Deg)":         0.0,
    "MW Load":             0.0,      # filled in Step 5
    "Load Mvar":           0.0,
    "Gen MW":              "",
    "Sub Num":             psse["Sub Num"],
    "Gen Mvar":            "",
    "Switched Shunts Mvar": "",
    "Act G Shunt MW":      0,
    "Act B Shunt Mvar":    0,
    "Zone Num":            psse["Zone Num"],
    "Bus Type":            "PQ",     # overridden to PV for gen buses in Step 3
    "Mismatch MW":         0.0,
    "Mismatch Mvar":       0,
    "Mismatch MVA":        0.0,
    "Bus Area":            psse["Bus Area"],
    "Sub Area":            psse["Sub Area"],
    # Traceability (not read by Vatic)
    "PSSE_BUS_NUMBER":     psse["PSSE_BUS_NUMBER"],
    "electrical_buses":    psse["electrical_buses"],
    "resource_nodes":      psse["resource_nodes"],
    "hub":                 psse["hub"].fillna(""),
    "geo_source":          psse["geo_source"],
    "geo_confidence":      psse["geo_confidence"].fillna("none"),
})

out.to_csv(OUT_DIR / "bus.csv", index=False)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
total      = len(out)
geo_v6     = (psse["v6_lat"].notna()).sum()
geo_zone   = total - geo_v6
high_med   = psse["geo_confidence"].isin(["high", "medium"]).sum()

print(f"Buses written:     {total:,}")
print(f"  Geo from v6:     {geo_v6:,}  ({100*geo_v6/total:.1f}%)")
print(f"  Zone centroid:   {geo_zone:,}  ({100*geo_zone/total:.1f}%)")
print(f"  High/med conf:   {high_med:,}  ({100*high_med/total:.1f}%)")
print()
print("Zone breakdown:")
for lz, short in ZONE_SHORT.items():
    n = (psse["SETTLEMENT_LOAD_ZONE"] == lz).sum()
    print(f"  {short:8s}: {n:,}")
unknown = (psse["Zone"] == "UNKNOWN").sum()
print(f"  UNKNOWN  : {unknown:,}")
print()
kv_dist = psse["BaseKV"].value_counts().sort_index()
print("BaseKV distribution (top 10):")
for kv, cnt in kv_dist.head(10).items():
    print(f"  {kv:>8.1f} kV: {cnt:,}")
print()
print(f"Output: {OUT_DIR / 'bus.csv'}")
