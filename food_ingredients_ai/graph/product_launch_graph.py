"""Graph-based new-product launch flow.

Business scenario: launching a new clean-label product. R&D formulates
the product, supply chain checks demand and production feasibility, ESG
reviews the footprint, and the customer advisor assembles the launch
pack (pricing + tech sheet). If production is infeasible, the launch is
blocked instead of proceeding on hope.

Topology::

    formulate --> check_feasibility --(feasible)--> esg_review --> launch_pack --> done
                        |
                        +--(not feasible)--> blocked (terminal)

Feasibility is decided by the supply-chain scheduler: ``schedule_production``
raises ``ValueError`` when demand cannot be met within capacity and
shelf-life, which the node converts into the ``feasible`` flag. Every node
calls the same deterministic ``Agent.execute()`` paths the sequential
demos use; the graph only changes *control flow*. Runtime:
``food_ingredients_ai/graph/graph.py``.
"""

from __future__ import annotations

from typing import Any, Dict

from food_ingredients_ai.agents.customer_advisor import CustomerAdvisorAgent
from food_ingredients_ai.agents.esg import ESGAgent
from food_ingredients_ai.agents.rd_formulation import RDFormulationAgent
from food_ingredients_ai.agents.supply_chain import SupplyChainAgent
from food_ingredients_ai.graph.graph import Graph

LAUNCH_CLAIMS = ["clean label", "no artificial ingredients", "reduced sugar"]
LAUNCH_SKU = "PF-200"
NEED_DAY = 14
SHELF_LIFE_DAYS = 30


def run_product_launch_graph(
    formula_id: str = "sweet_bakery_cake",
    capacity_per_day: float = 100.0,
) -> Dict[str, Any]:
    """Run the product-launch graph end-to-end, offline and deterministic.

    ``capacity_per_day`` controls the scenario: enough capacity and the
    launch pack is produced; starve it (e.g. ``0.001``) and the scheduler
    cannot fit demand, so the graph terminates at ``blocked``.

    Returns the final state: ``formula_id``, ``feasible`` (bool),
    ``outcome``, and per-node results under ``formulation``,
    ``feasibility``, ``esg``, ``launch_pack``.
    """
    rd = RDFormulationAgent()
    supply = SupplyChainAgent()
    esg = ESGAgent()
    advisor = CustomerAdvisorAgent()

    def formulate(state: Dict[str, Any]) -> Dict[str, Any]:
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
        return {"formulation": result}

    def check_feasibility(state: Dict[str, Any]) -> Dict[str, Any]:
        forecast = supply.execute(
            "forecast_demand",
            {"skus": [LAUNCH_SKU], "periods": 4, "blackboard": {}},
        )
        weekly = forecast["forecasts"][LAUNCH_SKU]["forecast"]
        demand = [
            {"sku": LAUNCH_SKU, "qty": round(sum(weekly), 2), "need_day": NEED_DAY}
        ]
        try:
            schedule = supply.execute(
                "schedule_production",
                {
                    "demand": demand,
                    "capacity_per_day": capacity_per_day,
                    "shelf_life_days": SHELF_LIFE_DAYS,
                    "blackboard": {},
                },
            )
            feasible = True
        except ValueError as exc:
            schedule = {"error": str(exc)}
            feasible = False
        return {
            "feasibility": schedule,
            "feasible": feasible,
            "demand": demand,
            "forecast": forecast,
        }

    def esg_review(state: Dict[str, Any]) -> Dict[str, Any]:
        result = esg.execute("esg_report", {"blackboard": {}})
        return {"esg": result}

    def launch_pack(state: Dict[str, Any]) -> Dict[str, Any]:
        formula = state["formulation"]["reformulated_formula"]
        pricing = advisor.execute(
            "estimate_pricing",
            {
                "formula": formula,
                "valid_claims": list(LAUNCH_CLAIMS),
                "blackboard": {},
            },
        )
        validated = advisor.execute(
            "validate_customer_claims",
            {
                "formula": formula,
                "target_claims": list(LAUNCH_CLAIMS),
                "region": "NA",
                "blackboard": {},
            },
        )
        sheet = advisor.execute(
            "generate_tech_sheet",
            {
                "formula": formula,
                "claims": validated["claims"],
                "blackboard": {},
            },
        )
        return {
            "launch_pack": {
                "pricing": pricing,
                "validated_claims": validated,
                "tech_sheet": sheet,
            },
            "outcome": "launch_ready",
        }

    def blocked(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "outcome": "blocked",
            "reason": (
                "production infeasible at capacity_per_day="
                f"{capacity_per_day}: {state['feasibility'].get('error')}"
            ),
        }

    def _is_feasible(state: Dict[str, Any]) -> bool:
        return bool(state.get("feasible"))

    graph = Graph()
    graph.add_node("formulate", formulate)
    graph.add_node("check_feasibility", check_feasibility)
    graph.add_node("esg_review", esg_review)
    graph.add_node("launch_pack", launch_pack)
    graph.add_node("blocked", blocked)
    graph.add_edge("formulate", "check_feasibility")
    graph.add_edge("esg_review", "launch_pack")
    graph.add_conditional("check_feasibility", _is_feasible, "esg_review", "blocked")
    # "launch_pack" and "blocked" have no outgoing edge: terminal nodes.

    return graph.run({"formula_id": formula_id, "feasible": False})
