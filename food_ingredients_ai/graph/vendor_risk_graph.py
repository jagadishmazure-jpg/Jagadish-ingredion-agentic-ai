"""Cross-vendor A2A handoff: procurement delegates to a vendor risk agent.

Business scenario: before raising a purchase order, the enterprise
procurement agent delegates a supplier credit check to a *third-party*
vendor risk agent (Dun & Bradstreet-style) over the A2A protocol. The
vendor's verdict branches the workflow: low/medium risk continues into
the existing procurement flow; high risk blocks the requisition with the
vendor's cited report.

Topology::

    discover_vendor --> risk_check --(low/medium risk)--> procurement_handoff --> done
                           |
                           +--(high risk)--> risk_blocked
                           |
                           +--(vendor error)--> vendor_error

The full A2A sequence is exercised: card discovery -> bearer auth ->
``message/send`` delegation -> ``tasks/get`` tracking -> artifacts. Every
cross-agent call records the caller identity for the audit trail. All
data is synthetic demo data; the vendor is simulated in-process but the
protocol path (auth, scopes, task lifecycle) is the real adapter code.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from food_ingredients_ai.governance.approvals import ApprovalGate
from food_ingredients_ai.graph.graph import Graph
from food_ingredients_ai.graph.procurement_graph import run_procurement_graph
from food_ingredients_ai.interop.a2a import A2AAdapter
from food_ingredients_ai.interop.auth import issue_token
from food_ingredients_ai.interop.vendor_agents import (
    VENDOR_AGENT_KEY,
    VENDOR_SCOPE,
    VENDOR_SKILL_ID,
    register_vendor_agent,
    vendor_adapter,
    vendor_risk_executor,
)

#: Demo suppliers. Scores are deterministic; see
#: ``food_ingredients_ai/interop/vendor_agents.py`` for the formula.
LOW_RISK_SUPPLIER: Dict[str, Any] = {
    "name": "Acme Ingredients Co.",
    "years_in_business": 22,
    "past_defaults": 0,
    "country_tier": "low",
}
HIGH_RISK_SUPPLIER: Dict[str, Any] = {
    "name": "FlyByNight Trading Ltd.",
    "years_in_business": 1,
    "past_defaults": 3,
    "country_tier": "high",
}

CALLER_SUBJECT = "svc:procurement-agent"


def _assessment_from_task(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for artifact in task.get("artifacts", []):
        if artifact.get("name") == "risk_assessment":
            for part in artifact.get("parts", []):
                if part.get("type") == "data":
                    return part.get("data")
    return None


def run_vendor_risk_graph(
    supplier: Optional[Dict[str, Any]] = None,
    item: str = "citric acid",
    qty_kg: float = 5000.0,
    approval_threshold_usd: float = 20000.0,
    approver: Optional[ApprovalGate] = None,
) -> Dict[str, Any]:
    """Run the cross-vendor risk-check flow end-to-end, offline.

    Returns the final state: ``risk_assessment``, ``risk_tier``,
    ``a2a_calls`` (audit trail of the cross-agent delegation), ``outcome``
    (one of ``"po_issued"``/``"held"``/``"rejected"`` from procurement,
    ``"risk_blocked"``, or ``"vendor_error"``), and per-node results.
    """
    supplier = dict(supplier) if supplier else dict(LOW_RISK_SUPPLIER)

    def discover_vendor(state: Dict[str, Any]) -> Dict[str, Any]:
        # The vendor agent is reached through the standard adapter; its
        # card is registered alongside the enterprise's own cards.
        adapter = register_vendor_agent(A2AAdapter(executor=vendor_risk_executor))
        card = adapter.get_agent_card(VENDOR_AGENT_KEY)
        token = issue_token(CALLER_SUBJECT, [VENDOR_SCOPE], ttl_seconds=300)
        return {
            "_adapter": adapter,
            "_token": token,
            "vendor_card": card,
            "a2a_calls": [],
        }

    def risk_check(state: Dict[str, Any]) -> Dict[str, Any]:
        adapter = state["_adapter"]
        token = state["_token"]
        # message/send: delegate the credit check to the vendor agent.
        resp = adapter.message_send(
            VENDOR_AGENT_KEY,
            f"credit check for supplier '{supplier['name']}'",
            context={"supplier": supplier},
            token=token,
            skill_id=VENDOR_SKILL_ID,
        )
        if "error" in resp:
            return {"vendor_error": resp["error"], "risk_tier": None}
        task = resp["task"]
        # tasks/get: track the delegated task (synchronous in the demo).
        tracked = adapter.tasks_get(task["id"], token=token)
        final_task = tracked.get("task", task)
        assessment = _assessment_from_task(final_task)
        if assessment is None:
            return {
                "vendor_error": {"code": -32000, "message": "no risk artifact"},
                "risk_tier": None,
            }
        call_record = {
            "task_id": final_task["id"],
            "agent": VENDOR_AGENT_KEY,
            "skill": VENDOR_SKILL_ID,
            # Identity attribution: who called across the vendor boundary.
            "caller": final_task.get("caller"),
            "risk_tier": assessment["risk_tier"],
            "risk_score": assessment["risk_score"],
        }
        return {
            "risk_assessment": assessment,
            "risk_tier": assessment["risk_tier"],
            "vendor_task": final_task,
            "a2a_calls": state["a2a_calls"] + [call_record],
        }

    def procurement_handoff(state: Dict[str, Any]) -> Dict[str, Any]:
        # Branch A: vendor cleared the supplier — hand off to the
        # existing procurement flow (budget check -> PO/approval).
        procurement = run_procurement_graph(
            item=item,
            qty_kg=qty_kg,
            approval_threshold_usd=approval_threshold_usd,
            approver=approver,
        )
        return {
            "procurement": procurement,
            "outcome": procurement.get("outcome"),
            "handoff": (
                f"vendor risk {state['risk_tier']} "
                f"(score {state['risk_assessment']['risk_score']}); "
                f"procurement outcome: {procurement.get('outcome')}"
            ),
        }

    def risk_blocked(state: Dict[str, Any]) -> Dict[str, Any]:
        # Branch B: high risk — block, citing the vendor's report.
        assessment = state["risk_assessment"]
        return {
            "outcome": "risk_blocked",
            "reason": (
                f"Requisition blocked: vendor risk agent scored supplier "
                f"'{supplier['name']}' as HIGH risk "
                f"({assessment['risk_score']}/100). Cited report: "
                f"{assessment['report']}"
            ),
        }

    def vendor_error(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "outcome": "vendor_error",
            "reason": f"vendor risk check failed: {state['vendor_error']}",
        }

    def _ok(state: Dict[str, Any]) -> bool:
        return state.get("risk_tier") is not None

    def _cleared(state: Dict[str, Any]) -> bool:
        return state.get("risk_tier") in ("low", "medium")

    # Tier routing is expressed as a node so the graph vocabulary stays
    # nodes/edges/conditionals only.
    def route_tier(state: Dict[str, Any]) -> Dict[str, Any]:
        return {"tier_routed": state["risk_tier"]}

    graph = Graph()
    graph.add_node("discover_vendor", discover_vendor)
    graph.add_node("risk_check", risk_check)
    graph.add_node("route_tier", route_tier)
    graph.add_node("procurement_handoff", procurement_handoff)
    graph.add_node("risk_blocked", risk_blocked)
    graph.add_node("vendor_error", vendor_error)
    graph.add_edge("discover_vendor", "risk_check")
    graph.add_conditional("risk_check", _ok, "route_tier", "vendor_error")
    graph.add_conditional(
        "route_tier", _cleared, "procurement_handoff", "risk_blocked"
    )
    # "procurement_handoff", "risk_blocked", "vendor_error" are terminal.

    return graph.run(
        {
            "supplier": supplier,
            "risk_tier": None,
            "outcome": None,
        }
    )


# Re-export the demo supplier fixtures and the default adapter factory.
__all__ = [
    "run_vendor_risk_graph",
    "LOW_RISK_SUPPLIER",
    "HIGH_RISK_SUPPLIER",
    "vendor_adapter",
]
