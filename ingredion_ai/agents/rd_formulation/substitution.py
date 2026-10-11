"""Substitution recommender: clean-label swaps + reformulation application.

Demo mapping pairs each known non-clean-label demo ingredient with a
clean-label alternative from the synthetic DB. Unknown flagged ingredients
fall back to same-function clean candidates sorted by cost.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from ingredion_ai.data.loader import get_ingredient, load_ingredients

# old ingredient id -> preferred clean-label replacement ids (demo mapping).
# An empty list means "remove; no clean-label alternative in the demo DB".
DEMO_SUBSTITUTION_MAP: Dict[str, List[str]] = {
    "MCS-10": ["PF-200"],
    "HFCS-42": ["FS-40"],
    "AV-01": ["NV-60"],
    "R40": ["BC-12"],
    "SBZ": ["CD-55"],
    "P60": ["SL-70"],
    "TD-99": [],
    "TBHQ": ["RE-77"],
}

WATER_ID = "WTR-00"


def _candidates_for(old: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Clean-label candidates for *old*, cheapest first."""
    preferred = DEMO_SUBSTITUTION_MAP.get(old["id"])
    pool = load_ingredients()
    if preferred is not None:
        ordered = [get_ingredient(pid) for pid in preferred]
        return [c for c in ordered if c["clean_label"]]
    same_function = [
        c
        for c in pool
        if c["clean_label"] and c["function"] == old["function"] and c["id"] != old["id"]
    ]
    return sorted(same_function, key=lambda c: c["cost_index"])


def suggest_substitutes(
    flagged: List[Dict[str, Any]], max_candidates: int = 2
) -> List[Dict[str, Any]]:
    """Recommend clean-label swaps for each flagged ingredient."""
    suggestions: List[Dict[str, Any]] = []
    for item in flagged:
        old = get_ingredient(item["ingredient_id"])
        candidates = _candidates_for(old)[:max_candidates]
        if not candidates:
            suggestions.append(
                {
                    "old_id": old["id"],
                    "old_name": old["name"],
                    "old_pct": item["pct"],
                    "action": "remove",
                    "new_id": None,
                    "new_name": None,
                    "new_pct": 0.0,
                    "reason": "no clean-label alternative in demo DB; removed",
                }
            )
            continue
        best = candidates[0]
        suggestions.append(
            {
                "old_id": old["id"],
                "old_name": old["name"],
                "old_pct": item["pct"],
                "action": "substitute",
                "new_id": best["id"],
                "new_name": best["name"],
                "new_pct": item["pct"],
                "reason": (
                    f"clean-label {best['function']} "
                    f"(cost index {best['cost_index']})"
                ),
                "alternatives": [c["id"] for c in candidates[1:]],
            }
        )
    return suggestions


def apply_substitutions(
    formula: Dict[str, Any],
    substitutions: List[Dict[str, Any]],
    adjustments: Optional[Dict[str, float]] = None,
    additions: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Build the reformulated formula.

    Substitutions replace 1:1 (clamped to the new ingredient's demo usage
    max); removals and freed percentages flow into water to keep the demo
    formula at 100%.
    """
    adjustments = adjustments or {}
    additions = additions or {}
    new_formula = deepcopy(formula)
    items: Dict[str, float] = {i["id"]: i["pct"] for i in new_formula["ingredients"]}

    for sub in substitutions:
        old_id = sub["old_id"]
        pct = items.pop(old_id, 0.0)
        if sub["action"] == "remove" or sub["new_id"] is None:
            items[WATER_ID] = items.get(WATER_ID, 0.0) + pct
            continue
        new_ing = get_ingredient(sub["new_id"])
        use_pct = min(pct, new_ing["usage_max"])
        items[sub["new_id"]] = items.get(sub["new_id"], 0.0) + use_pct
        leftover = pct - use_pct
        if leftover > 0:
            items[WATER_ID] = items.get(WATER_ID, 0.0) + leftover

    for ing_id, new_pct in adjustments.items():
        if ing_id not in items:
            raise KeyError(f"cannot adjust missing ingredient: {ing_id}")
        delta = items[ing_id] - new_pct
        items[ing_id] = new_pct
        items[WATER_ID] = items.get(WATER_ID, 0.0) + delta

    for ing_id, pct in additions.items():
        get_ingredient(ing_id)  # validates the id
        items[ing_id] = items.get(ing_id, 0.0) + pct
        items[WATER_ID] = items.get(WATER_ID, 0.0) - pct

    total = round(sum(items.values()), 6)
    if abs(total - 100.0) > 0.01:
        raise ValueError(f"reformulated formula does not sum to 100 (got {total})")
    if any(pct < -1e-9 for pct in items.values()):
        raise ValueError("reformulated formula has a negative percentage")

    new_formula["ingredients"] = [
        {"id": ing_id, "pct": round(pct, 4)}
        for ing_id, pct in items.items()
        if pct > 0
    ]
    new_formula["id"] = f"{formula['id']}__clean_label"
    new_formula["name"] = f"{formula['name']} (clean-label reformulation, demo)"
    return new_formula
