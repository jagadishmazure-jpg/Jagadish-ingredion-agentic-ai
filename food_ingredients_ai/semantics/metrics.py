"""Governed business metric definitions for the demo manufacturer.

A :class:`MetricDefinition` is the single source of truth for what a
business metric *means*: its formula as a named composition of base
measures, its owner, its version, and the upstream datasets it is
computed from. Agents resolve metrics through the registry — never by
guessing from raw tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class MetricDefinition:
    """One versioned business metric."""

    name: str
    description: str
    unit: str
    formula: str  # human-readable, e.g. "gross_margin_pct = (revenue - cogs) / revenue * 100"
    inputs: List[str]  # base measures the formula consumes, in attribution order
    owner: str
    version: str = "v1"
    upstream_datasets: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)  # natural-language hints
    # Callable: inputs dict -> metric value. Kept out of the dataclass repr.
    compute: Callable[[Dict[str, float]], float] = field(
        default=lambda _inputs: 0.0, repr=False, compare=False
    )

    def evaluate(self, inputs: Dict[str, float]) -> float:
        """Evaluate the metric from base-measure values (KeyError if missing)."""
        missing = [i for i in self.inputs if i not in inputs]
        if missing:
            raise KeyError(f"metric {self.name!r} missing inputs: {missing}")
        return self.compute({i: float(inputs[i]) for i in self.inputs})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "unit": self.unit,
            "formula": self.formula,
            "inputs": list(self.inputs),
            "owner": self.owner,
            "version": self.version,
            "upstream_datasets": list(self.upstream_datasets),
            "aliases": list(self.aliases),
        }


def _pct(numer: str, denom: str) -> Callable[[Dict[str, float]], float]:
    def _compute(inputs: Dict[str, float]) -> float:
        d = inputs[denom]
        if d == 0:
            raise ZeroDivisionError(f"denominator {denom!r} is zero")
        return inputs[numer] / d * 100.0

    return _compute


def _gross_margin(inputs: Dict[str, float]) -> float:
    revenue = inputs["revenue"]
    if revenue == 0:
        raise ZeroDivisionError("revenue is zero")
    return (revenue - inputs["cogs"]) / revenue * 100.0


def _carbon_intensity(inputs: Dict[str, float]) -> float:
    tonnes = inputs["production_tonnes"]
    if tonnes == 0:
        raise ZeroDivisionError("production_tonnes is zero")
    return inputs["emissions_tco2e"] * 1000.0 / tonnes


def DEMO_METRICS() -> List[MetricDefinition]:
    """The six governed demo metrics for the ingredient manufacturer."""
    return [
        MetricDefinition(
            name="gross_margin_pct",
            description="Gross margin percentage: share of revenue left after cost of goods sold.",
            unit="percent",
            formula="gross_margin_pct = (revenue - cogs) / revenue * 100",
            inputs=["revenue", "cogs"],
            owner="Finance",
            upstream_datasets=["demand", "formulas", "ingredients"],
            aliases=["gross margin", "margin", "profitability"],
            compute=_gross_margin,
        ),
        MetricDefinition(
            name="revenue",
            description="Total revenue for the period (tonnes sold × price).",
            unit="USD",
            formula="revenue = demand_tonnes * price_per_tonne",
            inputs=["demand_tonnes", "price_per_tonne"],
            owner="Finance",
            upstream_datasets=["demand"],
            aliases=["sales", "turnover", "top line"],
            compute=lambda i: i["demand_tonnes"] * i["price_per_tonne"],
        ),
        MetricDefinition(
            name="cogs",
            description="Cost of goods sold for the period.",
            unit="USD",
            formula="cogs = ingredient_cost_per_tonne * production_tonnes",
            inputs=["ingredient_cost_per_tonne", "production_tonnes"],
            owner="Finance",
            upstream_datasets=["ingredients", "esg_readings"],
            aliases=["cost of goods sold", "production cost"],
            compute=lambda i: i["ingredient_cost_per_tonne"] * i["production_tonnes"],
        ),
        MetricDefinition(
            name="clean_label_share_pct",
            description="Share of SKUs carrying a validated clean-label claim.",
            unit="percent",
            formula="clean_label_share_pct = clean_label_skus / total_skus * 100",
            inputs=["clean_label_skus", "total_skus"],
            owner="R&D",
            upstream_datasets=["formulas", "ingredients"],
            aliases=["clean label share", "clean label penetration"],
            compute=_pct("clean_label_skus", "total_skus"),
        ),
        MetricDefinition(
            name="otif_pct",
            description="On-time-in-full delivery rate: orders delivered complete and on time.",
            unit="percent",
            formula="otif_pct = on_time_full_orders / total_orders * 100",
            inputs=["on_time_full_orders", "total_orders"],
            owner="Supply Chain",
            upstream_datasets=["demand"],
            aliases=["otif", "on-time-in-full", "delivery performance"],
            compute=_pct("on_time_full_orders", "total_orders"),
        ),
        MetricDefinition(
            name="carbon_intensity_kg_per_tonne",
            description="Scope 1+2 carbon intensity per tonne produced.",
            unit="kgCO2e/tonne",
            formula="carbon_intensity_kg_per_tonne = emissions_tco2e * 1000 / production_tonnes",
            inputs=["emissions_tco2e", "production_tonnes"],
            owner="ESG",
            upstream_datasets=["esg_readings"],
            aliases=["carbon intensity", "emissions intensity", "co2 per tonne"],
            compute=_carbon_intensity,
        ),
    ]
