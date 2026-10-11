"""Ingredient recommender: filter the synthetic DB by category/claims/region."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ingredion_ai.data.loader import load_ingredients


def recommend(
    category: Optional[str] = None,
    claims: Sequence[str] = ("clean_label",),
    region: str = "NA",
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """Recommend demo ingredients, cheapest first.

    ``claims`` may contain ``"clean_label"`` and/or ``"natural"``.
    """
    results = []
    for ing in load_ingredients():
        if category and ing["category"] != category:
            continue
        if "clean_label" in claims and not ing["clean_label"]:
            continue
        if "natural" in claims and not ing["natural"]:
            continue
        if region not in ing["regions"]:
            continue
        results.append(
            {
                "id": ing["id"],
                "name": ing["name"],
                "category": ing["category"],
                "function": ing["function"],
                "cost_index": ing["cost_index"],
                "usage_min": ing["usage_min"],
                "usage_max": ing["usage_max"],
            }
        )
    results.sort(key=lambda r: r["cost_index"])
    return results[:max_results]
