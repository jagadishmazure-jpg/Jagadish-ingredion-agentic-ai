"""Water/energy intensity metrics over synthetic ESG readings."""

from __future__ import annotations

from typing import Any, Dict, List


def intensities(readings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Energy (kWh/t) and water (m3/t) intensity, overall and per plant."""
    total_energy = sum(r["energy_kwh"] for r in readings)
    total_water = sum(r["water_m3"] for r in readings)
    total_production = sum(r["production_tonnes"] for r in readings)
    by_plant: Dict[str, Dict[str, float]] = {}
    for r in readings:
        plant = by_plant.setdefault(
            r["plant"],
            {"energy_kwh": 0.0, "water_m3": 0.0, "production_tonnes": 0.0},
        )
        plant["energy_kwh"] += r["energy_kwh"]
        plant["water_m3"] += r["water_m3"]
        plant["production_tonnes"] += r["production_tonnes"]
    for plant in by_plant.values():
        prod = plant["production_tonnes"]
        plant["energy_kwh_per_tonne"] = round(plant["energy_kwh"] / prod, 2) if prod else 0.0
        plant["water_m3_per_tonne"] = round(plant["water_m3"] / prod, 3) if prod else 0.0
    return {
        "energy_kwh_per_tonne": round(total_energy / total_production, 2)
        if total_production
        else 0.0,
        "water_m3_per_tonne": round(total_water / total_production, 3)
        if total_production
        else 0.0,
        "by_plant": by_plant,
        "demo": True,
    }
