# Deploying on Azure AI Foundry (with Azure OpenAI)

This project is built on **Microsoft Agent Framework 1.0** (`agent-framework-core`
and `agent-framework-openai`, pinned to `==1.0.1`). The offline path runs fully
locally with a scripted fake chat client; the live path calls Azure OpenAI and
is structured so the same agents can be hosted on **Azure AI Foundry**.

> Synthetic-data disclaimer: every ingredient, formula, reading, and number in
> this repo is fictional demo data. This is an independent portfolio project,
> not affiliated with any real company.

## 1. Create the Foundry project

1. Go to [Azure AI Foundry](https://ai.azure.com) and sign in.
2. **Create a project** (select your Azure subscription and resource group).
3. Note the project's **endpoint** — you will not need it for the local live
   demo, but you will for hosted deployment.

## 2. Deploy an Azure OpenAI chat model

1. In the Foundry portal, open **Models + endpoints** (or your connected
   Azure OpenAI resource).
2. **Deploy** a chat model (e.g. `gpt-4o-mini`) and note the **deployment name**.
3. Copy the Azure OpenAI **endpoint**, e.g.
   `https://<your-resource>.openai.azure.com/`.

## 3. Configure the environment

```bash
cp .env.example .env
```

Fill in:

| Variable | Value |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI endpoint URL |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | Your chat deployment name |
| `AZURE_OPENAI_API_KEY` | (optional) API key; if omitted, `DefaultAzureCredential` is used |

Keyless (recommended): leave `AZURE_OPENAI_API_KEY` empty and authenticate
with `az login` locally, or a managed identity when hosted. The code uses
`azure.identity.DefaultAzureCredential` in that case.

Verify locally:

```bash
uv sync
uv run python -m food_ingredients_ai.demo --live
```

## 4. How the live path works

`food_ingredients_ai/framework/clients.py::build_chat_client(live=True)` builds the
framework's unified `OpenAIChatClient`:

```python
OpenAIChatClient(
    model=<AZURE_OPENAI_CHAT_DEPLOYMENT>,
    azure_endpoint=<AZURE_OPENAI_ENDPOINT>,
    api_version="2024-12-01-preview",
    credential=<api key | DefaultAzureCredential()>,
)
```

The same four domain agents (`food_ingredients_ai/framework/agents.py`) and the
`WorkflowBuilder` workflow (`food_ingredients_ai/framework/workflow.py`) run
unchanged — only the chat client is swapped. The offline fake client
(`FakeChatClient`) implements the framework's `BaseChatClient` interface,
which is why CI and tests need no secrets.

## 5. Hosting the agents on Foundry

Options, in increasing order of managed-ness:

1. **Container Apps / App Service (simplest).** Containerize the repo
   (`Dockerfile` pattern: `python:3.12-slim`, `uv sync`, `uv run ...`),
   set the `AZURE_OPENAI_*` app settings, and run the workflow as a job or
   expose it behind a small FastAPI endpoint that calls
   `run_reformulation(ctx, live=True)`. Use a managed identity and leave
   `AZURE_OPENAI_API_KEY` unset.

2. **Azure AI Foundry Agent Service.** Foundry's Agent Service can host
   agents built with Microsoft Agent Framework. Package each domain agent's
   instructions + function-tools (see `food_ingredients_ai/framework/agents.py`
   and `tools.py`) as a Foundry agent definition, pointing tools at Azure
   Functions/Logic Apps that wrap the deterministic domain modules. The
   `WorkflowBuilder` topology in `workflow.py` maps 1:1 to a Foundry
   multi-agent workflow (sequential R&D phase → fan-out to supporters).

3. **Durable workflows.** For long-running, checkpointed executions, the
   framework's durable workflow support (`agent-framework-durabletask`,
   same 1.0.x line) can wrap `build_reformulation_workflow` without
   changing the agents.

## 6. Production hardening checklist

- [ ] Replace the fake client with the Azure client everywhere (`live=True`).
- [ ] Move secrets to Azure Key Vault; reference via Key Vault references.
- [ ] Add `AgentSession`/thread persistence for multi-turn conversations.
- [ ] Enable OpenTelemetry export (the framework emits OTel spans) to
      Application Insights for tracing agent/tool calls (see §7).
- [ ] Add human-approval gates on high-impact tools (the framework supports
      approval-required function tools).
- [ ] Swap synthetic data modules for real SAP/PLM/LIMS/MES connectors
      behind the same tool function signatures.

## 7. RBAC & managed identity

Least-privilege access for the hosted service:

| Identity | Granted | How |
|---|---|---|
| Agent API managed identity | Cognitive Services OpenAI User on the Azure OpenAI resource | `azurerm_role_assignment` (Terraform, later phase) |
| Same | Key Vault Secrets User on the app vault | Terraform |
| Same | Search Index Data Reader on Azure AI Search (RAG live) | Terraform |
| AKS workload identity | Federated credential → Entra ID; per-agent Kubernetes `ServiceAccount` | Terraform + K8s manifests |
| Human operators | Foundry project roles (Reader/Contributor) via Entra ID groups | Entra ID |

No API keys in app settings: `DefaultAzureCredential` / workload identity
everywhere. A2A inter-agent calls use Entra ID OIDC tokens validated
against the tenant JWKS (the demo's synthetic JWT in `interop/auth.py`
keeps the same interface). See `docs/identity.md` for the full pattern.

## 8. Wiring observability to Application Insights

The project's observability layer is OTel-compatible by design:

1. `observability/logging.py` emits structured JSON logs — ship stdout to
   Log Analytics via the Container Insights agent.
2. `observability/tracing.py` creates spans per agent/tool call with an
   in-memory exporter offline; in production, attach the OTel Python SDK's
   `OTLPSpanExporter` (endpoint = the Application Insights connection
   string) — no code changes in the agents, only the exporter.
3. `observability/costs.py` token/latency/cost records become custom
   metrics (`track_metric`) for per-agent cost dashboards.
4. `observability/incidents.py` detection/response/false-positive metrics
   feed workbooks for the "beyond basic MTTR" measurement discipline
   (see `docs/soc-alignment.md`).
