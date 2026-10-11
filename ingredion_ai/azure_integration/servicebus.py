"""Service Bus abstraction: the reformulation job-queue pattern (demo).

Pattern
-------
API enqueues a :class:`ReformulationJob` → a worker dequeues it → runs the
agent workflow → publishes the result. Poison messages (repeated failures)
move to the dead-letter queue after ``max_deliveries``.

:class:`InMemoryMessageBus` is the offline fake: FIFO queues, topics with
named subscriptions, per-message delivery counting, and a DLQ. Production
swap (one line): wrap ``azure-servicebus.ServiceBusClient`` behind
:class:`MessageBus` — queue names, sessions, and DLQ semantics map 1:1
(``abandon`` → unlock, ``dead_letter`` → ``dead_letter_message``).

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ingredion_ai.azure_integration.events import (
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_STARTED,
    emit_lifecycle_event,
)

#: Queue holding reformulation jobs for workers.
JOBS_QUEUE = "reformulation-jobs"

#: Topic fanning job results out to subscribers (UI, analytics, Logic Apps).
RESULTS_TOPIC = "job-results"

#: Queue receiving poison messages.
DEAD_LETTER_QUEUE = "reformulation-jobs-dlq"

#: Deliveries before a message is declared poison.
DEFAULT_MAX_DELIVERIES = 3


@dataclass
class BusMessage:
    """One brokered message."""

    message_id: str
    body: Dict[str, Any]
    delivery_count: int = 0
    label: Optional[str] = None


@dataclass
class ReformulationJob:
    """A unit of work for the job queue."""

    job_id: str
    scenario: str
    formula_id: str
    target_claims: List[str] = field(default_factory=list)
    region: str = "NA"
    requested_by: str = "api"
    live: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "scenario": self.scenario,
            "formula_id": self.formula_id,
            "target_claims": list(self.target_claims),
            "region": self.region,
            "requested_by": self.requested_by,
            "live": self.live,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ReformulationJob":
        return cls(
            job_id=str(payload.get("job_id", "")),
            scenario=str(payload.get("scenario", "")),
            formula_id=str(payload.get("formula_id", "")),
            target_claims=list(payload.get("target_claims") or []),
            region=str(payload.get("region", "NA")),
            requested_by=str(payload.get("requested_by", "api")),
            live=bool(payload.get("live", False)),
        )


@dataclass
class JobResult:
    """Outcome of processing one job."""

    job_id: str
    ok: bool
    summary: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "ok": self.ok,
            "summary": dict(self.summary),
            "error": self.error,
        }


class MessageBus(ABC):
    """Queue/topic abstraction (Service Bus in production)."""

    @abstractmethod
    def send_queue(self, queue: str, message: BusMessage) -> None: ...

    @abstractmethod
    def receive_queue(self, queue: str, max_messages: int = 1) -> List[BusMessage]: ...

    @abstractmethod
    def complete(self, queue: str, message: BusMessage) -> None:
        """Acknowledge successful processing."""

    @abstractmethod
    def abandon(self, queue: str, message: BusMessage) -> None:
        """Return the message for redelivery (delivery_count += 1)."""

    @abstractmethod
    def dead_letter(self, queue: str, message: BusMessage, reason: str) -> None: ...

    @abstractmethod
    def publish_topic(self, topic: str, message: BusMessage) -> None: ...

    @abstractmethod
    def receive_subscription(
        self, topic: str, subscription: str, max_messages: int = 10
    ) -> List[BusMessage]: ...


class InMemoryMessageBus(MessageBus):
    """Offline Service Bus fake: queues, topics, DLQ, delivery counting."""

    def __init__(self, max_deliveries: int = DEFAULT_MAX_DELIVERIES) -> None:
        self.max_deliveries = max_deliveries
        self._queues: Dict[str, deque] = defaultdict(deque)
        self._topics: Dict[str, Dict[str, deque]] = defaultdict(
            lambda: defaultdict(deque)
        )
        self._inflight: Dict[str, BusMessage] = {}
        self.dead_lettered: List[Dict[str, Any]] = []

    # -- queues -----------------------------------------------------------

    def send_queue(self, queue: str, message: BusMessage) -> None:
        self._queues[queue].append(message)

    def receive_queue(self, queue: str, max_messages: int = 1) -> List[BusMessage]:
        out = []
        for _ in range(max_messages):
            if not self._queues[queue]:
                break
            msg = self._queues[queue].popleft()
            self._inflight[msg.message_id] = msg
            out.append(msg)
        return out

    def complete(self, queue: str, message: BusMessage) -> None:
        self._inflight.pop(message.message_id, None)

    def abandon(self, queue: str, message: BusMessage) -> None:
        message.delivery_count += 1
        self._inflight.pop(message.message_id, None)
        if message.delivery_count >= self.max_deliveries:
            self.dead_letter(queue, message, reason="max-deliveries-exceeded")
        else:
            self._queues[queue].append(message)

    def dead_letter(self, queue: str, message: BusMessage, reason: str) -> None:
        self._inflight.pop(message.message_id, None)
        self._queues[DEAD_LETTER_QUEUE].append(message)
        self.dead_lettered.append(
            {"queue": queue, "message_id": message.message_id, "reason": reason}
        )

    # -- topics ------------------------------------------------------------

    def publish_topic(self, topic: str, message: BusMessage) -> None:
        for subscription in self._topics[topic]:
            self._topics[topic][subscription].append(
                BusMessage(
                    message_id=f"{message.message_id}:{subscription}",
                    body=dict(message.body),
                    delivery_count=0,
                    label=message.label,
                )
            )

    def add_subscription(self, topic: str, subscription: str) -> None:
        self._topics[topic][subscription]  # touch to create

    def receive_subscription(
        self, topic: str, subscription: str, max_messages: int = 10
    ) -> List[BusMessage]:
        out = []
        backlog = self._topics[topic][subscription]
        for _ in range(max_messages):
            if not backlog:
                break
            out.append(backlog.popleft())
        return out

    # -- inspection helpers -------------------------------------------------

    def queue_depth(self, queue: str) -> int:
        return len(self._queues[queue]) + sum(
            1 for m in self._inflight.values()
        )

    def dlq_depth(self) -> int:
        return len(self._queues[DEAD_LETTER_QUEUE])


class JobProcessor:
    """Worker side of the job queue: dequeue → run → publish result.

    The ``runner`` is injected (``(job) -> summary dict``) so the processor
    never imports the agent framework directly — in production this runs
    inside the Azure Functions Service Bus trigger (see
    :mod:`ingredion_ai.azure_integration.functions`).
    """

    def __init__(
        self,
        bus: MessageBus,
        runner: Callable[[ReformulationJob], Dict[str, Any]],
        *,
        queue: str = JOBS_QUEUE,
        results_topic: str = RESULTS_TOPIC,
    ) -> None:
        self.bus = bus
        self.runner = runner
        self.queue = queue
        self.results_topic = results_topic
        self.processed = 0
        self.failed = 0

    def process_one(self) -> Optional[JobResult]:
        """Process a single job; returns None when the queue is empty."""
        messages = self.bus.receive_queue(self.queue, max_messages=1)
        if not messages:
            return None
        message = messages[0]
        try:
            job = ReformulationJob.from_dict(message.body.get("job") or {})
            if not job.job_id:
                raise ValueError("job missing job_id")
        except Exception as exc:  # noqa: BLE001 - malformed payloads must not kill the worker
            self.bus.dead_letter(self.queue, message, reason=f"bad-payload: {exc}")
            self.failed += 1
            return JobResult(job_id="", ok=False, error=f"bad-payload: {exc}")

        emit_lifecycle_event(RUN_STARTED, subject=f"job/{job.job_id}", data=job.to_dict())
        try:
            summary = self.runner(job)
            result = JobResult(job_id=job.job_id, ok=True, summary=summary)
            self.bus.complete(self.queue, message)
            self.processed += 1
            emit_lifecycle_event(
                RUN_COMPLETED, subject=f"job/{job.job_id}", data={"job_id": job.job_id}
            )
        except Exception as exc:  # noqa: BLE001 - worker must survive job failures
            result = JobResult(job_id=job.job_id, ok=False, error=str(exc))
            self.failed += 1
            emit_lifecycle_event(
                RUN_FAILED,
                subject=f"job/{job.job_id}",
                data={"job_id": job.job_id, "error": str(exc)},
            )
            # Requeue unless poison; abandon() dead-letters at max_deliveries.
            self.bus.abandon(self.queue, message)
            return result

        self.bus.publish_topic(
            self.results_topic,
            BusMessage(message_id=f"result-{job.job_id}", body=result.to_dict()),
        )
        return result

    def drain(self, max_jobs: int = 100) -> List[JobResult]:
        """Process until the queue is empty (or ``max_jobs`` reached)."""
        results = []
        for _ in range(max_jobs):
            result = self.process_one()
            if result is None:
                break
            results.append(result)
        return results


def enqueue_job(
    bus: MessageBus, job: ReformulationJob, *, queue: str = JOBS_QUEUE
) -> str:
    """API side: enqueue a reformulation job. Returns the message id."""
    message_id = f"msg-{job.job_id}"
    bus.send_queue(queue, BusMessage(message_id=message_id, body={"job": job.to_dict()}))
    return message_id
