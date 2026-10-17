"""Tests for the graph orchestration package.

All offline and deterministic; the end-to-end test uses the real
RDFormulationAgent execute() paths via run_reformulation_graph.
"""

import pytest

from food_ingredients_ai.graph import Graph, run_reformulation_graph

# --- Graph runtime -----------------------------------------------------------


def _linear_graph():
    g = Graph()
    g.add_node("a", lambda s: {"order": s.get("order", []) + ["a"]})
    g.add_node("b", lambda s: {"order": s["order"] + ["b"]})
    g.add_node("c", lambda s: {"order": s["order"] + ["c"]})
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    return g


def test_linear_chain_executes_in_order():
    out = _linear_graph().run({})
    assert out["order"] == ["a", "b", "c"]


def test_node_result_merged_into_state():
    g = Graph()
    g.add_node("one", lambda s: {"x": 1})
    g.add_node("two", lambda s: {"y": s["x"] + 1})
    g.add_edge("one", "two")
    out = g.run({"seed": True})
    assert out == {"seed": True, "x": 1, "y": 2}


def test_conditional_routes_true_branch():
    g = Graph()
    g.add_node("start", lambda s: {"flag": s["go"]})
    g.add_node("yes", lambda s: {"taken": "yes"})
    g.add_node("no", lambda s: {"taken": "no"})
    g.add_conditional("start", lambda s: s["flag"], "yes", "no")
    assert g.run({"go": True})["taken"] == "yes"


def test_conditional_routes_false_branch():
    g = Graph()
    g.add_node("start", lambda s: {"flag": s["go"]})
    g.add_node("yes", lambda s: {"taken": "yes"})
    g.add_node("no", lambda s: {"taken": "no"})
    g.add_conditional("start", lambda s: s["flag"], "yes", "no")
    assert g.run({"go": False})["taken"] == "no"


def test_cycle_executes_bounded_times_then_exits():
    g = Graph()
    g.add_node("tick", lambda s: {"n": s.get("n", 0) + 1})
    g.add_node("done", lambda s: {"finished": True})
    # Self-loop back-edge, exited once the conditional predicate is true.
    g.add_conditional("tick", lambda s: s["n"] >= 3, "done", "tick")
    out = g.run({})
    assert out["n"] == 3
    assert out["finished"] is True


def test_max_steps_guard_raises_on_runaway_cycle():
    g = Graph()
    g.add_node("spin", lambda s: {"spins": s.get("spins", 0) + 1})
    g.add_edge("spin", "spin")
    with pytest.raises(RuntimeError, match="max_steps=5 exceeded"):
        g.run({}, max_steps=5)


def test_empty_graph_raises():
    with pytest.raises(ValueError, match="empty graph"):
        Graph().run({})


# --- reformulation graph (domain-wired) ---------------------------------------


def test_reformulation_graph_runs_offline_end_to_end():
    state = run_reformulation_graph()
    for key in ("analyze", "substitute", "validate", "predict"):
        assert key in state, f"missing node result: {key}"
    assert state["formula_id"] == "sweet_bakery_cake"
    assert state["revisits"] == 2  # bounded retry budget exhausted deterministically
    assert state["invalid_claims"] == ["reduced sugar", "natural"]


def test_reformulation_graph_result_shapes():
    state = run_reformulation_graph()
    assert state["analyze"]["flagged_count"] == 7
    assert len(state["substitute"]["substitutions"]) == 7
    assert state["validate"]["claims"] and all(
        {"claim", "valid", "reasons"} <= set(c) for c in state["validate"]["claims"]
    )
    assert "prediction" in state["predict"]
    assert "revision_notes" in state  # revise node ran during the cycle
