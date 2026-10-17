"""Graph-based variant of the reformulation demo.

Topology::

    analyze -> substitute -> validate --(invalid claims AND revisits left)--> revise_substitutions
                                 |                                              |
                                 +--(else)--> predict -> done                  |
                                                ^------------------------------+

Every node calls the same deterministic ``RDFormulationAgent.execute()``
paths the sequential demo uses (same payload/blackboard shapes as
``food_ingredients_ai/framework/tools.py``), so results are byte-identical to the
linear pipeline — the graph only changes *control flow*, adding a bounded
revise-and-revalidate cycle.

Cycle semantics: after ``validate``, the conditional predicate routes back
to ``revise_substitutions`` while any label claim is invalid *and* fewer
than ``max_revisits`` revisions have happened. The revise node re-runs the
deterministic substitution path (idempotent in this offline demo — a real
deployment would take corrective action such as relaxing a constraint or
picking the next-best candidate) and bumps the ``revisits`` counter, so the
cycle always terminates: either claims converge or the revisit budget is
exhausted and the graph proceeds to ``predict``.

The node/edge/conditional vocabulary mirrors the framework
``WorkflowBuilder`` sequential and conditional concepts; the graph runtime
is the small stdlib-only implementation in
``food_ingredients_ai/graph/graph.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from food_ingredients_ai.agents.rd_formulation import RDFormulationAgent
from food_ingredients_ai.graph.graph import Graph

DEFAULT_TARGET_CLAIMS = ["no artificial ingredients", "reduced sugar", "natural"]


def run_reformulation_graph(
    formula_id: str = "sweet_bakery_cake",
    target_claims: Optional[List[str]] = None,
    region: str = "NA",
    max_revisits: int = 2,
) -> Dict[str, Any]:
    """Run the reformulation graph end-to-end, offline and deterministic.

    Returns the final state (blackboard-style): ``formula_id``,
    ``target_claims``, ``region``, ``revisits``, and per-node results under
    ``analyze``, ``substitute``, ``validate``, ``invalid_claims``, ``predict``.
    """
    rd = RDFormulationAgent()
    claims = list(target_claims) if target_claims else list(DEFAULT_TARGET_CLAIMS)

    def _payload(blackboard: Dict[str, Any]) -> Dict[str, Any]:
        # Same shape as food_ingredients_ai/framework/tools.py: task names double as
        # blackboard keys.
        return {
            "formula_id": formula_id,
            "target_claims": claims,
            "region": region,
            "blackboard": blackboard,
        }

    def analyze(state: Dict[str, Any]) -> Dict[str, Any]:
        result = rd.execute("analyze_ingredients", _payload({}))
        return {"analyze": result}

    def substitute(state: Dict[str, Any]) -> Dict[str, Any]:
        result = rd.execute(
            "suggest_substitutes",
            _payload({"analyze_ingredients": state["analyze"]}),
        )
        return {"substitute": result}

    def validate(state: Dict[str, Any]) -> Dict[str, Any]:
        result = rd.execute(
            "validate_claims",
            _payload(
                {
                    "analyze_ingredients": state["analyze"],
                    "suggest_substitutes": state["substitute"],
                }
            ),
        )
        invalid = [c["claim"] for c in result["claims"] if not c["valid"]]
        return {"validate": result, "invalid_claims": invalid}

    def revise_substitutions(state: Dict[str, Any]) -> Dict[str, Any]:
        revisits = state.get("revisits", 0) + 1
        result = rd.execute(
            "suggest_substitutes",
            _payload({"analyze_ingredients": state["analyze"]}),
        )
        return {
            "substitute": result,
            "revisits": revisits,
            "revision_notes": (
                f"revision {revisits}/{max_revisits}: re-ran substitution path "
                f"for invalid claims {state.get('invalid_claims', [])}"
            ),
        }

    def predict(state: Dict[str, Any]) -> Dict[str, Any]:
        result = rd.execute(
            "predict_texture_shelf_life",
            _payload({"suggest_substitutes": state["substitute"]}),
        )
        return {"predict": result}

    def _needs_revision(state: Dict[str, Any]) -> bool:
        return bool(state.get("invalid_claims")) and state.get("revisits", 0) < max_revisits

    graph = Graph()
    graph.add_node("analyze", analyze)
    graph.add_node("substitute", substitute)
    graph.add_node("validate", validate)
    graph.add_node("revise_substitutions", revise_substitutions)
    graph.add_node("predict", predict)
    graph.add_edge("analyze", "substitute")
    graph.add_edge("substitute", "validate")
    graph.add_edge("revise_substitutions", "validate")  # back-edge: the cycle
    graph.add_conditional("validate", _needs_revision, "revise_substitutions", "predict")
    # "predict" has no outgoing edge: terminal node.

    return graph.run(
        {
            "formula_id": formula_id,
            "target_claims": claims,
            "region": region,
            "revisits": 0,
        }
    )
