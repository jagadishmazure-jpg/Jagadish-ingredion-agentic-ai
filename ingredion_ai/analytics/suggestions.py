"""Proactive anomaly flags: surface issues without being asked.

Mirrors the embedded-analytics pattern of in-workflow suggestions:
after a run, flag cost spikes, shelf-life risk, claim gaps, and low
texture match so the UI can nudge the user proactively.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from ingredion_ai.analytics.aggregates import RunSummary
from ingredion_ai.analytics.benchmarking import PeerBenchmark

# Thresholds are demo heuristics, documented in docs/analytics.md.
COST_P90_SEVERITY = "warning"
TEXTURE_FLOOR_PCT = 85.0
SHELF_LIFE_FLOOR_DAYS = 7.0


@dataclass
class AnomalyFlag:
    severity: str  # info | warning | critical
    code: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def flag_anomalies(
    summary: RunSummary,
    benchmark: PeerBenchmark | None = None,
) -> List[AnomalyFlag]:
    """Return anomaly flags for one run summary (empty when healthy)."""
    flags: List[AnomalyFlag] = []
    bench = benchmark or PeerBenchmark()

    if summary.cost_per_kg_usd is not None:
        cmp_ = bench.compare("cost_per_kg_usd", summary.cost_per_kg_usd)
        if cmp_["verdict"] == "worse than peers":
            flags.append(
                AnomalyFlag(
                    severity=COST_P90_SEVERITY,
                    code="COST_SPIKE",
                    message=(
                        f"Cost ${summary.cost_per_kg_usd}/kg exceeds the "
                        f"synthetic peer p90 (${cmp_['peer_p90']}/kg). "
                        "Consider cheaper substitutions."
                    ),
                )
            )

    if summary.shelf_life_risk_flags:
        flags.append(
            AnomalyFlag(
                severity="critical" if summary.shelf_life_days is not None
                and summary.shelf_life_days < SHELF_LIFE_FLOOR_DAYS else "warning",
                code="SHELF_LIFE_RISK",
                message=(
                    f"{summary.shelf_life_risk_flags} shelf-life risk flag(s); "
                    f"projected {summary.shelf_life_days} days."
                ),
            )
        )

    if summary.claims_total and summary.claims_valid < summary.claims_total:
        flags.append(
            AnomalyFlag(
                severity="warning",
                code="CLAIM_GAP",
                message=(
                    f"{summary.claims_total - summary.claims_valid} of "
                    f"{summary.claims_total} target claims invalid — review "
                    "the claim validation step."
                ),
            )
        )

    if (
        summary.texture_match_pct is not None
        and summary.texture_match_pct < TEXTURE_FLOOR_PCT
    ):
        flags.append(
            AnomalyFlag(
                severity="warning",
                code="LOW_TEXTURE",
                message=(
                    f"Texture match {summary.texture_match_pct}% is below the "
                    f"{TEXTURE_FLOOR_PCT}% demo floor."
                ),
            )
        )

    return flags
