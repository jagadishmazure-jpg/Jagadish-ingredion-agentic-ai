"""Reformulation cycle-time estimator (demo heuristic).

Demo assumption: a clean-label reformulation takes 5-7 months without
assistance. The demo estimates
an agentic-AI-assisted cycle time from reformulation complexity — number of
substitutions, risk flags, and category difficulty (bakery is hardest) —
and reports the reduction versus that baseline. Fully deterministic.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Public-research baseline: average clean-label reformulation, months.
BASELINE_MONTHS_LOW = 5.0
BASELINE_MONTHS_HIGH = 7.0
BASELINE_WEEKS = (BASELINE_MONTHS_LOW + BASELINE_MONTHS_HIGH) / 2 * 52 / 12

# Demo effort model (weeks).
BASE_WEEKS = 2.0
WEEKS_PER_SUBSTITUTION = 0.6
WEEKS_PER_RISK_FLAG = 1.0
BAKERY_COMPLEXITY_WEEKS = 1.5
BAKERY_CATEGORIES = {"bakery", "bread"}


def estimate_cycle_time(
    formula: Dict[str, Any],
    substitutions: List[Dict[str, Any]],
    prediction: Dict[str, Any],
) -> Dict[str, Any]:
    """Estimate agentic-assisted reformulation cycle time vs the demo baseline."""
    n_substitutions = sum(
        1 for s in substitutions if s.get("action") == "substitute"
    )
    n_risk_flags = len(prediction.get("risk_flags", []))
    is_bakery = formula.get("category") in BAKERY_CATEGORIES

    weeks = (
        BASE_WEEKS
        + WEEKS_PER_SUBSTITUTION * n_substitutions
        + WEEKS_PER_RISK_FLAG * n_risk_flags
        + (BAKERY_COMPLEXITY_WEEKS if is_bakery else 0.0)
    )
    weeks = round(weeks, 1)
    reduction_pct = round(
        max(0.0, (BASELINE_WEEKS - weeks) / BASELINE_WEEKS) * 100, 1
    )
    return {
        "estimated_weeks": weeks,
        "estimated_months": round(weeks / (52 / 12), 2),
        "baseline_months": [BASELINE_MONTHS_LOW, BASELINE_MONTHS_HIGH],
        "baseline_weeks": round(BASELINE_WEEKS, 1),
        "reduction_pct": reduction_pct,
        "complexity": {
            "substitutions": n_substitutions,
            "risk_flags": n_risk_flags,
            "bakery_category": is_bakery,
        },
        "assumptions": [
            "demo heuristic model — not a real project-planning estimate",
            f"baseline {BASELINE_MONTHS_LOW}-{BASELINE_MONTHS_HIGH} months "
            "(demo assumption)",
            f"effort = {BASE_WEEKS}w base + {WEEKS_PER_SUBSTITUTION}w/substitution "
            f"+ {WEEKS_PER_RISK_FLAG}w/risk flag"
            + (" + 1.5w bakery complexity" if is_bakery else ""),
        ],
        "demo": True,
    }
