"""Tests for the cross-vendor A2A handoff (vendor risk agent)."""


from food_ingredients_ai.graph.vendor_risk_graph import (
    HIGH_RISK_SUPPLIER,
    LOW_RISK_SUPPLIER,
    run_vendor_risk_graph,
)
from food_ingredients_ai.interop.a2a import A2AAdapter
from food_ingredients_ai.interop.auth import issue_token
from food_ingredients_ai.interop.vendor_agents import (
    VENDOR_AGENT_KEY,
    VENDOR_SCOPE,
    VENDOR_SKILL_ID,
    build_vendor_card,
    register_vendor_agent,
    score_supplier_risk,
    vendor_adapter,
    vendor_risk_executor,
)


def _adapter():
    return register_vendor_agent(A2AAdapter(executor=vendor_risk_executor))


def _token(scopes):
    return issue_token("svc:procurement-agent", scopes, ttl_seconds=300)


# -- vendor risk engine --------------------------------------------------------


def test_score_supplier_risk_deterministic():
    a = score_supplier_risk(10, 1, "medium")
    b = score_supplier_risk(10, 1, "medium")
    assert a == b


def test_low_risk_supplier_scores_low():
    r = score_supplier_risk(
        LOW_RISK_SUPPLIER["years_in_business"],
        LOW_RISK_SUPPLIER["past_defaults"],
        LOW_RISK_SUPPLIER["country_tier"],
    )
    assert r["risk_tier"] == "low"
    assert r["risk_score"] < 30


def test_high_risk_supplier_scores_high():
    r = score_supplier_risk(
        HIGH_RISK_SUPPLIER["years_in_business"],
        HIGH_RISK_SUPPLIER["past_defaults"],
        HIGH_RISK_SUPPLIER["country_tier"],
    )
    assert r["risk_tier"] == "high"
    assert r["risk_score"] > 60


def test_medium_risk_supplier_scores_medium():
    r = score_supplier_risk(10, 0, "medium")
    assert r["risk_tier"] == "medium"


def test_risk_report_cites_inputs():
    r = score_supplier_risk(5, 2, "high")
    assert "5" in r["report"] and "2" in r["report"]
    assert r["inputs"]["country_tier"] == "high"


def test_unknown_country_tier_defaults_to_low():
    r = score_supplier_risk(10, 0, "antarctica")
    assert r["inputs"]["country_tier"] == "low"


# -- vendor card discovery -----------------------------------------------------


def test_vendor_card_discoverable_with_skills_and_scopes():
    card = build_vendor_card().to_dict()
    assert card["name"] == "vendor-risk-agent"
    assert card["skills"][0]["id"] == VENDOR_SKILL_ID
    assert card["authentication"]["skillScopes"][VENDOR_SKILL_ID] == [VENDOR_SCOPE]


def test_vendor_card_registered_on_adapter():
    adapter = _adapter()
    card = adapter.get_agent_card(VENDOR_AGENT_KEY)
    assert card["name"] == "vendor-risk-agent"


def test_vendor_message_send_requires_token():
    resp = _adapter().message_send(
        VENDOR_AGENT_KEY, "credit check", token=None, skill_id=VENDOR_SKILL_ID
    )
    assert resp["error"]["code"] == 401


def test_vendor_message_send_wrong_scope_rejected():
    token = _token(["formulation:read"])
    resp = _adapter().message_send(
        VENDOR_AGENT_KEY, "credit check", token=token, skill_id=VENDOR_SKILL_ID
    )
    assert resp["error"]["code"] == 403


def test_vendor_message_send_unknown_agent():
    resp = _adapter().message_send("nope", "hi", token=_token([VENDOR_SCOPE]))
    assert "error" in resp


def test_vendor_message_send_returns_risk_artifacts_with_caller_identity():
    adapter = _adapter()
    resp = adapter.message_send(
        VENDOR_AGENT_KEY,
        "credit check",
        context={"supplier": LOW_RISK_SUPPLIER},
        token=_token([VENDOR_SCOPE]),
        skill_id=VENDOR_SKILL_ID,
    )
    task = resp["task"]
    assert task["status"]["state"] == "completed"
    names = {a["name"] for a in task["artifacts"]}
    assert "risk_assessment" in names
    assert task["caller"]["subject"] == "svc:procurement-agent"
    assert VENDOR_SCOPE in task["caller"]["scopes"]


def test_vendor_task_tracking_via_tasks_get():
    adapter = _adapter()
    token = _token([VENDOR_SCOPE])
    task_id = adapter.message_send(
        VENDOR_AGENT_KEY,
        "credit check",
        context={"supplier": LOW_RISK_SUPPLIER},
        token=token,
        skill_id=VENDOR_SKILL_ID,
    )["task"]["id"]
    tracked = adapter.tasks_get(task_id, token=token)
    assert tracked["task"]["id"] == task_id
    assert tracked["task"]["status"]["state"] == "completed"


def test_vendor_executor_handles_missing_supplier_gracefully():
    result = vendor_risk_executor("credit check", {})
    assert result["risk_assessment"]["risk_tier"] == "medium"  # 50 -> medium
    assert result["supplier_name"] == "unknown"


# -- end-to-end graph ----------------------------------------------------------


def test_low_risk_supplier_continues_to_procurement():
    state = run_vendor_risk_graph(supplier=LOW_RISK_SUPPLIER)
    assert state["risk_tier"] == "low"
    assert state["outcome"] == "po_issued"
    assert state["procurement"]["purchase_order"]["status"] == "created"
    # Audit trail of the cross-agent delegation.
    assert len(state["a2a_calls"]) == 1
    call = state["a2a_calls"][0]
    assert call["agent"] == VENDOR_AGENT_KEY
    assert call["skill"] == VENDOR_SKILL_ID
    assert call["caller"]["subject"] == "svc:procurement-agent"
    assert call["risk_tier"] == "low"


def test_medium_risk_supplier_continues_to_procurement():
    supplier = dict(LOW_RISK_SUPPLIER, years_in_business=10, country_tier="medium")
    state = run_vendor_risk_graph(supplier=supplier)
    assert state["risk_tier"] == "medium"
    assert state["outcome"] == "po_issued"


def test_high_risk_supplier_blocks_requisition_with_cited_report():
    state = run_vendor_risk_graph(supplier=HIGH_RISK_SUPPLIER)
    assert state["risk_tier"] == "high"
    assert state["outcome"] == "risk_blocked"
    assert "FlyByNight" in state["reason"]
    assert "HIGH risk" in state["reason"]
    # The vendor's cited report is attached to the blocked state.
    assert state["risk_assessment"]["report"] in state["reason"]
    # No PO was created on the blocked branch.
    assert "procurement" not in state


def test_vendor_error_terminal_state():
    # Force an auth failure by making the graph's token invalid: patch the
    # supplier through but call the adapter directly with a bad token.
    adapter = _adapter()
    resp = adapter.message_send(
        VENDOR_AGENT_KEY,
        "credit check",
        context={"supplier": LOW_RISK_SUPPLIER},
        token="garbage",
        skill_id=VENDOR_SKILL_ID,
    )
    assert resp["error"]["code"] == 401


def test_graph_all_paths_terminate():
    for supplier in (LOW_RISK_SUPPLIER, HIGH_RISK_SUPPLIER):
        state = run_vendor_risk_graph(supplier=supplier)
        assert state["outcome"] in ("po_issued", "risk_blocked")


def test_vendor_adapter_factory_wires_card_and_executor():
    adapter = vendor_adapter()
    assert adapter.get_agent_card(VENDOR_AGENT_KEY)["name"] == "vendor-risk-agent"
    resp = adapter.message_send(
        VENDOR_AGENT_KEY,
        "credit check",
        context={"supplier": LOW_RISK_SUPPLIER},
        token=_token([VENDOR_SCOPE]),
        skill_id=VENDOR_SKILL_ID,
    )
    assert resp["task"]["status"]["state"] == "completed"
