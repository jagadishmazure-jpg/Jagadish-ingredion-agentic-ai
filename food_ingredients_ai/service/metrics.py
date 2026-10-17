"""Minimal Prometheus metrics registry (stdlib only, no client library).

Exposes counters and duration summaries rendered in the Prometheus text
exposition format for ``GET /metrics``. Thread-safe for the demo's
concurrency level.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Tuple


def _labels_str(labels: Dict[str, str]) -> str:
    if not labels:
        return ""
    parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return "{" + parts + "}"


#: Counter key: (metric name, sorted label tuple).
_CounterKey = Tuple[str, Tuple[Tuple[str, str], ...]]


class MetricsRegistry:
    """Counters + duration summaries with Prometheus text rendering."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._declared: Dict[str, Tuple[str, str]] = {}
        self._counters: Dict[_CounterKey, float] = {}
        self._durations: Dict[str, List[float]] = {}

    def inc(self, name: str, labels: Dict[str, str] | None = None, value: float = 1.0) -> None:
        """Increment a counter."""
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def observe_duration(self, name: str, seconds: float) -> None:
        """Record one duration observation (seconds)."""
        with self._lock:
            self._durations.setdefault(name, []).append(seconds)

    def declare(self, name: str, help_text: str, type_: str = "counter") -> None:
        """Pre-declare metric metadata so HELP/TYPE render even with no samples."""
        with self._lock:
            self._declared[name] = (help_text, type_)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._durations.clear()

    def render(self) -> str:
        """Render the Prometheus text exposition format."""
        lines: List[str] = []
        seen_help: set = set()
        with self._lock:
            declared = dict(self._declared)
            counters = dict(self._counters)
            durations = {k: list(v) for k, v in self._durations.items()}
        for name, (help_text, type_) in sorted(declared.items()):
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {type_}")
            seen_help.add(name)
        for (name, label_items), value in sorted(counters.items()):
            if name not in seen_help:
                lines.append(f"# HELP {name} Counter incremented by the agent service.")
                lines.append(f"# TYPE {name} counter")
                seen_help.add(name)
            lines.append(f"{name}{_labels_str(dict(label_items))} {value:g}")
        for name, observations in sorted(durations.items()):
            count = len(observations)
            total = sum(observations)
            base = name
            for suffix, typ, val in (
                ("_count", "counter", count),
                ("_sum", "counter", f"{total:.6f}"),
            ):
                full = base + suffix
                if full not in seen_help:
                    lines.append(
                        f"# HELP {full} Duration observations for {base}."
                    )
                    lines.append(f"# TYPE {full} {typ}")
                    seen_help.add(full)
                lines.append(f"{full} {val}")
        lines.append("# EOF")
        return "\n".join(lines) + "\n"


#: Process-wide registry used by the service middleware and endpoints.
registry = MetricsRegistry()

# Pre-declared metric metadata (HELP/TYPE render even before first sample).
registry.declare(
    "agent_service_http_requests_total",
    "Total HTTP requests handled by the agent service.",
)
registry.declare(
    "agent_service_http_request_duration_seconds_count",
    "Count of observed HTTP request durations.",
)
registry.declare(
    "agent_service_http_request_duration_seconds_sum",
    "Sum of observed HTTP request durations in seconds.",
)
registry.declare(
    "agent_service_agent_runs_total",
    "Total domain-agent runs executed by the service.",
)
registry.declare(
    "agent_service_live_fallback_total",
    "Total live-LLM failures gracefully degraded to the offline client.",
)
registry.declare(
    "agent_service_errors_total",
    "Total HTTP 5xx responses served.",
)
