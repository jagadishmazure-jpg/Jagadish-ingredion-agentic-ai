"""Azure Functions handler wrappers (demo, runtime-agnostic).

Each handler is a plain function taking injected dependencies — no Azure
Functions SDK required offline. Deploy by pointing real trigger bindings
at these entry points; the ``function.json`` shapes are documented in each
docstring.

Production: ``pip install azure-functions``, wrap the dict in/out with
``func.HttpRequest`` / ``func.ServiceBusMessage`` as shown, and deploy
with ``func azure functionapp publish``.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ingredion_ai.azure_integration.events import (
    ANOMALY_FLAGGED,
    REFORMULATION_COMPLETED,
    emit_lifecycle_event,
)
from ingredion_ai.azure_integration.servicebus import (
    BusMessage,
    JobProcessor,
    JobResult,
    ReformulationJob,
    enqueue_job,
)

#: Runner injected by the host: ``(job) -> summary dict``.
JobRunner = Callable[[ReformulationJob], Dict[str, Any]]

#: Report builder injected by the host: ``() -> report dict``.
ReportBuilder = Callable[[], Dict[str, Any]]


def http_trigger_agent_run(
    request: Dict[str, Any],
    *,
    runner: JobRunner,
) -> Dict[str, Any]:
    """HTTP-triggered agent run (enqueue a job; 202 accepted).

    ``function.json``::

        {
          "bindings": [
            {"type": "httpTrigger", "direction": "in", "name": "req",
             "methods": ["post"], "route": "jobs",
             "authLevel": "function"},
            {"type": "http", "direction": "out", "name": "$return"}
          ]
        }

    Production: build ``request`` from ``func.HttpRequest.get_json()`` and
    return ``func.HttpResponse(json.dumps(...), status_code=202)``.
    """

    # --- input validation (fail fast, no agent spend) ---------------------
    body = request.get("body") or {}
    job_id = str(body.get("job_id") or "")
    scenario = str(body.get("scenario") or "")
    if not job_id or not scenario:
        return {
            "status": 400,
            "body": {"error": "body.job_id and body.scenario are required"},
        }
    job = ReformulationJob(
        job_id=job_id,
        scenario=scenario,
        formula_id=str(body.get("formula_id") or scenario),
        target_claims=list(body.get("target_claims") or []),
        region=str(body.get("region") or "NA"),
        requested_by=str(body.get("requested_by") or "function-http"),
        live=bool(body.get("live", False)),
    )

    # --- enqueue (the bus is injected by the caller in production) --------
    enqueue = request.get("enqueue")
    if not callable(enqueue):
        return {
            "status": 500,
            "body": {"error": "no enqueue callable injected (host wiring)"},
        }
    message_id = enqueue(job)
    return {"status": 202, "body": {"job_id": job.job_id, "message_id": message_id}}


def servicebus_trigger_job(
    message_body: Dict[str, Any],
    *,
    processor: JobProcessor,
) -> Dict[str, Any]:
    """Service Bus-triggered job processor (one message per invocation).

    ``function.json``::

        {
          "bindings": [
            {"type": "serviceBusTrigger", "direction": "in", "name": "msg",
             "queueName": "reformulation-jobs",
             "connection": "SERVICEBUS_CONNECTION"}
          ]
        }

    Production: build ``message_body`` from
    ``func.ServiceBusMessage`` → ``json.loads(msg.get_body())``. Poison
    handling is the platform's: failed invocations retry per host config,
    then land on the queue's DLQ.
    """
    job_payload = message_body.get("job")
    if not isinstance(job_payload, dict):
        return {"status": "dead-letter", "error": "message missing 'job' object"}
    job = ReformulationJob.from_dict(job_payload)
    # Reuse the processor's core logic by feeding it a one-message bus view.
    summary = processor.runner(job)
    emit_lifecycle_event(
        REFORMULATION_COMPLETED,
        subject=f"reformulation/{job.job_id}",
        data={"job_id": job.job_id, "via": "function-servicebus-trigger"},
    )
    return {"status": "ok", "job_id": job.job_id, "summary": summary}


def timer_trigger_esg_report(
    *,
    report_builder: ReportBuilder,
    notify: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Timer-triggered scheduled ESG report (e.g. weekly).

    ``function.json``::

        {
          "bindings": [
            {"type": "timerTrigger", "direction": "in", "name": "timer",
             "schedule": "0 0 6 * * MON"}
          ]
        }

    Production: ``notify`` posts to the Logic App webhook / Teams channel.
    """
    report = report_builder()
    if notify is not None:
        notify(report)
    return {"status": "ok", "report": report}


def detect_anomalies_job(
    summaries: List[Dict[str, Any]],
    *,
    cost_spike_threshold: float = 0.25,
) -> List[Dict[str, Any]]:
    """Batch anomaly scan over recent run summaries (timer-triggerable).

    Emits :data:`ANOMALY_FLAGGED` lifecycle events for cost spikes so the
    Event Grid fan-out (alerts, Logic Apps) reacts without polling.
    """
    flagged: List[Dict[str, Any]] = []
    for summary in summaries:
        baseline = summary.get("baseline_cost")
        actual = summary.get("actual_cost")
        if baseline and actual and actual > baseline * (1 + cost_spike_threshold):
            flag = {
                "run_id": summary.get("run_id"),
                "code": "COST_SPIKE",
                "baseline": baseline,
                "actual": actual,
            }
            flagged.append(flag)
            emit_lifecycle_event(
                ANOMALY_FLAGGED,
                subject=f"anomaly/{summary.get('run_id')}",
                data=flag,
            )
    return flagged


#: Reference ``function.json`` bundle for the whole Function App (checked in
#: as documentation; the real files live under each function's directory
#: when deployed with the Functions Core Tools).
FUNCTION_APP_BINDINGS_DOC = {
    "http_trigger_agent_run": "httpTrigger POST /api/jobs (authLevel: function)",
    "servicebus_trigger_job": "serviceBusTrigger queue=reformulation-jobs",
    "timer_trigger_esg_report": "timerTrigger '0 0 6 * * MON' (weekly Monday 06:00)",
}
