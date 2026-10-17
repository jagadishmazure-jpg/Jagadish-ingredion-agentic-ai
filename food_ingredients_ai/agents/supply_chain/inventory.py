"""Inventory & procurement optimizer (demo rules)."""

from __future__ import annotations

import math
from typing import Any, Dict, List


def reorder_point(
    avg_daily_demand: float, lead_time_days: float, safety_factor: float = 0.2
) -> float:
    """Classic reorder point with safety stock (demo)."""
    if avg_daily_demand < 0 or lead_time_days < 0:
        raise ValueError("demand and lead time must be non-negative")
    return round(avg_daily_demand * lead_time_days * (1 + safety_factor), 2)


def suggest_purchases(
    inventory: Dict[str, Dict[str, float]],
    forecasts_weekly: Dict[str, List[float]],
    lead_time_days: float = 7.0,
    safety_factor: float = 0.2,
) -> List[Dict[str, Any]]:
    """Suggest purchase orders for SKUs below their reorder point.

    ``inventory``: ``{sku: {"on_hand_tonnes": x}}``.
    ``forecasts_weekly``: ``{sku: [weekly tonnes...]}``.
    """
    suggestions: List[Dict[str, Any]] = []
    for sku, inv in inventory.items():
        weekly = forecasts_weekly.get(sku, [])
        if not weekly:
            continue
        avg_daily = (sum(weekly) / len(weekly)) / 7.0
        rop = reorder_point(avg_daily, lead_time_days, safety_factor)
        on_hand = inv["on_hand_tonnes"]
        if on_hand < rop:
            order_qty = math.ceil(2 * rop - on_hand)
            suggestions.append(
                {
                    "sku": sku,
                    "on_hand_tonnes": on_hand,
                    "reorder_point_tonnes": rop,
                    "suggested_order_tonnes": order_qty,
                    "reason": "on-hand below reorder point (demo rule)",
                }
            )
    return sorted(suggestions, key=lambda s: s["sku"])
