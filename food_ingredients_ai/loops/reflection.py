"""Reflection loop: draft -> critique -> revise, bounded by ``max_iterations``.

The pattern is generic: any draft/critique/revise triple of callables can be
plugged in. The domain wiring at the bottom
(:func:`reflective_reformulate`) binds it to the R&D formulation agent's
real ``execute()`` paths, so the demo stays fully offline and deterministic.

Determinism note: the domain revise step re-runs the deterministic
``suggest_substitutes`` path, so in this offline demo it either converges
immediately (coverage is complete on the first draft) or exhausts
``max_iterations`` and returns ``approved=False``. In a live system the
revise step would take corrective action (e.g. relax a constraint or pick
the next-best candidate); the iteration bound is what keeps the loop safe.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from food_ingredients_ai.agents.rd_formulation import RDFormulationAgent

DraftFn = Callable[[], Dict[str, Any]]
CritiqueFn = Callable[[Dict[str, Any]], Dict[str, Any]]
ReviseFn = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]


def reflection_loop(
    draft_fn: DraftFn,
    critique_fn: CritiqueFn,
    revise_fn: ReviseFn,
    max_iterations: int = 3,
) -> Dict[str, Any]:
    """Run draft -> critique -> revise until approval or iteration budget.

    ``critique_fn`` returns a dict containing an ``"approved"`` bool.
    Returns ``{"result", "iterations", "approved", "critiques"}`` where
    ``iterations`` counts draft evaluations (the initial draft is iteration
    1) and ``critiques`` holds every critique in order.
    """
    critiques: List[Dict[str, Any]] = []
    draft = draft_fn()
    iterations = 0
    while True:
        iterations += 1
        critique = critique_fn(draft)
        critiques.append(critique)
        if critique.get("approved"):
            return {
                "result": draft,
                "iterations": iterations,
                "approved": True,
                "critiques": critiques,
            }
        if iterations >= max_iterations:
            return {
                "result": draft,
                "iterations": iterations,
                "approved": False,
                "critiques": critiques,
            }
        draft = revise_fn(draft, critique)


def _draft_substitutions(
    agent: RDFormulationAgent, formula_id: str
) -> Dict[str, Any]:
    return agent.execute("suggest_substitutes", {"formula_id": formula_id})


def _critique_coverage(
    agent: RDFormulationAgent, draft: Dict[str, Any], formula_id: str
) -> Dict[str, Any]:
    """Critique: every flagged non-clean ingredient must have a substitute
    (``action == "substitute"``) or an explicit removal reason
    (``action == "remove"`` with a ``reason``)."""
    analysis = agent.execute("analyze_ingredients", {"formula_id": formula_id})
    flagged_ids = {f["ingredient_id"] for f in analysis["flagged"]}
    covered = {
        s["old_id"]
        for s in draft.get("substitutions", [])
        if s.get("action") in {"substitute", "remove"} and s.get("reason")
    }
    missing = sorted(flagged_ids - covered)
    return {
        "approved": not missing,
        "flagged_count": len(flagged_ids),
        "covered_count": len(flagged_ids & covered),
        "missing": missing,
        "notes": (
            "all flagged ingredients covered by a substitution or removal"
            if not missing
            else f"flagged ingredients without a substitute or removal reason: {missing}"
        ),
    }


def _revise_substitutions(
    agent: RDFormulationAgent,
    formula_id: str,
    draft: Dict[str, Any],
    critique: Dict[str, Any],
) -> Dict[str, Any]:
    """Revise step: re-run the deterministic suggestion path.

    The demo substitution map is total (every known flagged ingredient maps
    to a clean-label alternative or an explicit removal), so a missing item
    is a caller-side bug rather than new information; the re-run is
    idempotent and the loop bound keeps the retry safe.
    """
    _ = draft, critique  # deterministic path; inputs recorded for provenance
    return _draft_substitutions(agent, formula_id)


def reflective_reformulate(
    formula_id: str = "sweet_bakery_cake",
) -> Dict[str, Any]:
    """Reflection loop over clean-label substitution, wired to the domain.

    Draft = ``RDFormulationAgent().execute("suggest_substitutes", ...)``;
    critique = coverage check against ``analyze_ingredients``; revise =
    deterministic re-run. Offline, no network.
    """
    agent = RDFormulationAgent()
    return reflection_loop(
        draft_fn=lambda: _draft_substitutions(agent, formula_id),
        critique_fn=lambda draft: _critique_coverage(agent, draft, formula_id),
        revise_fn=lambda draft, critique: _revise_substitutions(
            agent, formula_id, draft, critique
        ),
        max_iterations=3,
    )
