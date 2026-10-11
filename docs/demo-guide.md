# Demo Talk Track

A step-by-step script for the live demo. Run offline — deterministic, so it
never surprises you mid-demo.

> **Disclaimer.** Independent portfolio demo; all data synthetic; not
> affiliated with Ingredion Incorporated.

## Setup (1 min)

```bash
uv run python -m ingredion_ai.demo
```

**Say:** "Four specialist agents on Microsoft Agent Framework 1.0, one
workflow. Everything you're about to see is synthetic demo data — the point
is the architecture, governance, and evaluation, not the food science."

## STEP 1 — Analyze (R&D Formulation)

**Say:** "The R&D agent analyzes a sweet bakery cake formula and flags every
non-clean-label ingredient — seven flags, including refined sugar, a
synthetic color, and a preservative."

*Point to:* the flagged ingredient list and reasons.

## STEP 2 — Substitute (R&D Formulation)

**Say:** "The substitution engine ranks clean-label swaps. Ranking is
**cost-aware** — ingredient cost is the #1 reported reformulation barrier —
so the cheapest viable swap wins ties. Watch it handle the tricky ones:
titanium dioxide → calcium-carbonate whitener, synthetic color →
fruit/vegetable juice concentrate."

*Point to:* ranked substitution table.

## STEP 3 — Predict (R&D Formulation)

**Say:** "It predicts texture match and shelf-life with a documented linear
heuristic — 92.2% and 8.2 days — and raises **stability risk flags**,
stronger for bakery because that's where shelf-life anxiety is highest when
you remove familiar functional ingredients."

## STEP 4 — Claims (R&D Formulation)

**Say:** "The claim validator checks label claims against regional rules.
This is my favorite part: it **rejects** 'natural' while refined sugar is
still in the formula. Two of three claims pass. Agents that can't say no
aren't trustworthy."

*Point to:* the failed claim with its reason.

## STEP 5 — Fan-out (Supply Chain · ESG · Customer Advisor)

**Say:** "Now three agents run concurrently off the shared blackboard.
Supply chain forecasts demand and suggests purchase orders. ESG computes
carbon, water, and energy intensity from plant readings and drafts a
traceable report. The customer advisor prices the reformulation — with a
willingness-to-pay band, since about half of consumers pay 10%+ more for
claims they value."

## STEP 6 — Governance overlay (talk, don't run)

**Say:** "In production this sits behind policy gates: new formulations and
customer proposals need human approval, every action lands in a
hash-chained audit log, and agent-to-agent calls carry short-lived scoped
tokens verified per skill. Try the eval suite for the engineering rigor:
`python -m ingredion_ai.evaluation.runner` — 20 labeled cases, precision /
recall on claim validation, top-1 accuracy on substitutions."

## STEP 7 — Close

**Say:** "Same agents, same workflow — swap the fake chat client for Azure
OpenAI and it runs live. That's the whole pitch: deterministic offline,
governed by design, deployable on Foundry."

## Alternate scenarios

```bash
uv run python -m ingredion_ai.demo --scenario savory_bakery_crackers
uv run python -m ingredion_ai.demo --scenario energy_drink
uv run python -m ingredion_ai.demo --scenario flavored_water
uv run python -m ingredion_ai.demo --scenario nutritional_shake
uv run python -m ingredion_ai.demo --scenario cola_soft_drink
uv run python -m ingredion_ai.demo --audit-log /tmp/demo-audit.jsonl
```

Scenarios cover sweet/savory bakery and carbonated/energy/flavored-water/
nutritional beverages — the ebook's priority categories.
