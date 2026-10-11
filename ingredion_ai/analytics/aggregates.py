"""Per-run summaries extracted from workflow blackboards + aggregation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RunSummary:
    """One reformulation run, reduced to analytics-friendly numbers."""

    scenario: str
    formula_id: str
    region: str
    substituted_count: int = 0
    removed_count: int = 0
    cost_per_kg_usd: Optional[float] = None
    texture_match_pct: Optional[float] = None
    shelf_life_days: Optional[float] = None
    shelf_life_risk_flags: int = 0
    claims_valid: int = 0
    claims_total: int = 0
    claim_coverage_pct: Optional[float] = None
    cycle_weeks: Optional[float] = None
    elapsed_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _safe_get(mapping: Any, *keys: str, default: Any = None) -> Any:
    cur = mapping
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key, default)
    return cur


def extract_run_summary(
    blackboard: Dict[str, Any],
    scenario: Optional[str] = None,
    formula_id: str = "",
    region: str = "",
    elapsed_ms: Optional[int] = None,
) -> RunSummary:
    """Build a :class:`RunSummary` from a workflow blackboard (defensive)."""
    subs = blackboard.get("suggest_substitutes", {}) or {}
    pricing = _safe_get(blackboard, "estimate_pricing", "pricing", default={}) or {}
    prediction = (
        _safe_get(blackboard, "predict_texture_shelf_life", "prediction", default={})
        or {}
    )
    claims = blackboard.get("validate_claims", {}).get("claims", []) or []

    valid = sum(1 for c in claims if c.get("valid"))
    total = len(claims)
    coverage = round(valid / total * 100, 1) if total else None

    cycle_weeks: Optional[float] = None
    try:
        from ingredion_ai.agents.rd_formulation import cycle_time as _ct
        from ingredion_ai.data.loader import get_formula

        formula = get_formula(formula_id) if formula_id else {}
        if formula and subs.get("substitutions") is not None:
            est = _ct.estimate_cycle_time(
                formula, subs.get("substitutions", []), prediction or {}
            )
            cycle_weeks = est.get("estimated_weeks")
    except Exception:  # noqa: BLE001 - analytics must never break the run
        cycle_weeks = None

    return RunSummary(
        scenario=scenario or "",
        formula_id=formula_id,
        region=region,
        substituted_count=int(subs.get("substituted_count", 0) or 0),
        removed_count=int(subs.get("removed_count", 0) or 0),
        cost_per_kg_usd=pricing.get("cost_per_kg_usd"),
        texture_match_pct=prediction.get("texture_match_pct"),
        shelf_life_days=prediction.get("shelf_life_days"),
        shelf_life_risk_flags=len(prediction.get("risk_flags", []) or []),
        claims_valid=valid,
        claims_total=total,
        claim_coverage_pct=coverage,
        cycle_weeks=cycle_weeks,
        elapsed_ms=elapsed_ms,
    )


def _avg(values: List[Optional[float]]) -> Optional[float]:
    nums = [v for v in values if isinstance(v, (int, float))]
    return round(sum(nums) / len(nums), 2) if nums else None


class AggregateStore:
    """In-memory store of run summaries with aggregate metrics."""

    def __init__(self) -> None:
        self.runs: List[RunSummary] = []

    def record(self, summary: RunSummary) -> None:
        self.runs.append(summary)

    def clear(self) -> None:
        self.runs.clear()

    def summary(self) -> Dict[str, Any]:
        """Aggregate metrics across recorded runs."""
        runs = self.runs
        by_scenario: Dict[str, int] = {}
        for r in runs:
            by_scenario[r.scenario] = by_scenario.get(r.scenario, 0) + 1
        costs = [r.cost_per_kg_usd for r in runs]
        return {
            "run_count": len(runs),
            "runs_by_scenario": by_scenario,
            "avg_cost_per_kg_usd": _avg(costs),
            "min_cost_per_kg_usd": min(
                (c for c in costs if c is not None), default=None
            ),
            "max_cost_per_kg_usd": max(
                (c for c in costs if c is not None), default=None
            ),
            "avg_texture_match_pct": _avg([r.texture_match_pct for r in runs]),
            "avg_shelf_life_days": _avg([r.shelf_life_days for r in runs]),
            "avg_claim_coverage_pct": _avg(
                [r.claim_coverage_pct for r in runs]
            ),
            "avg_cycle_weeks": _avg([r.cycle_weeks for r in runs]),
            "total_substitutions": sum(r.substituted_count for r in runs),
            "total_removals": sum(r.removed_count for r in runs),
            "runs": [r.to_dict() for r in runs],
        }
