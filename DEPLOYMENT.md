# DEPLOYMENT.md — Ingredion Agentic AI: deployment runbook

**Primary deploy path: GitHub Actions** (`.github/workflows/deploy.yml`) —
push to `main` and the service builds, deploys to Azure Container Apps, and
smoke-tests itself. **Local fallback:** `./scripts/deploy-azure.sh`.
The **AKS + Terraform** path is the enterprise story in `infra/terraform/`.

> **Heads-up:** workflow files can't be pushed by the repo's automation
> identity (GitHub API returns 403 on `.github/workflows/*`). Add
> `.github/workflows/ci.yml`, `deploy.yml`, and `qa.yml` manually in the
> GitHub web UI (repo → Add file → Upload files), then push. Everything else
> in this repo is already pushed.

> All data in this project is **synthetic and fictional**. This is an
> independent portfolio project, not affiliated with Ingredion.

## One-time setup: OIDC federated credentials (no stored secrets)

The deploy workflow logs in to Azure with OIDC federated credentials —
there are **no long-lived secrets** to store in GitHub. Run once under your
own `az login`:

```bash
# 1. Entra app + service principal for GitHub Actions
APP_NAME="github-ingredion-deploys"
az ad app create --display-name "$APP_NAME"
APP_ID=$(az ad app list --display-name "$APP_NAME" --query '[0].appId' -o tsv)
az ad sp create --id "$APP_ID"

# 2. Contributor on the subscription (scope to the resource group if you prefer)
SUB_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
az role assignment create --assignee "$APP_ID" --role Contributor \
  --scope "/subscriptions/$SUB_ID"

# 3. Federated credential trusting the `production` environment of this repo
az ad app federated-credential create --id "$APP_ID" --parameters "{
  \"name\": \"github-production\",
  \"issuer\": \"https://token.actions.githubusercontent.com\",
  \"subject\": \"repo:jagadishmazure-jpg/Jagadish-ingredion-agentic-ai:environment:production\",
  \"audiences\": [\"api://AzureADTokenExchange\"]
}"

echo "AZURE_CLIENT_ID=$APP_ID"
echo "AZURE_TENANT_ID=$TENANT_ID"
echo "AZURE_SUBSCRIPTION_ID=$SUB_ID"
```

## Required GitHub variables

Repo → Settings → Secrets and variables → Actions → **Variables** (plain
variables, *not* secrets — OIDC mints short-lived tokens at runtime):

| Variable | Value | Required |
|---|---|---|
| `AZURE_CLIENT_ID` | `$APP_ID` from setup above | yes |
| `AZURE_TENANT_ID` | `$TENANT_ID` from setup above | yes |
| `AZURE_SUBSCRIPTION_ID` | `$SUB_ID` from setup above | yes |
| `AZURE_RESOURCE_GROUP` | `ingredion-agents-rg` | no (script default) |
| `AZURE_LOCATION` | `eastus` | no (script default) |

Also create the **`production` environment** (Settings → Environments →
New environment → `production`) — the workflow's `environment: production`
gate gives you a single approval/review checkpoint before Azure changes.

## How the deploy works

1. Push to `main` touching `ingredion_ai/**`, `Dockerfile`,
   `docker-compose.yml`, `scripts/deploy-azure.sh`, or `pyproject.toml`
   (or run it manually from the Actions tab via `workflow_dispatch`).
2. `azure/login@v2` authenticates with OIDC (no secrets).
3. `./scripts/deploy-azure.sh` runs — idempotent: creates the resource group,
   ACR (Basic), builds + pushes the image **in Azure** (`az acr build`, no
   local Docker needed), creates/updates the Container App with a
   system-assigned managed identity + `AcrPull`, and waits for
   `GET /api/health`.
4. A smoke-test step curls the live `/api/health` and `/api/scenarios`.

## Prerequisites (local fallback)

1. **Azure CLI** installed: https://learn.microsoft.com/cli/azure/install-azure-cli
2. **Logged in yourself** (the scripts never log in for you and never handle
   your credentials):
   ```bash
   az login
   az account show   # confirm the right subscription
   ```
3. For the local path: **Docker** with the `compose` plugin.

Nothing is provisioned by reading this file. Nothing has been deployed yet —
deployment happens only when you run the scripts below under your own login.

## Path 1 — Local demo (fastest, free)

```bash
chmod +x scripts/*.sh   # one time: file modes don't survive every push method
./scripts/deploy-local.sh
```

Opens the demo UI at **http://localhost:8000** and the API docs at
**http://localhost:8000/docs**. Runs fully offline (deterministic synthetic
data; no LLM keys needed). Stop with `docker compose down`.

## Path 2 — Azure Container Apps, local fallback

Same result as the GitHub Actions path, run from your machine:

```bash
# Offline demo mode (no keys needed):
./scripts/deploy-azure.sh

# Live Azure OpenAI mode:
export AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com/"
export AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4o-mini"
./scripts/deploy-azure.sh --live
```

The script is **idempotent** — safe to re-run; it reuses existing resources
and updates the container app in place. What it does:

1. Verifies `az login` (fails fast with a clear error otherwise).
2. Creates resource group `ingredion-agents-rg` (override: `RESOURCE_GROUP`).
3. Creates an ACR registry `Basic` SKU (globally-unique name derived from
   your subscription id; override: `ACR_NAME`).
4. Builds and pushes the Docker image **in Azure** (`az acr build` — no local
   Docker daemon needed).
5. Creates a Container Apps environment + app with external ingress,
   system-assigned managed identity, and `AcrPull` on the registry.
6. Sets env vars (`PORT`, `GUARDRAILS_STRICTNESS=standard`, plus
   `AZURE_OPENAI_*` in `--live` mode).
7. Waits for `https://<fqdn>/api/health` and prints the live URL.

Override knobs: `RESOURCE_GROUP`, `LOCATION` (default `eastus`), `APP_NAME`,
`ACR_NAME`, `IMAGE_TAG`.

## Cost estimate (Container Apps path, demo use)

| Resource | SKU | Approx. cost |
| --- | --- | --- |
| Container Apps | Consumption, min-replicas 0 (scale-to-zero) | ~$0 idle; pennies per demo session |
| Container Registry | Basic | ~$5/month |
| Log Analytics (env default) | Pay-as-you-go | <$1/month at demo volume |

Delete the resource group when done and the meter stops. A continuously
running demo with light traffic is typically **under $10/month**.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Not logged in to Azure` | Run `az login` yourself, then re-run the script. |
| `ACR name is already in use` | Set a custom `ACR_NAME` env var (must be globally unique, lowercase alphanumerics). |
| Health check times out | `az containerapp logs show --name ingredion-agentic-ai --resource-group ingredion-agents-rg` — most often the image pull is still in progress; wait and re-run (idempotent). |
| `--live` returns 503 | `AZURE_OPENAI_ENDPOINT`/`AZURE_OPENAI_CHAT_DEPLOYMENT` missing or wrong — the service fails loudly instead of silently degrading; check the values. |
| `docker: command not found` (local) | Install Docker Desktop; the Azure path doesn't need local Docker. |

## Path 3 — Enterprise: AKS + Terraform

`infra/terraform/` models the full enterprise topology: Azure Front Door +
WAF → API Management → AKS → ACR, Key Vault (workload identity), Application
Insights, Azure AI Services/OpenAI. See `docs/deployment-runbook.md` and
`docs/foundry-deployment.md`.

```bash
cd infra/terraform
terraform init
terraform validate
terraform plan -out tfplan
terraform apply tfplan
```

> Terraform needs your own `az login` and subscription too, and it provisions
> billable resources (AKS nodes). Validate HCL before first apply.

## Teardown

Container Apps path — deletes everything the script created:

```bash
az group delete --name ingredion-agents-rg --yes --no-wait
```

Local path:

```bash
docker compose down
```

AKS/Terraform path:

```bash
cd infra/terraform && terraform destroy
```
