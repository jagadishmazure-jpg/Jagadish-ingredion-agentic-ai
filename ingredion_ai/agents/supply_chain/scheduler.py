"""Production scheduler: respects daily capacity and shelf-life constraints."""

from __future__ import annotations

from typing import Any, Dict, List


def schedule_production(
    demand: List[Dict[str, Any]],
    capacity_per_day: float,
    shelf_life_days: int,
) -> Dict[str, Any]:
    """Schedule production backwards from each need day (latest first).

    ``demand``: ``[{"sku", "qty", "need_day"}]``. Produces as late as possible
    while respecting ``capacity_per_day`` and never producing earlier than
    ``shelf_life_days`` before the need day. Raises ``ValueError`` if infeasible.
    """
    if capacity_per_day <= 0:
        raise ValueError("capacity_per_day must be positive")
    if shelf_life_days < 0:
        raise ValueError("shelf_life_days must be non-negative")

    used: Dict[int, float] = {}
    schedule: List[Dict[str, Any]] = []
    for req in sorted(demand, key=lambda r: r["need_day"], reverse=True):
        remaining = float(req["qty"])
        day = int(req["need_day"])
        earliest = day - shelf_life_days
        while remaining > 0:
            if day < earliest or day < 0:
                raise ValueError(
                    f"infeasible: cannot schedule {req['qty']} of {req['sku']} "
                    f"for day {req['need_day']} within shelf-life {shelf_life_days}d"
                )
            free = capacity_per_day - used.get(day, 0.0)
            if free <= 0:
                day -= 1
                continue
            alloc = min(remaining, free)
            used[day] = used.get(day, 0.0) + alloc
            schedule.append({"day": day, "sku": req["sku"], "qty": round(alloc, 2)})
            remaining -= alloc
            if remaining > 0:
                day -= 1
    schedule.sort(key=lambda s: (s["day"], s["sku"]))
    return {
        "schedule": schedule,
        "days_used": sorted(used),
        "total_qty": round(sum(s["qty"] for s in schedule), 2),
        "demo": True,
    }
