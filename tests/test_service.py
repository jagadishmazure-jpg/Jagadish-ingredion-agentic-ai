"""Tests for the FastAPI agent service (all offline)."""

import pytest
from fastapi.testclient import TestClient

from food_ingredients_ai.interop.auth import issue_token
from food_ingredients_ai.service.app import AGENT_ORDER, AGENT_SKILL, app
from food_ingredients_ai.service.ui import INDEX_HTML

client = TestClient(app)

ALL_SCOPES = [
    "formulation:write",
    "formulation:read",
    "supply:read",
    "esg:read",
    "proposal:read",
    "proposal:write",
]


def _auth(scopes):
    return {"Authorization": f"Bearer {issue_token('test-client', scopes)}"}


# -- public endpoints --------------------------------------------------------


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_scenarios_lists_demo_scenarios():
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()["scenarios"]]
    assert "sweet_bakery_cake" in ids
    assert "energy_drink" in ids


def test_agent_cards_returns_four_cards_with_auth():
    r = client.get("/api/agent-cards")
    assert r.status_code == 200
    cards = r.json()
    assert set(cards) == set(AGENT_ORDER)
    for name, card in cards.items():
        assert card["authentication"]["skillScopes"], name
        assert card["skills"], name


def test_well_known_agent_json():
    r = client.get("/.well-known/agent.json")
    assert r.status_code == 200
    assert len(r.json()["agents"]) == 4


def test_ui_serves_demo_page():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    for marker in ("scenario-select", "token-input", "run-button", "results", "status"):
        assert f'id="{marker}"' in r.text, marker
    assert "synthetic" in r.text.lower()


# -- auth enforcement --------------------------------------------------------


def test_reformulate_requires_bearer_token():
    r = client.post("/api/reformulate", json={"scenario": "sweet_bakery_cake"})
    assert r.status_code == 401


def test_reformulate_rejects_forged_token():
    r = client.post(
        "/api/reformulate",
        json={"scenario": "sweet_bakery_cake"},
        headers={"Authorization": "Bearer forged.token.here"},
    )
    assert r.status_code == 401


def test_reformulate_rejects_out_of_scope_token():
    r = client.post(
        "/api/reformulate",
        json={"scenario": "sweet_bakery_cake"},
        headers=_auth(["supply:read"]),
    )
    assert r.status_code == 403


def test_agent_run_requires_token():
    r = client.post("/api/agents/esg/run", json={})
    assert r.status_code == 401


def test_agent_run_rejects_wrong_scope():
    # esg-report needs esg:read; a formulation-only token must fail.
    r = client.post(
        "/api/agents/esg/run", json={}, headers=_auth(["formulation:write"])
    )
    assert r.status_code == 403


# -- happy paths (offline, deterministic) ------------------------------------


def test_reformulate_full_workflow_offline():
    r = client.post(
        "/api/reformulate",
        json={"scenario": "sweet_bakery_cake"},
        headers=_auth(["formulation:write"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "offline"
    bb = body["blackboard"]
    for key in (
        "analyze_ingredients",
        "suggest_substitutes",
        "predict_texture_shelf_life",
        "calculate_nutrition",
        "validate_claims",
        "generate_documentation",
        "forecast_demand",
        "esg_report",
        "estimate_pricing",
    ):
        assert key in bb, key
    assert bb["analyze_ingredients"]["flagged_count"] == 7


def test_reformulate_unknown_scenario_is_400():
    r = client.post(
        "/api/reformulate",
        json={"scenario": "not_a_scenario"},
        headers=_auth(["formulation:write"]),
    )
    assert r.status_code == 400


def test_reformulate_explicit_fields():
    r = client.post(
        "/api/reformulate",
        json={
            "formula_id": "cola_soft_drink",
            "target_claims": ["no artificial ingredients"],
            "region": "NA",
        },
        headers=_auth(["formulation:write"]),
    )
    assert r.status_code == 200
    assert r.json()["blackboard"]["analyze_ingredients"]["formula_id"] == "cola_soft_drink"


@pytest.mark.parametrize("agent", AGENT_ORDER)
def test_agent_run_each_agent(agent):
    from food_ingredients_ai.interop.auth import required_scopes_for

    scopes = required_scopes_for(agent, AGENT_SKILL[agent])
    r = client.post(f"/api/agents/{agent}/run", json={}, headers=_auth(scopes))
    assert r.status_code == 200, f"{agent}: {r.text}"
    body = r.json()
    assert body["agent"] == agent
    assert body["summary"]
    assert body["blackboard"]


def test_agent_run_unknown_agent_is_404():
    r = client.post(
        "/api/agents/nope/run", json={}, headers=_auth(ALL_SCOPES)
    )
    assert r.status_code == 404


def test_reformulate_live_without_env_is_503(monkeypatch):
    # Hermetic: the test's promise is "no provider config → 503", so clear
    # every provider variable — a dev machine may legitimately have a real
    # OPENAI_API_KEY exported, which must not leak into this test.
    for var in (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
    ):
        monkeypatch.delenv(var, raising=False)
    r = client.post(
        "/api/reformulate",
        json={"scenario": "sweet_bakery_cake", "live": True},
        headers=_auth(["formulation:write"]),
    )
    assert r.status_code == 503


def test_ui_html_constant_matches_served_page():
    assert 'id="run-button"' in INDEX_HTML


# -- OpenAPI contract (consumed by the APIM import in infra/terraform) -------


def test_openapi_schema_exposes_expected_paths():
    """The APIM import (infra/terraform/apim.tf) reads infra/apim/openapi.json,
    which is generated from this schema — keep them in sync."""
    spec = app.openapi()
    paths = set(spec["paths"])
    expected = {
        "/api/health",
        "/api/scenarios",
        "/api/agent-cards",
        "/api/reformulate",
        "/api/agents/rd_formulation/run",
        "/api/agents/supply_chain/run",
        "/api/agents/esg/run",
        "/api/agents/customer_advisor/run",
    }
    assert expected <= paths, f"missing from OpenAPI schema: {expected - paths}"
    assert spec["openapi"].startswith("3.")


def test_exported_openapi_json_matches_app_schema():
    """infra/apim/openapi.json must match the live app schema so the
    Terraform APIM import never drifts from the service."""
    import json
    import pathlib

    exported = json.loads(
        pathlib.Path("infra/apim/openapi.json").read_text(encoding="utf-8")
    )
    assert set(exported["paths"]) == set(app.openapi()["paths"])
