"""Graph-based agentic procurement flow (agentic ERP: finance & operations).

Business scenario: a plant raises a purchase requisition for an
ingredient. The supply-chain agent first validates the requested quantity
against forecast demand (is the spend justified?), then a policy node
compares the requisition total against the approval threshold. Below the
threshold the purchase order is created automatically; above it the
human-in-the-loop approval gate decides; a rejected requisition
terminates without a PO.

Topology::

    intake_requisition --> validate_demand --(justified)--> policy_check --(under threshold)--> create_po --> notify_supplier --> done
                                |                                    |
                                +--(not justified)--> held           +--(over threshold)--> hitl_approval --(approved)--> create_po
                                                                                                |
                                                                                                +--(rejected)--> rejected

All numbers are synthetic demo data. Every node is deterministic; the
graph runtime is the small stdlib-only implementation in
``food_ingredients_ai/graph/graph.py``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from food_ingredients_ai.agents.supply_chain import SupplyChainAgent
from food_ingredients_ai.governance.approvals import ApprovalGate
from food_ingredients_ai.graph.graph import Graph
from food_ingredients_ai.loops.hitl import hitl_gate

#: Synthetic catalog prices (USD per kg) — demo data, not real pricing.
CATALOG_PRICES_USD_PER_KG: Dict[str, float] = {
    "citric acid": 2.10,
    "sugar": 0.85,
    "natural flavor": 12.50,
    "starch": 1.40,
    "salt": 0.60,
}

DEFAULT_ITEM = "citric acid"
DEFAULT_QTY_KG = 5000.0
DEFAULT_THRESHOLD_USD = 10000.0
#: Requested qty is justified when it does not exceed the agent's
#: suggested purchase by more than this factor.
JUSTIFICATION_FACTOR = 1.1


def _unit_price(item: str) -> float:
    return CATALOG_PRICES_USD_PER_KG.get(item.lower(), 1.00)


def _po_id(item: str, qty_kg: float) -> str:
    slug = item.upper().replace(" ", "-")
    return f"PO-{slug}-{int(qty_kg)}"


def run_procurement_graph(
    item: str = DEFAULT_ITEM,
    qty_kg: float = DEFAULT_QTY_KG,
    approval_threshold_usd: float = DEFAULT_THRESHOLD_USD,
    on_hand_tonnes: float = 0.0,
    approver: Optional[ApprovalGate] = None,
) -> Dict[str, Any]:
    """Run the procurement flow end-to-end, offline and deterministic.

    ``on_hand_tonnes`` steers demand validation: with no stock on hand the
    requested quantity is justified against forecast demand; with ample
    stock the requisition is held. ``approver`` overrides the HITL gate's
    approver (pass ``ApprovalGate(auto_approve=False)`` to exercise the
    rejection path).

    Returns the final state: ``requisition``, ``demand_justified`` (bool),
    ``needs_approval`` (bool), ``outcome`` (one of ``"po_issued"``,
    ``"held"``, ``"rejected"``), and per-node results.
    """
    supply = SupplyChainAgent()
    sku = item.upper().replace(" ", "-")

    def intake_requisition(state: Dict[str, Any]) -> Dict[str, Any]:
        unit_price = _unit_price(item)
        total = round(qty_kg * unit_price, 2)
        return {
            "requisition": {
                "item": item,
                "sku": sku,
                "qty_kg": qty_kg,
                "unit_price_usd_per_kg": unit_price,
                "total_usd": total,
                "requester": "plant-ops",
                "cost_center": "CC-4200",
            }
        }

    def validate_demand(state: Dict[str, Any]) -> Dict[str, Any]:
        result = supply.execute(
            "optimize_inventory",
            {
                "inventory": {sku: {"on_hand_tonnes": on_hand_tonnes}},
                "forecasts_weekly": {sku: [10.0, 10.0, 10.0, 10.0]},
                "blackboard": {},
            },
        )
        suggested = sum(
            p.get("suggested_order_tonnes", 0.0)
            for p in result.get("purchases", [])
            if p.get("sku") == sku
        )
        requested_tonnes = qty_kg / 1000.0
        justified = requested_tonnes <= suggested * JUSTIFICATION_FACTOR
        return {
            "demand_check": result,
            "suggested_qty_tonnes": round(suggested, 3),
            "demand_justified": justified,
        }

    def policy_check(state: Dict[str, Any]) -> Dict[str, Any]:
        total = state["requisition"]["total_usd"]
        needs_approval = total > approval_threshold_usd
        return {
            "needs_approval": needs_approval,
            "policy": {
                "total_usd": total,
                "approval_threshold_usd": approval_threshold_usd,
                "rule": "over-threshold requisitions require human approval",
            },
        }

    def hitl_approval(state: Dict[str, Any]) -> Dict[str, Any]:
        gate_result = hitl_gate(
            "procurement_plan",
            {
                "summary": (
                    f"Purchase {qty_kg:.0f} kg of {item} for "
                    f"${state['requisition']['total_usd']:,.2f}"
                ),
                "requisition": state["requisition"],
            },
            approver=approver,
        )
        return {
            "approval": gate_result,
            "approved": gate_result["decision"] == "approved",
        }

    def create_po(state: Dict[str, Any]) -> Dict[str, Any]:
        req = state["requisition"]
        return {
            "purchase_order": {
                "po_id": _po_id(item, qty_kg),
                "item": req["item"],
                "qty_kg": req["qty_kg"],
                "unit_price_usd_per_kg": req["unit_price_usd_per_kg"],
                "total_usd": req["total_usd"],
                "supplier": "Acme Ingredients Co. (demo)",
                "lead_time_days": 7,
                "status": "created",
            }
        }

    def notify_supplier(state: Dict[str, Any]) -> Dict[str, Any]:
        po = state["purchase_order"]
        return {
            "supplier_notification": {
                "to": po["supplier"],
                "subject": f"New purchase order {po['po_id']}",
                "body": (
                    f"Please confirm {po['qty_kg']:.0f} kg of {po['item']} "
                    f"at ${po['unit_price_usd_per_kg']:.2f}/kg "
                    f"(total ${po['total_usd']:,.2f})."
                ),
            },
            "outcome": "po_issued",
        }

    def held(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "outcome": "held",
            "reason": (
                f"Requested {qty_kg:.0f} kg of {item} not justified by forecast "
                f"demand (suggested {state['suggested_qty_tonnes']} t); "
                "requisition held for planner review"
            ),
        }

    def rejected(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "outcome": "rejected",
            "reason": "human approval denied; no purchase order created",
        }

    def _justified(state: Dict[str, Any]) -> bool:
        return bool(state.get("demand_justified"))

    def _needs_approval(state: Dict[str, Any]) -> bool:
        return bool(state.get("needs_approval"))

    def _approved(state: Dict[str, Any]) -> bool:
        return bool(state.get("approved"))

    graph = Graph()
    graph.add_node("intake_requisition", intake_requisition)
    graph.add_node("validate_demand", validate_demand)
    graph.add_node("policy_check", policy_check)
    graph.add_node("hitl_approval", hitl_approval)
    graph.add_node("create_po", create_po)
    graph.add_node("notify_supplier", notify_supplier)
    graph.add_node("held", held)
    graph.add_node("rejected", rejected)
    graph.add_edge("intake_requisition", "validate_demand")
    graph.add_edge("create_po", "notify_supplier")
    graph.add_conditional("validate_demand", _justified, "policy_check", "held")
    graph.add_conditional("policy_check", _needs_approval, "hitl_approval", "create_po")
    graph.add_conditional("hitl_approval", _approved, "create_po", "rejected")
    # "notify_supplier", "held" and "rejected" have no outgoing edge: terminal nodes.

    return graph.run(
        {
            "item": item,
            "qty_kg": qty_kg,
            "demand_justified": False,
            "needs_approval": False,
            "approved": False,
        }
    )
