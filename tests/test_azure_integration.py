"""Regression tests for the Azure integration-services package.

All offline: in-memory Service Bus / Event Grid / Event Hubs fakes,
injected runners, scripted webhooks. Covers: CloudEvents schema validity,
bus round-trip + topics, dead-lettering, Event Grid subject filtering,
Event Hub batching, Functions triggers, Logic Apps callbacks, and the
queue-consumer worker.
"""


import pytest

from food_ingredients_ai.azure_integration import (
    eventgrid,
    eventhub,
    functions,
    logicapps,
    servicebus,
)
from food_ingredients_ai.azure_integration import events as lifecycle
from food_ingredients_ai.azure_integration.events import (
    ANOMALY_FLAGGED,
    APPROVAL_GRANTED,
    APPROVAL_REQUESTED,
    CLAIM_VALIDATED,
    REFORMULATION_COMPLETED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_STARTED,
    EventValidationError,
    InMemoryLifecyclePublisher,
    make_event,
    validate_event,
)


@pytest.fixture(autouse=True)
def _fresh_publisher():
    pub = InMemoryLifecyclePublisher()
    lifecycle.set_lifecycle_publisher(pub)
    yield pub
    lifecycle.set_lifecycle_publisher(InMemoryLifecyclePublisher())


# -- CloudEvents ------------------------------------------------------------


def test_make_event_is_spec_shaped():
    evt = make_event(RUN_STARTED, subject="pipeline/ses-1", data={"k": "v"})
    d = evt.to_dict()
    assert d["specversion"] == "1.0"
    assert d["type"] == RUN_STARTED
    assert d["subject"] == "pipeline/ses-1"
    assert d["data"] == {"k": "v"}
    assert d["id"] and d["time"] and d["source"]
    assert d["datacontenttype"] == "application/json"


def test_validate_event_accepts_all_known_types():
    for t in (
        RUN_STARTED,
        RUN_COMPLETED,
        RUN_FAILED,
        APPROVAL_REQUESTED,
        APPROVAL_GRANTED,
        CLAIM_VALIDATED,
        ANOMALY_FLAGGED,
        REFORMULATION_COMPLETED,
    ):
        validate_event(make_event(t, subject="s").to_dict())


def test_validate_event_rejects_missing_fields():
    with pytest.raises(EventValidationError):
        validate_event({"type": RUN_STARTED})


def test_validate_event_rejects_unknown_type():
    with pytest.raises(EventValidationError):
        validate_event(make_event("com.example.nope.v1", subject="s").to_dict())


def test_validate_event_rejects_bad_specversion():
    evt = make_event(RUN_STARTED, subject="s").to_dict()
    evt["specversion"] = "0.3"
    with pytest.raises(EventValidationError):
        validate_event(evt)


def test_emit_lifecycle_event_publishes(_fresh_publisher):
    evt = lifecycle.emit_lifecycle_event(RUN_STARTED, subject="s", data={"a": 1})
    assert evt is not None
    assert _fresh_publisher.of_type(RUN_STARTED) == [evt]


# -- Service Bus ------------------------------------------------------------


def _job(job_id="job-1"):
    return servicebus.ReformulationJob(
        job_id=job_id, scenario="sweet_bakery_cake", formula_id="sweet_bakery_cake"
    )


def test_queue_round_trip():
    bus = servicebus.InMemoryMessageBus()
    bus.send_queue("q", servicebus.BusMessage("m1", {"a": 1}))
    msgs = bus.receive_queue("q")
    assert len(msgs) == 1 and msgs[0].body == {"a": 1}
    bus.complete("q", msgs[0])
    assert bus.receive_queue("q") == []


def test_topic_fanout_to_subscriptions():
    bus = servicebus.InMemoryMessageBus()
    bus.add_subscription("t", "s1")
    bus.add_subscription("t", "s2")
    bus.publish_topic("t", servicebus.BusMessage("m1", {"v": 2}))
    assert len(bus.receive_subscription("t", "s1")) == 1
    assert len(bus.receive_subscription("t", "s2")) == 1


def test_abandon_redelivers_then_dead_letters():
    bus = servicebus.InMemoryMessageBus(max_deliveries=2)
    bus.send_queue("q", servicebus.BusMessage("m1", {}))
    m = bus.receive_queue("q")[0]
    bus.abandon("q", m)  # delivery 1 -> requeue
    m2 = bus.receive_queue("q")[0]
    assert m2.delivery_count == 1
    bus.abandon("q", m2)  # delivery 2 -> DLQ
    assert bus.receive_queue("q") == []
    assert bus.dlq_depth() == 1
    assert bus.dead_lettered[0]["reason"] == "max-deliveries-exceeded"


def test_enqueue_job_message_id():
    bus = servicebus.InMemoryMessageBus()
    mid = servicebus.enqueue_job(bus, _job())
    assert mid == "msg-job-1"
    assert bus.queue_depth(servicebus.JOBS_QUEUE) == 1


def test_job_processor_happy_path(_fresh_publisher):
    bus = servicebus.InMemoryMessageBus()
    bus.add_subscription(servicebus.RESULTS_TOPIC, "ui")
    processor = servicebus.JobProcessor(bus, lambda job: {"done": job.job_id})
    servicebus.enqueue_job(bus, _job())
    result = processor.process_one()
    assert result.ok and result.job_id == "job-1"
    assert processor.processed == 1
    published = bus.receive_subscription(servicebus.RESULTS_TOPIC, "ui")
    assert published and published[0].body["ok"] is True
    assert _fresh_publisher.of_type(RUN_STARTED)
    assert _fresh_publisher.of_type(RUN_COMPLETED)


def test_job_processor_failure_requeues_then_dlq(_fresh_publisher):
    bus = servicebus.InMemoryMessageBus(max_deliveries=2)

    def boom(job):
        raise RuntimeError("workflow exploded")

    processor = servicebus.JobProcessor(bus, boom)
    servicebus.enqueue_job(bus, _job())
    r1 = processor.process_one()
    assert r1.ok is False
    r2 = processor.process_one()  # redelivered
    assert r2.ok is False
    assert bus.dlq_depth() == 1
    assert processor.process_one() is None  # queue empty now
    assert _fresh_publisher.of_type(RUN_FAILED)


def test_job_processor_bad_payload_dead_letters():
    bus = servicebus.InMemoryMessageBus()
    bus.send_queue(servicebus.JOBS_QUEUE, servicebus.BusMessage("m-bad", {"nope": 1}))
    processor = servicebus.JobProcessor(bus, lambda job: {})
    result = processor.process_one()
    assert result.ok is False and "bad-payload" in result.error
    assert bus.dlq_depth() == 1


def test_drain_stops_on_empty():
    bus = servicebus.InMemoryMessageBus()
    processor = servicebus.JobProcessor(bus, lambda job: {"ok": True})
    assert processor.drain() == []


# -- Event Grid --------------------------------------------------------------


def test_eventgrid_subject_filtering():
    pub = eventgrid.InMemoryDomainEventPublisher()
    seen = []
    pub.subscribe(
        eventgrid.GridSubscription("na-only", seen.append, subject_begins_with="reformulation/na")
    )
    pub.publish(eventgrid.REFORMULATION_COMPLETED, subject="reformulation/na-1", data={})
    pub.publish(eventgrid.REFORMULATION_COMPLETED, subject="reformulation/eu-1", data={})
    assert len(seen) == 1
    assert seen[0].subject == "reformulation/na-1"


def test_eventgrid_unfiltered_subscriber_gets_all():
    pub = eventgrid.InMemoryDomainEventPublisher()
    seen = []
    pub.subscribe(eventgrid.GridSubscription("all", seen.append))
    pub.publish(eventgrid.REFORMULATION_COMPLETED, subject="a", data={})
    pub.publish(eventgrid.CLAIM_VALIDATED_EVT, subject="b", data={})
    assert len(seen) == 2


def test_publish_reformulation_completed_helper():
    pub = eventgrid.InMemoryDomainEventPublisher()
    evt = eventgrid.publish_reformulation_completed(
        pub, job_id="j1", formula_id="f1", region="NA", claims_passed=2, claims_total=3
    )
    assert evt.subject == "reformulation/j1"
    assert evt.data["claims_passed"] == 2
    assert pub.published_of_type(eventgrid.REFORMULATION_COMPLETED)


def test_bad_subscriber_does_not_break_fanout():
    pub = eventgrid.InMemoryDomainEventPublisher()
    seen = []

    def boom(evt):
        raise RuntimeError("subscriber bug")

    pub.subscribe(eventgrid.GridSubscription("bad", boom))
    pub.subscribe(eventgrid.GridSubscription("good", seen.append))
    pub.publish(eventgrid.REFORMULATION_COMPLETED, subject="x", data={})
    assert len(seen) == 1


# -- Event Hubs ---------------------------------------------------------------


def test_eventhub_flushes_on_batch_size():
    prod = eventhub.InMemoryTelemetryProducer(batch_size=3)
    for i in range(3):
        prod.record(eventhub.RunMetric("run.latency_ms", float(i), f"r{i}"))
    assert prod.buffered == 0
    assert prod.total_shipped == 3


def test_eventhub_manual_flush():
    prod = eventhub.InMemoryTelemetryProducer(batch_size=100)
    prod.record(eventhub.RunMetric("run.tokens", 10.0, "r1"))
    batch = prod.flush()
    assert len(batch) == 1 and batch[0]["metric"] == "run.tokens"
    assert prod.flush() == []


def test_metrics_for_run_builds_standard_set():
    metrics = eventhub.metrics_for_run(
        run_id="r1", agent="rd_formulation", latency_ms=120.5, tokens=800, degraded=True
    )
    names = {m.metric for m in metrics}
    assert names == {
        "run.latency_ms",
        "run.tokens",
        "run.guardrail_flags",
        "run.degraded",
    }
    degraded = next(m for m in metrics if m.metric == "run.degraded")
    assert degraded.value == 1.0


# -- Functions triggers --------------------------------------------------------


def test_http_trigger_validates_then_enqueues():
    enqueued = []

    def fake_enqueue(job):
        enqueued.append(job)
        return "msg-x"

    resp = functions.http_trigger_agent_run(
        {"body": {"job_id": "j9", "scenario": "s1"}}, runner=lambda j: {},
        )
    # runner unused on the enqueue path; enqueue injected via request
    assert resp["status"] == 500  # no enqueue callable -> host wiring error

    resp = functions.http_trigger_agent_run(
        {"body": {"job_id": "j9", "scenario": "s1"}, "enqueue": fake_enqueue},
        runner=lambda j: {},
    )
    assert resp["status"] == 202
    assert resp["body"]["job_id"] == "j9"
    assert enqueued and enqueued[0].job_id == "j9"


def test_http_trigger_rejects_missing_fields():
    resp = functions.http_trigger_agent_run({"body": {}}, runner=lambda j: {})
    assert resp["status"] == 400


def test_servicebus_trigger_processes_message():
    bus = servicebus.InMemoryMessageBus()
    processor = servicebus.JobProcessor(bus, lambda job: {"summary": job.job_id})
    out = functions.servicebus_trigger_job(
        {"job": {"job_id": "j2", "scenario": "s"}}, processor=processor
    )
    assert out["status"] == "ok" and out["job_id"] == "j2"


def test_servicebus_trigger_rejects_bad_envelope():
    bus = servicebus.InMemoryMessageBus()
    processor = servicebus.JobProcessor(bus, lambda job: {})
    out = functions.servicebus_trigger_job({"nope": 1}, processor=processor)
    assert out["status"] == "dead-letter"


def test_timer_trigger_builds_and_notifies():
    notified = []
    out = functions.timer_trigger_esg_report(
        report_builder=lambda: {"co2e_t": 12.5},
        notify=notified.append,
    )
    assert out["status"] == "ok"
    assert out["report"]["co2e_t"] == 12.5
    assert notified == [{"co2e_t": 12.5}]


def test_detect_anomalies_flags_cost_spike(_fresh_publisher):
    flagged = functions.detect_anomalies_job(
        [{"run_id": "r1", "baseline_cost": 100.0, "actual_cost": 140.0},
         {"run_id": "r2", "baseline_cost": 100.0, "actual_cost": 105.0}],
        cost_spike_threshold=0.25,
    )
    assert len(flagged) == 1 and flagged[0]["run_id"] == "r1"
    assert _fresh_publisher.of_type(ANOMALY_FLAGGED)


# -- Logic Apps callbacks -------------------------------------------------------


def test_callback_receiver_valid_signature():
    rx = logicapps.LogicAppCallbackReceiver()
    logicapps.default_approval_handlers(rx)
    payload = {
        "action": logicapps.ACTION_APPROVAL_GRANTED,
        "data": {"approval_id": "a1", "subject": "reformulation/j1", "decided_by": "sam"},
    }
    out = rx.receive(payload, rx.sign(payload))
    assert out["decision"] == "granted"
    assert rx.received[0]["action"] == logicapps.ACTION_APPROVAL_GRANTED


def test_callback_receiver_rejects_bad_signature():
    rx = logicapps.LogicAppCallbackReceiver()
    logicapps.default_approval_handlers(rx)
    with pytest.raises(logicapps.CallbackValidationError):
        rx.receive({"action": logicapps.ACTION_APPROVAL_GRANTED, "data": {}}, "bogus")


def test_callback_receiver_rejects_unknown_action():
    rx = logicapps.LogicAppCallbackReceiver()
    payload = {"action": "nope.action", "data": {}}
    with pytest.raises(logicapps.CallbackValidationError):
        rx.receive(payload, rx.sign(payload))


def test_callback_denied_halts():
    rx = logicapps.LogicAppCallbackReceiver()
    logicapps.default_approval_handlers(rx)
    payload = {
        "action": logicapps.ACTION_APPROVAL_DENIED,
        "data": {"approval_id": "a2", "subject": "s", "decided_by": "sam"},
    }
    out = rx.receive(payload, rx.sign(payload))
    assert out == {"status": "halted", "decision": "denied"}


def test_build_approval_request_emits_event(_fresh_publisher):
    req = logicapps.build_approval_request(
        approval_id="a3", subject="reformulation/j9", action="approve formulation"
    )
    assert req.approval_id == "a3"
    assert _fresh_publisher.of_type(APPROVAL_REQUESTED)


# -- worker ---------------------------------------------------------------------


def test_worker_main_runs_demo_job(capsys):
    from food_ingredients_ai.azure_integration import worker

    rc = worker.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "job-demo-001" in out
    assert "processed=1" in out


# -- pipeline wiring --------------------------------------------------------------


def test_pipeline_emits_lifecycle_events(_fresh_publisher):
    import asyncio

    from food_ingredients_ai.service.memory import InMemorySessionStore
    from food_ingredients_ai.service.pipeline import AgenticPipeline

    async def fake_executor(ctx):
        ctx.result = {"ok": True}
        return {"ok": True}, False, None

    async def go():
        pipe = AgenticPipeline(store=InMemorySessionStore())
        return await pipe.run(
            kind="agent_run",
            identity_subject="tester",
            session_id="ses-test",
            params={"formula_id": "sweet_bakery_cake"},
            text_fields={"message": "Run your demo task."},
            live=False,
            agent_name="rd_formulation",
            executor=fake_executor,
        )

    body = asyncio.run(go())
    assert body  # run succeeded
    assert _fresh_publisher.of_type(RUN_STARTED)
    assert _fresh_publisher.of_type(RUN_COMPLETED)
