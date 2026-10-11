# Analytics

> All data is synthetic demo data. Nothing here is real market or business data.

## What's measured

`ingredion_ai/analytics/` reduces every reformulation run to a `RunSummary`
(`aggregates.py::extract_run_summary`) and aggregates across runs:

| Metric | Source |
|---|---|
| Reformulation counts (total, by scenario) | run log |
| Avg / min / max cost per kg | `estimate_pricing` blackboard |
| Avg texture match %, shelf-life days | `predict_texture_shelf_life` blackboard |
| Claim coverage % (valid / total target claims) | `validate_claims` blackboard |
| Avg cycle time (weeks) | `cycle_time.estimate_cycle_time` recomputed from formula + substitutions |
| Substitutions / removals | `suggest_substitutes` blackboard |

Served at `GET /api/analytics/summary` (requires the `analytics:read`
scope). The demo UI renders cost-vs-peers bars, shelf-life bars, a claim
coverage donut, and proactive flags after each run (dependency-free SVG).

## Benchmarking methodology

`benchmarking.py::PeerBenchmark` compares a run's metrics against
**deterministic synthetic peer distributions** (seeded PRNG, 500 samples
per metric, fixed means/stddevs in `PEER_METRICS`). Percentiles are
computed by linear interpolation; the verdict is:

- `better than peers` — at/above p50 in the favorable direction
- `in line with peers` — between p50 and p90
- `worse than peers` — beyond p90

**Caveats (read before quoting any number):**
- Peer distributions are invented constants, not market research.
- Every benchmark result carries `data_label: "synthetic demo data — not
  real market benchmarks"`; the UI repeats the label next to each chart.
- Cost/shelf-life/texture numbers come from demo heuristics, not food science.

## Proactive suggestions

`suggestions.py::flag_anomalies` mirrors the embedded-analytics pattern of
in-workflow nudges. Demo thresholds (`docs` keep them explicit):

| Flag | Rule | Severity |
|---|---|---|
| `COST_SPIKE` | cost/kg worse than synthetic peer p90 | warning |
| `SHELF_LIFE_RISK` | predictor risk flags present (critical if < 7 days) | warning/critical |
| `CLAIM_GAP` | any target claim invalid | warning |
| `LOW_TEXTURE` | texture match < 85% | warning |

Flags are returned by the analytics endpoint and rendered in the UI.
Tune thresholds per category before any production use.

## Trends

`trends.py` provides `moving_average` and `delta_vs_previous` over
run-history series for dashboard sparklines and week-over-week deltas.
