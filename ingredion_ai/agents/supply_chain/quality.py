"""Quality anomaly detector over synthetic MES/LIMS readings."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def detect_anomalies(
    readings: List[Dict[str, Any]],
    spec_limits: Dict[str, Tuple[float, float]],
) -> List[Dict[str, Any]]:
    """Flag readings outside their spec limits.

    ``readings``: ``[{"batch_id", "metric", "value"}]``.
    ``spec_limits``: ``{metric: (low, high)}``.
    """
    anomalies: List[Dict[str, Any]] = []
    for reading in readings:
        metric = reading["metric"]
        if metric not in spec_limits:
            continue
        low, high = spec_limits[metric]
        value = float(reading["value"])
        if value < low or value > high:
            anomalies.append(
                {
                    "batch_id": reading["batch_id"],
                    "metric": metric,
                    "value": value,
                    "spec_low": low,
                    "spec_high": high,
                    "deviation": round(value - high if value > high else value - low, 3),
                }
            )
    return anomalies
