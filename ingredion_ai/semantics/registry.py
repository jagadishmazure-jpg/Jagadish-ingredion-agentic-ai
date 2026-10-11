"""Versioned registry of governed metric definitions."""

from __future__ import annotations

from typing import Dict, List, Optional

from ingredion_ai.semantics.metrics import DEMO_METRICS, MetricDefinition


class MetricRegistry:
    """Register versioned metric definitions; single source of truth.

    - Same name + same version twice → :class:`ValueError` (duplicate guard).
    - Same name + new version → allowed; ``get`` without a version returns
      the latest registered version.
    """

    def __init__(self) -> None:
        self._defs: Dict[str, Dict[str, MetricDefinition]] = {}

    def register(self, metric: MetricDefinition) -> None:
        """Register one metric definition version."""
        versions = self._defs.setdefault(metric.name, {})
        if metric.version in versions:
            raise ValueError(
                f"metric {metric.name!r} version {metric.version!r} "
                "is already registered"
            )
        versions[metric.version] = metric

    def versions(self, name: str) -> List[str]:
        """Sorted registered versions for *name* (KeyError if unknown)."""
        try:
            return sorted(self._defs[name])
        except KeyError:
            raise KeyError(f"unknown metric: {name!r}") from None

    def get(self, name: str, version: Optional[str] = None) -> MetricDefinition:
        """Fetch a definition; omitted *version* → latest registered."""
        available = self.versions(name)
        chosen = version or available[-1]
        if chosen not in self._defs[name]:
            raise KeyError(
                f"metric {name!r} has no version {chosen!r}; "
                f"available: {available}"
            )
        return self._defs[name][chosen]

    def list(self) -> List[str]:
        """Sorted metric names."""
        return sorted(self._defs)

    def find_by_text(self, text: str) -> Optional[MetricDefinition]:
        """Best-effort natural-language resolution: match name or aliases.

        Returns the latest version of the first metric whose name or alias
        appears in *text* (case-insensitive), else None.
        """
        lowered = text.lower()
        for name in self.list():
            metric = self.get(name)
            candidates = [metric.name.replace("_", " "), *metric.aliases]
            if any(c.lower() in lowered for c in candidates):
                return metric
        return None


def default_metric_registry() -> MetricRegistry:
    """Registry pre-loaded with the six governed demo metrics."""
    reg = MetricRegistry()
    for metric in DEMO_METRICS():
        reg.register(metric)
    return reg
