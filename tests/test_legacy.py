"""Tests for the legacy intelligence layer: bridges, catalog, CDC, autonomy.

All offline, deterministic, synthetic data only.
"""

import time

import pytest

from food_ingredients_ai.legacy import (
    L0_MANUAL,
    L1_ASSIST,
    L2_AUGMENT,
    L3_AUTONOMOUS,
    AutonomyController,
    AutonomyPolicy,
    BridgeHealth,
    CapabilityCatalog,
    CatalogError,
    ChangeFeed,
    CRMBridge,
    LegacyError,
    LegacyEvent,
    SAPBridge,
    SimulatedEventSource,
    SyntheticLegacyBridge,
    ToolSpec,
    WebhookError,
    WebhookReceiver,
    WorkflowHistory,
    promotion_eligible,
)


def _echo_bridge(**kwargs):
    return SyntheticLegacyBridge(
        "demo-sys",
        {"ping_op": lambda p: {"echo": p.get("x")}, "whoami": lambda p: {"sys": "demo-sys"}},
        **kwargs,
    )


# -- bridge ---------------------------------------------------------------


def test_bridge_success_envelope_shape():
    env = _echo_bridge().call("ping_op", {"x": 1})
    assert env["ok"] is True
    assert env["system"] == "demo-sys"
    assert env["operation"] == "ping_op"
    assert env["data"] == {"echo": 1}
    assert isinstance(env["latency_ms"], float)


def test_bridge_unknown_operation_code():
    env = _echo_bridge().call("nope", {})
    assert env["ok"] is False
    assert env["error"]["code"] == "UNKNOWN_OPERATION"


def test_bridge_simulated_failure_is_retryable():
    env = _echo_bridge(fail_operations=["ping_op"]).call("ping_op", {})
    assert env["ok"] is False
    assert env["error"]["retryable"] is True
    assert env["error"]["code"] == "SIMULATED"


def test_bridge_timeout_envelope():
    def slow(payload):
        time.sleep(0.5)

    bridge = SyntheticLegacyBridge("slow-sys", {"slow": slow}, timeout_s=0.05)
    env = bridge.call("slow", {})
    assert env["ok"] is False
    assert env["error"]["code"] == "TIMEOUT"
    assert env["error"]["retryable"] is True


def test_bridge_request_response_mapping_hooks():
    class Mapped(SyntheticLegacyBridge):
        def map_request(self, operation, payload):
            return {"x": payload["agent_field"] * 2}

        def map_response(self, operation, raw):
            return {"doubled": raw["echo"]}

    env = Mapped("m", {"ping_op": lambda p: {"echo": p["x"]}}).call(
        "ping_op", {"agent_field": 21}
    )
    assert env["ok"] is True
    assert env["data"] == {"doubled": 42}


def test_bridge_health_check_healthy():
    health = _echo_bridge().health_check()
    assert isinstance(health, BridgeHealth)
    assert health.healthy is True
    assert health.system == "demo-sys"


def test_bridge_health_check_unhealthy():
    class Down(SyntheticLegacyBridge):
        def ping(self):
            raise LegacyError("connection refused", code="TRANSPORT")

    health = Down("down", {}).health_check()
    assert health.healthy is False
    assert "refused" in health.detail


def test_crm_bridge_get_account():
    env = CRMBridge().call("get_account", {"account_id": "ACME-001"})
    assert env["ok"] is True
    assert env["data"]["tier"] == "gold"


def test_crm_bridge_unknown_account_not_found():
    env = CRMBridge().call("get_account", {"account_id": "NOPE-999"})
    assert env["ok"] is False
    assert env["error"]["code"] == "NOT_FOUND"


def test_crm_bridge_unknown_operation():
    env = CRMBridge().call("delete_everything", {})
    assert env["ok"] is False
    assert env["error"]["code"] == "UNKNOWN_OPERATION"


def test_sap_bridge_get_inventory():
    plants = SAPBridge().call("list_plants", {})
    assert plants["ok"] is True
    assert len(plants["data"]["items"]) >= 1
    plant_id = plants["data"]["items"][0]["plant_id"]
    inv = SAPBridge().call("get_inventory", {"plant_id": plant_id})
    assert inv["ok"] is True
    assert isinstance(inv["data"], dict)


def test_sap_bridge_unknown_material():
    env = SAPBridge().call("get_material", {"material_id": "NOPE"})
    assert env["ok"] is False
    assert env["error"]["code"] == "NOT_FOUND"


# -- catalog ---------------------------------------------------------------


def _spec(name="crm.get_account", version="1.0", **kw):
    base = dict(
        description="demo",
        input_schema={
            "type": "object",
            "properties": {"account_id": {"type": "string"}},
            "required": ["account_id"],
        },
    )
    base.update(kw)
    return ToolSpec(name=name, version=version, **base)


def test_catalog_latest_version_resolution():
    cat = CapabilityCatalog()
    cat.register(_spec(version="1.0"))
    cat.register(_spec(version="2.0"))
    assert cat.get("crm.get_account").version == "2.0"
    assert cat.get("crm.get_account", version="1.0").version == "1.0"


def test_catalog_unknown_tool_and_version():
    cat = CapabilityCatalog()
    with pytest.raises(CatalogError):
        cat.get("nope")
    cat.register(_spec())
    with pytest.raises(CatalogError):
        cat.get("crm.get_account", version="9.9")


def test_catalog_duplicate_registration_rejected():
    cat = CapabilityCatalog()
    cat.register(_spec())
    with pytest.raises(CatalogError):
        cat.register(_spec())


def test_catalog_deprecation_flow():
    cat = CapabilityCatalog()
    cat.register(_spec(version="1.0"))
    cat.register(_spec(version="2.0"))
    cat.deprecate("crm.get_account", "2.0", "use v3")
    # latest non-deprecated wins
    assert cat.get("crm.get_account").version == "1.0"
    with pytest.raises(CatalogError):
        cat.get("crm.get_account", version="2.0")
    spec = cat.get("crm.get_account", version="2.0", allow_deprecated=True)
    assert spec.deprecated is True


def test_catalog_call_validates_args():
    bridge = _echo_bridge()
    cat = CapabilityCatalog()
    cat.register_bridge_operations(
        bridge,
        [
            {
                "name": "echo",
                "operation": "ping_op",
                "description": "echo",
                "input_schema": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                    "required": ["x"],
                },
            }
        ],
    )
    ok = cat.call("demo-sys.echo", {"x": 5})
    assert ok["ok"] is True
    assert ok["tool_version"] == "1.0"
    bad = cat.call("demo-sys.echo", {"x": "not-an-int"})
    assert bad["ok"] is False
    assert bad["error"]["code"] == "INVALID_ARGS"


def test_catalog_deprecated_call_carries_notice():
    cat = CapabilityCatalog()
    cat.register(_spec(version="1.0", bridge=_echo_bridge(), operation="ping_op"))
    cat.deprecate("crm.get_account", "1.0", "migrate to v2")
    env = cat.call("crm.get_account", {"account_id": "ACME-001"}, allow_deprecated=True)
    assert "deprecation" in env
    assert "migrate to v2" in env["deprecation"]


def test_catalog_list_hides_deprecated_by_default():
    cat = CapabilityCatalog()
    cat.register(_spec(name="a.tool", version="1.0"))
    cat.register(_spec(name="b.tool", version="1.0"))
    cat.deprecate("a.tool", "1.0", "old")
    assert [s.name for s in cat.list()] == ["b.tool"]
    assert len(cat.list(include_deprecated=True)) == 2


def test_catalog_as_function_tools():
    cat = CapabilityCatalog()
    cat.register(_spec(version="1.0", bridge=_echo_bridge(), operation="ping_op"))
    tools = cat.as_function_tools()
    assert "crm.get_account" in tools
    env = tools["crm.get_account"]({"account_id": "ACME-001"})
    assert env["ok"] is True


# -- CDC --------------------------------------------------------------------


def _event(eid="e1", etype="order.created"):
    return LegacyEvent(event_id=eid, source="sap", event_type=etype,
                       payload={"order": "PO-1"})


def test_simulated_source_poll_drains():
    src = SimulatedEventSource([_event("e1"), _event("e2")])
    assert len(src.poll()) == 2
    assert src.poll() == []
    src.inject(_event("e3"))
    assert [e.event_id for e in src.poll()] == ["e3"]


def test_change_feed_dedupes_and_dispatches():
    src = SimulatedEventSource([_event("e1"), _event("e1")])
    feed = ChangeFeed(src)
    feed.subscribe("order.created",
                   lambda e: {"workflow": "supply_check", "input": e.payload})
    triggers = feed.poll_once()
    assert len(triggers) == 1
    assert triggers[0]["handled"] is True
    assert triggers[0]["trigger"]["workflow"] == "supply_check"
    assert feed.seen_count == 1


def test_change_feed_unhandled_event_record():
    feed = ChangeFeed(SimulatedEventSource([_event("e1", "weird.type")]))
    (trigger,) = feed.poll_once()
    assert trigger["handled"] is False
    assert "no handler" in trigger["reason"]


def test_change_feed_survives_handler_error():
    def boom(event):
        raise RuntimeError("boom")

    feed = ChangeFeed(SimulatedEventSource([_event("e1")]))
    feed.subscribe("order.created", boom)
    feed.subscribe("*", lambda e: {"workflow": "audit", "input": {}})
    triggers = feed.poll_once()
    assert any(t["handled"] is False and "boom" in t["reason"] for t in triggers)
    assert any(t["handled"] is True for t in triggers)


def test_change_feed_wildcard_handler():
    feed = ChangeFeed(SimulatedEventSource([_event("e1", "a"), _event("e2", "b")]))
    feed.subscribe("*", lambda e: {"workflow": "log", "input": {"t": e.event_type}})
    assert len(feed.poll_once()) == 2


def test_webhook_sign_verify_roundtrip():
    rx = WebhookReceiver(secret="s3cret")
    envelope = {"id": "wh-1", "type": "inventory.changed",
                "data": {"sku": "PF-200"}}
    event = rx.receive(envelope, rx.sign(envelope))
    assert event.event_id == "wh-1"
    assert event.event_type == "inventory.changed"
    assert event.payload == {"sku": "PF-200"}


def test_webhook_bad_signature_rejected():
    rx = WebhookReceiver(secret="s3cret")
    with pytest.raises(WebhookError):
        rx.receive({"id": "wh-1", "type": "t"}, "deadbeef")


def test_webhook_missing_field_rejected():
    rx = WebhookReceiver()
    envelope = {"id": "wh-1"}  # no type
    with pytest.raises(WebhookError):
        rx.receive(envelope, rx.sign(envelope))


# -- autonomy ------------------------------------------------------------------


def _policy(level, **kw):
    base = dict(workflow="sap_order_check", level=level,
                guardrails_required=True, audit_required=True,
                rollback_plan="reverse the PO in SAP", max_impact="medium")
    base.update(kw)
    return AutonomyPolicy(**base)


def test_l0_always_requires_approval():
    ctrl = AutonomyController()
    d = ctrl.decide(agent="supply_chain", action="forecast_demand",
                    policy=_policy(L0_MANUAL), impact="low")
    assert d["decision"] == "require_approval"


def test_l1_low_proceeds_high_needs_approval():
    ctrl = AutonomyController()
    assert ctrl.decide(agent="supply_chain", action="forecast_demand",
                       policy=_policy(L1_ASSIST), impact="low")["decision"] == "proceed"
    assert ctrl.decide(agent="supply_chain", action="forecast_demand",
                       policy=_policy(L1_ASSIST), impact="high")["decision"] == "require_approval"


def test_l2_requires_guardrails():
    ctrl = AutonomyController()
    d = ctrl.decide(agent="supply_chain", action="forecast_demand",
                    policy=_policy(L2_AUGMENT, guardrails_required=False), impact="low")
    assert d["decision"] == "deny"
    assert any("guardrails" in r for r in d["reasons"])


def test_l2_low_proceeds():
    ctrl = AutonomyController()
    d = ctrl.decide(agent="supply_chain", action="forecast_demand",
                    policy=_policy(L2_AUGMENT), impact="low")
    assert d["decision"] == "proceed"
    assert d["level"] == "L2-augment"


def test_l3_requires_audit_and_rollback():
    ctrl = AutonomyController()
    d = ctrl.decide(agent="supply_chain", action="forecast_demand",
                    policy=_policy(L3_AUTONOMOUS, rollback_plan=""), impact="low")
    assert d["decision"] == "deny"
    d2 = ctrl.decide(agent="supply_chain", action="forecast_demand",
                     policy=_policy(L3_AUTONOMOUS), impact="low")
    assert d2["decision"] == "proceed"


def test_l3_high_impact_still_needs_approval():
    ctrl = AutonomyController()
    d = ctrl.decide(agent="supply_chain", action="forecast_demand",
                    policy=_policy(L3_AUTONOMOUS, max_impact="high"), impact="high")
    assert d["decision"] == "require_approval"


def test_policy_deny_wins_over_autonomy():
    ctrl = AutonomyController()
    d = ctrl.decide(agent="supply_chain", action="place_order",  # denied in policy
                    policy=_policy(L3_AUTONOMOUS, max_impact="high"), impact="low")
    assert d["decision"] == "deny"


def test_impact_above_max_requires_approval():
    ctrl = AutonomyController()
    d = ctrl.decide(agent="supply_chain", action="forecast_demand",
                    policy=_policy(L2_AUGMENT, max_impact="low"), impact="medium")
    assert d["decision"] == "require_approval"


def test_promotion_eligible_when_criteria_met():
    policy = _policy(L1_ASSIST)
    history = WorkflowHistory(eval_scores=[0.95, 0.93], approvals=6, runs=25)
    eligible, reasons = promotion_eligible(policy, history)
    assert eligible is True
    assert reasons == []


def test_promotion_blocked_with_reasons():
    policy = _policy(L1_ASSIST)
    history = WorkflowHistory(eval_scores=[0.5], approvals=1, runs=2, incidents=1)
    eligible, reasons = promotion_eligible(policy, history)
    assert eligible is False
    assert len(reasons) >= 3  # score, approvals, runs, incidents


def test_promotion_l2_to_l3_needs_rollback():
    policy = _policy(L2_AUGMENT, rollback_plan="")
    history = WorkflowHistory(eval_scores=[0.99], approvals=10, runs=50)
    eligible, reasons = promotion_eligible(policy, history)
    assert eligible is False
    assert any("rollback" in r for r in reasons)


def test_promotion_at_top_of_ladder():
    eligible, reasons = promotion_eligible(
        _policy(L3_AUTONOMOUS), WorkflowHistory([1.0], 99, 99))
    assert eligible is False
    assert reasons == ["already at L3-autonomous (top of ladder)"]


def test_invalid_level_and_impact_rejected():
    with pytest.raises(ValueError):
        AutonomyPolicy(workflow="w", level=99)
    ctrl = AutonomyController()
    with pytest.raises(ValueError):
        ctrl.decide(agent="supply_chain", action="forecast_demand",
                    policy=_policy(L1_ASSIST), impact="extreme")
