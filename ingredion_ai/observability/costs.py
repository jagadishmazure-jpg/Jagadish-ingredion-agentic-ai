"""Cost and latency tracking per agent run (demo).

Token counts are estimated deterministically from text length so offline
runs stay reproducible; live runs can override with real usage. Costs use
configurable demo per-1k-token rates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

# Demo rates (USD per 1k tokens) — placeholders, not real Azure pricing.
DEMO_INPUT_RATE_PER_1K = 0.005
DEMO_OUTPUT_RATE_PER_1K = 0.015
CHARS_PER_TOKEN = 4  # rough heuristic, deterministic


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


class CostTracker:
    """Record per-operation latency/token/cost; summarize per agent."""

    def __init__(
        self,
        input_rate_per_1k: float = DEMO_INPUT_RATE_PER_1K,
        output_rate_per_1k: float = DEMO_OUTPUT_RATE_PER_1K,
    ) -> None:
        self.input_rate = input_rate_per_1k
        self.output_rate = output_rate_per_1k
        self.records: List[RunRecord] = []

    def record(
        self,
        agent: str,
        operation: str,
        latency_ms: float,
        input_text: str = "",
        output_text: str = "",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> RunRecord:
        """Record one operation; token counts estimated unless given."""
        in_tok = input_tokens if input_tokens is not None else estimate_tokens(input_text)
        out_tok = output_tokens if output_tokens is not None else estimate_tokens(output_text)
        cost = round(
            in_tok / 1000 * self.input_rate + out_tok / 1000 * self.output_rate, 6
        )
        record = RunRecord(
            agent=agent,
            operation=operation,
            latency_ms=round(latency_ms, 3),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
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
