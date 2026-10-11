"""Event Grid abstraction: domain-event fan-out (demo).

Downstream subscribers — Logic Apps, webhooks, the analytics store —
subscribe with subject-prefix filters and receive matching domain events.

:class:`InMemoryDomainEventPublisher` is the offline fake. Production swap
(one line): wrap ``azure-eventgrid.EventGridPublisherClient`` and call
``send(CloudEvent(...))`` — :mod:`ingredion_ai.azure_integration.events`
already emits spec-shaped payloads; set it via
:func:`ingredion_ai.azure_integration.events.set_lifecycle_publisher`.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ingredion_ai.azure_integration.events import (
    CloudEvent,
    emit_lifecycle_event,
    make_event,
)

#: Domain event types fanned out on the grid topic.
REFORMULATION_COMPLETED = "com.ingredion.agents.reformulation.completed.v1"
CLAIM_VALIDATED_EVT = "com.ingredion.agents.claim.validated.v1"
ANOMALY_FLAGGED_EVT = "com.ingredion.agents.anomaly.flagged.v1"
APPROVAL_REQUESTED_EVT = "com.ingredion.agents.approval.requested.v1"


@dataclass
class GridSubscription:
    """A subscriber with an optional subject-prefix filter."""

    name: str
    handler: Callable[[CloudEvent], None]
    subject_begins_with: Optional[str] = None

    def matches(self, event: CloudEvent) -> bool:
        return self.subject_begins_with is None or event.subject.startswith(
            self.subject_begins_with
        )


class DomainEventPublisher(ABC):
    """Fan-out publisher (Event Grid topic in production)."""

    @abstractmethod
    def publish(self, event_type: str, subject: str, data: Dict[str, Any]) -> CloudEvent: ...

    @abstractmethod
    def subscribe(self, subscription: GridSubscription) -> None: ...


class InMemoryDomainEventPublisher(DomainEventPublisher):
    """Offline Event Grid fake with subject-prefix filtering."""

    def __init__(self) -> None:
        self.subscriptions: List[GridSubscription] = []
        self.published: List[CloudEvent] = []

    def subscribe(self, subscription: GridSubscription) -> None:
        self.subscriptions.append(subscription)

    def publish(
        self, event_type: str, subject: str, data: Dict[str, Any]
    ) -> CloudEvent:
        event = emit_lifecycle_event(event_type, subject=subject, data=data)
        # emit_lifecycle_event never raises; keep a local record too.
        assert event is not None
        self.published.append(event)
        for sub in self.subscriptions:
            if sub.matches(event):
                try:
                    sub.handler(event)
                except Exception:  # noqa: BLE001 - one bad subscriber must not break fan-out
                    continue
        return event

    def published_of_type(self, event_type: str) -> List[CloudEvent]:
        return [e for e in self.published if e.type == event_type]


def publish_reformulation_completed(
    publisher: DomainEventPublisher,
    *,
    job_id: str,
    formula_id: str,
    region: str,
    claims_passed: int,
    claims_total: int,
) -> CloudEvent:
    """Convenience helper for the headline domain event."""
    return publisher.publish(
        REFORMULATION_COMPLETED,
        subject=f"reformulation/{job_id}",
        data={
            "job_id": job_id,
            "formula_id": formula_id,
            "region": region,
            "claims_passed": claims_passed,
            "claims_total": claims_total,
        },
    )
