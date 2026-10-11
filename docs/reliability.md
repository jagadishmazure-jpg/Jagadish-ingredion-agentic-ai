# Reliability Strategy

> **Disclaimer.** Independent portfolio demo; all data synthetic; not
> affiliated with Ingredion Incorporated.

How the agent service stays up, what breaks gracefully, and what fails
closed. Three layers: service (app), Kubernetes, Azure (Terraform).

## SLOs (demo targets)

| Signal | Target (30d) | Notes |
|---|---|---|
| API availability (`/api/health` 2xx) | 99.5% | Probes every 10s |
| Reformulation p95 latency (offline) | < 120s | Deterministic fake path |
| Reformulation p95 latency (live) | < 300s | Depends on Azure OpenAI |
| Successful non-degraded responses | 99% of 2xx | Degraded still counts as served |

These are demo targets, not contractual SLAs. Tune `SERVICE_*` env vars
(see below) before any real load.

## Service layer (`ingredion_ai/service/`)

| Mechanism | Where | Behavior |
|---|---|---|
| Retry + exponential backoff + jitter | `reliability.retry_sync` | Transient errors (timeouts, connection errors) retried; full jitter on the sleep |
| Circuit breaker | `reliability.live_llm_breaker` (reuses `harness.CircuitBreaker`) | 3 consecutive live-LLM failures → fail fast for 60s instead of hammering |
| Graceful degradation | `app._run_resilient` | Live LLM unreachable → automatic fallback to the offline fake client; response carries `degraded: true` + `X-Service-Degraded: true` header |
| Request timeout | `SERVICE_REQUEST_TIMEOUT_S` (default 300) | Slow runs → 504. Caveat: the worker thread keeps running; the client just stops waiting |
| Per-client rate limiting | `reliability.rate_limiter` (`SERVICE_RATE_LIMIT_PER_MIN`, default 60) | Over quota → 429 + `Retry-After` |
| Idempotency keys | `reliability.IdempotencyStore`, `Idempotency-Key` header | Replays return the stored response (`X-Idempotent-Replay: true`) without re-executing; 1h TTL |
| Auth | `interop/auth.py` | Missing/forged/expired token → 401; wrong scope → 403 (fail closed) |
| Live-mode config check | `app._LiveConfigError` | `live=true` without Azure OpenAI env → 503 (fail, don't silently degrade — it's a config bug, not an outage) |

## Kubernetes layer (`infra/k8s/`)

| Choice | Why |
|---|---|
| `replicas: 2` (min) | No single point of failure at the pod level |
| Pod anti-affinity (preferred, hostname) | Spread replicas across nodes; with zonal node pools, across zones |
| PodDisruptionBudget (`minAvailable: 1`) | Survive voluntary disruptions (upgrades, drains) |
| HPA 2–6 replicas, CPU 70% | Absorb traffic spikes |
| Liveness + readiness probes on `/api/health` | Unhealthy pods are restarted / removed from service |
| `runAsNonRoot`, `seccompProfile: RuntimeDefault` | Least-privilege pod security |
| Resource requests/limits (250m–2 CPU, 512Mi–2Gi) | Scheduling guarantees + noisy-neighbor protection |

## Azure layer (`infra/terraform/`)

| Choice | Why |
|---|---|
| AKS node pool across availability zones (`aks_availability_zones`) | Zone outage ≠ cluster outage |
| ACR `admin_enabled = false` | No long-lived registry passwords; kubelet uses `AcrPull` RBAC |
| Key Vault RBAC-only (no access policies) | Auditable, least-privilege secret access |
| Workload identity (federated credential) | Pods authenticate to Azure with short-lived tokens; no keys to rotate or leak |
| Azure OpenAI retry/fallback note | The model deployment is treated as fallible (see Service layer); production would add a second regional deployment |

## Failure modes

| Failure | Detection | Mitigation | Outcome |
|---|---|---|---|
| Azure OpenAI timeout / 5xx | Retry + breaker | Backoff+jitter retries → breaker → offline fallback | **Degrades gracefully** (flagged) |
| Azure OpenAI misconfigured (no env) | Startup of live call | Immediate 503 | **Fails closed** (config bug) |
| Key Vault outage | Pod start / secret rotation | Pods already running keep serving (offline needs no secrets); new pods fail to start | **Fails closed** for new pods; running pods unaffected |
| AKS node failure | K8s probes | Anti-affinity + PDB + HPA reschedule | **Degrades gracefully** (brief capacity dip) |
| AZ outage | K8s + Azure | Zonal node pool + anti-affinity | **Degrades gracefully** |
| ACR outage | Image pull | Existing pods keep running; new pulls fail | **Fails closed** for deploys only |
| Caller without token / wrong scope | Auth middleware | 401 / 403 | **Fails closed** |
| Rate-limit breach | Rate limiter | 429 + `Retry-After` | **Fails closed** (protects the service) |
| Duplicate POST (client retry) | Idempotency-Key | Stored replay, no re-execution | **Safe retry** |
| Request exceeds timeout | `asyncio.wait_for` | 504 to client | **Fails closed** for that request |

**Rule of thumb:** infrastructure and auth failures fail closed (loud,
safe); *model* failures degrade gracefully (the demo's value is the
deterministic offline pipeline — an LLM outage shouldn't take down the
API that serves it).

## What to watch (App Insights)

- `X-Service-Degraded` response rate (spike = LLM trouble)
- 429 rate per client (abuse or misconfigured caller)
- 503 rate on `live=true` (config drift)
- p95 latency of `/api/reformulate` by mode
- Circuit-breaker state transitions (log when it opens)
