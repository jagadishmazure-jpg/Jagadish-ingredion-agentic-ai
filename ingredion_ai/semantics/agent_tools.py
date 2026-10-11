"""Agent-callable tools over the semantic metric layer.

These wrap the registry, lineage, and explainer so agents answer
metric questions from governed definitions — never by inventing
business logic from raw tables.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ingredion_ai.core.tools import Tool, ToolRegistry
from ingredion_ai.semantics.explainer import explain_change, summarize
from ingredion_ai.semantics.lineage import explain_lineage
from ingredion_ai.semantics.registry import MetricRegistry, default_metric_registry

# Deterministic demo period data for the six governed metrics.
# period "Q2" vs "Q3": citric-acid cost spike + clean-label mix shift.
DEMO_PERIOD_DATA: Dict[str, Dict[str, Dict[str, float]]] = {
    "gross_margin_pct": {
        "Q2": {"revenue": 4_800_000.0, "cogs": 3_120_000.0},
        "Q3": {"revenue": 4_920_000.0, "cogs": 3_444_000.0},
    },
    "revenue": {
        "Q2": {"demand_tonnes": 12_000.0, "price_per_tonne": 400.0},
        "Q3": {"demand_tonnes": 12_300.0, "price_per_tonne": 400.0},
    },
    "cogs": {
        "Q2": {"ingredient_cost_per_tonne": 260.0, "production_tonnes": 12_000.0},
        "Q3": {"ingredient_cost_per_tonne": 280.0, "production_tonnes": 12_300.0},
    },
    "clean_label_share_pct": {
        "Q2": {"clean_label_skus": 42.0, "total_skus": 120.0},
        "Q3": {"clean_label_skus": 51.0, "total_skus": 124.0},
    },
    "otif_pct": {
        "Q2": {"on_time_full_orders": 940.0, "total_orders": 1000.0},
        "Q3": {"on_time_full_orders": 918.0, "total_orders": 1010.0},
    },
    "carbon_intensity_kg_per_tonne": {
        # Mirrors the shape of esg_readings.json (Demo Plant Alpha, Q1→Q2).
        "Q2": {"emissions_tco2e": 85.0, "production_tonnes": 500.0},
        "Q3": {"emissions_tco2e": 92.0, "production_tonnes": 520.0},
    },
}


def build_semantic_tools(
    registry: MetricRegistry | None = None,
) -> List[Tool]:
    """Build the four semantic-layer tools bound to *registry*."""
    reg = registry or default_metric_registry()

    def define_metric(
        name: str,
        description: str,
        unit: str,
        formula: str,
        inputs: List[str],
        owner: str,
        upstream_datasets: List[str],
    ) -> Dict[str, Any]:
        from ingredion_ai.semantics.metrics import MetricDefinition

        metric = MetricDefinition(
            name=name,
            description=description,
            unit=unit,
            formula=formula,
            inputs=list(inputs),
            owner=owner,
            upstream_datasets=list(upstream_datasets),
        )
        reg.register(metric)
        return {"registered": metric.to_dict()}

    def get_metric_definition(
        name: str, version: str = ""
    ) -> Dict[str, Any]:
        metric = reg.get(name, version or None)
        return metric.to_dict()

    def list_metrics() -> Dict[str, Any]:
        return {
            "metrics": [
                {"name": n, "versions": reg.versions(n)} for n in reg.list()
            ]
        }

    def explain_metric_change(
        metric_name: str, period_a: str = "Q2", period_b: str = "Q3"
    ) -> Dict[str, Any]:
        metric = reg.get(metric_name)
        try:
            data = DEMO_PERIOD_DATA[metric_name]
        except KeyError:
            raise KeyError(
                f"no demo period data for metric {metric_name!r}"
            ) from None
        attribution = explain_change(
            metric, data[period_a], data[period_b],
            label_a=period_a, label_b=period_b,
        )
        attribution["lineage"] = explain_lineage(metric_name, reg)
        attribution["summary"] = summarize(attribution)
        return attribution

    return [
        Tool(
            "define_metric",
            "Register a governed business metric definition",
            define_metric,
            {
                "name": "metric name",
                "description": "what it measures",
                "unit": "unit of measure",
                "formula": "formula over named base measures",
                "inputs": "base measure names, in attribution order",
                "owner": "owning team",
                "upstream_datasets": "source dataset names",
            },
        ),
        Tool(
            "get_metric_definition",
            "Fetch the governed definition of a metric",
            get_metric_definition,
            {"name": "metric name", "version": "optional version (latest if empty)"},
        ),
        Tool(
            "list_metrics",
            "List all governed metrics and their versions",
            list_metrics,
            {},
        ),
        Tool(
            "explain_metric_change",
            "Attribute a metric's change between two periods to drivers, with lineage citations",
            explain_metric_change,
            {
                "metric_name": "governed metric name",
                "period_a": "baseline period label",
                "period_b": "comparison period label",
            },
        ),
    ]


def register_semantic_tools(
    tool_registry: ToolRegistry,
    registry: MetricRegistry | None = None,
) -> ToolRegistry:
    """Register the semantic tools on a :class:`ToolRegistry` (agent style)."""
    for tool in build_semantic_tools(registry):
        tool_registry.register(tool)
    return tool_registry
