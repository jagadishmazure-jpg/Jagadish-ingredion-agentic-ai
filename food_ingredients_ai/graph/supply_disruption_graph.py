"""Graph-based supply-disruption response flow.

Business scenario: a key ingredient SKU is running low. The supply-chain
agent flags the shortage, R&D finds a clean-label substitute, ESG
re-scores the carbon footprint of the swap, and the customer advisor
drafts the customer notification as a tech sheet.

Topology::

    check_inventory --(shortage)--> find_substitute --> rescore_carbon --> notify_customer --> done
           |
           +--(no shortage)--> no_action (terminal)

Every node calls the same deterministic ``Agent.execute()`` paths the
sequential demos use, so the graph only changes *control flow*. The graph
runtime is the small stdlib-only implementation in
``food_ingredients_ai/graph/graph.py``.
"""

from __future__ import annotations

from typing import Any, Dict

from food_ingredients_ai.agents.customer_advisor import CustomerAdvisorAgent
from food_ingredients_ai.agents.esg import ESGAgent
from food_ingredients_ai.agents.rd_formulation import RDFormulationAgent
from food_ingredients_ai.agents.supply_chain import SupplyChainAgent
from food_ingredients_ai.graph.graph import Graph

DEFAULT_FORMULA_ID = "sweet_bakery_cake"
DEFAULT_WEEKLY_FORECAST = [10.0, 10.0, 10.0, 10.0]
NOTIFICATION_CLAIMS = ["clean label", "no artificial ingredients"]


def run_supply_disruption_graph(
    sku: str = "PF-200",
    formula_id: str = DEFAULT_FORMULA_ID,
    on_hand_tonnes: float = 0.5,
) -> Dict[str, Any]:
    """Run the supply-disruption response graph end-to-end, offline.

    ``on_hand_tonnes`` controls the scenario: below the reorder point a
    shortage is flagged and the full response chain runs; at or above it
    the graph terminates at ``no_action``.

    Returns the final state: ``sku``, ``shortage`` (bool), ``outcome``,
    and per-node results under ``inventory``, ``substitute``, ``carbon``,
    ``notification``.
    """
    supply = SupplyChainAgent()
    rd = RDFormulationAgent()
    esg = ESGAgent()
    advisor = CustomerAdvisorAgent()

    def check_inventory(state: Dict[str, Any]) -> Dict[str, Any]:
        result = supply.execute(
            "optimize_inventory",
            {
                "inventory": {sku: {"on_hand_tonnes": on_hand_tonnes}},
                "forecasts_weekly": {sku: list(DEFAULT_WEEKLY_FORECAST)},
                "blackboard": {},
            },
        )
        shortage = any(p["sku"] == sku for p in result["purchases"])
        return {"inventory": result, "shortage": shortage}

    def find_substitute(state: Dict[str, Any]) -> Dict[str, Any]:
        analysis = rd.execute(
            "analyze_ingredients", {"formula_id": formula_id, "blackboard": {}}
        )
        result = rd.execute(
            "suggest_substitutes",
            {
                "formula_id": formula_id,
                "blackboard": {"analyze_ingredients": analysis},
            },
        )
        return {"substitute": result}

    def rescore_carbon(state: Dict[str, Any]) -> Dict[str, Any]:
        result = esg.execute("calculate_carbon", {"blackboard": {}})
        return {"carbon": result}

    def notify_customer(state: Dict[str, Any]) -> Dict[str, Any]:
        reformulated = state["substitute"]["reformulated_formula"]
        validated = advisor.execute(
            "validate_customer_claims",
            {
                "formula": reformulated,
                "target_claims": list(NOTIFICATION_CLAIMS),
                "region": "NA",
                "blackboard": {},
            },
        )
        result = advisor.execute(
            "generate_tech_sheet",
            {
                "formula": reformulated,
                "claims": validated["claims"],
                "blackboard": {},
            },
        )
        return {
            "notification": result,
            "validated_claims": validated,
            "outcome": "customer_notified",
        }

    def no_action(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "outcome": "no_action",
            "reason": f"SKU {sku} on-hand ({on_hand_tonnes}t) at/above reorder point",
        }

    def _has_shortage(state: Dict[str, Any]) -> bool:
        return bool(state.get("shortage"))

    graph = Graph()
    graph.add_node("check_inventory", check_inventory)
    graph.add_node("find_substitute", find_substitute)
    graph.add_node("rescore_carbon", rescore_carbon)
    graph.add_node("notify_customer", notify_customer)
    graph.add_node("no_action", no_action)
    graph.add_edge("find_substitute", "rescore_carbon")
    graph.add_edge("rescore_carbon", "notify_customer")
    graph.add_conditional("check_inventory", _has_shortage, "find_substitute", "no_action")
    # "notify_customer" and "no_action" have no outgoing edge: terminal nodes.

    return graph.run({"sku": sku, "formula_id": formula_id, "shortage": False})
