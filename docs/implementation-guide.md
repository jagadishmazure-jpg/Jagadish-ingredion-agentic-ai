# Implementation guide

How to take this demo to a real Azure tenant. Nothing here has been deployed;
these are the steps I would follow, in order, with what to check at each one.

## 1. Run it locally first

```bash
uv sync --group dev
uv run python -m pytest -q
uv run python -m food_ingredients_ai.demo
uv run uvicorn food_ingredients_ai.service.app:app --port 8000
```

Check: tests pass, the demo prints the 7 / 6 / 1 headline, and
`GET /api/health` answers.

## 2. Switch to a real model

1. Create an Azure AI Foundry project and deploy a chat model.
2. Copy `.env.example` to `.env`; set `AZURE_OPENAI_ENDPOINT` and
   `AZURE_OPENAI_CHAT_DEPLOYMENT`. Leave the API key empty to use
   `DefaultAzureCredential` (managed identity in Azure, `az login` locally).
3. Run `python -m food_ingredients_ai.demo --live`.

Check: output matches the offline run on the deterministic steps; the
service reports `degraded: true` if the model call fails rather than erroring.
Details: [real-llm.md](real-llm.md), [foundry-deployment.md](foundry-deployment.md).

## 3. Replace synthetic data with real systems

| Demo piece | Real system | Contract to keep |
|---|---|---|
| `data/` JSON and CSV | Fabric / OneLake tables or Azure SQL | `datalayer/` registry, schema validation, lineage |
| CRM double | Dynamics 365 or Salesforce | `integrations/` CRM adapter interface |
| SAP double | SAP S/4HANA via OData or BAPI | `integrations/` SAP adapter interface |
| Hash embeddings | Azure OpenAI embeddings + Azure AI Search | `rag/` retriever interface |
| Heuristic texture and shelf-life model | A model trained on lab data | `predict_texture_shelf_life` tool signature |

Check: each adapter passes the existing contract tests before the double is removed.

## 4. Identity and access

- Users sign in with Entra ID; replace `interop/auth.py` token checks with
  OIDC/JWKS validation (same interface).
- The service uses a managed identity (workload identity on AKS) for Azure OpenAI,
  Key Vault and storage. No keys in config.
- Map per-skill scopes (`formulation:write`, `supply:read`, …) to Entra app roles.

## 5. Infrastructure

1. Create a remote state backend (storage account) by hand once.
2. `cd infra/terraform && terraform init && terraform plan` with your own variables.
3. Review the plan (AKS, ACR, Key Vault, App Insights, Foundry, Service Bus,
   Event Grid, Event Hubs, Functions, Logic Apps, APIM, Front Door) and cut what
   you do not need; APIM and Front Door are the costliest.
4. Apply, then follow [deployment-runbook.md](deployment-runbook.md) for the
   Kubernetes manifests in `infra/k8s/`.

## 6. Operate

- Send traces to Application Insights; use the KQL and burn-rate alerts in
  [monitoring.md](monitoring.md).
- Keep the 20-case eval suite in CI and grow it from real reviewed cases.
- Keep the human approval gates on anything that changes a formula or a price.

## What to measure

- Reformulation proposals accepted by R&D without major changes.
- Time from request to an approved proposal, against the current baseline.
- Claim-validation precision against regulatory review.
- Cost per proposal (model tokens plus infrastructure).
