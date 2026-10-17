# Deployment Runbook — Agent Service on Azure (AKS)

End-to-end: provision Azure with Terraform → build & push the Docker
image → deploy to AKS → verify. Build-first, deploy-when-ready: every
step below is a command you run; nothing here auto-deploys on its own.

> **Disclaimer.** Independent portfolio demo; all data synthetic; not
> affiliated with any real company.

## 0. Prerequisites (manual, one time)

- An Azure subscription you control. Run **`az login`** and confirm the
  right subscription: `az account show --output table`.
- CLI tools: `terraform >= 1.9`, `docker`, `kubectl`, `az` CLI.
  (`az aks install-cli` for kubectl if needed.)
- Terraform remote state: configure your own backend before the first
  apply (the config intentionally ships without one — never commit
  `*.tfstate`).

## 1. Provision Azure

```bash
cd infra/terraform
terraform init
terraform plan -var environment=dev      # review the plan
terraform apply -var environment=dev
```

Capture the outputs — everything downstream needs them:

```bash
terraform output -raw acr_login_server          # e.g. ingaid...acr....azurecr.io
terraform output -raw aks_name
terraform output -raw resource_group_name
terraform output -raw key_vault_name
terraform output -raw workload_identity_client_id
terraform output -raw openai_endpoint
terraform output -raw openai_deployment_name
terraform output -raw app_insights_connection_string   # sensitive
```

What you get: resource group, ACR (admin keys off), AKS with OIDC +
workload identity, RBAC-only Key Vault, Log Analytics + App Insights, a
user-assigned managed identity federated to the K8s service account, an
Azure AI Services (Foundry) account with a chat-model deployment,
**API Management (Developer SKU)** with the agent API imported from
`infra/apim/openapi.json` plus Entra ID JWT / rate-limit / CORS inbound
policies, and **Azure Front Door (Standard + WAF)** as the global entry
point. RBAC: kubelet → `AcrPull`; workload identity → Key Vault Secrets
User + Cognitive Services OpenAI User. See `infra/terraform/README.md`.

**Traffic path (client → service):**

```
Client
  → Front Door (https://<fd-endpoint-hostname>, WAF, TLS)
  → APIM gateway (JWT validation, rate limiting, CORS, subscription key)
  → AKS nginx ingress (https://<app_host>, var.app_host)
  → agent service (ClusterIP)
```

APIM needs two variables at apply time (no defaults — pass them
explicitly): `-var entra_tenant_id=<tenant>` and
`-var entra_api_audience=<api-app-client-id>` for the `validate-jwt`
policy, and `-var app_host=<your-dns-name>` matching `__APP_HOST__` in
`infra/k8s/ingress.yaml`. Regenerate the OpenAPI import file after any
service route change (a test fails if it drifts):

```bash
python -c "import json; from food_ingredients_ai.service.app import app; \
  json.dump(app.openapi(), open('infra/apim/openapi.json','w'), indent=2)"
```

## 2. Build & push the image

```bash
ACR=$(cd infra/terraform && terraform output -raw acr_login_server)
az acr login --name "${ACR%%.*}"

docker build -t "$ACR/food-ingredients-agentic-ai:0.1.0" .
docker push "$ACR/food-ingredients-agentic-ai:0.1.0"
```

Image notes: multi-stage `python:3.12-slim`, non-root `appuser`,
healthcheck on `GET /api/health`. Offline demo needs no secrets; live
mode reads `AZURE_OPENAI_*` from the environment (see step 4).

## 3. Fill the K8s placeholders

`infra/k8s/*.yaml` ships with `__PLACEHOLDERS__`. Fill them from the
Terraform outputs (one-time per environment):

| Placeholder | Value |
|---|---|
| `__ACR_LOGIN_SERVER__` | `terraform output -raw acr_login_server` |
| `__IMAGE_TAG__` | image tag you pushed (e.g. `0.1.0`) |
| `__WORKLOAD_IDENTITY_CLIENT_ID__` | `terraform output -raw workload_identity_client_id` |
| `__KEY_VAULT_NAME__` | `terraform output -raw key_vault_name` |
| `__TENANT_ID__` | `az account show --query tenantId -o tsv` |
| `__AZURE_OPENAI_ENDPOINT__` | `terraform output -raw openai_endpoint` |
| `__APP_HOST__` | your DNS name (see step 5) |

The CSI `SecretProviderClass` additionally needs the Secrets Store CSI
driver + Azure provider installed on the cluster (one time):

```bash
az aks get-credentials -g <rg> -n <aks-name>
helm repo add csi-secrets-store-provider-azure \
  https://azure.github.io/secrets-store-csi-driver-provider-azure/charts
helm install csi-secrets-store-provider-azure/csi-secrets-store-provider-azure \
  --namespace kube-system --generate-name
```

## 4. Deploy

```bash
az aks get-credentials -g <resource-group> -n <aks-name>
kubectl apply -k infra/k8s/
kubectl rollout status deployment/food-ingredients-agent-svc -n food-ingredients-ai
```

Verify inside the cluster:

```bash
# health
kubectl run smoke --rm -i --restart=Never -n food-ingredients-ai \
  --image=curlimages/curl:8.10.1 -- \
  curl -fsS http://food-ingredients-agent-svc/api/health
# full workflow (mint a token first)
TOKEN=$(python -m food_ingredients_ai.service.mint_token \
  --scopes formulation:write | tail -1)
kubectl run demo --rm -i --restart=Never -n food-ingredients-ai \
  --image=curlimages/curl:8.10.1 -- \
  curl -fsS -X POST http://food-ingredients-agent-svc/api/reformulate \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"scenario":"sweet_bakery_cake"}' | head -c 400
```

Live mode (Azure OpenAI): set `AZURE_OPENAI_CHAT_DEPLOYMENT` to the
Terraform output `openai_deployment_name`; the pod authenticates to
Azure OpenAI with **workload identity** (no keys). `AZURE_OPENAI_API_KEY`
via Key Vault exists only as a documented fallback.

## 5. Public access (manual)

- Point DNS at your ingress controller's external IP and set `__APP_HOST__`
  (must equal Terraform `var.app_host` — APIM uses it as the backend target).
- TLS: terminate at the ingress (cert-manager `ClusterIssuer` or your
  controller's mechanism) — left manual on purpose.
- The demo UI is served at `GET /`; agent cards at
  `GET /.well-known/agent.json`.

### Verify the edge path (Front Door → APIM → AKS)

```bash
FD=$(terraform -chdir=infra/terraform output -raw frontdoor_endpoint_hostname)
APIM=$(terraform -chdir=infra/terraform output -raw apim_gateway_url)

# 1. APIM imported the API (expect the operation list, not 404)
curl -fsS "$APIM/v1/api/health" -H "Ocp-Apim-Subscription-Key: $SUB_KEY" | head -c 200

# 2. JWT policy rejects anonymous traffic (expect 401)
curl -s -o /dev/null -w "%{http_code}\n" "$APIM/v1/api/health"

# 3. Front Door serves the edge (expect 200 via the FD hostname)
curl -fsS "https://$FD/api/health" -H "Ocp-Apim-Subscription-Key: $SUB_KEY" | head -c 200
```

Get a subscription key from the Azure portal (APIM → Subscriptions) or
`az apim subscription list`. For an Entra ID user token, register an app
and use the client-credentials or auth-code flow against
`var.entra_api_audience`.

## 6. CI/CD (optional)

**Planned, not in the repo yet:** a `.github/workflows/deploy.yml` that
automates steps 2–4 on push to `main` (build → push to ACR → `kubectl apply -k`
→ rollout check → smoke test) using OIDC federated credentials.

## 7. Rollback & teardown

```bash
# rollback the service
kubectl rollout undo deployment/food-ingredients-agent-svc -n food-ingredients-ai
# tear everything down (destroys Azure resources)
cd infra/terraform && terraform destroy -var environment=dev
```

## What's manual vs automated

| Step | How |
|---|---|
| `az login`, subscription choice | manual (your credentials) |
| Terraform remote-state backend | manual, one time |
| `terraform apply` | manual command (or your own pipeline) |
| Docker build/push | manual command or `deploy.yml` |
| K8s placeholder fill | manual one time, then `deploy.yml` |
| `kubectl apply`, rollout | manual command or `deploy.yml` |
| DNS + TLS | manual |
| Entra ID app registration for end users | only if you add interactive user login; the service-to-Azure path needs none (managed identity) |
| APIM JWT policy vars (`entra_tenant_id`, `entra_api_audience`, `app_host`) | manual `-var` flags at `terraform apply` |
| APIM subscription key for edge smoke tests | manual (portal or `az apim`) |
