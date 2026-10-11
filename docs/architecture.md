# Architecture

> Demo project. All data synthetic and fictional. Not affiliated with Ingredion.

## Multi-agent architecture (demo)

```text
                    ┌──────────────────────────────┐
                    │        User / Demo CLI       │
                    │   python -m ingredion_ai.demo│
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   Orchestrator (planner)     │
                    │  - decomposes goal→tasks    │
                    │  - routes to specialist     │
                    │  - blackboard state sharing │
                    └──────┬───┬───┬───┬───────────┘
                           │   │   │   │
        ┌──────────────────┘   │   │   └──────────────────┐
        ▼                      ▼   ▼                      ▼
┌───────────────┐   ┌───────────────┐ ┌───────────┐ ┌──────────────────┐
│ R&D           │   │ Supply Chain  │ │ ESG       │ │ Customer Advisor │
│ Formulation   │   │               │ │           │ │                  │
├───────────────┤   ├───────────────┤ ├───────────┤ ├──────────────────┤
│ - analyzer    │   │ - forecaster  │ │ - collect │ │ - recommender    │
│ - substitution│   │ - inventory   │ │ - carbon  │ │ - sample formula │
│ - predictor   │   │ - scheduler   │ │ - intensity│ │ - claim validator│
│ - nutrition   │   │ - quality     │ │ - report  │ │ - pricing        │
│ - regulatory  │   │               │ │           │ │ - tech sheet     │
│ - docs        │   │               │ │           │ │                  │
└───────┬───────┘   └───────┬───────┘ └─────┬─────┘ └────────┬─────────┘
        └───────────────────┴───────────────┴──────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   Synthetic data layer       │
                    │  ingredients.json (45)       │
                    │  formulas.json (3)           │
                    │  demand.csv · esg_readings   │
                    └──────────────────────────────┘
```

### How it runs

1. `Orchestrator.plan("reformulate")` matches the goal keyword to a
   declarative plan template (`GOAL_PLANS`) and asks the deterministic
   `FakeLLM` to narrate it.
2. Each `Task` is routed to its registered agent (`rd_formulation`,
   `supply_chain`, `esg`, `customer_advisor`).
3. Task outputs accumulate on a shared **blackboard** dict that later tasks
   read (e.g. substitutions read the analysis flags; claim validation reads
   the reformulated formula and nutrition).
4. Failures become failed `TaskResult`s and stop the run — no exceptions
   escape the orchestrator.

### Conceptual Azure mapping

This repo is intentionally offline, but each piece maps 1:1 to an Azure
deployment for an interview conversation:

| Demo component              | Azure equivalent (conceptual)                          |
|-----------------------------|--------------------------------------------------------|
| Orchestrator / planner      | Microsoft Agent Framework (planner + orchestration)    |
| Specialist agents           | Agent Framework agents / Azure AI Foundry agents       |
| Tool functions              | Azure Functions behind Azure API Management            |
| FakeLLM                     | Azure OpenAI (swap-in point; interface-compatible)     |
| ingredients/formulas JSON   | PLM / ingredient DB via Fabric lakehouse               |
| demand.csv                  | SAP IBP via Data Factory → Fabric                      |
| ESG readings                | Plant telemetry / sustainability DB in Fabric          |
| Claim rules                 | Policy engine / regulatory service                     |
| Docs / reports              | Generated artifacts stored in Blob / SharePoint         |
| pytest + CI                 | GitHub Actions (this repo) → Azure DevOps pipelines    |
| Tracing (task results)      | Azure Monitor + Log Analytics                          |

### Design choices

- **Deterministic everywhere**: no randomness, no network, no API keys.
  Tests assert exact values, and the demo prints identically on every run.
- **Honest heuristics**: the texture/shelf-life "predictor" is a documented
  linear demo model, not food science. It exists to show orchestration, not
  to formulate real products.
- **Claims can fail**: the regulatory checker rejects invalid claims
  (e.g. "natural" fails while refined sugar remains) — a feature, not a bug.
