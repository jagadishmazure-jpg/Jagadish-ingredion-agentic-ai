"""Texture & shelf-life predictor.

Heuristic demo model (NOT a real food-science model): every substitution
carries a ``texture_impact`` score from the synthetic DB; texture match and
shelf-life degrade linearly with total impact. Fully deterministic.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ingredion_ai.data.loader import get_ingredient

CATEGORY_BASE_SHELF_LIFE_DAYS = {"bakery": 9.5, "bread": 6.0, "beverage": 21.0}
TEXTURE_PENALTY_FACTOR = 1.2
SHELF_LIFE_IMPACT_FACTOR = 0.2
TEXTURE_RISK_THRESHOLD = 85.0
SHELF_LIFE_TARGET_DAYS = 7.0

# Categories with elevated texture/shelf-stability sensitivity in the demo.
# Rationale (paraphrased from public clean-label manufacturer research):
# shelf-life anxiety is a top barrier to conversion, especially in bakery
# where gums and functional starches drive stability. The demo therefore
# emits an extra advisory flag for these categories whenever a reformulation
# introduces any texture impact — the numeric prediction is unchanged so
# existing regression expectations stay intact.
BAKERY_CATEGORIES = {"bakery", "bread"}


def bakery_stability_advisory(
    formula: Dict[str, Any], prediction: Dict[str, Any]
) -> List[str]:
    """Advisory shelf-stability flags for bakery/bread reformulations (demo).

    Returns extra human-readable advisories; empty when the category is not
    bakery/bread or when the reformulation introduced no texture impact.
    """
    if formula.get("category") not in BAKERY_CATEGORIES:
        return []
    if prediction.get("substitutions_evaluated", 0) <= 0:
        return []
    total_impact = 100.0 - prediction.get("texture_match_pct", 100.0)
    if total_impact <= 0:
        return []
    return [
        "bakery advisory: elevated texture/shelf-stability sensitivity — "
        "schedule benchtop texture and accelerated shelf-life checks before scale-up (demo)"
    ]


def predict(
    formula: Dict[str, Any], substitutions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Predict texture match (%) and shelf-life (days) for a reformulation."""
    total_impact = 0.0
    for sub in substitutions:
        if sub.get("action") == "substitute" and sub.get("new_id"):
            total_impact += float(get_ingredient(sub["new_id"])["texture_impact"])

    texture_match_pct = max(
        40.0, round(100.0 - TEXTURE_PENALTY_FACTOR * total_impact, 1)
    )
    base_shelf = CATEGORY_BASE_SHELF_LIFE_DAYS.get(formula.get("category", "bakery"), 9.5)
    shelf_life_days = max(
        1.0, round(base_shelf - SHELF_LIFE_IMPACT_FACTOR * total_impact, 1)
    )

    risk_flags: List[str] = []
    if texture_match_pct < TEXTURE_RISK_THRESHOLD:
        risk_flags.append(
            f"texture deviation risk: {texture_match_pct}% below "
            f"{TEXTURE_RISK_THRESHOLD}% demo threshold"
        )
    if shelf_life_days < SHELF_LIFE_TARGET_DAYS:
        risk_flags.append(
            f"shelf-life {shelf_life_days}d below {SHELF_LIFE_TARGET_DAYS}d demo target"
        )

    return {
        "texture_match_pct": texture_match_pct,
        "shelf_life_days": shelf_life_days,
        "risk_flags": risk_flags,
        "substitutions_evaluated": len(substitutions),
        "assumptions": [
            "demo heuristic model — not a real food-science prediction",
            f"texture penalty = {TEXTURE_PENALTY_FACTOR} x total texture impact",
            f"shelf-life = category base - {SHELF_LIFE_IMPACT_FACTOR} x total impact",
        ],
    }
