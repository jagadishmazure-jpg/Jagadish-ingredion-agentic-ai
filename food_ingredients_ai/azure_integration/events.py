"""CloudEvents v1.0 schemas for agent lifecycle events.

Every cross-service signal in this project (Service Bus jobs, Event Grid
domain events, Function triggers, Logic Apps callbacks) is expressed as a
CloudEvent so producers and consumers stay decoupled.

Production: publish these shapes with
``azure-eventgrid.EventGridPublisherClient.send(...)`` — the payload is
already spec-shaped. Swap the publisher with
:func:`set_lifecycle_publisher` (one line).

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

#: CloudEvents spec version we emit.
SPECVERSION = "1.0"

#: Event source for events produced by this platform.
DEFAULT_SOURCE = "demo.foodingredients.agents/service"

#: Lifecycle event types (reverse-DNS, versioned by convention).
RUN_STARTED = "demo.foodingredients.agents.run.started.v1"
RUN_COMPLETED = "demo.foodingredients.agents.run.completed.v1"
RUN_FAILED = "demo.foodingredients.agents.run.failed.v1"
APPROVAL_REQUESTED = "demo.foodingredients.agents.approval.requested.v1"
APPROVAL_GRANTED = "demo.foodingredients.agents.approval.granted.v1"
APPROVAL_DENIED = "demo.foodingredients.agents.approval.denied.v1"
ANOMALY_FLAGGED = "demo.foodingredients.agents.anomaly.flagged.v1"
CLAIM_VALIDATED = "demo.foodingredients.agents.claim.validated.v1"
REFORMULATION_COMPLETED = "demo.foodingredients.agents.reformulation.completed.v1"

#: Every type this package knows how to validate.
KNOWN_TYPES = {
    RUN_STARTED,
    RUN_COMPLETED,
    RUN_FAILED,
    APPROVAL_REQUESTED,
    APPROVAL_GRANTED,
    APPROVAL_DENIED,
    ANOMALY_FLAGGED,
    CLAIM_VALIDATED,
    REFORMULATION_COMPLETED,
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CloudEvent:
    """A CloudEvents v1.0 structured-mode event."""

    id: str
    source: str
    specversion: str
    type: str
    time: str
    subject: str
    datacontenttype: str = "application/json"
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CloudEvent":
        return cls(
            id=str(payload.get("id", "")),
            source=str(payload.get("source", "")),
            specversion=str(payload.get("specversion", "")),
            type=str(payload.get("type", "")),
            time=str(payload.get("time", "")),
            subject=str(payload.get("subject", "")),
            datacontenttype=str(payload.get("datacontenttype", "application/json")),
            data=dict(payload.get("data") or {}),
        )


def make_event(
    event_type: str,
    *,
    subject: str,
    data: Optional[Dict[str, Any]] = None,
    source: str = DEFAULT_SOURCE,
    event_id: Optional[str] = None,
) -> CloudEvent:
    """Build a spec-shaped CloudEvent."""
    return CloudEvent(
        id=event_id or f"evt-{uuid.uuid4().hex[:16]}",
        source=source,
        specversion=SPECVERSION,
        type=event_type,
        time=_utcnow(),
        subject=subject,
        data=dict(data or {}),
    )


class EventValidationError(Exception):
    """A CloudEvent failed schema validation."""


def validate_event(payload: Dict[str, Any]) -> CloudEvent:
    """Validate a CloudEvents dict; raise :class:`EventValidationError`."""
    event = CloudEvent.from_dict(payload)
    missing = [
        name
        for name in ("id", "source", "specversion", "type", "time", "subject")
        if not getattr(event, name)
    ]
    if missing:
        raise EventValidationError(f"missing required attributes: {missing}")
    if event.specversion != SPECVERSION:
        raise EventValidationError(
            f"unsupported specversion {event.specversion!r} (want {SPECVERSION!r})"
        )
    if event.type not in KNOWN_TYPES:
        raise EventValidationError(f"unknown event type {event.type!r}")
    if not isinstance(event.data, dict):
        raise EventValidationError("data must be a JSON object")
    return event


class LifecyclePublisher:
    """Abstract sink for lifecycle events (Event Grid in production)."""

    def publish(self, event: CloudEvent) -> None:
        raise NotImplementedError


class InMemoryLifecyclePublisher(LifecyclePublisher):
    """Offline publisher: records events for tests/demos."""

    def __init__(self) -> None:
        self.events: List[CloudEvent] = []

    def publish(self, event: CloudEvent) -> None:
        self.events.append(event)

    def of_type(self, event_type: str) -> List[CloudEvent]:
        return [e for e in self.events if e.type == event_type]


_publisher: LifecyclePublisher = InMemoryLifecyclePublisher()


def get_lifecycle_publisher() -> LifecyclePublisher:
    """Return the active lifecycle publisher (in-memory by default)."""
    return _publisher


def set_lifecycle_publisher(publisher: LifecyclePublisher) -> None:
    """Swap the publisher — the one-line production hook.

    Production: pass an adapter wrapping
    ``azure-eventgrid.EventGridPublisherClient``.
    """
    global _publisher
    _publisher = publisher


def emit_lifecycle_event(
    event_type: str, *, subject: str, data: Optional[Dict[str, Any]] = None
) -> Optional[CloudEvent]:
    """Build + publish a lifecycle event. Returns None on publisher error."""
    try:
        event = make_event(event_type, subject=subject, data=data)
        get_lifecycle_publisher().publish(event)
        return event
    except Exception:  # noqa: BLE001 - lifecycle events are best-effort
        return None


#: Callback type for lifecycle subscribers (used by tests/workers).
EventHandler = Callable[[CloudEvent], None]
