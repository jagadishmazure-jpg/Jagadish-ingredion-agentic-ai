"""Metric-level lineage: metric → base measures → upstream datasets.

The datalayer tracks dataset provenance (content hashes). This module
lifts lineage one level up: every driver cited in an explanation can be
traced back through the metric's formula to the exact datasets — and
dataset versions — it was computed from.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from food_ingredients_ai.semantics.registry import MetricRegistry


def explain_lineage(
    metric_name: str,
    registry: MetricRegistry,
    version: Optional[str] = None,
    dataset_versions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Return the full lineage chain for *metric_name*.

    ``dataset_versions`` optionally pins upstream dataset versions
    (e.g. from the datalayer registry); unpinned datasets are marked
    ``"version": "unpinned"``.
    """
    metric = registry.get(metric_name, version)
    dataset_versions = dataset_versions or {}
    chain: List[Dict[str, Any]] = []
    for dataset in metric.upstream_datasets:
        chain.append(
            {
                "dataset": dataset,
                "version": dataset_versions.get(dataset, "unpinned"),
                "role": "upstream source",
            }
        )
    return {
        "metric": metric.name,
        "metric_version": metric.version,
        "formula": metric.formula,
        "owner": metric.owner,
        "unit": metric.unit,
        # The chain, top-down: metric → base measures → datasets.
        "chain": [
            {
                "level": "metric",
                "name": metric.name,
                "detail": metric.formula,
            },
            {
                "level": "base_measures",
                "names": list(metric.inputs),
                "detail": "formula inputs; each driver cites these",
            },
            {
                "level": "upstream_datasets",
                "entries": chain,
                "detail": "governed datasets the measures are computed from",
            },
        ],
        "citation": (
            f"{metric.name}@{metric.version} :: {metric.formula} :: "
            f"datasets[{', '.join(metric.upstream_datasets)}]"
        ),
    }
