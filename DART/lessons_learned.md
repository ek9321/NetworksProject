# Lessons Learned: Building an Open-Source ERCOT Grid Model with AI Agents

> 80+ experiments, 3 topology versions, 9 simulation days, and one long conversation about what went wrong.

---

## Grid Modeling

**1. Compensating errors are load-bearing walls — remove one at your peril.**
The model worked at 82 MW shed because two wrong things (inflated 138 kV ratings and unconstrained junction branches) canceled out. Fixing just one — constraining junctions to physical ratings — caused shedding to explode to 6,117 MW. This took 30 experiments to understand. Kirchner's "right answers for the right reasons" problem from hydrology [1] applies directly to power systems: a model that matches observations through offsetting biases will catastrophically fail when you fix only one bias.

**2. The topology is the model. Everything else is tuning knobs.**
Three topology versions each changed results more than any combination of rating adjustments, load allocation, or reserve requirements. V3's geometry-based line splitting reduced baseline shedding from 8,622 MW to 1,195 MW at identical ratings. Branch ratings are first-order, but the graph they ride on is zeroth-order.

**3. OSM gives you corridors, not meshes — but good extraction can fix that.**
Raw OSM extraction produced a 50% bridge ratio (half of all lines were the only path between their endpoints). V3's geometry-based line splitting brought it to 14.4%, actually exceeding real ERCOT's aggregate metrics (E/N 1.46 vs ~1.31; Aksoy 2018). The lesson isn't that OSM data is sparse — it's that naive parsing loses the connectivity that's already there. PyPSA-Eur reports similar raw E/N (~1.25) before their cleanup pipeline [2]. OSM coordinates are GPS-precise to meter level; when connections are lost, the pipeline is lossy, not the data.

**4. More granular data can make things worse.**
Census tract-level population (vs county) for load allocation caused shedding to jump from 0 to 16,161 MW. Tract data correctly concentrates load on urban cores — which sit behind the most congested corridors. The county-level uniform allocation accidentally matched the simplified topology's delivery capacity. Precision in one input without precision in all inputs is a regression.

**5. Synthetic grid generators solve the wrong problem for the wrong audience.**
Birchfield/TAMU synthetic grids [3] target E/N ratios of 1.5–1.66 and are tuned to converge in AC power flow — deliberately over-meshed relative to reality (real ERCOT ~1.31). They're research test cases, not representations of real infrastructure. OSM-extracted grids start too sparse; TAMU grids start too dense. Neither gives you the actual network, because CEII rules [4] make the actual network illegal to share. The entire field of synthetic grid generation exists as a workaround for FERC 18 CFR 388.113.

**6. The binding constraint you protect is more informative than the shedding you eliminate.**
WESTEX (Morgan Creek→Tonkawa) binding on high-wind days was the single most important calibration signal — more important than total shedding. Multiple configurations achieved low shedding by *removing* realistic congestion rather than resolving it. When your "improvement" makes a known real-world constraint disappear, you've made the model worse.

**7. Validation must span regimes, not just load levels.**
The winning config (0 MW shed on 3 tuning days) passed cleanly on 4 of 6 unseen validation days spanning high wind (CF 0.65), low wind (CF 0.004), spring, fall, and summer. The two partial failures — evening ramp scarcity at record-low wind, Houston corridor saturation at 77 GW record peak — revealed real physics, not bugs. Low-wind days correctly showed flat LMPs at ~$28 (marginal gas). A model validated only on "typical" days will fool you about its failure modes.

**8. The last 10% of shedding has a completely different root cause than the first 90%.**
Going from 27,000 MW to 82 MW was cold-start fixes and rating adjustments. Going from 82 MW to 0 required rebuilding the entire topology pipeline. Going from "0 on tuning days" to "0 on validation days" required iterative binding-line identification, floor ratings, and reserve requirements. No single lever was sufficient. Each order-of-magnitude improvement demanded a different class of intervention.

**9. The 80-experiment calibration log is the actual deliverable, not the final config.**
The winning configuration (135 targeted upgrades + f1200 floor + 15% reserves) is fragile knowledge — it works but doesn't explain why. The experiment log documenting what was tried, what failed, and what each failure revealed about the system is the durable contribution. Anyone can run the final config; understanding which knobs matter and which are compensating errors requires the full trail.

---

## Working with AI Agents

**10. The agent will enthusiastically optimize the wrong thing until you force it to look at the right thing.**
18 experiments tuning branch ratings before someone opened the HTML map and saw lines weren't connecting at substations. The agent had been calibrating ratings on a broken graph — every fix was a compensating error on top of a topology bug. Error propagation across steps looks plausible at each stage, and the agent won't spontaneously question the layer beneath the one it's working on [5].

**11. Visualization is the human's superpower. Build diagnostic tools early.**
Every major breakthrough — the bridge ratio discovery, Houston corridor saturation, the tract-allocation regression — followed from visual inspection, not from metrics alone. The agent can crunch numbers all day, but it cannot see that lines are spatially disconnected from substations. The topology pivot happened because someone opened a Leaflet map and *looked*.

**12. Your CLAUDE.md should shrink over time, not grow.**
The project's CLAUDE.md started as a detailed 9-step autonomous loop (~150 lines) and was simplified to "read first, act second — these are messy but solvable problems" (~60 lines). Claude Code's creator runs with ~100 lines [6]. The consensus from practitioners [7]: if it's too long, the agent ignores half. If the agent already does something right, delete the instruction.

**13. Agents are exceptional experiment runners but mediocre experiment designers.**
The agent submitted 103 SLURM tasks, pulled results via SCP, built comparison tables, and iterated on binding lines across 80+ experiments — tireless and systematic. But the *hypotheses* that mattered (the topology is broken; floor ratings compensate for missing parallel paths; the reserve factor is a unit-commitment problem, not congestion) came from human domain intuition or from the agent being explicitly told to investigate a specific mechanism.

**14. "Compensating error" is the default state of agent-built systems. Name it, or it will eat you.**
The V1 model's 82 MW shed looked like success. It was a broken topology masked by infinite-capacity branches. The agent never flagged it — it just reported the 82 MW number and moved on. Agents will not notice compensating errors because each individual metric looks acceptable. You have to ask: "why is this working?"

**15. Domain-specific feedback memories outweigh pages of upfront instructions.**
Two 15-line feedback memories — "OSM data is precise, don't use fuzzy clustering" and "use principled ratio-based heuristics, not arbitrary thresholds" — reshaped entire pipeline versions. They corrected deep assumptions, not surface behaviors. Anthropic calls this pattern "compounding engineering" [8]: every time the agent makes a class of error, add a correction so it never recurs.

**16. The agent's greatest contribution: making iteration cheap, not smart.**
80+ experiments in days instead of weeks. The intelligence was in experiment design (human) and root-cause analysis (joint). The throughput was entirely the agent's. This matches what experienced developers report about AI coding agents: they control the direction, the agent provides velocity [9].

**17. The human's job shifted from writing code to writing constraints.**
Across the project, almost no pipeline code was written by the human directly. Instead: CLAUDE.md instructions, feedback memories, experiment design documents, calibration metrics with priority ordering ("zone LMP ordering first, shedding second"), and physics constraints ("345 kV all at 2400 except WESTEX"). The agent wrote the code. The skill was knowing which constraints to impose and which to leave open — a form of specification that is harder than it looks.

---

## Sources

[1] Kirchner, J. W. (2006). "Getting the right answers for the right reasons: Linking measurements, analyses, and models to advance the science of hydrology." *Water Resources Research*, 42(3). https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2005WR004362

[2] Xiong, B. et al. (2025). "Modelling the high-voltage grid using open data for Europe and beyond." *Scientific Data*, Nature. https://www.nature.com/articles/s41597-025-04550-7

[3] Birchfield, A. B. et al. (2017). "Grid Structural Characteristics as Validation Criteria for Synthetic Networks." *IEEE Transactions on Power Systems*. Texas A&M Birchfield Research Group: https://birchfield.engr.tamu.edu/

[4] FERC. "Critical Energy/Electric Infrastructure Information (CEII)." 18 CFR 388.113. https://www.ferc.gov/ceii

[5] Galileo AI. "How to Debug AI Agents." https://galileo.ai/blog/debug-ai-agents

[6] MindWired AI. "Claude Code Creator's Workflow: The 100-Line CLAUDE.md." https://mindwiredai.com/2026/03/25/claude-code-creator-workflow-claudemd/

[7] HumanLayer. "Writing a Good CLAUDE.md." https://www.humanlayer.dev/blog/writing-a-good-claude-md

[8] Anthropic. "Best Practices for Claude Code." https://code.claude.com/docs/en/best-practices

[9] Patten, D. (2026). "The State of AI Coding Agents 2026: From Pair Programming to Autonomous AI Teams." https://medium.com/@dave-patten/the-state-of-ai-coding-agents-2026-from-pair-programming-to-autonomous-ai-teams-b11f2b39232a

Additional references:
- ERCOT 2024 Constraints Report: https://www.ercot.com/files/docs/2024/12/20/2024-report-on-existing-and-potential-electric-system-constraints-and-needs.pdf
- OSM Power Networks Quality Assurance: https://wiki.openstreetmap.org/wiki/Power_networks/Quality_Assurance
- arXiv 2511.14478: "Agentic AI in Power Systems Engineering": https://arxiv.org/html/2511.14478v2
