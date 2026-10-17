# Multi-Agent Business Flows

Four end-to-end orchestration flows in `food_ingredients_ai/graph/`, each wiring
multiple specialist agents into one business scenario. They follow the
exact pattern of `reformulation_graph.py`: nodes are `fn(state) -> dict`,
edges/conditionals come from `food_ingredients_ai/graph/graph.py`, and every
agent call uses the same deterministic `Agent.execute()` paths as the
sequential demos — the graphs only change *control flow*.

All four run offline (no API keys) and are covered by
`tests/test_business_graphs.py` (happy path + branch path each).

## 1. Supply disruption response — `supply_disruption_graph.py`

**Trigger:** a key ingredient SKU drops below its reorder point.
**Flow:** supply chain flags the shortage → R&D finds a clean-label
substitute → ESG re-scores the carbon footprint → customer advisor drafts
the customer notification as a tech sheet.

```
check_inventory --(shortage)--> find_substitute --> rescore_carbon --> notify_customer --> done
       |
       +--(no shortage)--> no_action
```

- `run_supply_disruption_graph(sku="PF-200", on_hand_tonnes=0.5)`
- `on_hand_tonnes` controls the branch: below reorder point → full chain;
  at/above → terminal `no_action`.
- Tasks: `optimize_inventory` → `suggest_substitutes` →
  `calculate_carbon` → `validate_customer_claims` + `generate_tech_sheet`.

## 2. New product launch — `product_launch_graph.py`

**Trigger:** launching a new clean-label product.
**Flow:** R&D formulates → supply chain forecasts demand and schedules
production (feasibility gate) → ESG reviews the footprint → advisor
assembles the launch pack (pricing + tech sheet).

```
formulate --> check_feasibility --(feasible)--> esg_review --> launch_pack --> done
                 |
                 +--(not feasible)--> blocked
```

- `run_product_launch_graph(formula_id="sweet_bakery_cake", capacity_per_day=100.0)`
- `capacity_per_day` controls the branch: the scheduler raises
  `ValueError` when demand cannot fit capacity/shelf-life → terminal
  `blocked` instead of launching on hope.
- Tasks: `analyze_ingredients` + `suggest_substitutes` →
  `forecast_demand` + `schedule_production` → `esg_report` →
  `estimate_pricing` + `validate_customer_claims` + `generate_tech_sheet`.

## 3. Quality complaint triage — `quality_issue_graph.py`

**Trigger:** a customer reports a quality problem with a batch.
**Flow:** advisor logs the complaint (validating the claims in it) →
supply chain traces the batch for spec anomalies → *only if an anomaly
is found* → R&D investigates root cause → ESG confirms label claims
still hold → advisor issues a corrective-action note.

```
intake --> trace_batch --(anomaly)--> investigate --> confirm_claims --> corrective_note --> done
                |
                +--(no anomaly)--> no_issue
```

- `run_quality_issue_graph(batch_id="B-1042", inject_anomaly=True)`
- `inject_anomaly` controls the branch: out-of-spec viscosity reading →
  full investigation; in-spec → terminal `no_issue_found`.
- Tasks: `validate_customer_claims` → `detect_quality_anomalies` →
  `analyze_ingredients` → `esg_report` → `generate_tech_sheet`.

## 4. Cost spike response — `cost_spike_graph.py`

**Trigger:** a key ingredient's cost spikes (e.g. +35%).
**Flow:** supply chain flags the spike → R&D finds a cheaper clean-label
substitute → *only if the swap beats the hurdle* → ESG verifies the
footprint is not worse → advisor updates customer pricing.

```
flag_spike --> find_saving --(saving found)--> verify_footprint --> update_pricing --> done
                  |
                  +--(no saving)--> no_action
```

- `run_cost_spike_graph(sku="PF-200", spike_pct=35.0, min_saving_pct=5.0)`
- Saving is measured against the **spiked baseline**: what the original
  formula would cost at spiked prices vs the reformulated formula. (Note:
  clean-label substitutes usually cost *more* than the original — the
  honest comparison is reformulate-vs-absorb-the-spike.)
- `min_saving_pct` controls the branch: below hurdle → terminal
  `no_action`, formula left unchanged.
- Tasks: `optimize_inventory` → `suggest_substitutes` (+ honest pricing
  comparison) → `calculate_carbon` → `estimate_pricing`.

## Design notes

- **Deterministic branching:** each conditional reads a flag the previous
  node computed from real agent output (purchase suggestions, scheduler
  feasibility, anomaly count, saving vs hurdle) — no mocks, no randomness.
- **Termination:** every path ends at a terminal node; the graph runtime
  additionally guards with `max_steps`.
- **Going live:** these flows use `Agent.execute()` directly (deterministic
  skills). To put a real LLM in the loop, see `docs/real-llm.md` and
  `build_chat_client(live=True)` — direct OpenAI via `OPENAI_API_KEY` or
  Azure OpenAI.
