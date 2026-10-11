"""Sample formulation generator from recommended demo ingredients."""

from __future__ import annotations

from typing import Any, Dict, List

from ingredion_ai.data.loader import get_ingredient


def generate_sample_formula(
    ingredient_ids: List[str], name: str = "Demo Sample Formula"
) -> Dict[str, Any]:
    """Build a demo formula: each ingredient at its usage midpoint, normalized.

    Raises ``ValueError`` on empty input or duplicate functions; ``KeyError``
    on unknown ids.
    """
    if not ingredient_ids:
        raise ValueError("need at least one ingredient id")
    seen_functions = set()
    raw: List[Dict[str, Any]] = []
    for ing_id in ingredient_ids:
        ing = get_ingredient(ing_id)
        if ing["function"] in seen_functions:
            raise ValueError(f"duplicate function in demo formula: {ing['function']}")
        seen_functions.add(ing["function"])
        midpoint = (ing["usage_min"] + ing["usage_max"]) / 2
        raw.append({"id": ing_id, "weight": midpoint})
    total_weight = sum(r["weight"] for r in raw)
    ingredients = [
        {"id": r["id"], "pct": round(r["weight"] / total_weight * 100, 2)} for r in raw
    ]
    return {
        "id": "demo_sample_formula",
        "name": name,
        "category": "bakery",
        "servings": 10,
        "ingredients": ingredients,
        "demo": True,
    }
