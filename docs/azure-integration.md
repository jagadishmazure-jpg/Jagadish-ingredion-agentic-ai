# Azure Integration Services — Opportunities in This Project

How the Azure integration surface (Functions, Logic Apps, Service Bus,
Event Grid, Event Hubs) plugs into the agentic platform — and where each
service earns its keep. Everything below runs offline against in-memory
fakes; the production swaps are one-liners documented per module.

## Opportunities matrix

| Azure service | Concrete use case here | Pattern | Module |
|---|---|---|---|
| Service Bus queue | Reformulation jobs decouple the API from long agent runs; workers scale independently | Job queue + DLQ | `azure_integration/servicebus.py` |
| Service Bus topic | Job results fan out to UI push, analytics sink, audit archiver | Pub/sub | `azure_integration/servicebus.py` |
| Event Grid | `reformulation.completed`, `claim.validated`, `anomaly.flagged` trigger Logic Apps, webhooks, partner systems | Domain-event fan-out, subject filtering | `azure_integration/eventgrid.py` |
| Event Hubs | Stream run metrics (latency, tokens, guardrail flags) at volume to dashboards | Batched telemetry producer | `azure_integration/eventhub.py` |
| Functions (HTTP) | `POST /jobs` enqueue endpoint, autoscaled to zero when idle | HTTP trigger | `azure_integration/functions.py` |
| Functions (SB trigger) | Each queued job runs the agent workflow in isolation with platform retries → DLQ | Queue trigger | `azure_integration/functions.py` |
| Functions (timer) | Weekly ESG report generation, nightly anomaly scans | Timer trigger (cron) | `azure_integration/functions.py` |
| Logic Apps | Human-approval workflow: reformulation → approval card (Teams/email) → callback → writeback | Webhook + callback | `azure_integration/logicapps.py`, `infra/logicapps/reformulation-approval.json` |

## Event flow (text diagram)

```text
Client ──POST /api/reformulate──▶ FastAPI service
                                      │ ① lifecycle: run.started (Event Grid shape)
                                      ▼
                              ┌─ inline (sync demo)
                              │   8-stage pipeline ──▶ run.completed ──▶ Event Grid
                              │                                              │
                              │                                    ┌────────┼────────┐
                              │                              Logic Apps  Webhooks  Analytics
                              │
                              └─ queued (production pattern)
                                  Service Bus: reformulation-jobs
                                      │  (Functions SB trigger / worker)
                                      ▼
                                  JobProcessor → workflow → results topic
                                      │                        ├─ ui-updates subscription
                                      │                        └─ analytics-sink subscription
                                      ▼ (poison after 3 deliveries)
                                  DLQ: reformulation-jobs-dlq

Telemetry (always): run metrics ──batch──▶ Event Hubs: run-telemetry ──▶ dashboards

Approvals: agent → approval.requested ──▶ Logic App ──▶ Teams card
           Logic App ──HMAC callback──▶ /api callback receiver ──▶ resume/halt
```

## Production swap guide

| Offline (now) | Production (one line) |
|---|---|
| `InMemoryMessageBus` | `azure-servicebus.ServiceBusClient` via `DefaultAzureCredential`; queue/topic names unchanged |
| `InMemoryDomainEventPublisher` | `azure-eventgrid.EventGridPublisherClient` → `send(CloudEvent(...))`; payloads already spec-shaped |
| `InMemoryTelemetryProducer` | `azure-eventhub.EventHubProducerClient` → `send_batch` |
| `set_lifecycle_publisher(...)` | Pass an Event Grid-backed publisher; service pipeline needs no other change |
| Function handlers | `pip install azure-functions`; wrap dict in/out with `func.HttpRequest` / `func.ServiceBusMessage`; `func azure functionapp publish` |
| Logic App JSON | `az logic workflow update --definition @infra/logicapps/reformulation-approval.json` |
| Callback HMAC secret | Read from Key Vault; rotate on a schedule |

Auth in production: managed identity everywhere (Function App → Service Bus
Data Receiver/Sender, Event Hubs Data Sender — see `integration.tf`);
no connection strings in code or config.

## Cost notes (demo-cheap defaults)

- Service Bus **Basic**: queues + topics; move to **Premium** only for VNet isolation, sessions, or >80 GB.
- Event Grid: pay-per-operation; domain events are low-volume by design.
- Event Hubs **Basic** (1 TU): fine for demo telemetry; **Standard** adds Capture + retention for prod analytics.
- Functions **Consumption (Y1)**: pay-per-execution; the SB trigger scales workers with queue depth.
- Logic Apps **Consumption**: pay-per-action; the approval workflow sleeps (Wait) cheaply between steps.

## What is deliberately *not* here

Durable Functions orchestration (the 8-stage pipeline already covers the
orchestration story), API Management policies for the integration endpoints
(see `docs/stack-alignment.md`), and private-endpoint networking (documented
as the production path in `docs/deployment-runbook.md`).
