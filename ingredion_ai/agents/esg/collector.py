"""ESG data collector: loads synthetic plant readings (demo)."""

from __future__ import annotations

from typing import Any, Dict, List

from ingredion_ai.data.loader import load_esg_readings


def collect(plant: str | None = None) -> Dict[str, Any]:
    """Collect synthetic ESG readings, optionally filtered by plant."""
    readings: List[Dict[str, Any]] = load_esg_readings()
    if plant:
        readings = [r for r in readings if r["plant"] == plant]
    return {"readings": readings, "reading_count": len(readings), "demo": True}
