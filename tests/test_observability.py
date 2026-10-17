"""Tests for the observability package: logging, tracing, costs, incidents."""

import json
import logging

import pytest

from food_ingredients_ai.observability import costs, incidents, tracing
from food_ingredients_ai.observability import logging as json_logging

# -- structured JSON logging ---------------------------------------------------


def test_json_logger_emits_json_lines():
    logger = json_logging.get_json_logger("demo-test-logger")
    handler = logger.handlers[0]
    record = logging.LogRecord(
        name="demo-test-logger", level=logging.INFO, pathname=__file__,
        lineno=1, msg="hello", args=(), exc_info=None,
    )
    parsed = json.loads(handler.format(record))
    assert parsed["message"] == "hello"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "demo-test-logger"
    assert "timestamp" in parsed


def test_json_logger_includes_extra_fields():
    logger = json_logging.get_json_logger("demo-test-logger-2")
    handler = logger.handlers[0]
    record = logging.LogRecord(
        name="demo-test-logger-2", level=logging.INFO, pathname=__file__,
        lineno=1, msg="hi", args=(), exc_info=None,
    )
    record.extra_fields = {"agent": "esg"}
    parsed = json.loads(handler.format(record))
    assert parsed["agent"] == "esg"


# -- tracing -------------------------------------------------------------------


def test_span_records_attributes_and_duration():
    tracer = tracing.Tracer(tracing.InMemoryExporter())
    with tracer.span("analyze", {"agent": "rd_formulation"}) as span:
        span.add_event("tool_call")
    assert span.attributes["agent"] == "rd_formulation"
    assert span.duration_ms >= 0
    assert len(span.events) == 1


def test_tracer_exports_to_in_memory_exporter():
    exporter = tracing.InMemoryExporter()
    tracer = tracing.Tracer(exporter)
    with tracer.span("op1"):
        pass
    with tracer.span("op2"):
        pass
    assert [s.name for s in exporter.spans] == ["op1", "op2"]


def test_noop_exporter_discards_spans():
    tracer = tracing.Tracer()  # default NoOpExporter
    with tracer.span("op"):
        pass  # no error, nothing stored


def test_span_records_error_and_reraises():
    exporter = tracing.InMemoryExporter()
    tracer = tracing.Tracer(exporter)
    with pytest.raises(ValueError), tracer.span("boom"):
        raise ValueError("demo failure")
    span = exporter.spans[0]
    assert span.status == "error"
    assert "ValueError" in span.error


def test_span_otel_dict_shape():
    tracer = tracing.Tracer(tracing.InMemoryExporter())
    with tracer.span("x") as span:
        pass
    d = span.to_otel_dict()
    assert {"traceId", "spanId", "name", "attributes", "status"} <= set(d)
    assert d["status"]["code"] == "OK"


# -- cost / latency tracking -----------------------------------------------------


def test_cost_tracker_records_and_summarizes():
    tracker = costs.CostTracker()
    tracker.record("rd_formulation", "analyze", latency_ms=12.5,
                   input_tokens=100, output_tokens=50)
    tracker.record("rd_formulation", "validate", latency_ms=7.5,
                   input_tokens=200, output_tokens=50)
    summary = tracker.summary()["rd_formulation"]
    assert summary["operations"] == 2
    assert summary["input_tokens"] == 300
    assert summary["cost_usd"] > 0


def test_cost_tracker_estimates_tokens_from_text():
    tracker = costs.CostTracker()
    record = tracker.record("esg", "report", latency_ms=1.0,
                            input_text="hello world foo bar")
    assert record.input_tokens > 0


def test_timed_context_manager_records():
    tracker = costs.CostTracker()
    with tracker.timed("supply_chain", "forecast"):
        pass
    assert tracker.summary()["supply_chain"]["operations"] == 1


# -- incident-style metrics ------------------------------------------------------


def test_incident_track_detect_and_respond():
    tracker = incidents.IncidentTracker()
    rec = tracker.detect("claim_rejected", {"claim": "natural"})
    tracker.respond(rec, resolved=True)
    assert rec.response_time_ms is not None
    assert rec.response_time_ms >= 0


def test_incident_metrics_rates():
    tracker = incidents.IncidentTracker()
    r1 = tracker.detect("a")
    tracker.respond(r1, resolved=True, false_positive=False, automated=True)
    r2 = tracker.detect("b")
    tracker.respond(r2, resolved=False, false_positive=True, automated=False)
    m = tracker.metrics()
    assert m["incidents_total"] == 2
    assert m["false_positive_rate"] == 0.5
    assert m["automation_rate"] == 0.5
    assert m["resolved_rate"] == 0.5


def test_incident_track_context_manager_resolves():
    tracker = incidents.IncidentTracker()
    with tracker.track("risk_flag") as rec:
        assert rec.kind == "risk_flag"
    assert rec.resolved
    assert tracker.metrics()["incidents_total"] == 1


def test_incident_track_context_manager_marks_failure():
    tracker = incidents.IncidentTracker()
    with pytest.raises(RuntimeError):
        with tracker.track("risk_flag"):
            raise RuntimeError("demo")
    assert tracker.metrics()["resolved_rate"] == 0.0


def test_incident_metrics_empty_tracker():
    m = incidents.IncidentTracker().metrics()
    assert m["incidents_total"] == 0
    assert m["mean_response_time_ms"] == 0.0
