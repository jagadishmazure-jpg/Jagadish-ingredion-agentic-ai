# FinOps: LLM + Azure Cost Controls

> Demo price tables are placeholders, not real Azure pricing. Swap in
> actual rates before any real spend.

## LLM cost tracking (in code)

`ingredion_ai/observability/costs.py`:

- **Per-model price table** (`MODEL_PRICE_TABLE`): configurable USD-per-1k-token
  rates per model/deployment name (`demo-cheap`, `demo-standard`,
  `demo-premium`). `CostTracker.record(..., model=...)` prices each
  operation against the table; unknown models raise `KeyError`
  (fail-fast, no silent mispricing).
- **Budget tracking** (`BudgetTracker`): set a USD budget; warning alert at
  80% (configurable), breach alert at 100%. Alerts fire once per level.
- **Recommendations** (`recommend_optimizations`): rule-based, from run history —
  cache repeated responses when avg output tokens are high, route small
  tasks to cheaper deployments, cache RAG retrievals, batch tiny ops.
  Each recommendation carries an estimated saving % (demo heuristic).

Wire the tracker into production agent runs and export
`BudgetTracker.status()` to your ops dashboard.

## Azure cost controls

| Control | Where | Notes |
|---|---|---|
| Budget alerts | Cost Management | Create budgets on the resource group with 80%/100% action groups (email/webhook). The in-code `BudgetTracker` is for LLM spend; Azure budgets cover infra. |
| AKS right-sizing | `infra/terraform` | Start with small system + user node pools; enable cluster autoscaler; use the `aks_availability_zones` var as-is (zones don't add cost, SKUs do). |
| APIM SKU | `infra/terraform/apim.tf` | Developer SKU for demo (no SLA, cheap); Premium for production VNET/private-link — the single biggest cost step in this architecture. |
| Front Door | `infra/terraform/frontdoor.tf` | Standard SKU; WAF policy adds cost — keep in Prevention mode only where needed. |
| Azure OpenAI | Foundry project | Prefer smaller/cheaper deployments for simple tasks (the `DOWNSHIFT_MODEL` recommendation); set token limits and quota alerts per deployment. |
| Container Registry | `infra/terraform` | Basic SKU for demo; enable retention policies to prune old images. |
| Log Analytics / App Insights | `infra/terraform` | Set daily ingestion caps; sample aggressively in dev. |
| Key Vault | `infra/terraform` | Operations are cheap; prefer RBAC + managed identity (already configured) over per-call auth. |

## Cost review cadence

Weekly in pilot: LLM spend vs budget (in-code tracker), Azure spend vs
Cost Management budget, top-3 cost drivers, and whether any
`recommend_optimizations` output was actioned. Promote to a FinOps
dashboard once the pilot goes multi-tenant.
