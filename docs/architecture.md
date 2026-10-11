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
                    │  ingredients.json (55)       │
                    │  formulas.json (8)           │
                    │  demand.csv · esg_readings   │
                    │  glossary.md (semantic layer)│
                    └──────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Cross-cutting layers (used by every agent)                       │
├──────────────┬───────────────────┬──────────────────────────────┤
│ Governance   │ Observability     │ Interop                      │
│ - policy     │ - JSON logging    │ - A2A agent cards + tasks    │
│ - HITL gates │ - OTel tracing    │ - MCP server (tools/list)    │
│ - audit JSONL│ - cost/latency    │ - CRM/SAP adapter interfaces │
│ - sanitizer  │ - incident metrics│ - scoped-token auth          │
│ - PII scrub  │                   │                              │
├──────────────┴───────────────────┴──────────────────────────────┤
│ Engineering layers                                               │
│ - rag/ (ingest→embed→retrieve) · context/ (assemble+budget)      │
│ - harness/ (retries/timeouts/circuit breaker)                    │
│ - loops/ (reflection, HITL) · graph/ (nodes/edges/conditionals)  │
└─────────────────────────────────────────────────────────────────┘
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
| OTel tracing hooks          | Application Insights (see foundry-deployment §7)        |
| Agent cards / A2A tasks     | Foundry Agent Service inter-agent calls                |
| MCP server                  | External copilots/IDEs invoking domain tools           |
| CRM/SAP demo adapters       | Salesforce/Dynamics, S/4HANA via managed identity      |
| Scoped tokens (demo JWT)    | Entra ID OIDC tokens, workload identity in AKS         |
| In-memory vector store      | Azure AI Search                                        |
| Hash embeddings (offline)   | Azure OpenAI embeddings (live)                         |

### Layer map

| Layer | Purpose | Key modules |
|---|---|---|
| Framework | MAF 1.0 agents, function-tools, WorkflowBuilder | `framework/` |
| Domain agents | Deterministic business logic per specialty | `agents/` |
| Data + semantic | Synthetic datasets + governed glossary | `data/`, `docs/glossary.md` |
| RAG / context | Grounded retrieval, prompt assembly, budgeting | `rag/`, `context/` |
| Harness / loops / graph | Resilient execution, reflection, orchestration | `harness/`, `loops/`, `graph/` |
| Governance | Policy, HITL, audit, security, identity | `governance/` |
| Observability | Logging, tracing, costs, incident metrics | `observability/` |
| Evaluation | Regression + accuracy-style eval suites | `evaluation/`, `evals/` |
| Interop | A2A, MCP, CRM/SAP adapters | `interop/`, `integrations/` |

### Design choices

- **Deterministic everywhere**: no randomness, no network, no API keys.
  Tests assert exact values, and the demo prints identically on every run.
- **Honest heuristics**: the texture/shelf-life "predictor" is a documented
  linear demo model, not food science. It exists to show orchestration, not
  to formulate real products.
- **Claims can fail**: the regulatory checker rejects invalid claims
  (e.g. "natural" fails while refined sugar remains) — a feature, not a bug.
