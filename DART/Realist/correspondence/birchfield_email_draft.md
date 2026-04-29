# Draft Email — Adam Birchfield

**To:** adam.birchfield@[university]
**CC:** [Professor Name] <[prof@princeton.edu]>
**Subject:** Open-source DC-SCED model of ERCOT from public data — research direction advice

---

Dear Prof. Birchfield,

I am a junior at Princeton studying Operations Research, doing independent research with
Prof. [Name] — I believe the two of you have met. I am writing because our work builds
directly on Texas-2k/7k and you are the right person to ask about where it should go.

**What we built.** We assembled a DC-SCED-ready model of the ERCOT network from entirely
public, non-CEII sources: OSM transmission line geometry, ERCOT's public electrical bus
catalog and generator registration data (MORA April 2026), EIA-860 coordinates, and
ERCOT's 60-day SCED disclosure for cost curves. The model has 4,303 buses (real OSM
substation locations plus synthetic T-junction nodes) and 4,656 branches across the
138–500 kV voltage tiers, with all generators anchored to registered ERCOT resource nodes
via a four-stage bus assignment chain. It runs end-to-end through Vatic. We have completed
a 24-hour v.1 simulation.

The novel claim is that every bus is physically located — not placed at a county centroid.
To our knowledge, this is the first public DC-SCED model of ERCOT built without CEII.

**The open problem.** Our biggest unresolved uncertainty is line capacity. We use flat
tier defaults (300 / 600 / 1,200 / 2,000 MVA by voltage class). The v.1 run shows the
expected West Texas curtailment concurrent with East Texas load shedding — the chronic
West-NORTH spread — but the magnitude is likely exaggerated by conservative 138 kV ratings
and gaps in OSM's sub-transmission coverage. We can iterate, but we cannot close this
uncertainty without CEII.

I have three questions I would value your perspective on:

1. **Calibration without CEII.** Do you know of systematic methods for inferring MVA
   ratings from public data — conductor geometry visible in OSM tags, historical loading
   statistics, FERC Form 715 public portions, or similar? Or is this fundamentally an
   irreducible uncertainty in any public model, better treated as a sensitivity parameter
   than a calibration target?

2. **OSM 138 kV coverage.** OSM appears to undercount Texas sub-transmission relative
   to ERCOT's actual network. Are there supplementary public sources you would recommend
   (HIFLD, state utility filings, NERC reliability reports) that could improve coverage
   without touching non-public material?

3. **Research direction.** Given an open-source, geographically grounded ERCOT SCED
   model that any researcher can run and extend — what experiment do you think is most
   likely to produce an influential contribution? We are weighing transmission expansion
   analysis, renewable siting sensitivity, storage placement, and direct LMP validation
   against the SCED disclosure. Prof. [Name]'s interest is in realistic ISO models for
   market experiments; I am also interested in this as a pipeline methodology paper —
   documenting how to construct a public-data DC-SCED model for any U.S. ISO.

I would be glad to share the repository and the interactive grid visualizer (a full OSM
topology map of Texas with ERCOT substation matching, EIA-860 generators, and live LMP
overlay), or to set up a brief call if that would be more useful.

Thank you for your time.

Emmett Souder
Princeton University, Class of 2027
Operations Research and Financial Engineering

---

*Cc: Prof. [Name] — who suggested I reach out given your prior conversations.*
