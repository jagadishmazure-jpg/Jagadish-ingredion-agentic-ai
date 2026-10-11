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

## Framework

Built on **Microsoft Agent Framework 1.0** (`agent-framework-core==1.0.1`,
`agent-framework-openai==1.0.1`):

- One framework `Agent` per domain (R&D formulation, supply chain, ESG,
  customer advisor), each with role instructions.
- Domain logic exposed as framework **function-tools** (plain annotated
  Python functions in `ingredion_ai/framework/tools.py`).
- End-to-end demo runs on a `WorkflowBuilder` workflow: sequential R&D
  tool phase → concurrent fan-out to the three supporting agents
  (`ingredion_ai/framework/workflow.py`).
- Chat clients are swappable: a scripted `FakeChatClient` (implements the
  framework's `BaseChatClient` interface) for offline/tests, and the
  framework's unified `OpenAIChatClient` against **Azure OpenAI** for live.

The legacy `ingredion_ai/core` modules (planner, tool registry, `FakeLLM`)
remain as the tested deterministic execution substrate the function-tools
call into; all agent construction goes through the framework layer.

## Quickstart

Requires Python 3.12+.

```bash
# with uv (recommended)
uv sync --group dev
uv run python -m ingredion_ai.demo            # offline: fake client, deterministic
uv run python -m ingredion_ai.demo --live     # live: Azure OpenAI (needs .env)

# or plain pip
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"   # dev extra pulls pytest via dependency-groups; or: pip install pyyaml pytest
python -m ingredion_ai.demo
```

For live mode, copy `.env.example` to `.env` and set
`AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_CHAT_DEPLOYMENT` (see
[docs/foundry-deployment.md](docs/foundry-deployment.md)). With
`AZURE_OPENAI_API_KEY` unset, `DefaultAzureCredential` is used.

Run the tests:

```bash
uv run pytest -q        # or: python -m pytest -q
```

Expected: **339 tests, all passing, fully offline** — no network, no API
keys. The framework agents run against the scripted `FakeChatClient`.

## Deploy on Foundry

The agents are structured for **Azure AI Foundry**: same agents, same
workflow, only the chat client changes. Step-by-step — Foundry project
setup, model deployment, env config, live demo, and hosting options
(Container Apps, Foundry Agent Service) — in
[docs/foundry-deployment.md](docs/foundry-deployment.md).

## Deployment (service → Docker → AKS)

The full deployment track — build everything now, deploy when ready:

| Layer | Location |
|---|---|
| Agent service (FastAPI) + demo web UI | `ingredion_ai/service/` |
| Docker image (multi-stage, non-root) | `Dockerfile`, `.dockerignore` |
| Terraform (Azure-first, multi-cloud-ready) | `infra/terraform/` |
| Kubernetes manifests (Kustomize) | `infra/k8s/` |
| CI/CD (build → push to ACR → deploy) | `.github/workflows/deploy.yml` |
| Runbook | [docs/deployment-runbook.md](docs/deployment-runbook.md) |
| Reliability strategy | [docs/reliability.md](docs/reliability.md) |
| Azure Agentic AI Stack alignment | [docs/stack-alignment.md](docs/stack-alignment.md) |

```bash
# run the service locally (offline demo, deterministic)
uv run uvicorn ingredion_ai.service.app:app --port 8000
# mint a demo bearer token, then open http://localhost:8000/
uv run python -m ingredion_ai.service.mint_token \
  --scopes formulation:write,supply:read,esg:read,proposal:read
```

Service endpoints: `GET /api/health`, `GET /api/scenarios`,
`GET /api/agent-cards`, `GET /.well-known/agent.json` (public);
`POST /api/reformulate` and `POST /api/agents/{agent}/run`
(bearer-token auth with per-skill scopes, rate limiting, idempotency
keys). Live-LLM failures degrade gracefully to the offline pipeline
(`degraded: true` + `X-Service-Degraded` header).

> **Note:** `.github/workflows/deploy.yml` can't be pushed via the
> repo's automation identity — add it manually like `ci.yml`, then set
> the repo secrets listed at the top of the file.

## Agent catalog

| Agent | Function-tools (framework layer) | Deterministic core |
|---|---|---|
| **R&D Formulation** | `analyze_ingredients` · `suggest_substitutes` · `predict_texture_shelf_life` · `calculate_nutrition` · `validate_claims` · `generate_documentation` | `agents/rd_formulation/`: analyzer (injection-aware), cost-aware substitution, texture/shelf-life predictor + bakery stability advisory, nutrition, claim hierarchy validator, doc generator, 5–7-month cycle-time estimator |
| **Supply Chain** | `forecast_demand` · `optimize_inventory` · `schedule_production` · `detect_quality_anomalies` | `agents/supply_chain/`: trend forecaster, reorder-point inventory (SAP-adapter aware), capacity/shelf-life scheduler, anomaly detection |
| **ESG** | `collect_esg` · `calculate_carbon` · `esg_report` | `agents/esg/`: synthetic plant readings, carbon footprint, water/energy intensity, traceable markdown report |
| **Customer Advisor** | `recommend_ingredients` · `generate_sample_formula` · `validate_customer_claims` · `estimate_pricing` · `generate_tech_sheet` | `agents/customer_advisor/`: claim-filtered recommender, sample formulation, WTP-band pricing (+CRM personalization), tech sheet |

Cross-cutting: **governance** (policy engine, HITL approval gates, hash-chained audit, sanitizer/PII scrubber, scoped-token identity), **observability** (JSON logs, OTel tracing, cost/latency, incident metrics), **evaluation** (20-case accuracy suite + demo regression), **interop** (A2A cards/tasks with auth, MCP server, CRM/SAP adapters), **engineering layers** (RAG, context assembly/budgeting, harness, loops, graph orchestration).

## Interview demo guide

The 7-step talk track lives in [docs/demo-guide.md](docs/demo-guide.md). The
30-second version:

```bash
uv run python -m ingredion_ai.demo
```

**Say:** "Four specialist agents on Microsoft Agent Framework 1.0, one
workflow, fully offline and deterministic. The R&D agent flags 7
non-clean-label ingredients, substitutes 6 cost-aware, predicts texture and
shelf-life with documented heuristics, and *rejects* an invalid 'natural'
claim — agents that can't say no aren't trustworthy. Three agents fan out
concurrently for supply, ESG, and customer pricing. Governance is built in:
policy gates, human approvals, audit trails, scoped inter-agent auth."

Then show the engineering rigor: `python -m ingredion_ai.evaluation.runner`
(20/20 labeled eval cases) and the alternate scenarios
(`--scenario energy_drink`, `--scenario savory_bakery_crackers`, …).

## Architecture

```text
Demo CLI → Framework workflow (WorkflowBuilder)
             ├── R&D Formulation Agent  (6 function-tools, sequential)
             ├── fan-out ─┬─ Supply Chain Agent   (concurrent)
             │            ├─ ESG Agent            (concurrent)
             │            └─ Customer Advisor Agent (concurrent)
             └── shared blackboard ← tool results (deterministic)
```

Chat client swap: `FakeChatClient` (offline/tests) ↔ `OpenAIChatClient`
against Azure OpenAI (live). See [docs/architecture.md](docs/architecture.md)
for the full diagram, design choices, and a conceptual mapping of each
component to Azure (APIM, Functions, Agent Framework, Fabric, Azure OpenAI).

## Project structure

```text
ingredion_ai/
  service/         FastAPI agent service + demo web UI: 8-stage agentic
                   pipeline (intake → intent+guardrails → memory read →
                   RAG grounding → tool execution → response+guardrails →
                   memory write → feedback), session store, bearer auth,
                   rate limiting, idempotency, retry/breaker/fallback
  framework/       Microsoft Agent Framework 1.0 layer:
                   clients (fake + Azure OpenAI), function-tools,
                   4 domain Agents, WorkflowBuilder workflow, demo runner
  core/            Deterministic execution substrate: Agent base,
                   Orchestrator/planner, ToolRegistry, message & task-state
                   types, FakeLLM (kept; all tests pin its behavior)
  agents/
    rd_formulation/  analyzer, substitution, predictor, nutrition,
                     regulatory, documentation, cycle_time
    supply_chain/    forecaster, inventory, scheduler, quality
    esg/             collector, carbon, intensity, report
    customer_advisor/ recommender, formulation, claims, pricing, tech_sheet
  governance/      policy engine, HITL approvals, hash-chained audit,
                   input sanitizer, PII scrubber, secret checks, identity
  observability/   JSON logging, OTel-compatible tracing, cost/latency,
                   incident-style metrics
  evaluation/      datasets, metrics (precision/recall/F1/top-1), runner
  interop/         A2A agent cards + task protocol + scoped-token auth,
                   MCP server (tools/list, tools/call, stdio)
  integrations/   CRM + SAP adapter interfaces with synthetic demo doubles
  rag/             doc ingestion/chunking, hash embeddings (offline) /
                   Azure OpenAI embeddings (live), vector store, retrieval
  context/         prompt assembler (instructions+glossary+RAG+blackboard),
                   context-window budgeting
  harness/         retries/backoff, timeouts, circuit breaker, guardrails,
                   eval hooks
  loops/           reflection loop (draft→critique→revise), HITL gate loop
  graph/           nodes/edges/conditional routing/cycles; graph-based
                   reformulation variant
  data/            Synthetic JSON/CSV datasets + loader (all fictional)
  demo.py          Runnable end-to-end narrative: python -m ingredion_ai.demo
                   (--live for Azure OpenAI; --scenario …; --audit-log …)
evals/             Regression expectations for the demo (deterministic)
docs/              Architecture, Foundry deployment, identity, governance,
                   integrations, benefits, demo guide, glossary, SOC +
                   architecture alignment, attachments coverage, usecases,
                   context-engineering, harness, loops, graph, reliability,
                   deployment runbook, stack alignment
infra/
  terraform/       Azure IaC: RG, ACR, AKS (zonal, workload identity),
                   Key Vault, App Insights, Foundry account + model
                   deployment, least-privilege RBAC
  k8s/             Kustomize manifests: namespace, PDB, anti-affinity,
                   HPA, probes, workload-identity SA, Key Vault CSI
Dockerfile         Multi-stage service image (python:3.12-slim, non-root)
tests/             300+ offline pytest tests
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
