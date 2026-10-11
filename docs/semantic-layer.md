# Semantic Metric Layer

## The problem

When a stakeholder asks "why did gross margin drop in Q3?", an agent with
raw table access will happily invent an answer: it guesses what "margin"
means, picks whatever columns look relevant, and narrates a plausible story.
The numbers may even look right. They are not governed — the same question
asked twice can produce two different definitions of margin, and nobody can
audit which one was used.

This is the failure mode both major data platforms now design against:
Databricks frames it as the *context problem* (Genie Ontology as the
business-context layer agents reason over), and Snowflake's Cortex patterns
keep agents on governed semantic objects rather than raw tables. The
principle is the same: **agents must answer business questions from governed
metric definitions, never by improvising business logic.**

## The answer in this repo

`ingredion_ai/semantics/` is the governed middle layer between agents and
data:

| Component | File | Job |
|---|---|---|
| Metric definitions | `semantics/metrics.py` | One versioned definition per metric: formula over named base measures, owner, upstream datasets |
| Registry | `semantics/registry.py` | Single source of truth; duplicate-name+version guard; natural-language resolution |
| Lineage | `semantics/lineage.py` | metric → base measures → upstream datasets chain; every driver cites it |
| Explainer | `semantics/explainer.py` | Deterministic variance decomposition of period deltas into drivers |
| Agent tools | `semantics/agent_tools.py` | `define_metric`, `get_metric_definition`, `list_metrics`, `explain_metric_change` |
| Insight flow | `graph/metric_insight_graph.py` | "Why did it change?" as an orchestrated, terminating graph |

It sits *above* `datalayer/` (which governs datasets: versions, schemas,
content hashes) and *below* the agents: the metric layer turns governed
datasets into governed *business meaning*.

## The six demo metrics

| Metric | Formula | Owner | Upstream datasets |
|---|---|---|---|
| `gross_margin_pct` | (revenue − cogs) / revenue × 100 | Finance | demand, formulas, ingredients |
| `revenue` | demand_tonnes × price_per_tonne | Finance | demand |
| `cogs` | ingredient_cost_per_tonne × production_tonnes | Finance | ingredients, esg_readings |
| `clean_label_share_pct` | clean_label_skus / total_skus × 100 | R&D | formulas, ingredients |
| `otif_pct` | on_time_full_orders / total_orders × 100 | Supply Chain | demand |
| `carbon_intensity_kg_per_tonne` | emissions_tco2e × 1000 / production_tonnes | ESG | esg_readings |

## Lineage example

`explain_lineage("gross_margin_pct", registry)` returns the chain:

```
metric: gross_margin_pct@v1
  formula: gross_margin_pct = (revenue - cogs) / revenue * 100
base_measures: [revenue, cogs]
upstream_datasets: [demand, formulas, ingredients]
citation: gross_margin_pct@v1 :: gross_margin_pct = (revenue - cogs) / revenue * 100
            :: datasets[demand, formulas, ingredients]
```

Every driver in an explanation carries a `cites` field pointing back to
this chain, so an answer is auditable end to end.

## "Why" attribution example

`explain_metric_change("gross_margin_pct", "Q2", "Q3")` decomposes the
delta with sequential variance decomposition over the formula inputs:

```
gross_margin_pct moved from 35.0 to 30.0 percent (Q2 → Q3), a delta of -5.0.
- revenue: 4800000.0 → 4920000.0 contributed +0.61 (up) [gross_margin_pct@v1 :: input 'revenue']
- cogs: 3120000.0 → 3444000.0 contributed -5.61 (down) [gross_margin_pct@v1 :: input 'cogs']
```

Contributions telescope: they sum exactly to the delta (residual ≈ 0).
Attribution is order-dependent by design — the metric's declared input
order is the documented attribution order, stated in the confidence note.

## Mapping to platform patterns

| Platform pattern | This repo's equivalent |
|---|---|
| Databricks Genie Ontology (business context layer) | `semantics/` registry + definitions |
| Snowflake governed semantic objects | Versioned `MetricDefinition` + duplicate guard |
| "Talk to your data" agents | `graph/metric_insight_graph.py` ("why did it change?") |
| Metric lineage | `explain_lineage` chain with dataset versions |

## Design notes

- **Deterministic.** No LLM in the attribution path; the same inputs
  always produce the same decomposition. The agent's job is question
  parsing and answer composition, not arithmetic.
- **Flat data → empty drivers.** When nothing moved, the explainer says
  so instead of inventing a story.
- **Unknown metric → suggestions.** The graph terminates with the governed
  metric list rather than guessing.
- **Synthetic data.** All demo period data is fictional and illustrative.
