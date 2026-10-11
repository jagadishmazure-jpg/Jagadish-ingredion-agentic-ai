"""Queue-consumer worker entrypoint (demo).

Run with::

    python -m ingredion_ai.azure_integration.worker

Builds an in-memory Service Bus, enqueues one demo reformulation job,
drains it through :class:`JobProcessor` with a scripted runner, and
prints the result + lifecycle events. Production: this logic runs inside
the Azure Functions Service Bus trigger
(:func:`ingredion_ai.azure_integration.functions.servicebus_trigger_job`).

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from ingredion_ai.azure_integration import events as lifecycle
from ingredion_ai.azure_integration.servicebus import (
    InMemoryMessageBus,
    JobProcessor,
    ReformulationJob,
    enqueue_job,
)


def demo_runner(job: ReformulationJob) -> Dict[str, Any]:
    """Scripted runner standing in for the agent workflow (offline demo)."""
    return {
        "job_id": job.job_id,
        "scenario": job.scenario,
        "formula_id": job.formula_id,
        "ingredients_flagged": 7,
        "substitutions": 6,
        "texture_match_pct": 92.2,
        "claims_passed": 2,
        "claims_total": 3,
        "mode": "offline-demo",
    }


def main() -> int:
    publisher = lifecycle.InMemoryLifecyclePublisher()
    lifecycle.set_lifecycle_publisher(publisher)

    bus = InMemoryMessageBus()
    processor = JobProcessor(bus, demo_runner)

    job = ReformulationJob(
        job_id="job-demo-001",
        scenario="sweet_bakery_cake",
        formula_id="sweet_bakery_cake",
        target_claims=["no artificial ingredients", "reduced sugar"],
        region="NA",
    )
    message_id = enqueue_job(bus, job)
    print(f"enqueued {message_id} (queue depth: {bus.queue_depth('reformulation-jobs')})")

    results = processor.drain()
    for result in results:
        print(json.dumps(result.to_dict(), indent=2))

    started = publisher.of_type(lifecycle.RUN_STARTED)
    completed = publisher.of_type(lifecycle.RUN_COMPLETED)
    print(f"lifecycle events: {len(started)} started, {len(completed)} completed")
    print(f"processed={processor.processed} failed={processor.failed} "
          f"dlq_depth={bus.dlq_depth()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
