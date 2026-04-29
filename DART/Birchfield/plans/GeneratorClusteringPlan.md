Always follow the README.md and CLAUDE.md instructions. Default gen-load sampler

Default gen_load_ratio_sampler:
  def default_sampler(rng):
      # rng is a numpy Generator initialized with the pipeline random_seed
      u = rng.uniform(-1.0, 1.0)
      return math.exp(u)


Use this unless a different sampler is explicitly configured.

Deterministic weighted sampling for selecting N_b clusters

Use numpy RNG initialized with random_seed:
  probs = [c.mw_load for c in clusters if c.mw_load > 0]
  normalized = probs / sum(probs)
  selected_indices = rng.choice(indices_of_clusters_with_positive_load,
                                size=N_b, replace=False, p=normalized)


If there are fewer eligible clusters than N_b, raise an error.

Distance usage

Compute haversine distance in kilometers between substation centroid and each unassigned generator. Use that value for:
  - filtering candidates: distance <= max_assignment_radius_km (or no limit if None)
  - sorting candidates: primary key = distance ascending; tie-breaker: nameplate_mw descending; then generator_id ascending


Insufficient generation

If assigned_gen_mw < target_gen_mw after exhausting candidates:
  - set shortfall_mw = target_gen_mw - assigned_gen_mw
  - write a per-substation warning
  - include shortfall_mw in output entry


I/O conventions

Input clustered load nodes path: data/synthetic/clustered_load_nodes.json
Input generators path: data/external/eia860_generators.csv (or .json)
Output Type b file: data/synthetic/substations/type_b_assigned.json
Format: single JSON array of objects (as specified in original spec)


Validation rules

- Require nameplate_mw > 0, lat/lng present.
- Exclude clusters with mw_load <= 0 from selection pool unless N_b > eligible_clusters (then error).
- All distances in km, double precision.
- All operations deterministic with provided random_seed.


Logging & metrics

Produce a small summary JSON alongside output:
  data/synthetic/substations/type_b_assigned_summary.json
Contents:
  - total_requested_N_b
  - total_selected
  - total_assigned_generators
  - total_assigned_gen_mw
  - total_target_gen_mw
  - total_shortfall_mw
  - warnings: [per-substation messages]