"""Semantic metric layer: governed business metrics with lineage and
"why did it change" attribution.

Agents must never query raw tables and invent business logic. This
package is the governed middle layer: every business metric has one
versioned definition, a formula over named base measures, and full
lineage back to the datasets it was computed from — the same pattern as
Databricks Genie Ontology and Snowflake's semantic layer.
"""

from ingredion_ai.semantics.explainer import explain_change
from ingredion_ai.semantics.lineage import explain_lineage
from ingredion_ai.semantics.metrics import DEMO_METRICS, MetricDefinition
from ingredion_ai.semantics.registry import MetricRegistry, default_metric_registry

__all__ = [
    "MetricDefinition",
    "DEMO_METRICS",
    "MetricRegistry",
    "default_metric_registry",
    "explain_lineage",
    "explain_change",
]
