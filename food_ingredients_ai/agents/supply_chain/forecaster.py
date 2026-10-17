"""Demand forecaster: moving-average + linear trend over synthetic series."""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any, Dict, List

from food_ingredients_ai.data.loader import load_demand


def forecast(
    series: List[float], periods: int = 4, window: int = 4
) -> Dict[str, Any]:
    """Forecast *periods* steps ahead from *series* (deterministic demo model).

    Uses the mean of the last ``window`` points plus the linear trend fitted
    on those points. Confidence interval is +/- 1.5 x population stdev.
    """
    if len(series) < 2:
        raise ValueError("need at least 2 data points to forecast")
    recent = series[-window:]
    n = len(recent)
    x_mean = (n - 1) / 2
    y_mean = mean(recent)
    denom = sum((x - x_mean) ** 2 for x in range(n))
    slope = (
        sum((x - x_mean) * (y - y_mean) for x, y in enumerate(recent)) / denom
        if denom
        else 0.0
    )
    base = y_mean
    points = [round(base + slope * (i + 1), 2) for i in range(periods)]
    ci = round(1.5 * (pstdev(recent) if n > 1 else 0.0), 2)
    return {
        "forecast": points,
        "method": f"mean_plus_trend(window={n})",
        "slope_per_period": round(slope, 4),
        "confidence_interval": ci,
        "demo": True,
    }


def forecast_sku(sku: str, periods: int = 4) -> Dict[str, Any]:
    """Forecast weekly demand (tonnes) for one demo SKU."""
    series = [
        r["demand_tonnes"] for r in load_demand() if r["sku"] == sku
    ]
    if not series:
        raise KeyError(f"unknown demo sku: {sku}")
    out = forecast(sorted_series(series), periods)
    out["sku"] = sku
    return out


def sorted_series(series: List[float]) -> List[float]:
    return list(series)
