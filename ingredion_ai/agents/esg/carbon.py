"""Carbon footprint calculator over synthetic ESG readings."""

from __future__ import annotations

from typing import Any, Dict, List


def carbon_footprint(readings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Total emissions and intensity (tCO2e per tonne, demo)."""
    total_emissions = round(sum(r["emissions_tco2e"] for r in readings), 2)
    total_production = round(sum(r["production_tonnes"] for r in readings), 2)
    by_plant: Dict[str, Dict[str, float]] = {}
    for r in readings:
        plant = by_plant.setdefault(
            r["plant"], {"emissions_tco2e": 0.0, "production_tonnes": 0.0}
        )
        plant["emissions_tco2e"] += r["emissions_tco2e"]
        plant["production_tonnes"] += r["production_tonnes"]
    for plant in by_plant.values():
        plant["emissions_tco2e"] = round(plant["emissions_tco2e"], 2)
        plant["production_tonnes"] = round(plant["production_tonnes"], 2)
        plant["intensity_tco2e_per_tonne"] = (
            round(plant["emissions_tco2e"] / plant["production_tonnes"], 4)
            if plant["production_tonnes"]
            else 0.0
        )
    return {
        "total_tco2e": total_emissions,
        "total_production_tonnes": total_production,
        "intensity_tco2e_per_tonne": round(
            total_emissions / total_production, 4
        )
        if total_production
        else 0.0,
        "by_plant": by_plant,
        "demo": True,
    }
