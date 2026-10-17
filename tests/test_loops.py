"""Tests for the loop engineering package (reflection + HITL gate).

All offline and deterministic; the domain-backed tests use the real
RDFormulationAgent execute() paths and the real governance approvals API.
"""

from food_ingredients_ai.governance.approvals import ApprovalGate, ApprovalRecord
from food_ingredients_ai.loops import hitl_gate, reflection_loop, reflective_reformulate

# --- reflection_loop with mock functions -----------------------------------


def _always_approve(draft):
    return {"approved": True, "notes": "mock: good draft"}


def test_reflection_approves_good_draft_first_try():
    calls = []

    def draft_fn():
        calls.append("draft")
        return {"text": "clean draft"}

    def critique_fn(draft):
        calls.append("critique")
        return _always_approve(draft)

    def revise_fn(draft, critique):
        calls.append("revise")
        return draft

    out = reflection_loop(draft_fn, critique_fn, revise_fn)
    assert out["approved"] is True
    assert out["iterations"] == 1
    assert out["result"] == {"text": "clean draft"}
    assert len(out["critiques"]) == 1
    assert calls == ["draft", "critique"]  # revise never ran


def test_reflection_revises_then_approves():
    def draft_fn():
        return {"quality": 0}

    def critique_fn(draft):
        return {"approved": draft["quality"] >= 2, "quality": draft["quality"]}

    def revise_fn(draft, critique):
        return {"quality": draft["quality"] + 1}

    out = reflection_loop(draft_fn, critique_fn, revise_fn, max_iterations=5)
    assert out["approved"] is True
    assert out["iterations"] == 3
    assert out["result"] == {"quality": 2}
    assert [c["quality"] for c in out["critiques"]] == [0, 1, 2]


def test_reflection_exhausts_max_iterations_with_approved_false():
    def draft_fn():
        return {"quality": 0}

    def critique_fn(draft):
        return {"approved": False, "reason": "mock: never good enough"}

    def revise_fn(draft, critique):
        return {"quality": draft["quality"] + 1}

    out = reflection_loop(draft_fn, critique_fn, revise_fn, max_iterations=3)
    assert out["approved"] is False
    assert out["iterations"] == 3
    assert len(out["critiques"]) == 3
    # The best-effort final draft is still returned.
    assert out["result"] == {"quality": 2}


# --- reflective_reformulate (domain-wired) ----------------------------------


def test_reflective_reformulate_runs_offline_with_expected_keys():
    out = reflective_reformulate("sweet_bakery_cake")
    assert set(out) == {"result", "iterations", "approved", "critiques"}
    assert out["approved"] is True
    assert out["iterations"] == 1
    assert "substitutions" in out["result"]
    assert out["result"]["substituted_count"] + out["result"]["removed_count"] == len(
        out["result"]["substitutions"]
    )


def test_reflective_reformulate_critique_covers_all_flagged_ingredients():
    out = reflective_reformulate("sweet_bakery_cake")
    critique = out["critiques"][0]
    assert critique["approved"] is True
    assert critique["missing"] == []
    assert critique["flagged_count"] == 7
    assert critique["covered_count"] == critique["flagged_count"]


# --- hitl_gate --------------------------------------------------------------


def test_hitl_gate_approves_low_risk_action_without_looping():
    out = hitl_gate("analysis_summary", {"summary": "read-only demo summary"})
    assert out["decision"] == "approved"
    assert out["rounds"] == 0
    assert out["requires_approval"] is False
    assert out["record"] is None


def test_hitl_gate_approves_high_impact_action_with_simulated_approver():
    out = hitl_gate("new_formulation", {"summary": "demo formulation release"})
    assert out["decision"] == "approved"
    assert out["rounds"] == 1
    assert out["requires_approval"] is True
    record = out["record"]
    assert isinstance(record, ApprovalRecord)
    assert record.approved is True
    assert record.simulated is True
    assert record.approver == "simulated-human-approver"


class _RejectOnceGate:
    """Gate-like approver: rejects the first round, approves the second."""

    def __init__(self):
        self.calls = 0

    def request(self, output_type, summary, payload=None):
        self.calls += 1
        return ApprovalRecord(
            output_type=output_type,
            summary=summary,
            approved=self.calls >= 2,
            approver="test-human",
            decided_at="2026-10-10T00:00:00+00:00",
            simulated=False,
            notes="test approver",
        )


def test_hitl_gate_loops_on_high_impact_action_and_returns_decision():
    gate = _RejectOnceGate()
    out = hitl_gate("new_formulation", {"summary": "needs a human"}, approver=gate)
    assert gate.calls == 2
    assert out["decision"] == "approved"
    assert out["rounds"] == 2
    assert out["requires_approval"] is True
    assert out["record"].approver == "test-human"


def test_hitl_gate_rejects_after_max_rounds_when_never_approved():
    gate = ApprovalGate(auto_approve=False)  # real human gate: stays pending
    out = hitl_gate("esg_report", {"summary": "nobody home"}, approver=gate, max_rounds=2)
    assert out["decision"] == "rejected"
    assert out["rounds"] == 2
    assert out["requires_approval"] is True
    assert out["record"].approved is False
