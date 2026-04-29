# Strategy: Email to Prof. Birchfield

## Context

You are a Princeton ORFE junior doing independent research. Your professor (a markets researcher)
wants a realistic, runnable model of ERCOT and NYISO. You are building that. You are emailing
Adam Birchfield — the author of the Texas-2k and Texas-7k synthetic grid cases — to get his
expert input on where this project could go as a publishable research contribution.

Your professor has met Birchfield before. CC him. The email should feel like an informed
peer reaching out, not a student asking for help.

---

## What Makes This Project Novel (say this clearly)

The Texas-2k/7k benchmarks are the standard academic ERCOT reference cases. Both are
**synthetic** — buses placed at county population centroids, generators assigned
probabilistically by fuel-zone statistics. Birchfield knows this better than anyone;
his methodology paper is the reference for it.

This project builds the same kind of model — a DC-SCED-ready power network — but from
entirely public, non-CEII data:

- **OSM** for transmission line geometry and substation locations
- **ERCOT public data** (MORA, electrical bus catalog, settlement points, 60-day SCED disclosure)
  for generator registration and cost curves
- **EIA-860** for generator coordinates as a geo-snap fallback

The result: every bus is anchored to a real physical location. Every generator is a registered
ERCOT resource. It runs through Vatic (Birchfield's group's own solver).

This is the first public DC-SCED model of ERCOT built without CEII. That matters for
reproducibility: anyone can re-run it.

---

## The Honest Uncertainty You Need Help With

The biggest unresolved problem is **line capacity calibration**. ERCOT's actual MVA ratings
are CEII and not public. The current model uses flat tier defaults:
- 138 kV: 300 MVA
- 230 kV: 600 MVA
- 345 kV: 1,200 MVA
- 500 kV: 2,000 MVA

The v.1 run shows West Texas wind curtailing while East Texas load is shed — the classic
ERCOT West-North spread. This is physically real, but the magnitude is exaggerated because
(a) the flat ratings are probably too conservative for the major 345 kV corridors and
(b) OSM undercounts 138 kV sub-transmission, so congestion on modeled lines absorbs flow
that in reality routes around it.

You can iterate on both (better OSM coverage, voltage-class variation in ratings) but you
cannot close this uncertainty without CEII data. Birchfield is the right person to ask
whether there are systematic methods for calibrating ratings from public loading data.

---

## Questions Worth Asking (in priority order)

**1. Line rating calibration without CEII**
Is there a published methodology for inferring MVA ratings from public data — e.g.,
using historical loading patterns, line geometry (tower type, conductor count visible in
OSM tags), or statistical fits against published congestion reports? Or is this simply
an irreducible uncertainty in any public model?

**2. OSM 138 kV coverage gap**
The 138 kV network in OSM appears significantly incomplete relative to ERCOT's actual
sub-transmission. Do you know of supplementary public sources (HIFLD, FERC Form 715
public portions, state utility filings) that could improve coverage without touching CEII?

**3. Research contribution framing**
Given a geographically-grounded, open-source ERCOT DC-SCED model that anyone can run —
what experiment do you think yields the most influential research contribution? Candidates:
- Transmission expansion analysis (add lines, measure LMP spread reduction)
- Renewable integration under different siting assumptions
- Sensitivity of LMP prices to line rating assumptions (a meta-study of the calibration
  uncertainty itself)
- Storage placement optimization
- Direct comparison of model outputs against published ERCOT SCED shadow prices

**4. NYISO extension**
The Birchfield methodology has a validated New York case. Would an OSM-based public
pipeline be feasible for NYISO? What are the main structural differences from ERCOT
that complicate it? (NYISO is more regulated, different data disclosure rules, etc.)

**5. Pipeline-as-contribution**
A reproducible methodology document — "how to build a DC-SCED model of a U.S. ISO
from public data" — may itself be a publishable contribution independent of the model's
calibration quality. Is there precedent for this in the literature? Where would it fit?

---

## Tone and Length

- One screen or less. Birchfield is a professor; he gets a lot of email.
- Lead with what you built, not with your background.
- Your background (Princeton ORFE, Jane Street) is worth one sentence — credibility
  signal, not a resume.
- Frame the questions as genuinely open, not as "please validate my work."
- End with an offer: share the repo / the HTML visualizer / a Zoom call.
- CC your professor at the bottom; mention the prior connection explicitly.

---

## What NOT to Ask

- Don't ask him to validate your impedance formulas or bus assignment logic — that's
  homework you can do yourself.
- Don't ask about Vatic internals — his group wrote it; he'll assume you've read it.
- Don't ask him to co-author unless he offers — leave that door open but don't push it.
