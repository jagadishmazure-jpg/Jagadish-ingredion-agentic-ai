# Terraform — Azure deployment track

Azure-first infrastructure for the agent service, written for
multi-cloud portability later (provider blocks are isolated in this
`azure/` directory; a future `aws/` or `gcp/` sibling reuses the
variable/output shapes).

## What it provisions

| Resource | Purpose |
|---|---|
| Resource group | Everything lives here |
| Container Registry (ACR) | Service image store (admin keys off) |
| AKS | Kubernetes host (OIDC + workload identity on) |
| Key Vault (RBAC-only) | Secrets; no access policies |
| Log Analytics + Application Insights | Logs, traces, metrics |
| User-assigned managed identity + federated credential | AKS service account → Azure (no secrets) |
| Azure AI Services account (`AIServices`) + OpenAI deployment | Foundry + chat model for live mode |
| API Management (Developer SKU) | Edge gateway: OpenAPI import, Entra ID JWT validation, rate limiting, CORS; backend = AKS ingress |
| Front Door (Standard) + WAF | Global entry point: load balancing, TLS, bot/OWASP rules → APIM |
| Service Bus (Basic) | `reformulation-jobs` queue (+DLQ) and `job-results` topic |
| Event Grid topic | Domain-event fan-out (`reformulation.completed`, …) |
| Event Hubs (Basic) | `run-telemetry` hub for run metrics |
| Function App (Consumption) | HTTP/SB-queue/timer triggers for the agent workloads |
| Logic App (Consumption) | Human-approval workflow (definition in `infra/logicapps/`) |

RBAC wiring: AKS kubelet → `AcrPull` on ACR; workload identity →
`Key Vault Secrets User` and `Cognitive Services OpenAI User`.

## Usage

```bash
az login                                    # prerequisite; sets subscription
cd infra/terraform
terraform init
terraform plan -var environment=dev         # review
terraform apply -var environment=dev
```

Useful outputs for the next steps:

```bash
terraform output -raw acr_login_server
terraform output -raw aks_name
terraform output -raw key_vault_name
terraform output -raw workload_identity_client_id
terraform output -raw openai_endpoint
terraform output -raw openai_deployment_name
```

Feed these into `infra/k8s/` placeholders and the CI secrets — see
[docs/deployment-runbook.md](../../docs/deployment-runbook.md).

## Remote state

Not configured here on purpose. Before first apply, point Terraform at
your own backend (e.g. an `azurerm` backend with a storage account) —
never commit `*.tfstate`.
