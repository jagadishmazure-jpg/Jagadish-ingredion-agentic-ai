"""Run analytics: aggregates, peer benchmarking, trends, proactive suggestions.

All data is synthetic demo data. Benchmarks are computed against
deterministic synthetic peer distributions and are always labeled as
such — they illustrate the benchmarking *pattern*, not real market data.
"""

from ingredion_ai.analytics.aggregates import AggregateStore, RunSummary, extract_run_summary
from ingredion_ai.analytics.benchmarking import PeerBenchmark, SYNTHETIC_LABEL
from ingredion_ai.analytics.suggestions import AnomalyFlag, flag_anomalies
from ingredion_ai.analytics.trends import delta_vs_previous, moving_average

__all__ = [
    "AggregateStore",
    "RunSummary",
    "extract_run_summary",
    "PeerBenchmark",
    "SYNTHETIC_LABEL",
    "AnomalyFlag",
    "flag_anomalies",
    "delta_vs_previous",
    "moving_average",
]
