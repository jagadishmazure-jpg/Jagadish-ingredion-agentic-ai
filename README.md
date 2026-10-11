# Jagadish Ingredion Agentic AI (Demo)

A from-scratch, multi-agent AI system for **clean-label ingredient
manufacturing** — built as an interview-ready portfolio demo.

> **Disclaimer — read first.** This is an **independent portfolio project**.
> It is **not affiliated with, endorsed by, or connected to Ingredion
> Incorporated**. Every ingredient, formula, demand series, ESG reading,
> price, and prediction in this repository is **synthetic demo data invented
> for illustration**. Ingredient names are fictional. Nothing here is food-
> science advice and nothing should be used to formulate real products.

## What it does

Four specialist agents, coordinated by a planner/orchestrator, walk through
an end-to-end clean-label reformulation:

| Agent | Capabilities |
|---|---|
| **R&D Formulation** | Flags non-clean-label ingredients · recommends clean-label swaps · predicts texture & shelf-life (demo heuristic) · computes nutrition · validates label claims per region · generates formulation spec + tech sheet |
| **Supply Chain** | Demand forecasting (trend model) · inventory/procurement optimization · capacity- and shelf-life-aware production scheduling · quality anomaly detection |
| **ESG** | Synthetic plant data collection · carbon footprint · water/energy intensity · markdown ESG report with traceable calculations |
| **Customer Advisor** | Ingredient recommendations by category/claims/region · sample formulation generator · claim validation · willingness-to-pay pricing bands · customer technical sheet |

The headline scenario: reformulate a **sweet bakery cake** to clean label —
7 ingredients flagged, 6 substituted, 1 removed, texture match 92.2%,
shelf-life 8.2 days, and an honest claim check where 2 of 3 claims pass
("natural" correctly fails while refined sugar remains).

## Quickstart

Requires Python 3.12+.

```bash
# with uv (recommended)
uv sync --group dev
uv run python -m ingredion_ai.demo

# or plain pip
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"   # dev extra pulls pytest via dependency-groups; or: pip install pyyaml pytest
python -m ingredion_ai.demo
```

Run the tests:

```bash
uv run pytest -q        # or: python -m pytest -q
```

Expected: **100+ tests, all passing, fully offline** — no network, no API
keys. Agents reason through a deterministic `FakeLLM`.

## Architecture

```text
Demo CLI → Orchestrator (goal → tasks → agents, blackboard state)
             ├── R&D Formulation   (analyze → substitute → predict → validate → document)
             ├── Supply Chain      (forecast → inventory → schedule → quality)
             ├── ESG               (collect → carbon → report)
             └── Customer Advisor  (recommend → formulate → validate → price)
```

See [docs/architecture.md](docs/architecture.md) for the full diagram,
design choices, and a conceptual mapping of each component to Azure
(APIM, Functions, Agent Framework, Fabric, Azure OpenAI).

## Project structure

```text
ingredion_ai/
  core/            Agent base, Orchestrator/planner, ToolRegistry,
                   message & task-state types, deterministic FakeLLM
  agents/
    rd_formulation/  analyzer, substitution, predictor, nutrition,
                     regulatory, documentation
    supply_chain/    forecaster, inventory, scheduler, quality
    esg/             collector, carbon, intensity, report
    customer_advisor/ recommender, formulation, claims, pricing, tech_sheet
  data/            Synthetic JSON/CSV datasets + loader (all fictional)
  demo.py          Runnable end-to-end narrative: python -m ingredion_ai.demo
evals/             Regression expectations for the demo (deterministic)
docs/              Architecture doc
tests/             100+ offline pytest tests
```

## Key design decisions

- **Deterministic**: same inputs → same outputs, always. The regression eval
  pins the demo's headline numbers.
- **Claims can fail**: the regulatory checker rejects invalid claims instead
  of rubber-stamping them.
- **Honest heuristics**: the texture/shelf-life predictor is a documented
  linear demo model, not a food-science model.
- **Safe scheduling**: production is never scheduled earlier than shelf-life
  allows, and daily capacity is never exceeded (infeasible plans raise
  errors instead of silently overloading).

## CI

GitHub Actions runs the full pytest suite on every push and pull request
(Python 3.12, via `uv`).

## License

MIT — see [LICENSE](LICENSE).
