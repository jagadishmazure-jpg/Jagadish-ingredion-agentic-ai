"""ESG agent: collection, carbon, intensity, reporting (demo)."""

from __future__ import annotations

from typing import Any, Dict

from food_ingredients_ai.agents.esg import carbon, collector, intensity, report
from food_ingredients_ai.core.agent import Agent
from food_ingredients_ai.core.fake_llm import FakeLLM
from food_ingredients_ai.core.tools import Tool

__all__ = ["ESGAgent"]


class ESGAgent(Agent):
    """Specialist for ESG data, carbon, and reporting (demo)."""

    name = "esg"
    role = "ESG & sustainability specialist"
    description = (
        "Collects ESG readings, calculates carbon footprint and resource "
        "intensity, generates ESG reports."
    )

    def __init__(self, llm: FakeLLM | None = None) -> None:
        super().__init__(llm)
        self.tools.register(
            Tool(
                "collect_esg",
                "Collect synthetic ESG readings",
                collector.collect,
                {"plant": "optional plant filter"},
            )
        )
        self.tools.register(
            Tool(
                "calculate_carbon",
                "Compute carbon footprint",
                carbon.carbon_footprint,
                {"readings": "ESG reading list"},
            )
        )

    def execute(self, task_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        bb = payload.get("blackboard", {})

        if task_name == "collect_esg":
            return collector.collect(payload.get("plant"))

        if task_name == "calculate_carbon":
            readings = (
                bb["collect_esg"]["readings"]
                if "collect_esg" in bb
                else collector.collect()["readings"]
            )
            calc = carbon.carbon_footprint(readings)
            calc["intensities"] = intensity.intensities(readings)
            return {"carbon": calc}

        if task_name == "esg_report":
            readings = (
                bb["collect_esg"]["readings"]
                if "collect_esg" in bb
                else collector.collect()["readings"]
            )
            if "calculate_carbon" in bb:
                calc = dict(bb["calculate_carbon"]["carbon"])
                intens = calc.pop("intensities")
            else:
                calc = carbon.carbon_footprint(readings)
                intens = intensity.intensities(readings)
            md = report.generate_esg_report(
                readings, calc, intens, period=payload.get("period", "Q1-Q2 (demo)")
            )
            return {"report_markdown": md}

        raise ValueError(f"unknown task for {self.name}: {task_name}")
