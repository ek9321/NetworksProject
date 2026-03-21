#!/usr/bin/env python3
"""
build_network.py — Build a simplified ERCOT transmission network from SCED data.

Reads bus.csv, branch.csv, gen.csv from the parent SCED pipeline and produces:
  - nodes.csv: substations with zone, voltage, location, aggregated generation & load
  - edges.csv: transmission lines with voltage, length_km, capacity_mva, reactance
  - ercot_network.graphml: NetworkX graph for analysis

No storage, no dispatch, no market clearing — just the physical network.
"""

import csv
import math
import os
import sys

try:
    import networkx as nx
except ImportError:
    print("pip install networkx")
    sys.exit(1)

# ── paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCED_DIR = os.path.join(SCRIPT_DIR, "..", "grid_data", "sced_inputs", "SourceData")
OUT_DIR = SCRIPT_DIR  # outputs go next to this script


# ── helpers ──────────────────────────────────────────────────────────────────
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def voltage_to_capacity_mva(kv):
    """Default capacity rating by voltage class (conservative estimates)."""
    if kv >= 345:
        return 1200  # single-circuit 345 kV
    elif kv >= 230:
        return 600
    else:
        return 400  # 138 kV


# ── 1. read buses ────────────────────────────────────────────────────────────
print("Reading buses...")
buses = {}
with open(os.path.join(SCED_DIR, "bus.csv")) as f:
    for row in csv.DictReader(f):
        bid = int(row["Bus ID"])
        buses[bid] = {
            "id": bid,
            "name": row["Bus Name"],
            "zone": row["Zone"],
            "base_kv": float(row["BaseKV"]),
            "lat": float(row["lat"]),
            "lng": float(row["lng"]),
            "mw_load": float(row["MW Load"]),
            "is_split": row["is_split"] == "True",
            # will be filled from gen.csv
            "gen_mw": 0.0,
            "gen_fuels": set(),
        }
print(f"  {len(buses)} buses loaded")


# ── 2. aggregate generators onto buses ───────────────────────────────────────
print("Reading generators...")
gen_count = 0
with open(os.path.join(SCED_DIR, "gen.csv")) as f:
    for row in csv.DictReader(f):
        bid = int(row["Bus ID"])
        if bid in buses:
            buses[bid]["gen_mw"] += float(row["PMax MW"])
            buses[bid]["gen_fuels"].add(row["Fuel"])
            gen_count += 1
print(f"  {gen_count} generators aggregated")


# ── 3. read branches and compute edge attributes ────────────────────────────
print("Reading branches...")
edges = []
with open(os.path.join(SCED_DIR, "branch.csv")) as f:
    for row in csv.DictReader(f):
        a = int(row["From Bus"])
        b = int(row["To Bus"])
        if a not in buses or b not in buses:
            continue

        # voltage = max of endpoint base voltages
        kv = max(buses[a]["base_kv"], buses[b]["base_kv"])

        # line length from coordinates
        length_km = haversine_km(
            buses[a]["lat"], buses[a]["lng"],
            buses[b]["lat"], buses[b]["lng"],
        )

        # capacity: use actual rating unless it's the 999999 sentinel
        raw_rating = float(row["Cont Rating"])
        if raw_rating >= 999000:
            capacity_mva = voltage_to_capacity_mva(kv)
        else:
            capacity_mva = raw_rating

        reactance = float(row["X"])

        edges.append({
            "uid": row["UID"],
            "from_bus": a,
            "to_bus": b,
            "voltage_kv": kv,
            "length_km": round(length_km, 2),
            "capacity_mva": capacity_mva,
            "reactance": reactance,
        })
print(f"  {len(edges)} edges loaded")


# ── 4. write nodes.csv ──────────────────────────────────────────────────────
print("Writing nodes.csv...")
nodes_path = os.path.join(OUT_DIR, "nodes.csv")
with open(nodes_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "name", "zone", "base_kv", "lat", "lng",
                "mw_load", "gen_mw", "gen_fuels"])
    for bid in sorted(buses):
        b = buses[bid]
        fuels = ";".join(sorted(b["gen_fuels"])) if b["gen_fuels"] else ""
        w.writerow([b["id"], b["name"], b["zone"], b["base_kv"],
                    b["lat"], b["lng"], b["mw_load"], round(b["gen_mw"], 1),
                    fuels])
print(f"  {len(buses)} nodes written")


# ── 5. write edges.csv ──────────────────────────────────────────────────────
print("Writing edges.csv...")
edges_path = os.path.join(OUT_DIR, "edges.csv")
with open(edges_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["uid", "from_bus", "to_bus", "voltage_kv", "length_km",
                "capacity_mva", "reactance"])
    for e in edges:
        w.writerow([e["uid"], e["from_bus"], e["to_bus"], e["voltage_kv"],
                    e["length_km"], e["capacity_mva"], e["reactance"]])
print(f"  {len(edges)} edges written")


# ── 6. build and save NetworkX graph ────────────────────────────────────────
print("Building NetworkX graph...")
G = nx.Graph()

for bid, b in buses.items():
    G.add_node(bid,
               name=b["name"],
               zone=b["zone"],
               base_kv=b["base_kv"],
               lat=b["lat"],
               lng=b["lng"],
               mw_load=b["mw_load"],
               gen_mw=b["gen_mw"],
               gen_fuels=";".join(sorted(b["gen_fuels"])))

for e in edges:
    # if parallel edges exist between same pair, keep the one with higher capacity
    a, b = e["from_bus"], e["to_bus"]
    key = (min(a, b), max(a, b))
    if G.has_edge(*key):
        existing = G.edges[key]
        # aggregate parallel lines: sum capacity, use min reactance
        existing["capacity_mva"] += e["capacity_mva"]
        existing["n_circuits"] = existing.get("n_circuits", 1) + 1
    else:
        G.add_edge(a, b,
                   voltage_kv=e["voltage_kv"],
                   length_km=e["length_km"],
                   capacity_mva=e["capacity_mva"],
                   reactance=e["reactance"],
                   n_circuits=1)

# remove isolated nodes (no edges)
isolates = list(nx.isolates(G))
G.remove_nodes_from(isolates)

print(f"  {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
print(f"  {len(isolates)} isolated nodes removed")
print(f"  Connected components: {nx.number_connected_components(G)}")

graphml_path = os.path.join(OUT_DIR, "ercot_network.graphml")
nx.write_graphml(G, graphml_path)
print(f"  Saved to {graphml_path}")


# ── 7. quick summary stats ──────────────────────────────────────────────────
print("\n── Network Summary ─────────────────────────────────────")
print(f"Nodes:  {G.number_of_nodes()}")
print(f"Edges:  {G.number_of_edges()}")

degrees = [d for _, d in G.degree()]
print(f"Degree: min={min(degrees)}, max={max(degrees)}, "
      f"mean={sum(degrees)/len(degrees):.1f}")

# zone breakdown
from collections import Counter
zone_counts = Counter(nx.get_node_attributes(G, "zone").values())
print(f"Zones:  {dict(zone_counts)}")

# voltage breakdown
kv_counts = Counter()
for _, _, d in G.edges(data=True):
    kv_counts[d["voltage_kv"]] += 1
print(f"Edges by voltage: {dict(sorted(kv_counts.items()))}")

# generation by zone
zone_gen = Counter()
for n, d in G.nodes(data=True):
    zone_gen[d["zone"]] += d["gen_mw"]
print(f"Gen MW by zone: { {z: round(mw) for z, mw in sorted(zone_gen.items())} }")

# largest connected component
gcc = max(nx.connected_components(G), key=len)
print(f"Giant component: {len(gcc)} nodes ({100*len(gcc)/G.number_of_nodes():.1f}%)")

print("\nDone.")
