"""Event Hubs abstraction: high-volume telemetry streaming (demo).

Run metrics (latency, token usage, guardrail flags, degradation) stream
through here in batches toward dashboards — the hot path that would
drown a request/response API.

:class:`InMemoryTelemetryProducer` buffers events and flushes on batch
size or explicit ``flush()``. Production swap (one line): wrap
``azure-eventhub.EventHubProducerClient`` and call
``send_batch`` — the buffered dicts are already JSON-serializable.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunMetric:
    """One telemetry point for an agent run."""

    metric: str  # e.g. "run.latency_ms", "run.tokens", "run.guardrail_flags"
    value: float
    run_id: str
    agent: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    ts: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TelemetryProducer(ABC):
    """Batched telemetry sink (Event Hubs in production)."""

    @abstractmethod
    def record(self, metric: RunMetric) -> None: ...

    @abstractmethod
    def flush(self) -> List[Dict[str, Any]]:
        """Ship buffered events; return what was shipped."""


class InMemoryTelemetryProducer(TelemetryProducer):
    """Offline Event Hubs fake with batch flushing."""

    def __init__(self, batch_size: int = 50) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self.batch_size = batch_size
        self._buffer: List[Dict[str, Any]] = []
        self.shipped_batches: List[List[Dict[str, Any]]] = []

    def record(self, metric: RunMetric) -> None:
        self._buffer.append(metric.to_dict())
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> List[Dict[str, Any]]:
        batch = self._buffer
        self._buffer = []
        if batch:
            self.shipped_batches.append(batch)
        return batch

    @property
    def buffered(self) -> int:
        return len(self._buffer)

    @property
    def total_shipped(self) -> int:
        return sum(len(b) for b in self.shipped_batches)


def metrics_for_run(
    *,
    run_id: str,
    agent: str,
    latency_ms: float,
    tokens: int = 0,
    guardrail_flags: int = 0,
    degraded: bool = False,
) -> List[RunMetric]:
    """Build the standard metric set for one agent run."""
    return [
        RunMetric("run.latency_ms", float(latency_ms), run_id, agent),
        RunMetric("run.tokens", float(tokens), run_id, agent),
        RunMetric("run.guardrail_flags", float(guardrail_flags), run_id, agent),
        RunMetric("run.degraded", 1.0 if degraded else 0.0, run_id, agent),
    ]
