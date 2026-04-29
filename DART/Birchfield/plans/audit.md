#  Prompt for Coding Agent

You are auditing our implementation of the Birchfield synthetic grid transmission topology algorithm (IEEE T-PWRS 2017).

We observe that our generated 345 kV topology lacks the long, directional bulk-transfer corridors (e.g., east–west sweeps) seen in the Texas-2000 case described in the paper.

Your task is to **diagnose whether our implementation of the line placement penalty system and DC flow integration is structurally equivalent to the methodology described in the paper**, and whether scaling differences explain the qualitative topology differences.

---

## PART 1 — Verify Structural Fidelity to Paper

Carefully compare our implementation against the following required elements from Birchfield:

### A. Candidate Edge Set

Confirm that:

* Candidate lines are restricted to:

  * Delaunay triangulation edges
  * Delaunay 2-neighbors
  * Delaunay 3-neighbors
* No other edges are considered
* Delaunay categories are correctly labeled

Report:

* Total candidate count
* Count per Delaunay category

---

### B. Penalty Structure

For each candidate edge, verify we compute penalties for:

1. Distance penalty: +2 per mile
2. DC flow reward: −0.5 × Pest
3. Delaunay category quota penalty (+200 if ahead of quota)
4. Voltage-level connectivity reward (−300)
5. Overall connectivity reward (−1000)
6. Line intersection penalty (+500)

For each component, report:

* Exact formula used
* Scaling constants
* Units
* Whether values are normalized

Then compute:

* Typical magnitude of each term during early iterations
* Typical magnitude mid-process
* Typical magnitude near completion

Output a table like:

| Term | Mean | Std | Max | Min |

We want to see if DC reward is numerically dominating or negligible.

---

## PART 2 — DC Power Flow Implementation Audit

Confirm whether we correctly implement:

1. Standard DC PF:
   θ = −B⁻¹ P_inj

2. Temporary MST impedances:

   * Are they added when network is disconnected?
   * How are their impedances scaled?
   * Are they gradually increased?
   * When are they removed?

3. Pest calculation:
   Pest = xl · d21 · (θ2 − θ1)

Check:

* Is xl computed from per-mile reactance?
* Is d21 distance?
* Are we multiplying or dividing correctly?
* Are angle units radians?

Report:

* Distribution of θ differences
* Distribution of Pest
* Max absolute Pest across all candidate edges

We want to know if angle gradients are strong enough to drive corridor formation.

---

## PART 3 — Sensitivity Experiment

Run controlled experiments:

### Experiment 1

Set DC reward weight = 0
Generate 345 kV network.
Measure:

* Mean line length
* Longest line
* Anisotropy metric (see below)

### Experiment 2

Multiply DC reward weight by 5
Repeat metrics.

### Experiment 3

Multiply DC reward weight by 10
Repeat metrics.

Define anisotropy metric:

* Compute principal direction of edge vectors
* Measure variance ratio between major and minor axis

If corridors form, anisotropy should increase significantly.

---

## PART 4 — Voltage-Level Node Selection Audit

Check how 345 kV substations are selected.

Confirm:

* % of substations with 345 kV buses
* Whether probability is proportional to load
* Whether generation-heavy nodes are preferentially selected

Compare spatial distribution of 345 kV nodes to:

* Load distribution
* Generation distribution

Plot spatial density map.

If 345 kV nodes are spatially uniform, corridor formation will be weaker.

---

## PART 5 — Iterative Selection Mechanics

Confirm:

* How many lines are added per iteration?
* Are candidates rescored after each addition?
* Are quotas dynamically enforced?
* Are penalties cumulative or recalculated fresh?

Small differences here can strongly alter macro-structure.

---

## PART 6 — Quantitative Corridor Diagnosis

For the final 345 kV network compute:

* Mean line length
* 90th percentile line length
* Longest line
* Edge orientation histogram
* Principal component anisotropy ratio

Compare against Texas-7k benchmark.

Report whether differences are:

* DC-driven
* Geometric
* Voltage assignment driven
* Or quota-driven

---

## Deliverable

Produce:

1. A numerical diagnostic report
2. A short explanation of which mechanism is suppressing long corridors
3. A ranked list of likely causes

Do NOT speculate qualitatively.
Back conclusions with numerical evidence.

---

