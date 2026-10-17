# Microsoft Azure Agentic AI Stack — Alignment Map

> **Disclaimer.** Independent portfolio demo; all data synthetic; not
> affiliated with any real company.

This document maps every box of the **Microsoft Azure Agentic AI Stack**
reference diagram to this project's implementation, its Terraform/K8s
resources, or its documented production path. Each box is marked:

- ✅ **Implemented** — in the repo, tested offline.
- 🟡 **Demo path** — a working offline/demo implementation with a
  documented production swap.
- 🔵 **Documented** — production path described in docs; not built here.
- ⏳ **Future** — noted as a future channel/extension.

## 1. Knowledge + Data Sources → ✅ / 🟡

| Diagram source | Our mapping |
|---|---|
| Documents, wikis, product catalogs | `docs/` (glossary, usecases, architecture) indexed by `rag/` at service startup for grounding |
| Business systems (CRM, ERP/SAP) | `integrations/crm.py`, `integrations/sap.py` — adapter interfaces + synthetic offline doubles; real connectors are extension points (🟡) |
| Consumer insights | Synthetic insights dataset under `food_ingredients_ai/data/`; queried via the RAG retriever (🟡) |
| Telemetry / plant readings | Synthetic ESG readings via `agents/esg/collector.py` (🟡) |

## 2. Event & Integration Sources → 🟡

Webhooks / queues / timers are **not** wired in this demo. The seam is
ready: the A2A `message/send` task protocol (`interop/a2a.py`) and the
MCP server (`interop/mcp.py`) are the inbound event surfaces; a
production deployment would front them with Azure Event Grid / Service
Bus (🔵, noted in `docs/architecture.md`).

## 3. Knowledge Bases (RAG) → ✅ / 🟡

- Implemented: `rag/` — chunking, hash embeddings (offline deterministic),
  in-memory vector store, `Retriever`, retrieval function-tool wired into
  the R&D and customer-advisor agents.
- Service grounding: stage 4 of the pipeline (`service/pipeline.py`)
  retrieves glossary/usecase chunks per request and returns them as
  citations in the response.
- Production path (🟡): swap `InMemoryVectorStore` → Azure AI Search and
  `HashEmbedding` → Azure OpenAI embeddings — the interfaces are
  backend-agnostic (documented in `rag/retrieval.py`).

## 4. Channels → ✅ + ⏳

- ✅ **Web UI** — single-page demo UI at `GET /` (`service/ui.py`), the
  Playwright UI-test target and primary demo surface.
- ✅ **API** — REST endpoints (`POST /api/reformulate`,
  `POST /api/agents/{agent}/run`, `GET /api/agent-cards`,
  `GET /.well-known/agent.json`).
- ✅ **Agent-to-agent** — A2A task protocol + agent cards; **MCP** server
  for tool consumers.
- ⏳ **Future channels** — Microsoft Teams (Bot Framework adapter in front
  of the same FastAPI service) and Copilot extensions are noted as future
  channels; the service's auth (bearer/OIDC) and A2A cards are already
  shaped for them. Not built in this demo.

## 5. Safety + Governance → ✅ / 🟡

Our controls today, and how they map to the diagram's Safety boxes:

| Diagram box | Our equivalent | Status |
|---|---|---|
| Foundry Guardrails (content filtering on the model) | `governance/security.py::sanitize_input` (prompt-injection patterns, fail-closed 400 at the service boundary) + `governance/policy.py` (per-agent action policy) | 🟡 Demo equivalent; production enables Azure AI Content Safety / Foundry guardrails on the model deployment (🔵) |
| Content Safety (output filtering) | `governance/security.py::scrub_pii` applied to every service response (stage 6) | 🟡 Demo equivalent; production adds the Content Safety API on outputs (🔵) |
| Prompt Shields (injection defense) | `sanitize_input` injection patterns + `require_scopes` inter-agent authz; tested with injection payloads | 🟡 Demo equivalent; production enables Prompt Shields in Foundry (🔵) |
| Governance (oversight) | `governance/`: policy engine, human-in-the-loop approval gates (`approvals.py`), hash-chained audit trail (`audit.py`), secret hygiene (`assert_no_hardcoded_secrets`) | ✅ Implemented |

Honest framing: the demo enforces the *same control points* (input
check → authz → output check → audit) with local implementations; a
production Azure deployment keeps the control points and swaps the
mechanisms for the managed Safety services. See `docs/identity.md` and
`docs/governance.md`.

## 6. The 8-Step Agentic Loop → ✅

Implemented literally as `food_ingredients_ai/service/pipeline.py`
(`AgenticPipeline`), one named stage per loop step:

| # | Loop step | Implementation |
|---|---|---|
| 1 | Request Intake | `stage_intake` — normalize/validate (auth + rate limiting enforced in FastAPI deps) |
| 2 | Intent Understanding + Guardrails | `stage_intent_guardrails` — intent classification + injection guardrails (400 on hit) |
| 3 | Memory/State read | `stage_memory_read` — `service/memory.py` session store |
| 4 | Retrieve + Ground (RAG) | `stage_retrieve_ground` — glossary/usecase chunks as citations |
| 5 | Tool Selection & Execution | `stage_tool_execution` — framework workflow/agents via the resilient runner (retry + breaker + offline fallback) |
| 6 | Generate Response (+ output guardrails) | `stage_generate_response` — assemble + PII scrub |
| 7 | Memory/State write | `stage_memory_write` — turns, last intent, result keys |
| 8 | Feedback Loop (eval/log) | `stage_feedback` — JSON log line + optional audit-trail entry |

Every response carries `stages_ms` (per-stage latency), `session_id`,
`intent`, and `grounding` citations — the loop is observable, not just
aspirational.

## 7. Memory/State → ✅ / 🟡

- ✅ `service/memory.py`: `SessionStore` interface + thread-safe
  `InMemorySessionStore` (TTL, eviction), wired into pipeline stages 3
  and 7; session via `X-Session-Id` header.
- 🟡 Production: implement `SessionStore` on Cosmos DB (partitioned by
  `session_id`, document TTL) or Redis (`EXPIRE`) — service code is
  unchanged.

## 8. Agent Orchestration → ✅

- `framework/workflow.py` — `WorkflowBuilder`: sequential R&D tool phase
  → concurrent fan-out to supply-chain, ESG, customer advisor.
- `graph/` — explicit graph orchestration (nodes/edges/conditional
  routing/cycles) + a graph-based reformulation variant.
- `loops/` — reflection loop (draft → critique → revise), HITL gate loop.
- `core/planner.py` — the legacy deterministic orchestrator (kept as the
  tested execution substrate).

## 9. Agentic Frameworks → ✅

Microsoft Agent Framework 1.0 (`agent-framework-core==1.0.1`,
`agent-framework-openai==1.0.1`): one framework `Agent` per domain, plain
functions as function-tools, swappable chat clients (`FakeChatClient`
offline ↔ `OpenAIChatClient` on Azure OpenAI). See `framework/`.

## 10. Tools & Integrations → ✅ / 🟡

- ✅ 10+ function-tools (`framework/tools.py`) over the deterministic
  domain modules; MCP server (`interop/mcp.py`) exposes them to external
  clients; A2A adapter (`interop/a2a.py`) exposes agents as tasks.
- ✅ API Management (`infra/terraform/apim.tf`, Developer SKU for demo):
  API imported from the FastAPI OpenAPI document (`infra/apim/openapi.json`,
  contract-tested), inbound policies — Entra ID JWT validation, IP-based
  rate limiting, CORS — backend pool pointing at the AKS ingress.
  Production path: Premium SKU with VNET injection + Private Link.
- 🟡 CRM/SAP adapters ship with synthetic doubles; real connectors plug
  into the same interfaces.

## 11. Foundation Models → 🟡

- Demo: scripted `FakeChatClient` — deterministic, offline, tested.
- Live: `OpenAIChatClient` against Azure OpenAI on the Foundry
  (`AIServices`) account provisioned by Terraform
  (`azurerm_cognitive_account` + `azurerm_cognitive_deployment`).
- Reliability: the live path is treated as fallible — retry with
  backoff+jitter, circuit breaker, graceful offline fallback
  (`docs/reliability.md`).

## 12. Identity + Access → ✅ / 🟡

- ✅ Service: bearer-token auth on write/run endpoints, per-skill scopes
  (`interop/auth.py`); 401/403 fail closed. Mint demo tokens with
  `python -m food_ingredients_ai.service.mint_token`.
- ✅ Inter-agent: every A2A call authenticates the caller and enforces the
  skill scopes declared on the agent card.
- 🟡 Production: `verify_token` keeps its interface and validates Entra
  ID tokens via OIDC/JWKS; AKS uses workload identity (federated
  credential in Terraform, annotated `ServiceAccount` in K8s) — no keys.
  See `docs/identity.md`.

## 13. Observability + Evaluation → ✅

- Observability: JSON structured logs (`observability/logging.py`),
  OTel-compatible tracing spans per agent/tool (`tracing.py`),
  cost/latency tracking (`costs.py`), incident-style metrics
  (`incidents.py`) → Application Insights in Azure.
- Evaluation: `evaluation/` — 20-case labeled accuracy suite
  (precision/recall/F1) + demo regression eval; harness eval hooks per run.
- Service: per-request `stages_ms`, `X-Service-Degraded` signaling, audit
  trail entries.

## 14. Deployment Infrastructure → ✅ (build-ready)

| Concern | Implementation |
|---|---|
| Image | Multi-stage `Dockerfile` (python:3.12-slim, non-root, healthcheck) |
| IaC | `infra/terraform/` — RG, ACR, AKS (zonal, workload identity), Key Vault (RBAC), App Insights, Foundry account + model deployment, least-privilege RBAC |
| K8s | `infra/k8s/` — namespace, PDB, anti-affinity, HPA, probes, workload-identity SA, Key Vault CSI |
| CI/CD | planned `.github/workflows/deploy.yml` — build → push to ACR → deploy (not in the repo yet) |
| Edge / load balancing | Azure Front Door (Standard, WAF Prevention) → APIM gateway → AKS ingress → service (`infra/terraform/frontdoor.tf`, `apim.tf`). Traffic path: Client → Front Door → APIM → AKS ingress → agent service |
| Runbook | `docs/deployment-runbook.md` — provision → build → deploy → verify |

Actual `terraform apply` / deployment runs under the operator's
`az login` — this repo ships everything up to that line (build-first,
deploy-when-ready).

## Demo vs. production at a glance

| Capability | Demo (this repo) | Production (documented path) |
|---|---|---|
| LLM | Scripted fake client | Azure OpenAI on Foundry |
| Guardrails | Local sanitizer/policy/PII scrubber | + Foundry Guardrails, Content Safety, Prompt Shields |
| Identity | Synthetic JWT (dev key) | Entra ID OIDC + workload identity |
| RAG store | In-memory + hash embeddings | Azure AI Search + OpenAI embeddings |
| Session state | In-memory | Cosmos DB / Redis |
| Secrets | Env vars | Key Vault via CSI driver |
| Channels | Web UI + REST + A2A/MCP | + Teams, Copilot |
| Events | A2A/MCP surfaces | + Event Grid / Service Bus |

The architecture keeps every seam backend-agnostic so the production
column is a swap, not a rewrite.
