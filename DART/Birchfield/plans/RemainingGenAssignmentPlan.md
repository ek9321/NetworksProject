Spec — Cluster remaining generators into Type-g substations (CSV I/O)
Purpose

Cluster the pool of unassigned generators into N_g generator-only substations (Type g). Clusters are generator-only and subject to fuel-type homogeneity constraints. Output is written as CSV files consistent with the existing pipeline.

Inputs
1. Unassigned generators (CSV)

Input are the generators NOT already assigned in the previous step.

Required columns:

generator_id (string, unique)

lat (float, degrees)

lng (float, degrees)

nameplate_mw (float > 0)

fuel_type (string)

2. Configuration parameters

N_g (int): target number of Type-g substations. This is 5% of N. 

enforce_fuel_homogeneity (bool, default true)

fuel_types_exempt_from_mixing (list of strings, default
["NUCLEAR", "HYDRO", "WIND", "SOLAR", "OTHER_RENEWABLE"])

distance_metric: haversine (km) (fixed)

random_seed (int)

Outputs
1. Type-g substations (CSV)

Path: data/synthetic/substations/type_g_assigned.csv

Each row represents one Type-g substation:

substation_id (int, sequential starting at 1)

generator_ids (string; semicolon-delimited list of generator_id)

lat (float; capacity-weighted centroid)

lng (float)

total_capacity_mw (float)

num_generators (int)

fuel_type (string; single fuel type or "MIXED")

2. Summary file (CSV)

Path: data/synthetic/substations/type_g_assigned_summary.csv

Single-row CSV with columns:

requested_N_g

actual_N_g

total_generators_clustered

total_capacity_mw

num_merges

warnings (string; semicolon-delimited)

Algorithm
Step 0 — Validation & preprocessing

Load CSV.

Drop generators with:

missing lat/lng

nameplate_mw <= 0

If no generators remain → error.

If N_g <= 0 → error.

Let M = number of remaining generators.

If N_g >= M:

Each generator becomes its own Type-g substation.

Write outputs and exit.

Step 1 — Initialization

For each generator, create an initial cluster with:

members = [generator_id]

total_capacity = nameplate_mw

lat, lng = generator lat/lng

fuel_type = generator fuel_type

cluster_id = sequential integer (used internally only)

Step 2 — Distance definition

Distance between two clusters is:

Haversine distance (km) between their capacity-weighted centroids

Centroid update on merge:

new_lat = (cap_A * lat_A + cap_B * lat_B) / (cap_A + cap_B)

new_lng = same

new_total_capacity = cap_A + cap_B

Step 3 — Fuel-type merge constraints

If enforce_fuel_homogeneity is true, a merge between clusters A and B is allowed only if:

fuel_type_A == fuel_type_B, or

neither A nor B contains a fuel type listed in fuel_types_exempt_from_mixing

Otherwise, the merge is forbidden.

If homogeneity is disabled, all merges are allowed.

Step 4 — Agglomerative merging loop

While number_of_clusters > N_g:

Among all allowed cluster pairs, find the pair with minimum distance.

Tie-breaking (deterministic):

Smaller combined total_capacity first

Then smaller ordered (cluster_id_A, cluster_id_B)

Merge selected clusters into new cluster M:

members = members_A ∪ members_B

total_capacity = cap_A + cap_B

lat, lng = capacity-weighted centroid

fuel_type:

same fuel if identical

"MIXED" if different and mixing allowed

assign new monotonically increasing cluster_id

Remove A and B, insert M.

Recompute distances only for pairs involving M.

Step 5 — Infeasible merge handling

If at any iteration:

no allowed merges exist, and

number_of_clusters > N_g

Then:

Stop clustering

Set actual_N_g = number_of_clusters

Record warning:
"Fuel-type constraints prevented reaching requested N_g"

Proceed to output

Step 6 — Output construction

Sort final clusters by total_capacity_mw descending.

Assign substation_id = 1, 2, …

Write:

type_g_assigned.csv

type_g_assigned_summary.csv