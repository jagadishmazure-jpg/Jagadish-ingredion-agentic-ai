"""Cost and latency tracking per agent run (demo).

Token counts are estimated deterministically from text length so offline
runs stay reproducible; live runs can override with real usage. Costs use
configurable demo per-1k-token rates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List

# Demo rates (USD per 1k tokens) — placeholders, not real Azure pricing.
DEMO_INPUT_RATE_PER_1K = 0.005
DEMO_OUTPUT_RATE_PER_1K = 0.015
CHARS_PER_TOKEN = 4  # rough heuristic, deterministic

#: Configurable per-model/per-deployment price table (USD per 1k tokens).
#: "demo-*" names are placeholders; swap in real Azure OpenAI / Foundry
#: deployment prices for production (see docs/finops.md).
MODEL_PRICE_TABLE: Dict[str, Dict[str, float]] = {
    "demo-cheap": {"input_per_1k": 0.001, "output_per_1k": 0.003},
    "demo-standard": {
        "input_per_1k": DEMO_INPUT_RATE_PER_1K,
        "output_per_1k": DEMO_OUTPUT_RATE_PER_1K,
    },
    "demo-premium": {"input_per_1k": 0.020, "output_per_1k": 0.060},
}


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate from character length (demo)."""
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class RunRecord:
    agent: str
    operation: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str = "demo-standard"


class CostTracker:
    """Record per-operation latency/token/cost; summarize per agent.

    *price_table* maps model/deployment names to per-1k-token rates;
    *default_model* selects the table entry used when a record does not
    name one. Defaults preserve the original demo rates.
    """

    def __init__(
        self,
        input_rate_per_1k: float = DEMO_INPUT_RATE_PER_1K,
        output_rate_per_1k: float = DEMO_OUTPUT_RATE_PER_1K,
        price_table: Dict[str, Dict[str, float]] | None = None,
        default_model: str = "demo-standard",
    ) -> None:
        self.input_rate = input_rate_per_1k
        self.output_rate = output_rate_per_1k
        self.price_table = price_table if price_table is not None else dict(MODEL_PRICE_TABLE)
        self.default_model = default_model
        self.records: List[RunRecord] = []

    def _rates_for(self, model: str) -> tuple:
        entry = self.price_table.get(model)
        if entry is None:
            raise KeyError(f"unknown model in price table: {model!r}")
        return entry["input_per_1k"], entry["output_per_1k"]

    def record(
        self,
        agent: str,
        operation: str,
        latency_ms: float,
        input_text: str = "",
        output_text: str = "",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        model: str | None = None,
    ) -> RunRecord:
        """Record one operation; token counts estimated unless given.

        *model* selects the price-table entry (defaults to the tracker's
        default model).
        """
        in_tok = input_tokens if input_tokens is not None else estimate_tokens(input_text)
        out_tok = output_tokens if output_tokens is not None else estimate_tokens(output_text)
        model_name = model or self.default_model
        in_rate, out_rate = self._rates_for(model_name)
        cost = round(in_tok / 1000 * in_rate + out_tok / 1000 * out_rate, 6)
        record = RunRecord(
            agent=agent,
            operation=operation,
            latency_ms=round(latency_ms, 3),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            model=model_name,
        )
        self.records.append(record)
        return record

    def timed(self, agent: str, operation: str):
        """Context manager that times a block and records it (demo texts empty)."""
        tracker = self

        class _Timer:
            def __enter__(self) -> "_Timer":
                self._start = time.perf_counter()
                return self

            def __exit__(self, *exc: Any) -> None:
                ms = (time.perf_counter() - self._start) * 1000
                tracker.record(agent, operation, ms)

        return _Timer()

    def summary(self) -> Dict[str, Dict[str, Any]]:
        """Aggregate totals per agent."""
        agg: Dict[str, Dict[str, Any]] = {}
        for r in self.records:
            entry = agg.setdefault(
                r.agent,
                {"operations": 0, "latency_ms": 0.0, "input_tokens": 0,
                 "output_tokens": 0, "cost_usd": 0.0},
            )
            entry["operations"] += 1
            entry["latency_ms"] = round(entry["latency_ms"] + r.latency_ms, 3)
            entry["input_tokens"] += r.input_tokens
            entry["output_tokens"] += r.output_tokens
            entry["cost_usd"] = round(entry["cost_usd"] + r.cost_usd, 6)
        return agg

    def total_cost_usd(self) -> float:
        return round(sum(r.cost_usd for r in self.records), 6)


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------


@dataclass
class BudgetAlert:
    level: str  # "warning" | "breached"
    message: str
    spent_usd: float
    budget_usd: float


class BudgetTracker:
    """Track spend against a budget; emit alerts at thresholds.

    *warn_at* (default 0.8) fires a warning alert once spend crosses 80%
    of the budget; crossing 100% fires a breach alert. Alerts fire once
    per level until :meth:`reset_alerts` is called.
    """

    def __init__(self, budget_usd: float, warn_at: float = 0.8) -> None:
        if budget_usd <= 0:
            raise ValueError("budget_usd must be positive")
        if not 0 < warn_at < 1:
            raise ValueError("warn_at must be between 0 and 1")
        self.budget_usd = budget_usd
        self.warn_at = warn_at
        self.spent_usd = 0.0
        self.alerts: List[BudgetAlert] = []
        self._warned = False
        self._breached = False

    def add(self, cost_usd: float) -> List[BudgetAlert]:
        """Add spend; return any newly fired alerts."""
        self.spent_usd = round(self.spent_usd + cost_usd, 6)
        fired: List[BudgetAlert] = []
        if not self._warned and self.spent_usd >= self.budget_usd * self.warn_at:
            self._warned = True
            alert = BudgetAlert(
                level="warning",
                message=(
                    f"spend ${self.spent_usd} reached "
                    f"{int(self.warn_at * 100)}% of ${self.budget_usd} budget"
                ),
                spent_usd=self.spent_usd,
                budget_usd=self.budget_usd,
            )
            self.alerts.append(alert)
            fired.append(alert)
        if not self._breached and self.spent_usd >= self.budget_usd:
            self._breached = True
            alert = BudgetAlert(
                level="breached",
                message=(
                    f"spend ${self.spent_usd} breached ${self.budget_usd} budget"
                ),
                spent_usd=self.spent_usd,
                budget_usd=self.budget_usd,
            )
            self.alerts.append(alert)
            fired.append(alert)
        return fired

    def status(self) -> Dict[str, Any]:
        pct = round(self.spent_usd / self.budget_usd * 100, 1)
        state = "breached" if self._breached else "warning" if self._warned else "ok"
        return {
            "spent_usd": self.spent_usd,
            "budget_usd": self.budget_usd,
            "pct_used": pct,
            "state": state,
            "alerts": [a.__dict__ for a in self.alerts],
        }

    def reset_alerts(self) -> None:
        self.alerts.clear()
        self._warned = False
        self._breached = False


# ---------------------------------------------------------------------------
# Spend forecasting
# ---------------------------------------------------------------------------


def forecast_spend(
    costs: List[float],
    days_ahead: int = 30,
    window: int = 7,
) -> Dict[str, Any]:
    """Project future spend from a chronological list of per-run costs.

    Method (deterministic, stdlib only): take the mean of the last
    ``window`` runs as the daily average, fit a least-squares trend line
    over the full history for the daily growth slope, then project the
    average daily cost over the horizon as ``daily_average + slope *
    days_ahead / 2`` (the midpoint of the linear trend).

    Returns ``{"projected_spend", "daily_average", "trend",
    "trend_pct_per_day", "confidence_note"}`` where ``trend`` is one of
    ``"growing"`` / ``"stable"`` / ``"declining"``. Empty history yields
    zeros with an "insufficient data" note — never an exception.
    """
    result: Dict[str, Any] = {
        "projected_spend": 0.0,
        "daily_average": 0.0,
        "trend": "stable",
        "trend_pct_per_day": 0.0,
        "confidence_note": "no run history — cannot forecast",
    }
    n = len(costs)
    if n == 0 or days_ahead <= 0:
        return result

    recent = costs[-window:] if window > 0 else costs
    daily_average = sum(recent) / len(recent)

    # Least-squares slope of cost vs run index (0..n-1).
    slope = 0.0
    if n > 1:
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(costs) / n
        denom = sum((x - mean_x) ** 2 for x in xs)
        if denom:
            slope = sum(
                (x - mean_x) * (y - mean_y) for x, y in zip(xs, costs)
            ) / denom

    trend_pct = (slope / daily_average * 100) if daily_average else 0.0
    if trend_pct > 1.0:
        trend = "growing"
    elif trend_pct < -1.0:
        trend = "declining"
    else:
        trend = "stable"

    projected_daily = max(0.0, daily_average + slope * days_ahead / 2)
    projected_spend = round(projected_daily * days_ahead, 2)

    if n < 7:
        confidence = (
            f"low — only {n} data point(s); treat the projection as directional"
        )
    elif n < 30:
        confidence = "medium — under 30 data points; re-run weekly"
    else:
        confidence = "high — 30+ data points of history"
    if abs(trend_pct) > 10.0:
        confidence += "; steep trend — validate the driver before budgeting"

    result.update(
        {
            "projected_spend": projected_spend,
            "daily_average": round(daily_average, 6),
            "trend": trend,
            "trend_pct_per_day": round(trend_pct, 2),
            "confidence_note": confidence,
        }
    )
    return result


# ---------------------------------------------------------------------------
# Optimization recommendations
# ---------------------------------------------------------------------------

#: Heuristic thresholds for the recommendation rules (demo values).
AVG_OUTPUT_TOKENS_HIGH = 1500
SMALL_TASK_TOKENS = 400


@dataclass
class OptimizationRecommendation:
    code: str
    message: str
    estimated_saving_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "estimated_saving_pct": self.estimated_saving_pct,
        }


def recommend_optimizations(
    tracker: CostTracker,
    price_table: Dict[str, Dict[str, float]] | None = None,
) -> List[OptimizationRecommendation]:
    """Rule-based cost-optimization recommendations from run history.

    Rules (demo heuristics):
    - high average output tokens → enable response caching / shorter prompts
    - premium-model records with small token counts → route to a cheaper deployment
    - repeated RAG retrieval operations → cache RAG results
    - many tiny operations → batch where safe
    """
    table = price_table if price_table is not None else tracker.price_table
    recs: List[OptimizationRecommendation] = []
    records = tracker.records
    if not records:
        return recs

    avg_out = sum(r.output_tokens for r in records) / len(records)
    if avg_out > AVG_OUTPUT_TOKENS_HIGH:
        recs.append(
            OptimizationRecommendation(
                code="CACHE_RESPONSES",
                message=(
                    f"average output {avg_out:.0f} tokens/run exceeds "
                    f"{AVG_OUTPUT_TOKENS_HIGH}; cache repeated responses and "
                    "tighten agent instructions"
                ),
                estimated_saving_pct=25.0,
            )
        )

    models = sorted({r.model for r in records})
    cheap = min(
        table.items(), key=lambda kv: kv[1]["output_per_1k"]
    )[0]
    premiumish = [
        r for r in records
        if r.model != cheap and r.input_tokens + r.output_tokens < SMALL_TASK_TOKENS
    ]
    if premiumish and len(models) > 1:
        recs.append(
            OptimizationRecommendation(
                code="DOWNSHIFT_MODEL",
                message=(
                    f"{len(premiumish)} small task(s) ran on pricier models; "
                    f"route sub-{SMALL_TASK_TOKENS}-token tasks to '{cheap}'"
                ),
                estimated_saving_pct=40.0,
            )
        )

    rag_ops = [r for r in records if "rag" in r.operation.lower()]
    if len(rag_ops) >= 3:
        recs.append(
            OptimizationRecommendation(
                code="CACHE_RAG",
                message=(
                    f"{len(rag_ops)} RAG retrievals recorded; cache retrieval "
                    "results per glossary version"
                ),
                estimated_saving_pct=15.0,
            )
        )

    tiny = [r for r in records if r.input_tokens + r.output_tokens < 100]
    if len(tiny) >= 5:
        recs.append(
            OptimizationRecommendation(
                code="BATCH_SMALL_OPS",
                message=(
                    f"{len(tiny)} tiny operations recorded; batch independent "
                    "tool calls where safe"
                ),
                estimated_saving_pct=10.0,
            )
        )
    return recs
