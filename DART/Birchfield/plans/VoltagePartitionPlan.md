Step: Voltage partition & initial setup (separate from topology generator)
Purpose

Assign nominal voltage buses and internal transformers to each substation, choose which substations get higher-voltage buses, attach loads to low-voltage buses and attach generators to the highest-voltage bus at their substation. Produce CSV intermediates for the topology algorithm.

Config source

Read parameters from config/global.yaml. Required keys used:

voltage_levels (ordered list highest→lowest, e.g. [345, 115])

pct_substations_with_high_voltage (per-voltage fractions)

high_voltage_selection_weight (metric: max_load_or_generation)

random_seed

underground_line thresholds (kept for later)

target_mn_ratio (for topology step; read now for validation)

Inputs (paths)

data/synthetic/clustered_load_nodes.csv — clustered load nodes (cluster_id, lat, lng, population, mw_load, member_ids)

data/synthetic/type_b_assigned.csv — Type-b assignments (substation = source_cluster_id, assigned_generators, assigned_gen_mw, target_gen_mw)

data/synthetic/generators/unassigned_generators.csv (optional — for metadata if needed)

config/global.yaml

Outputs (CSV paths)

data/synthetic/substations_with_buses.csv — one row per substation (see schema below)

data/synthetic/buses.csv — one row per bus created

data/synthetic/transformers.csv — internal transformer records (connect bus ids, ratios)

data/synthetic/voltage_partition_summary.csv — single-row summary (counts, pct_high_volt_actual, warnings)

Data model / CSV schemas (concise)

substations_with_buses.csv:

substation_id (int) — sequential, derived from cluster_id mapping

cluster_id (int) — source cluster id

lat, lng (float)

mw_load (float)

assigned_generators (semicolon-delimited generator_id list or empty)

total_assigned_gen_mw (float)

has_high_voltage_bus_<V> (bool) for each voltage level V (e.g., has_high_voltage_bus_345)

buses.csv:

bus_id (int, sequential)

substation_id (int)

voltage_kv (int)

role (string: "load", "generator", "transmission")

connected_load_mw (float)

connected_generator_ids (semicolon-delimited)

transformers.csv:

transformer_id (int)

substation_id (int)

from_bus_id (int)

to_bus_id (int)

from_kv, to_kv

rating_mva (float, default heuristic)

voltage_partition_summary.csv:

total_substations, requested_pct_high_345, actual_pct_high_345, num_buses_created, num_transformers, warnings (semicolon-delimited)

Algorithm (step-by-step)

Load config from config/global.yaml. Initialize RNG with random_seed.

Load clustered substations CSV and Type-b assignment CSV. Join Type-b info to clusters by cluster_id.

Compute per-substation selection score:

score = max(mw_load, total_assigned_gen_mw) (per config)

If a substation lacks generators, total_assigned_gen_mw = 0.

Exclude substations with mw_load <= 0 from high-voltage candidates unless forced.

For each high voltage level V (iterate from highest to lowest excluding lowest which is present everywhere):

Let target_num = round(pct_substations_with_high_voltage[V] × total_substations)

Select target_num substations without replacement using weighted sampling proportional to score.

Use numpy.default_rng(random_seed).choice(..., replace=False, p=weights) (deterministic given seed).

Mark has_high_voltage_bus_V = True for selected substations.

For multi-level systems, ensure monotonicity: if a substation receives an even-higher voltage bus, it is eligible to also receive lower-level buses (i.e., keep all buses below present).

Create buses:

For every substation, create a bus row for every voltage level that that substation has (always lowest level; higher if selected).

Assign role:

load role on the lowest voltage bus (connected_load_mw = mw_load).

generator role on the highest voltage bus present (connected_generator_ids = assigned_generators from Type-b file).

transmission for intermediate buses if multi-level (no direct connections initially).

Assign sequential bus_ids.

Create internal transformers:

For each substation that has more than one bus, create transformers connecting adjacent voltage levels (highest↔next... until lowest).

Transformer rating_mva: heuristic equal to max( (connected generation total + connected load) × safety margin, min_threshold ).

Example default: rating_mva = max( (connected_generator_mw + connected_load_mw) × 1.2, 50 )

Assign sequential transformer_ids.

Attach loads and generators:

Loads attached to lowest-voltage bus; set connected_load_mw.

Generators assigned by earlier step attach to the highest-voltage bus present; set connected_generator_ids and ensure connected_generator_ids is empty if none.

Write CSV outputs (buses, transformers, substations_with_buses). Write summary CSV.

Validations (fail or warn)

actual_pct_high_345 must be within ±2% of requested; if not, log warning.

All generators assigned to Type-b must be attached to a bus at their substation (highest voltage). If any assigned generator’s substation lacks a high voltage bus, promote that substation (log and flag).

Each substation must have at least one bus (lowest-level). If not, error.

No duplicate bus_id or transformer_id.

Determinism: repeated runs with same inputs and random_seed produce identical outputs.

Logging & outputs

Detailed log of selections and any promotions to satisfy generator attachments.

Output voltage_partition_summary.csv with warnings and counts.

If promotions were required (to attach assigned generators), list substation_ids promoted in warnings.

Notes for topology step (what to consume)

Topology generator will read:

buses.csv to know which substations have buses at which voltages, where loads/gens connect.

transformers.csv for internal per-substation connections.

substations_with_buses.csv for substation coordinates and flags (used for Delaunay computation per voltage).

The topology generator should use voltage_levels ordering from config/global.yaml (consistent with bus assignments).