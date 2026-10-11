"""Anonymized peer benchmarking on synthetic data.

The peer distributions are deterministic synthetic samples (seeded PRNG),
so benchmarks are reproducible offline. Every result carries
:data:`SYNTHETIC_LABEL` — this demonstrates the benchmarking *pattern*;
it is not real market data and must never be presented as such.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

SYNTHETIC_LABEL = "synthetic demo data — not real market benchmarks"


@dataclass(frozen=True)
class PeerMetric:
    """Definition of one benchmarkable metric."""

    name: str
    # (mean, stddev) of the synthetic peer distribution; lower_is_better
    # flips the verdict direction.
    mean: float
    stddev: float
    lower_is_better: bool = True
    unit: str = ""


PEER_METRICS: Dict[str, PeerMetric] = {
    "cost_per_kg_usd": PeerMetric("cost_per_kg_usd", 10.5, 2.1, True, "USD/kg"),
    "shelf_life_days": PeerMetric("shelf_life_days", 9.0, 2.5, False, "days"),
    "texture_match_pct": PeerMetric("texture_match_pct", 88.0, 5.0, False, "%"),
    "claim_coverage_pct": PeerMetric("claim_coverage_pct", 75.0, 15.0, False, "%"),
    "cycle_weeks": PeerMetric("cycle_weeks", 22.0, 4.0, True, "weeks"),
}

_PEER_SAMPLE_SIZE = 500


def _peer_sample(metric: PeerMetric) -> List[float]:
    rng = random.Random(f"peer-{metric.name}")  # deterministic
    return [max(0.0, rng.gauss(metric.mean, metric.stddev)) for _ in range(_PEER_SAMPLE_SIZE)]


def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    frac = k - lo
    return round(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac, 2)


class PeerBenchmark:
    """Compare a run's metrics against synthetic peer distributions."""

    def __init__(self, metrics: Optional[Dict[str, PeerMetric]] = None) -> None:
        self.metrics = metrics or PEER_METRICS
        self._samples = {name: sorted(_peer_sample(m)) for name, m in self.metrics.items()}

    def compare(self, metric_name: str, value: float) -> Dict[str, Any]:
        """Return p50/p90, the value's percentile, and a verdict."""
        if metric_name not in self.metrics:
            raise KeyError(f"unknown benchmark metric: {metric_name!r}")
        metric = self.metrics[metric_name]
        sample = self._samples[metric_name]
        below = sum(1 for v in sample if v < value)
        your_pct = round(below / len(sample) * 100, 1)
        p50 = _percentile(sample, 50)
        p90 = _percentile(sample, 90)
        if metric.lower_is_better:
            verdict = (
                "better than peers" if value <= p50
                else "in line with peers" if value <= p90
                else "worse than peers"
            )
        else:
            verdict = (
                "better than peers" if value >= p50
                else "in line with peers" if value >= p90
                else "worse than peers"
            )
        return {
            "metric": metric_name,
            "value": value,
            "unit": metric.unit,
            "peer_p50": p50,
            "peer_p90": p90,
            "your_percentile": your_pct,
            "verdict": verdict,
            "data_label": SYNTHETIC_LABEL,
        }

    def compare_summary(self, summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Benchmark every available numeric field of a run summary."""
        out = []
        for name in self.metrics:
            value = summary.get(name)
            if isinstance(value, (int, float)):
                out.append(self.compare(name, float(value)))
        return out
