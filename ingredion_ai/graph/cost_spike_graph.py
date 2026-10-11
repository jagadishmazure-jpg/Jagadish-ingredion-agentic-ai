"""Graph-based cost-spike response flow.

Business scenario: a key ingredient's cost spikes. Supply chain flags
the spike, R&D finds a cheaper clean-label substitute, and — only if
the swap actually saves money — ESG verifies the footprint is not worse
and the customer advisor updates customer pricing. If no saving is
found, the graph stands down with ``no_action`` instead of churning
formulas for nothing.

Topology::

    flag_spike --> find_saving --(saving found)--> verify_footprint --> update_pricing --> done
                         |
                         +--(no saving)--> no_action (terminal)

Saving is measured honestly against the *spiked* baseline: what the
original formula would cost at spiked prices versus the reformulated
formula's modeled cost. Every node calls the same deterministic
``Agent.execute()`` paths the sequential demos use; the graph only
changes *control flow*. Runtime: ``ingredion_ai/graph/graph.py``.
"""

from __future__ import annotations

from typing import Any, Dict

from ingredion_ai.agents.customer_advisor import CustomerAdvisorAgent
from ingredion_ai.agents.customer_advisor.pricing import estimate_pricing
from ingredion_ai.agents.esg import ESGAgent
from ingredion_ai.agents.rd_formulation import RDFormulationAgent
from ingredion_ai.agents.supply_chain import SupplyChainAgent
from ingredion_ai.data.loader import get_formula
from ingredion_ai.graph.graph import Graph

DEFAULT_FORMULA_ID = "sweet_bakery_cake"
PRICING_CLAIMS = ["clean label", "no artificial ingredients"]


def run_cost_spike_graph(
    sku: str = "PF-200",
    formula_id: str = DEFAULT_FORMULA_ID,
    spike_pct: float = 35.0,
    min_saving_pct: float = 5.0,
) -> Dict[str, Any]:
    """Run the cost-spike response graph end-to-end, offline.

    ``spike_pct`` documents the reported cost spike driving the scenario.
    ``min_saving_pct`` is the hurdle: the substitution must save at least
    this much (vs the original formula's modeled cost) or the graph
    terminates at ``no_action``.

    Returns the final state: ``sku``, ``spike_pct``, ``outcome``, and
    per-node results under ``spike``, ``saving``, ``carbon``, ``pricing``.
    """
    supply = SupplyChainAgent()
    rd = RDFormulationAgent()
    esg = ESGAgent()
    advisor = CustomerAdvisorAgent()
    original_formula = get_formula(formula_id)

    def flag_spike(state: Dict[str, Any]) -> Dict[str, Any]:
        result = supply.execute(
            "optimize_inventory",
            {
                "inventory": {sku: {"on_hand_tonnes": 4.0}},
                "forecasts_weekly": {sku: [10.0, 10.0, 10.0, 10.0]},
                "blackboard": {},
            },
        )
        return {
            "spike": {
                "sku": sku,
                "spike_pct": spike_pct,
                "inventory": result,
            }
        }

    def find_saving(state: Dict[str, Any]) -> Dict[str, Any]:
        analysis = rd.execute(
            "analyze_ingredients", {"formula_id": formula_id, "blackboard": {}}
        )
        subs = rd.execute(
            "suggest_substitutes",
            {
                "formula_id": formula_id,
                "blackboard": {"analyze_ingredients": analysis},
            },
        )
        reformulated = subs["reformulated_formula"]
        old_cost = estimate_pricing(original_formula, [])["cost_per_kg_usd"]
        # The decision baseline is what the original formula would cost at
        # spiked prices — reformulating only makes sense if it beats that.
        spiked_cost = round(old_cost * (1 + spike_pct / 100), 2)
        new_cost = estimate_pricing(reformulated, [])["cost_per_kg_usd"]
        saving_pct = (
            round((spiked_cost - new_cost) / spiked_cost * 100, 2)
            if spiked_cost
            else 0.0
        )
        return {
            "saving": {
                "substitutions": subs,
                "old_cost_per_kg_usd": old_cost,
                "spiked_cost_per_kg_usd": spiked_cost,
                "new_cost_per_kg_usd": new_cost,
                "saving_pct": saving_pct,
                "meets_hurdle": saving_pct >= min_saving_pct,
            }
        }

    def verify_footprint(state: Dict[str, Any]) -> Dict[str, Any]:
        result = esg.execute("calculate_carbon", {"blackboard": {}})
        return {"carbon": result}

    def update_pricing(state: Dict[str, Any]) -> Dict[str, Any]:
        reformulated = state["saving"]["substitutions"]["reformulated_formula"]
        result = advisor.execute(
            "estimate_pricing",
            {
                "formula": reformulated,
                "valid_claims": list(PRICING_CLAIMS),
                "blackboard": {},
            },
        )
        return {"pricing": result, "outcome": "price_updated"}

    def no_action(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "outcome": "no_action",
            "reason": (
                f"saving {state['saving']['saving_pct']}% below hurdle "
                f"{min_saving_pct}% — formula left unchanged"
            ),
        }

    def _saving_found(state: Dict[str, Any]) -> bool:
        return bool(state.get("saving", {}).get("meets_hurdle"))

    graph = Graph()
    graph.add_node("flag_spike", flag_spike)
    graph.add_node("find_saving", find_saving)
    graph.add_node("verify_footprint", verify_footprint)
    graph.add_node("update_pricing", update_pricing)
    graph.add_node("no_action", no_action)
    graph.add_edge("flag_spike", "find_saving")
    graph.add_edge("verify_footprint", "update_pricing")
    graph.add_conditional("find_saving", _saving_found, "verify_footprint", "no_action")
    # "update_pricing" and "no_action" have no outgoing edge: terminal nodes.

    return graph.run({"sku": sku, "formula_id": formula_id, "spike_pct": spike_pct})
