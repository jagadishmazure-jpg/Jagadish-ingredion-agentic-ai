"""Graph-based quality-complaint triage flow.

Business scenario: a customer reports a quality problem with a batch.
The customer advisor logs the complaint (validating the claims in it),
supply chain traces the batch for spec anomalies, and — only if an
anomaly is found — R&D investigates the root cause, ESG confirms the
label claims still hold, and the advisor issues a corrective-action
note. A clean batch terminates early with ``no_issue_found``.

Topology::

    intake --> trace_batch --(anomaly)--> investigate --> confirm_claims --> corrective_note --> done
                    |
                    +--(no anomaly)--> no_issue (terminal)

Every node calls the same deterministic ``Agent.execute()`` paths the
sequential demos use, so the graph only changes *control flow*. The graph
runtime is the small stdlib-only implementation in
``ingredion_ai/graph/graph.py``.
"""

from __future__ import annotations

from typing import Any, Dict

from ingredion_ai.agents.customer_advisor import CustomerAdvisorAgent
from ingredion_ai.agents.esg import ESGAgent
from ingredion_ai.agents.rd_formulation import RDFormulationAgent
from ingredion_ai.agents.supply_chain import SupplyChainAgent
from ingredion_ai.data.loader import get_formula
from ingredion_ai.graph.graph import Graph

DEFAULT_FORMULA_ID = "sweet_bakery_cake"
COMPLAINT_CLAIMS = ["clean label", "no artificial ingredients"]
SPEC_LIMITS = {"viscosity_cp": (400.0, 600.0)}
NOMINAL_VISCOSITY_CP = 500.0
ANOMALOUS_VISCOSITY_CP = 950.0


def run_quality_issue_graph(
    batch_id: str = "B-1042",
    formula_id: str = DEFAULT_FORMULA_ID,
    inject_anomaly: bool = True,
) -> Dict[str, Any]:
    """Run the quality-triage graph end-to-end, offline and deterministic.

    ``inject_anomaly`` controls the scenario: ``True`` feeds an
    out-of-spec viscosity reading so the full investigation runs;
    ``False`` feeds an in-spec reading and the graph terminates at
    ``no_issue``.

    Returns the final state: ``batch_id``, ``anomaly_found`` (bool),
    ``outcome``, and per-node results under ``intake``, ``trace``,
    ``investigation``, ``esg``, ``corrective_note``.
    """
    advisor = CustomerAdvisorAgent()
    supply = SupplyChainAgent()
    rd = RDFormulationAgent()
    esg = ESGAgent()
    formula = get_formula(formula_id)

    def intake(state: Dict[str, Any]) -> Dict[str, Any]:
        result = advisor.execute(
            "validate_customer_claims",
            {
                "formula": formula,
                "target_claims": list(COMPLAINT_CLAIMS),
                "region": "NA",
                "blackboard": {},
            },
        )
        return {"intake": result}

    def trace_batch(state: Dict[str, Any]) -> Dict[str, Any]:
        value = ANOMALOUS_VISCOSITY_CP if inject_anomaly else NOMINAL_VISCOSITY_CP
        result = supply.execute(
            "detect_quality_anomalies",
            {
                "readings": [
                    {
                        "batch_id": batch_id,
                        "metric": "viscosity_cp",
                        "value": value,
                    }
                ],
                "spec_limits": dict(SPEC_LIMITS),
                "blackboard": {},
            },
        )
        return {"trace": result, "anomaly_found": result["anomaly_count"] > 0}

    def investigate(state: Dict[str, Any]) -> Dict[str, Any]:
        result = rd.execute(
            "analyze_ingredients", {"formula_id": formula_id, "blackboard": {}}
        )
        return {"investigation": result}

    def confirm_claims(state: Dict[str, Any]) -> Dict[str, Any]:
        result = esg.execute("esg_report", {"blackboard": {}})
        return {"esg": result}

    def corrective_note(state: Dict[str, Any]) -> Dict[str, Any]:
        result = advisor.execute(
            "generate_tech_sheet",
            {
                "formula": formula,
                "claims": state["intake"]["claims"],
                "blackboard": {},
            },
        )
        return {"corrective_note": result, "outcome": "corrective_action_issued"}

    def no_issue(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "outcome": "no_issue_found",
            "reason": f"batch {batch_id} readings within spec limits",
        }

    def _anomaly_found(state: Dict[str, Any]) -> bool:
        return bool(state.get("anomaly_found"))

    graph = Graph()
    graph.add_node("intake", intake)
    graph.add_node("trace_batch", trace_batch)
    graph.add_node("investigate", investigate)
    graph.add_node("confirm_claims", confirm_claims)
    graph.add_node("corrective_note", corrective_note)
    graph.add_node("no_issue", no_issue)
    graph.add_edge("intake", "trace_batch")
    graph.add_edge("investigate", "confirm_claims")
    graph.add_edge("confirm_claims", "corrective_note")
    graph.add_conditional("trace_batch", _anomaly_found, "investigate", "no_issue")
    # "corrective_note" and "no_issue" have no outgoing edge: terminal nodes.

    return graph.run({"batch_id": batch_id, "formula_id": formula_id})
