"""Graph-based "why did it change" metric insight flow.

Business scenario: a stakeholder asks "why did gross margin drop in Q3?"
The agent must answer from the *governed metric definition* — never by
inventing business logic from raw tables. It resolves the metric via the
semantic registry, attributes the change to drivers with lineage
citations, and composes a cited answer.

Topology::

    parse_question --> resolve_metric --(found)--> compute_value --> attribute_change --> compose_answer --> done
                            |
                            +--(not found)--> suggest_metrics (terminal)

Every node is deterministic and offline. The graph runtime is the small
stdlib-only implementation in ``food_ingredients_ai/graph/graph.py``.
"""

from __future__ import annotations

from typing import Any, Dict

from food_ingredients_ai.graph.graph import Graph
from food_ingredients_ai.semantics.agent_tools import DEMO_PERIOD_DATA
from food_ingredients_ai.semantics.explainer import explain_change, summarize
from food_ingredients_ai.semantics.lineage import explain_lineage
from food_ingredients_ai.semantics.registry import MetricRegistry, default_metric_registry

DEFAULT_PERIOD_A = "Q2"
DEFAULT_PERIOD_B = "Q3"


def run_metric_insight_graph(
    question: str = "why did gross margin drop in Q3?",
    period_a: str = DEFAULT_PERIOD_A,
    period_b: str = DEFAULT_PERIOD_B,
    registry: MetricRegistry | None = None,
) -> Dict[str, Any]:
    """Run the metric-insight graph end-to-end, offline and deterministic.

    Returns the final state: ``question``, ``metric_found`` (bool),
    ``outcome``, and per-node results under ``parsed``, ``metric``,
    ``values``, ``attribution``, ``answer`` (or ``suggestions``).
    """
    reg = registry or default_metric_registry()

    def parse_question(state: Dict[str, Any]) -> Dict[str, Any]:
        metric = reg.find_by_text(question)
        return {
            "parsed": {
                "question": question,
                "candidate": metric.name if metric else None,
            },
            "metric_found": metric is not None,
            "metric_name": metric.name if metric else None,
        }

    def compute_value(state: Dict[str, Any]) -> Dict[str, Any]:
        metric = reg.get(state["metric_name"])
        data = DEMO_PERIOD_DATA[state["metric_name"]]
        return {
            "metric": metric.to_dict(),
            "values": {
                "value_a": metric.evaluate(data[period_a]),
                "value_b": metric.evaluate(data[period_b]),
                "unit": metric.unit,
            },
        }

    def attribute_change(state: Dict[str, Any]) -> Dict[str, Any]:
        metric = reg.get(state["metric_name"])
        data = DEMO_PERIOD_DATA[state["metric_name"]]
        attribution = explain_change(
            metric, data[period_a], data[period_b],
            label_a=period_a, label_b=period_b,
        )
        attribution["lineage"] = explain_lineage(state["metric_name"], reg)
        return {"attribution": attribution}

    def compose_answer(state: Dict[str, Any]) -> Dict[str, Any]:
        attribution = state["attribution"]
        answer = summarize(attribution)
        return {
            "answer": answer,
            "citations": [
                attribution["lineage"]["citation"],
                *(d["cites"] for d in attribution["drivers"]),
            ],
            "outcome": "answered",
        }

    def suggest_metrics(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "outcome": "metric_not_found",
            "suggestions": reg.list(),
            "reason": (
                f"Could not resolve a governed metric from {question!r}. "
                "Available governed metrics are listed under 'suggestions'."
            ),
        }

    def _found(state: Dict[str, Any]) -> bool:
        return bool(state.get("metric_found"))

    graph = Graph()
    graph.add_node("parse_question", parse_question)
    graph.add_node("compute_value", compute_value)
    graph.add_node("attribute_change", attribute_change)
    graph.add_node("compose_answer", compose_answer)
    graph.add_node("suggest_metrics", suggest_metrics)
    graph.add_conditional("parse_question", _found, "compute_value", "suggest_metrics")
    graph.add_edge("compute_value", "attribute_change")
    graph.add_edge("attribute_change", "compose_answer")
    # "compose_answer" and "suggest_metrics" have no outgoing edge: terminal.

    return graph.run(
        {"question": question, "metric_found": False, "metric_name": None}
    )
