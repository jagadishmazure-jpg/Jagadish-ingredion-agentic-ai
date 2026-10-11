# Monitoring

## Metrics endpoint

`GET /metrics` (public, standard Prometheus scrape target) exposes
Prometheus text format from `ingredion_ai/service/metrics.py` (stdlib
only, no client library):

| Metric | Type | Labels |
|---|---|---|
| `agent_service_http_requests_total` | counter | method, route, status |
| `agent_service_http_request_duration_seconds_{count,sum}` | summary | — |
| `agent_service_agent_runs_total` | counter | agent |
| `agent_service_live_fallback_total` | counter | — |
| `agent_service_errors_total` | counter | route |

Route templates are normalized (`/api/agents/{agent}/run`) to keep
cardinality low. In AKS, scrape via a Prometheus `ServiceMonitor` or
the Azure Monitor managed-Prometheus addon; the demo also ships example
alert rules (`infra/monitoring/prometheus-rules.yaml`) and a Grafana
dashboard (`infra/monitoring/grafana-dashboard.json`).

## SLIs / SLOs (demo starting points)

| SLI | SLO | Alert |
|---|---|---|
| Availability: 1 − 5xx rate | 99.5% / 30d | `HighErrorRate` (>5% for 5m) |
| Latency: avg request duration | < 5s avg | `HighLatency` (>5s for 10m) |
| Freshness: agent runs occurring | > 0 / 30m in prod hours | `NoAgentRuns` |
| Degradation: live→offline fallbacks | < 10 / 15m | `LiveFallbackStorm` |

Tune from real traffic before committing to these. See
`docs/reliability.md` for the failure-modes table these SLOs guard.

## Burn-rate alerting

For production, convert the demo threshold alerts to multi-window
burn-rate alerts (e.g., 14.4× burn over 1h + 6× over 6h pages; 6× over
1h + 3× over 6h tickets), following the standard SRE workbook pattern.
The error-budget burn is computed from `agent_service_errors_total /
agent_service_http_requests_total` against the 99.5% SLO.

## Application Insights query examples

With the Terraform-provisioned App Insights (see `infra/terraform`),
the same signals are queryable in KQL:

```kusto
// 5xx rate by route, last hour
requests
| where timestamp > ago(1h)
| summarize errorRate = countif(success == false) * 100.0 / count() by operation_Name
| order by errorRate desc

// p95 dependency latency (Azure OpenAI calls), last 6h
dependencies
| where timestamp > ago(6h) and target has "openai"
| summarize p95 = percentile(duration, 95) by bin(timestamp, 15m)

// traces for degraded (offline-fallback) runs
traces
| where timestamp > ago(24h) and message has "degraded"
| project timestamp, message, customDimensions
```

Correlate with the Prometheus alerts: the `LiveFallbackStorm` alert
should line up with Azure OpenAI `dependencies` failures or throttling
(`429`) in App Insights.
