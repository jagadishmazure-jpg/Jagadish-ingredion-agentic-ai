"""Tests for Prometheus metrics + the analytics API endpoint (all offline)."""

import pytest
from fastapi.testclient import TestClient

from ingredion_ai.interop.auth import issue_token
from ingredion_ai.service import app as app_module
from ingredion_ai.service.app import app
from ingredion_ai.service.metrics import registry

client = TestClient(app)

ALL_SCOPES = [
    "formulation:write",
    "formulation:read",
    "supply:read",
    "esg:read",
    "proposal:read",
    "proposal:write",
    "analytics:read",
]


def _auth(scopes):
    return {"Authorization": f"Bearer {issue_token('test-client', scopes)}"}


@pytest.fixture(autouse=True)
def _clean_state():
    registry.reset()
    app_module.analytics_store.clear()
    yield
    registry.reset()
    app_module.analytics_store.clear()


# -- /metrics -----------------------------------------------------------------


def test_metrics_content_type_and_shape():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "# HELP agent_service_http_requests_total" in body
    assert "# TYPE agent_service_http_requests_total counter" in body
    assert body.rstrip().endswith("# EOF")


def test_metrics_counts_requests():
    client.get("/api/health")
    client.get("/api/health")
    body = client.get("/metrics").text
    assert 'agent_service_http_requests_total{method="GET",route="/api/health",status="200"} 2' in body


def test_metrics_normalizes_agent_routes():
    headers = _auth(ALL_SCOPES)
    r = client.post(
        "/api/agents/esg/run",
        json={"message": "demo", "formula_id": "sweet_bakery_cake"},
        headers=headers,
    )
    assert r.status_code == 200
    body = client.get("/metrics").text
    assert 'route="/api/agents/{agent}/run"' in body
    assert 'agent_service_agent_runs_total{agent="esg"} 1' in body


def test_metrics_records_durations():
    client.get("/api/health")
    body = client.get("/metrics").text
    assert "agent_service_http_request_duration_seconds_count 1" in body
    assert "agent_service_http_request_duration_seconds_sum" in body


# -- /api/analytics/summary ----------------------------------------------------


def test_analytics_requires_auth():
    r = client.get("/api/analytics/summary")
    assert r.status_code == 401


def test_analytics_requires_scope():
    r = client.get(
        "/api/analytics/summary", headers=_auth(["formulation:read"])
    )
    assert r.status_code == 403


def test_analytics_empty_state():
    r = client.get("/api/analytics/summary", headers=_auth(ALL_SCOPES))
    assert r.status_code == 200
    data = r.json()
    assert data["aggregates"]["run_count"] == 0
    assert data["latest_run"] is None
    assert data["peer_benchmarks"] == []
    assert "synthetic" in data["synthetic_data_note"]


def test_analytics_after_reformulate():
    headers = _auth(ALL_SCOPES)
    r = client.post("/api/reformulate", json={"scenario": "sweet_bakery_cake"}, headers=headers)
    assert r.status_code == 200
    r = client.get("/api/analytics/summary", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["aggregates"]["run_count"] == 1
    latest = data["latest_run"]
    assert latest["scenario"] == "sweet_bakery_cake"
    assert latest["cost_per_kg_usd"] is not None
    metrics = {b["metric"] for b in data["peer_benchmarks"]}
    assert "cost_per_kg_usd" in metrics
    assert all("synthetic" in b["data_label"] for b in data["peer_benchmarks"])
    assert isinstance(data["anomaly_flags"], list)


def test_reformulate_records_all_four_agent_runs_in_metrics():
    headers = _auth(ALL_SCOPES)
    client.post("/api/reformulate", json={"scenario": "sweet_bakery_cake"}, headers=headers)
    body = client.get("/metrics").text
    for agent in ("rd_formulation", "supply_chain", "esg", "customer_advisor"):
        assert f'agent_service_agent_runs_total{{agent="{agent}"}} 1' in body
