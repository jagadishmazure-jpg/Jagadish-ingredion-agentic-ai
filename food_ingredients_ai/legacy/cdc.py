"""Change-data-capture: legacy events become agent triggers (demo).

Two ingestion paths, both offline-capable:

- :class:`SimulatedEventSource` — a scripted pollable event source standing
  in for database CDC / message-queue consumers (Debezium, Event Hubs).
- :class:`WebhookReceiver` — validates and normalizes inbound webhook
  envelopes (HMAC-SHA256 signature; the demo secret is synthetic — production
  swaps in the real webhook secret from Key Vault).

:class:`ChangeFeed` polls a source, dedupes by ``event_id``, and dispatches
to subscribed handlers. Handlers return *trigger records* describing what the
agent should do next (which workflow, with what input) — the feed itself
never executes agent logic.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LegacyEvent:
    """One normalized legacy-system event."""

    event_id: str
    source: str
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=_utcnow)


class EventSource(ABC):
    """Pollable source of legacy events."""

    @abstractmethod
    def poll(self) -> List[LegacyEvent]:
        """Return newly available events (may be empty)."""


class SimulatedEventSource(EventSource):
    """Scripted event source for offline demos and tests."""

    def __init__(self, events: Optional[List[LegacyEvent]] = None):
        self._events: List[LegacyEvent] = list(events or [])
        self._cursor = 0

    def inject(self, event: LegacyEvent) -> None:
        """Append an event (as if it just happened in the legacy system)."""
        self._events.append(event)

    def poll(self) -> List[LegacyEvent]:
        batch = self._events[self._cursor :]
        self._cursor = len(self._events)
        return batch


class WebhookError(Exception):
    """Raised when a webhook envelope fails validation."""


class WebhookReceiver:
    """Validate + normalize inbound webhook envelopes.

    The signature is ``HMAC-SHA256(secret, canonical_json(envelope))`` sent
    as a hex string. The default secret is synthetic and for demo only.
    """

    def __init__(self, *, secret: str = "demo-webhook-secret", source: str = "webhook"):
        self._secret = secret.encode("utf-8")
        self._source = source

    def sign(self, envelope: Dict[str, Any]) -> str:
        """Compute the expected signature (used by tests / demo senders)."""
        canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        return hmac.new(self._secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()

    def receive(self, envelope: Dict[str, Any], signature: str) -> LegacyEvent:
        """Validate *signature* and normalize *envelope* to a :class:`LegacyEvent`."""
        expected = self.sign(envelope)
        if not hmac.compare_digest(expected, signature):
            raise WebhookError("webhook signature mismatch")
        try:
            event_id = str(envelope["id"])
            event_type = str(envelope["type"])
        except KeyError as exc:
            raise WebhookError(f"webhook envelope missing field: {exc}") from exc
        return LegacyEvent(
            event_id=event_id,
            source=str(envelope.get("source", self._source)),
            event_type=event_type,
            payload=dict(envelope.get("data", {})),
            ts=str(envelope.get("ts", _utcnow())),
        )


# Handler: (event) -> trigger record dict {"workflow": str, "input": dict, ...}
Handler = Callable[[LegacyEvent], Dict[str, Any]]


class ChangeFeed:
    """Poll → dedupe → dispatch. Handlers produce agent trigger records."""

    def __init__(self, source: EventSource):
        self._source = source
        self._seen: set[str] = set()
        self._handlers: Dict[str, List[Handler]] = {}

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register *handler* for *event_type* (``"*"`` matches all types)."""
        self._handlers.setdefault(event_type, []).append(handler)

    def poll_once(self) -> List[Dict[str, Any]]:
        """Poll the source once; return trigger records for new events.

        Duplicate ``event_id``s are skipped. Handler exceptions are captured
        into an error trigger record instead of killing the feed.
        """
        triggers: List[Dict[str, Any]] = []
        for event in self._source.poll():
            if event.event_id in self._seen:
                continue
            self._seen.add(event.event_id)
            handlers = self._handlers.get(event.event_type, []) + self._handlers.get("*", [])
            if not handlers:
                triggers.append(
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "handled": False,
                        "reason": "no handler subscribed",
                    }
                )
                continue
            for handler in handlers:
                try:
                    record = handler(event)
                    triggers.append(
                        {
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                            "handled": True,
                            "trigger": record,
                        }
                    )
                except Exception as exc:  # noqa: BLE001 - feed must survive
                    triggers.append(
                        {
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                            "handled": False,
                            "reason": f"handler error: {exc}",
                        }
                    )
        return triggers

    @property
    def seen_count(self) -> int:
        return len(self._seen)
