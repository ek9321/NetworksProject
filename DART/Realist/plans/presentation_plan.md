# Presentation Plan — Professor Meeting (April 3, 2026)

*10 days out. Audience: professor, grad students, a couple visiting students. Chill but informed.*

---

## Two Goals for the Next 10 Days

### Goal 1: Carry the work forward (days 1–7)
### Goal 2: Build the presentation (days 7–10)

---

## Work to Do Before the Talk

### Must-do (high leverage, directly improves the story)

1. **Fix SPL segment ratings.** Right now 70% of the 138 kV network is set to 999,999 MVA because those segments touch T-junction split points. The real fix: give SPL segments their parent line's voltage-tier rating (250 MVA for 138 kV), not infinity. This is the single biggest known modeling error. If it works with ~250 MVA and proper SPL ratings, the 138 kV story becomes "we have realistic ratings on a realistic topology" instead of "we have compensating errors that happen to cancel."

2. **Run a third calibration day.** Two days (Nov 5, Jun 17) is thin. Pick a high-wind winter day (Jan or Feb 2024) where WEST-NORTH spread is large. Three days across two seasons makes "the model generalizes" much more defensible.

3. **Make one clean comparison figure.** Calibration trajectory: v1 (27,242 MW) → v2 (2,976) → clean-build (82) → all345+storage (22). X-axis = experiment, Y-axis = log-scale shed. This is the hero chart. One slide, tells the whole story.

### Nice-to-have (if time permits)

4. **Zone LMP comparison chart.** Side-by-side: actual ERCOT RTM SPP zone prices vs model prices for Jun 17. Even if magnitudes are off, the ordering (WEST < NORTH) being correct is visually compelling.

5. **Map of binding lines.** The grid_visualizer.html already shows the network. Overlay the binding lines from jun17-all345 in red. Morgan Creek→Tonkawa highlighted. This is the "money shot" for anyone who knows ERCOT.

6. **Storage dispatch plot.** Hours 0-1 showing storage absorbing the startup transient on Nov 5. Quick win, shows the pipeline handles BESS.

---

## Presentation Structure (15–20 min, flexible)

### Slide 1: What is this?
DC-SCED of real ERCOT from entirely public data. Every bus is a real OSM substation. Every generator is a registered ERCOT resource. No synthetic anything.

### Slide 2: Why does it matter?
- ERCOT's actual SCED is proprietary
- Existing open models (Texas-2k, ACTIVSg) use synthetic topologies
- If you can reproduce congestion patterns from public data, you can study market structure without a market participant account

### Slide 3: The pipeline
OSM + MORA + EIA-860 → build scripts → Vatic DC-SCED (Gurobi on Adroit). One diagram.

### Slide 4: The calibration trajectory (hero chart)
27,242 → 2,976 → 82 → 22 MW shed. Each drop annotated with what fixed it (warm start, OSM network, 138 kV ratings, 345 kV blanket, storage).

### Slide 5: The scientific result
WEST < NORTH all 24 hours on Jun 17. Morgan Creek→Tonkawa binding. This is the real ERCOT WESTEX export constraint, reproduced from OSM data. Map with binding line highlighted.

### Slide 6: What's honestly wrong
- 138 kV ratings are a compensating error (2.4x overrated, but topology is 2x sparse)
- Jun 17 still sheds 317–1,004 MW (actual: 0)
- LMP magnitudes off by 5–80x on congested hours
- Offer curves from wrong date
- Only validated on 2 days

### Slide 7: Where it's going
- SPL segment fix → realistic 138 kV ratings without compensating errors
- More calibration days → seasonal robustness
- Offer curve procurement (ERCOT MIS archive)
- Achievable target: zone ordering correct, magnitudes within 3x, shed < 50 MW

---

## Hardball Questions to Prepare For

### "How do you know the congestion patterns aren't just artifacts of bad ratings?"
**Answer:** We tested this systematically. floor/2x experiments showed all shed is from branch ratings. We isolated SPL artifacts (65% of shed), then 138 kV (94% of remainder). The WESTEX result is robust across every rating configuration we tested — it's topology-driven, not rating-driven. Morgan Creek→Tonkawa binds whether 138 kV is at 300, 600, or 250 MVA.

### "The 138 kV compensating error — doesn't that invalidate intra-zone results?"
**Answer:** We traced this precisely (session_2026-03-24). The issue isn't "missing OSM lines" — OSM has 2,641 138 kV features in Houston. The issues are: (1) the 138 kV network is almost purely radial (mesh ratio 1.06, vs ~1.3+ in real urban grids), (2) Houston fragments into 42 disconnected 138 kV islands connected only through unconstrained proxy-transformer branches, and (3) we have no explicit 345→138 kV transformer ratings. The 600 MVA + SPL-unconstrain is standing in for transformer capacity. Inter-zone results (345 kV driven) are robust. Intra-zone requires transformer modeling — that's the clearest next improvement for the summer intern.

### "Why OSM instead of FERC Form 715 or other utility data?"
**Answer:** FERC 715 is CEII (Critical Energy Infrastructure Information) — restricted access, can't publish. OSM is fully open, georeferenced, and surprisingly complete for HV transmission. The 345 kV network matches Texas-2k within 1% on ratings. 138 kV is sparser but that's a tractable problem (fill in missing lines, or use compensating ratings as we've been doing).

### "What's the scientific contribution? You're just running someone else's solver on public data."
**Answer:** The contribution is proving that the OSM transmission skeleton captures enough real topology to reproduce qualitatively correct congestion patterns. This wasn't obvious — plenty of grid models with better data fail to get zone ordering right. The pipeline itself (OSM→MORA→Vatic) is the artifact. Anyone can reproduce it.

### "You've validated on two days. How do you know this generalizes?"
**Answer:** We don't, fully. That's why a third calibration day (different season) is the next priority. But the WESTEX result is structurally encouraging — it's not tuned to one day, it falls out of the topology. The 345 kV blanket upgrade was validated to not break WESTEX across both Nov 5 and Jun 17.

### "What was a waste of time?"
**Answer (be honest):**
- The PSSE-bus approach (v1) was a dead end. Two attempts at mapping ERCOT buses to PSSE node IDs failed before we pivoted to OSM-native. ~2 weeks lost.
- v3–v5 regressions were never properly logged. We know the network rebuilds made things worse but don't know exactly why. Poor experiment hygiene.
- The LOAD_NAMED_ONLY experiment was a bad hypothesis — removing load from unnamed nodes made things worse because those nodes are real substations.
- The "renewable capacity gap" panic was based on stale README numbers. The actual gen.csv had 98%+ coverage the whole time. Hours spent investigating a non-problem.
- Individual 345 kV overrides (targeted-hv) didn't work because congestion shifts to parallel paths. Should have gone straight to blanket upgrade.

### "What would you do differently?"
- Log every experiment change meticulously from day one (we started doing this in session_2026-03-19, should have from v1)
- Start with the floor/2x diagnostic experiments earlier — would have identified branch ratings as the sole issue in week 1 instead of month 2
- Compare against Texas-2k ratings earlier for sanity-checking
- Keep a single source of truth for fleet capacity numbers (the stale README was misleading for weeks)

---

## Things NOT to Oversell

- Don't claim LMP accuracy. The model gets ordering right, not magnitudes.
- Don't claim the 138 kV network is realistic. It's a compensating approximation.
- Don't claim storage "works" broadly — it ran once on Nov 5 with zone aggregation. Hourly-varying storage on Jun 17 hasn't been tested.
- Don't imply this could replace ERCOT's actual SCED. It can't, and that's fine — the value is in the open-source, public-data constraint.

---

## Logistics

- PowerPoint via Claude — formatting is fast, focus on content
- Keep it to ~15 slides max. Dense slides are fine for this audience.
- Have grid_visualizer.html open in a browser tab for live demo if anyone asks about topology
- Have the experiment table (experiments.md) printable as a handout or backup slide
