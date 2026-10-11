"""ESG report generator: markdown with traceable demo calculations."""

from __future__ import annotations

from typing import Any, Dict, List


def generate_esg_report(
    readings: List[Dict[str, Any]],
    carbon: Dict[str, Any],
    intensity: Dict[str, Any],
    period: str = "Q1-Q2 (demo)",
) -> str:
    """Render a markdown ESG report showing inputs alongside results."""
    lines = [
        "# ESG Report (Demo — Synthetic Data)",
        "",
        f"**Period:** {period}",
        f"**Readings used:** {len(readings)} plant-quarters",
        "",
        "## Carbon Footprint",
        "",
        f"- Total emissions: **{carbon['total_tco2e']} tCO2e**",
        f"- Total production: **{carbon['total_production_tonnes']} tonnes**",
        f"- Intensity: **{carbon['intensity_tco2e_per_tonne']} tCO2e/tonne**",
        "",
        "| Plant | Emissions (tCO2e) | Production (t) | Intensity (tCO2e/t) |",
        "|---|---|---|---|",
    ]
    for plant, vals in sorted(carbon["by_plant"].items()):
        lines.append(
            f"| {plant} | {vals['emissions_tco2e']} | {vals['production_tonnes']} "
            f"| {vals['intensity_tco2e_per_tonne']} |"
        )
    lines += [
        "",
        "## Resource Intensity",
        "",
        f"- Energy: **{intensity['energy_kwh_per_tonne']} kWh/tonne**",
        f"- Water: **{intensity['water_m3_per_tonne']} m3/tonne**",
        "",
        "| Plant | Energy (kWh/t) | Water (m3/t) |",
        "|---|---|---|",
    ]
    for plant, vals in sorted(intensity["by_plant"].items()):
        lines.append(
            f"| {plant} | {vals['energy_kwh_per_tonne']} | {vals['water_m3_per_tonne']} |"
        )
    lines += [
        "",
        "## Traceability",
        "",
        "Each intensity = sum(metric) / sum(production_tonnes) over the demo readings above.",
        "",
        "_Demo document — synthetic data only. Not affiliated with Ingredion._",
        "",
    ]
    return "\n".join(lines)
