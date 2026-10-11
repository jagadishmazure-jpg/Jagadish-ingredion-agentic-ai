"""Trend helpers over run-history series."""

from __future__ import annotations

from typing import Dict, List, Optional


def moving_average(values: List[float], window: int = 3) -> List[Optional[float]]:
    """Simple moving average; leading entries are None until window fills."""
    if window < 1:
        raise ValueError("window must be >= 1")
    out: List[Optional[float]] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
        else:
            chunk = values[i + 1 - window : i + 1]
            out.append(round(sum(chunk) / len(chunk), 3))
    return out


def delta_vs_previous(values: List[float]) -> List[Optional[float]]:
    """Point-to-point deltas; first entry is None."""
    return [None] + [round(b - a, 3) for a, b in zip(values, values[1:])]


def trend_report(series: Dict[str, List[float]], window: int = 3) -> Dict[str, Dict[str, List[Optional[float]]]]:
    """Moving averages + deltas for each named series."""
    return {
        name: {
            "moving_average": moving_average(vals, window),
            "delta_vs_previous": delta_vs_previous(vals),
        }
        for name, vals in series.items()
    }
