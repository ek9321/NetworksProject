# Clustered load nodes process (census / postal-code data)

## Purpose
Aggregate geographic census (postal code) data into a fixed number of load substations using population-weighted geographic clustering.

## Inputs
* A set of postal codes
* For each postal code:
   * Latitude (degrees)
   * Longitude (degrees)
   * Population (integer)
* Target number of load substations: N_target = Nl + Nb

## Definitions

Each cluster maintains:
* A set of member postal codes
* Total population = sum of populations of all members
* Cluster location = population-weighted average latitude and longitude of its members

### Distance between two clusters

The distance between two clusters c1 and c2 is defined as follows:

For every postal code m1 in cluster c1 and every postal code m2 in cluster c2:
1. Compute the Haversine distance (in kilometers) between m1 and m2
2. Multiply this distance by (population of m1 + population of m2)

The cluster-to-cluster distance is the sum of all such weighted distances divided by the sum of all weights (population of m1 + population of m2 over all pairs).

All distances are computed using double-precision floating point.

## Explicit assumptions enforced

1. **Maximum population per cluster**
   * Let total_population be the sum of all postal-code populations
   * Define max_cluster_population = 3 × (total_population / N_target)
   * A merge is disallowed if the combined population of two clusters exceeds this value
   * If no valid merge exists, increase max_cluster_population by 10% and continue

2. **Exact distance recomputation**
   * After each merge, distances are recomputed exactly between the new cluster and all remaining clusters
   * Distances between unaffected cluster pairs are cached and reused

3. **Distance metric**
   * Geographic distances use the Haversine formula on a spherical Earth
   * Units: kilometers

4. **Deterministic tie-breaking**
   * If multiple cluster pairs have equal minimum distance:
      1. Prefer the pair with smaller combined population
      2. If still tied, prefer the pair with the lowest lexicographic cluster ID ordering

## Clustering algorithm

1. **Initialization**
   * Initialize one cluster per postal code
   * Compute total_population
   * Set current number of clusters k = number of postal codes

2. **Iterative merging**
   * While k > N_target:
      * Identify all valid cluster pairs whose merged population does not exceed max_cluster_population
      * Among those pairs, select the pair with the minimum cluster-to-cluster distance
      * Break ties deterministically as specified above
      * Merge the selected pair into a new cluster
      * Update:
         * Total population
         * Population-weighted geographic location
      * Remove the two original clusters and insert the merged cluster
      * Update distances involving the new cluster
      * Decrement k by 1

3. **Termination**
   * Stop when exactly N_target clusters remain


Clarifying Questions — Final Answers
1. N_target parameter

The clustering method should take N_target as a single integer input parameter.

The values Nl and Nb are configuration-level concepts and should be resolved upstream (e.g., from the New York and Texas YAML config files). The clustering algorithm itself should not know about Nl or Nb; it only receives the final target number of clusters.

This allows the same clustering method to be reused across multiple regions and pipeline runs.

2. Output format

The clustering algorithm should not write directly to disk and should not return Bus objects.

Instead, it should return an intermediate in-memory cluster representation containing only the information produced by clustering (location, population, member postal codes).

A separate pipeline method is responsible for:

Calling the clustering algorithm

Converting clusters into Bus objects

Assigning global identifiers and names

Writing results to data/synthetic/...

This keeps the clustering logic reusable, testable, and independent of filesystem and graph-level concerns.

3. Bus fields to populate

The clustering algorithm itself does not populate Bus fields.

The pipeline method that converts clusters into Bus objects should populate:

bus_id

sub_num

sub_name

lat

lng

mw_load

The mw_load value is computed in the pipeline step as:

mw_load = population × MW_PER_CAPITA, where MW_PER_CAPITA = 2.0

This keeps unit scaling and graph semantics out of the clustering logic.

4. Cluster naming / numbering

Clusters should be assigned sequential numeric IDs at initialization (one per postal code).

When two clusters are merged, the new cluster receives a new, monotonically increasing ID. Cluster IDs are never reused.

Cluster IDs are internal identifiers used only during clustering and are not exposed as bus IDs.

5. Cluster ID for tie-breaking

Tie-breaking during clustering should use deterministic lexicographic ordering of cluster IDs.

When multiple cluster pairs have equal minimum distance:

Prefer the pair with smaller combined population

If still tied, prefer the pair with the smaller ordered tuple of cluster IDs

Using sequential cluster IDs ensures deterministic and reproducible clustering behavior.


## More on the algo:

What makes this totally fine on a Mac
1. Precompute base distances once

Compute postal-to-postal Haversine distances once

Store in a dense numpy array or memory-mapped file

Index by integer IDs

This is the only truly O(N²) step.

Example scale:

10k nodes → 100M distances

float64 → ~800 MB (too big)

float32 → ~400 MB (barely OK)

But you can:

Restrict to k-nearest neighbors

Or chunk by region (recommended)

2. Cache cluster statistics aggressively

For each cluster, store:

member indices

total population

a vector of population weights

When merging A and B:

You never recompute distances among old clusters

You only compute distances between (A∪B) and C for all remaining C

3. Use the weighted-average update formula (this matters)

Distance between merged cluster M = A ∪ B and some other cluster C:

Plain text formula:

distance(M, C) =
(pop_A × distance(A, C) + pop_B × distance(B, C))
divided by
(pop_A + pop_B)

This is mathematically exact for the all-pairs metric.

Meaning:

You do O(1) work per cluster pair after merge

No nested loops over members

This is the trick that makes the algorithm scale.

If you are not using this formula, stop — you’re leaving performance on the table.

4. Use a priority queue, not a full scan

Maintain:

a min-heap of (distance, cluster_i, cluster_j)

After a merge:

Invalidate heap entries involving A or B

Insert new distances for M vs remaining clusters

This avoids repeated O(N) scans.

Rough runtime estimates (MacBook-class machine)

Assuming:

~8k initial nodes

~1–2k final clusters

cached distances + weighted updates

Python + numpy

You’re looking at:

Minutes, not hours

Memory usage: a few GB peak if careless, <1 GB if careful

This is well within reach of a modern Mac.