"""Supply chain agent: forecasting, inventory, scheduling, quality (demo)."""

from __future__ import annotations

from typing import Any, Dict

from ingredion_ai.agents.supply_chain import (
    forecaster,
    inventory,
    quality,
    scheduler,
)
from ingredion_ai.core.agent import Agent
from ingredion_ai.core.fake_llm import FakeLLM
from ingredion_ai.core.tools import Tool

__all__ = ["SupplyChainAgent"]


class SupplyChainAgent(Agent):
    """Specialist for demand, inventory, production and quality (demo)."""

    name = "supply_chain"
    role = "Supply chain optimization specialist"
    description = (
        "Forecasts demand, optimizes inventory/procurement, schedules production, "
        "detects quality anomalies."
    )

    def __init__(self, llm: FakeLLM | None = None) -> None:
        super().__init__(llm)
        self.tools.register(
            Tool(
                "forecast_demand",
                "Forecast weekly demand per SKU",
                forecaster.forecast_sku,
                {"sku": "demo SKU id", "periods": "periods ahead"},
            )
        )
        self.tools.register(
            Tool(
                "optimize_inventory",
                "Suggest purchase orders",
                inventory.suggest_purchases,
                {"inventory": "on-hand map", "forecasts_weekly": "forecast map"},
            )
        )
        self.tools.register(
            Tool(
                "schedule_production",
                "Schedule production within capacity/shelf-life",
                scheduler.schedule_production,
                {"demand": "demand list", "capacity_per_day": "capacity"},
            )
        )
        self.tools.register(
            Tool(
                "detect_quality_anomalies",
                "Flag out-of-spec readings",
                quality.detect_anomalies,
                {"readings": "reading list", "spec_limits": "spec map"},
            )
        )

    def execute(self, task_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if task_name == "forecast_demand":
            skus = payload.get("skus", ["PF-200", "HB-10", "VP-80"])
            periods = payload.get("periods", 4)
            forecasts = {sku: forecaster.forecast_sku(sku, periods) for sku in skus}
            return {"forecasts": forecasts}

        if task_name == "optimize_inventory":
            bb = payload.get("blackboard", {})
            if "forecast_demand" in bb:
                forecasts_weekly = {
                    sku: f["forecast"]
                    for sku, f in bb["forecast_demand"]["forecasts"].items()
                }
            else:
                forecasts_weekly = payload.get("forecasts_weekly", {})
            inv = payload.get("inventory")
            plant_id = payload.get("plant_id")
            source = "payload"
            if inv is None and plant_id:
                # Enterprise wiring: pull live-ish inventory from SAP.
                # Offline this resolves to the synthetic DemoSAPAdapter.
                from ingredion_ai.integrations.sap import sap_from_env

                inv = sap_from_env().get_inventory(plant_id)
                source = f"sap:{plant_id}"
            purchases = inventory.suggest_purchases(
                inv or {},
                forecasts_weekly,
                lead_time_days=payload.get("lead_time_days", 7.0),
            )
            return {"purchases": purchases, "inventory_source": source}

        if task_name == "schedule_production":
            return scheduler.schedule_production(
                payload.get("demand", []),
                payload.get("capacity_per_day", 100.0),
                payload.get("shelf_life_days", 7),
            )

        if task_name == "detect_quality_anomalies":
            anomalies = quality.detect_anomalies(
                payload.get("readings", []), payload.get("spec_limits", {})
            )
            return {"anomalies": anomalies, "anomaly_count": len(anomalies)}

        raise ValueError(f"unknown task for {self.name}: {task_name}")
