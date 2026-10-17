"""Tracing hooks with OpenTelemetry-compatible span output (demo).

Dependency-free: spans are recorded as plain dicts shaped like OTel span
JSON. ``InMemoryExporter`` keeps spans for tests; ``NoOpExporter`` drops
them (default). To ship to Application Insights, export the dicts through
the Azure Monitor OpenTelemetry distro (see docs/governance.md).
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional


class Span:
    """A single timed operation with attributes, events, and status."""

    def __init__(self, name: str, trace_id: Optional[str] = None) -> None:
        self.name = name
        self.trace_id = trace_id or uuid.uuid4().hex
        self.span_id = uuid.uuid4().hex[:16]
        self.start_time = time.perf_counter()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.end_time: Optional[float] = None
        self.attributes: Dict[str, Any] = {}
        self.events: List[Dict[str, Any]] = []
        self.status = "ok"
        self.error: Optional[str] = None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        self.events.append(
            {
                "name": name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "attributes": attributes or {},
            }
        )

    def record_error(self, message: str) -> None:
        self.status = "error"
        self.error = message

    def finish(self) -> None:
        self.end_time = time.perf_counter()

    @property
    def duration_ms(self) -> float:
        end = self.end_time if self.end_time is not None else time.perf_counter()
        return round((end - self.start_time) * 1000, 3)

    def to_otel_dict(self) -> Dict[str, Any]:
        """Span as an OTel-compatible JSON dict (demo mapping)."""
        return {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "name": self.name,
            "startTimeUnixNano": int(self.start_time * 1e9),
            "endTimeUnixNano": int((self.end_time or time.perf_counter()) * 1e9),
            "attributes": dict(self.attributes),
            "events": list(self.events),
            "status": {"code": "ERROR" if self.status == "error" else "OK"},
        }


class NoOpExporter:
    """Exporter that drops spans (default, zero overhead)."""

    def export(self, span: Span) -> None:
        pass


class InMemoryExporter:
    """Exporter that retains spans (tests and offline inspection)."""

    def __init__(self) -> None:
        self.spans: List[Span] = []

    def export(self, span: Span) -> None:
        self.spans.append(span)

    def names(self) -> List[str]:
        return [s.name for s in self.spans]

    def clear(self) -> None:
        self.spans.clear()


class Tracer:
    """Create spans; export on context exit (even on exceptions)."""

    def __init__(self, exporter: Optional[NoOpExporter | InMemoryExporter] = None) -> None:
        self.exporter = exporter or NoOpExporter()

    @contextmanager
    def span(
        self, name: str, attributes: Optional[Dict[str, Any]] = None
    ) -> Iterator[Span]:
        span = Span(name)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:  # noqa: BLE001 - record then re-raise
            span.record_error(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            span.finish()
            self.exporter.export(span)
