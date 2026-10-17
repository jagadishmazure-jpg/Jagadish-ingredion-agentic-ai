# Microsoft Enterprise AI Alignment

How this project's architecture maps to Microsoft's enterprise AI agenda
(as articulated across the October–November 2026 Discovery Sessions and
Microsoft Ignite): moving AI from demos to production, grounding agents
in business data, agentic ERP, FinOps, cloud-native foundations, and
troubleshootable agents.

## 1. "Go beyond the AI demo" → production readiness

Microsoft's core enterprise message: a demo proves an idea; production
requires reference architectures, security, governance, and a deployment
path. This project's production-readiness surface:

| Production concern | Implementation |
|---|---|
| Deployment runbook | `DEPLOYMENT.md` — local, Container Apps, and AKS paths |
| Infrastructure as code | `infra/terraform/` (APIM, Front Door/WAF, AKS, Key Vault, App Insights) |
| Containerization | `Dockerfile` (pinned base, non-root), `docker-compose.yml` |
| Kubernetes manifests | `infra/k8s/` (deployment, HPA, PDB, ingress, Key Vault CSI) |
| CI on every push | `.github/workflows/main.yml` — full test suite + static checks |
| E2E verification | `.github/workflows/qa.yml` — Playwright against the live service |

## 2. Context-aware agents grounded in business data

Microsoft's pattern (Fabric, Azure AI, Copilot Studio): agents are only
as good as the business context they are grounded in.

- **Context engineering** (`food_ingredients_ai/context/`) — assembles the
  briefing pack per request under a token budget (`budget.py`), so the
  agent sees the most relevant information first.
- **Governed data layer** (`food_ingredients_ai/datalayer/`) — versioned dataset
  registry, schema contracts, lineage: the "trusted data" foundation
  agents consume safely.
- **RAG** (`food_ingredients_ai/rag/`) — ingest → embeddings → vector store →
  retrieval, exposed as agent tools so claims are grounded in documents,
  not hallucinated.

## 3. Agentic ERP: finance & operations

Aligned to the agentic-ERP theme (Dynamics 365, Copilot, autonomous
finance operations), this project implements two deterministic
multi-agent finance flows in `food_ingredients_ai/graph/`:

- **`procurement_graph.py`** — requisition intake → supply-chain demand
  validation → policy/budget check → automatic PO below the approval
  threshold, human-in-the-loop approval above it, supplier notification.
- **`invoice_graph.py`** — deterministic 3-way match (purchase order vs
  goods receipt vs invoice) within tolerance → payment scheduling and
  ledger entry on match; line-item investigation and human escalation
  on mismatch.

Both terminate on all paths and run fully offline with synthetic data.

## 4. AI cost forecasting & FinOps

Microsoft's FinOps guidance: forecast spend, govern usage, optimize cost
per outcome — before costs scale.

- **Cost tracking** (`food_ingredients_ai/observability/costs.py`) — per-agent,
  per-operation token and cost attribution with a configurable price
  table, budget alerts, and rule-based optimization recommendations.
- **Spend forecasting** (`forecast_spend`) — projects 30-day spend from
  run history using a moving average plus a least-squares growth trend,
  with a confidence note that degrades honestly on thin history.
- **Budgets in the pipeline** — cost budgets and alerts are wired into
  the service reliability layer; see `docs/finops.md`.

## 5. Cloud-native AI foundation

The project follows cloud-native practice end to end: containerized
service, declarative Kubernetes manifests, Terraform-provisioned Azure
landing zone (networking, identity via workload identity, secrets via
Key Vault), and GitHub Actions as the delivery mechanism with OIDC
(no stored credentials) — see `docs/architecture.md`.

## 6. Troubleshootable agents

Microsoft's observability theme: teams must be able to spot and resolve
agent failures quickly.

- **Distributed tracing** (`food_ingredients_ai/observability/tracing.py`) —
  follow one request through agents, tools, and guardrails.
- **Deterministic test suite** — 590+ pytest tests (offline, fake LLM
  clients) plus Playwright E2E; every incident class has a regression
  test.
- **Failure-mode documentation** — `docs/reliability.md` catalogs
  failure modes, mitigations, and SLOs.
- **Audit trail** (`food_ingredients_ai/governance/audit.py`) — hash-chained,
  tamper-evident record of every agent action for post-incident review.
