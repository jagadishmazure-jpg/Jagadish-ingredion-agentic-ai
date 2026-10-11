"""Tests for interop: A2A cards/protocol, scoped-token auth, MCP server."""

import json

import pytest

from ingredion_ai.interop import a2a, auth
from ingredion_ai.interop.a2a import A2AAdapter, FakeTransport
from ingredion_ai.interop.auth import (
    AuthenticationError,
    AuthorizationError,
    authenticate_and_authorize,
    issue_token,
    verify_token,
)
from ingredion_ai.interop.mcp import InProcessClient, MCPServer

ECHO_EXECUTOR = lambda message, context: {"echo": message}  # noqa: E731


def _adapter():
    return A2AAdapter(executor=ECHO_EXECUTOR)


def _token(scopes, **kwargs):
    return issue_token("svc:test-caller", scopes, **kwargs)


# -- agent cards -----------------------------------------------------------------


def test_build_agent_cards_four_agents():
    cards = a2a.build_agent_cards()
    assert set(cards) == {"rd_formulation", "supply_chain", "esg", "customer_advisor"}


def test_agent_card_declares_auth_requirements():
    card = a2a.build_agent_cards()["rd_formulation"].to_dict()
    authn = card["authentication"]
    assert "schemes" in authn
    assert authn["skillScopes"]["reformulate"] == ["formulation:write"]
    assert authn["skillScopes"]["validate-claims"] == ["formulation:read"]


def test_agent_card_skills_have_modes():
    card = a2a.build_agent_cards()["supply_chain"].to_dict()
    skill = card["skills"][0]
    assert skill["id"] == "forecast-demand"
    assert "text/plain" in skill["inputModes"]


def test_get_agent_card_unknown_agent():
    assert "error" in _adapter().get_agent_card("nope")


# -- A2A task protocol -------------------------------------------------------------


def test_message_send_completes_with_valid_token():
    adapter = _adapter()
    token = _token(["formulation:write"])
    resp = adapter.message_send("rd_formulation", "reformulate the cake", token=token)
    task = resp["task"]
    assert task["status"]["state"] == "completed"
    assert task["artifacts"][0]["name"] == "echo"
    assert task["caller"]["subject"] == "svc:test-caller"


def test_message_send_unknown_agent():
    resp = _adapter().message_send("nope", "hi", token=_token(["formulation:write"]))
    assert "error" in resp


def test_tasks_get_roundtrip():
    adapter = _adapter()
    token = _token(["formulation:write"])
    task_id = adapter.message_send("rd_formulation", "hi", token=token)["task"]["id"]
    got = adapter.tasks_get(task_id, token=token)
    assert got["task"]["id"] == task_id


def test_tasks_get_unknown():
    assert "error" in _adapter().tasks_get("task-missing")


def test_tasks_cancel_terminal_task_is_idempotent():
    adapter = _adapter()
    token = _token(["formulation:write"])
    task_id = adapter.message_send("rd_formulation", "hi", token=token)["task"]["id"]
    again = adapter.tasks_cancel(task_id, token=token)
    assert again["task"]["status"]["state"] == "completed"


def test_fake_transport_dispatches():
    transport = FakeTransport(adapter=_adapter())
    token = _token(["supply:read"])
    resp = transport.call(
        "message/send",
        {"agent": "supply_chain", "message": "forecast", "token": token},
    )
    assert resp["task"]["status"]["state"] == "completed"
    assert transport.sent[0]["method"] == "message/send"


def test_fake_transport_unknown_method():
    transport = FakeTransport(adapter=_adapter())
    assert "error" in transport.call("nope/method", {})


# -- auth: the four required cases ---------------------------------------------------


def test_unauthenticated_call_rejected():
    resp = _adapter().message_send("rd_formulation", "hi", token=None)
    assert resp["error"]["code"] == 401


def test_expired_token_rejected():
    token = _token(["formulation:write"], ttl_seconds=-10)
    resp = _adapter().message_send("rd_formulation", "hi", token=token)
    assert resp["error"]["code"] == 401
    assert "expired" in resp["error"]["message"]


def test_invalid_signature_rejected():
    token = _token(["formulation:write"])
    forged = token[:-4] + "AAAA"
    resp = _adapter().message_send("rd_formulation", "hi", token=forged)
    assert resp["error"]["code"] == 401


def test_wrong_scope_rejected():
    token = _token(["supply:read"])  # valid token, wrong scope
    resp = _adapter().message_send("rd_formulation", "hi", token=token)
    assert resp["error"]["code"] == 403
    assert "formulation:write" in resp["error"]["message"]


def test_verify_token_returns_identity():
    token = issue_token("svc:a", ["x:read"], ttl_seconds=60)
    ident = verify_token(token)
    assert ident.subject == "svc:a"
    assert ident.has_scopes(["x:read"])
    assert not ident.has_scopes(["x:write"])


def test_verify_token_malformed_rejected():
    with pytest.raises(AuthenticationError):
        verify_token("not-a-jwt")


def test_authenticate_and_authorize_ok():
    token = _token(["formulation:read"])
    ident = authenticate_and_authorize(token, ["formulation:read"])
    assert ident.subject == "svc:test-caller"


def test_authenticate_and_authorize_missing_token():
    with pytest.raises(AuthenticationError):
        authenticate_and_authorize(None, ["formulation:read"])


def test_authenticate_and_authorize_missing_scope():
    token = _token(["formulation:read"])
    with pytest.raises(AuthorizationError):
        authenticate_and_authorize(token, ["formulation:write"])


def test_required_scopes_for_unknown_skill():
    with pytest.raises(KeyError):
        auth.required_scopes_for("rd_formulation", "nope")


# -- MCP -----------------------------------------------------------------------------


def test_mcp_initialize_handshake():
    client = InProcessClient()
    result = client.initialize()
    assert result["serverInfo"]["name"] == "ingredion-agentic-ai-mcp"
    assert "tools" in result["capabilities"]


def test_mcp_tools_list_has_expected_tools():
    client = InProcessClient()
    client.initialize()
    names = {t["name"] for t in client.list_tools()}
    assert {
        "analyze_ingredients",
        "validate_claims",
        "forecast_demand",
        "optimize_inventory",
        "generate_esg_report",
        "recommend_ingredients",
        "estimate_pricing",
    } <= names


def test_mcp_tool_input_schemas_are_json_schema():
    client = InProcessClient()
    client.initialize()
    for tool in client.list_tools():
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema


def test_mcp_call_analyze_ingredients():
    client = InProcessClient()
    client.initialize()
    result = client.call_tool("analyze_ingredients", {"formula_id": "sweet_bakery_cake"})
    assert not result["isError"]
    payload = json.loads(result["content"][0]["text"])
    assert "flagged" in payload


def test_mcp_call_validate_claims():
    client = InProcessClient()
    client.initialize()
    result = client.call_tool(
        "validate_claims",
        {"formula_id": "sweet_bakery_cake",
         "target_claims": ["no artificial ingredients"], "region": "NA"},
    )
    assert not result["isError"]


def test_mcp_call_optimize_inventory_uses_sap():
    client = InProcessClient()
    client.initialize()
    result = client.call_tool("optimize_inventory", {"plant_id": "PLANT-NA-01"})
    assert not result["isError"]
    payload = json.loads(result["content"][0]["text"])
    assert payload["inventory_source"] == "sap:PLANT-NA-01"


def test_mcp_call_unknown_tool_is_error():
    client = InProcessClient()
    client.initialize()
    result = client.call_tool("does_not_exist", {})
    assert result["isError"]


def test_mcp_handle_message_unknown_method():
    server = MCPServer()
    resp = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "nope"})
    assert resp["error"]["code"] == -32601


def test_mcp_notification_returns_no_response():
    server = MCPServer()
    assert server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_mcp_ping():
    server = MCPServer()
    resp = server.handle_message({"jsonrpc": "2.0", "id": 7, "method": "ping"})
    assert resp["result"] == {}
