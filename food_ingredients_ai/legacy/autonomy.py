"""Autonomy ladder L0 -> L3 for legacy workflows (demo).

- **L0 manual** — the agent only drafts; a human decides and acts.
- **L1 assist** — the agent drafts and recommends; the human decides.
- **L2 augment** — the agent acts inside guardrails; the human reviews.
- **L3 autonomous** — the agent acts; the human audits afterwards.

Promotion between levels is driven by evidence: eval scores, approval
history, and run counts (:func:`promotion_eligible`). Enforcement goes
through the existing governance policy engine, plus ladder-specific rules:

- L2+ requires guardrails to be enabled,
- L3 additionally requires an audit trail and a rollback plan,
- high-impact actions always require approval, even at L3.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

L0_MANUAL = 0
L1_ASSIST = 1
L2_AUGMENT = 2
L3_AUTONOMOUS = 3

LEVEL_NAMES = {
    L0_MANUAL: "L0-manual",
    L1_ASSIST: "L1-assist",
    L2_AUGMENT: "L2-augment",
    L3_AUTONOMOUS: "L3-autonomous",
}

_IMPACT_ORDER = {"low": 0, "medium": 1, "high": 2}


@dataclass
class AutonomyPolicy:
    """Per-workflow autonomy configuration."""

    workflow: str
    level: int = L1_ASSIST
    guardrails_required: bool = True
    audit_required: bool = True
    rollback_plan: str = ""
    max_impact: str = "low"

    def __post_init__(self) -> None:
        if self.level not in LEVEL_NAMES:
            raise ValueError(f"unknown autonomy level: {self.level}")
        if self.max_impact not in _IMPACT_ORDER:
            raise ValueError(f"unknown impact: {self.max_impact!r}")


@dataclass
class WorkflowHistory:
    """Evidence used for promotion decisions."""

    eval_scores: List[float] = field(default_factory=list)
    approvals: int = 0
    runs: int = 0
    incidents: int = 0

    @property
    def mean_eval_score(self) -> float:
        return sum(self.eval_scores) / len(self.eval_scores) if self.eval_scores else 0.0


@dataclass
class PromotionCriteria:
    """Thresholds a workflow must clear to move up one level."""

    min_eval_score: float = 0.9
    min_approvals: int = 5
    min_runs: int = 20
    max_incidents: int = 0


def promotion_eligible(
    policy: AutonomyPolicy,
    history: WorkflowHistory,
    criteria: PromotionCriteria | None = None,
) -> Tuple[bool, List[str]]:
    """Return ``(eligible, reasons)`` for promoting *policy* one level up."""
    criteria = criteria or PromotionCriteria()
    reasons: List[str] = []
    if policy.level >= L3_AUTONOMOUS:
        return False, ["already at L3-autonomous (top of ladder)"]
    if history.mean_eval_score < criteria.min_eval_score:
        reasons.append(
            f"mean eval score {history.mean_eval_score:.3f} "
            f"< {criteria.min_eval_score:.3f}"
        )
    if history.approvals < criteria.min_approvals:
        reasons.append(f"approvals {history.approvals} < {criteria.min_approvals}")
    if history.runs < criteria.min_runs:
        reasons.append(f"runs {history.runs} < {criteria.min_runs}")
    if history.incidents > criteria.max_incidents:
        reasons.append(
            f"incidents {history.incidents} > {criteria.max_incidents}"
        )
    # Structural gates for the *target* level.
    target = policy.level + 1
    if target >= L2_AUGMENT and not policy.guardrails_required:
        reasons.append("promotion to L2+ requires guardrails_required=True")
    if target >= L3_AUTONOMOUS:
        if not policy.audit_required:
            reasons.append("promotion to L3 requires audit_required=True")
        if not policy.rollback_plan.strip():
            reasons.append("promotion to L3 requires a rollback_plan")
    return (not reasons), reasons


class AutonomyController:
    """Enforce autonomy policies at action time.

    Decisions: ``"proceed"`` (act now), ``"require_approval"`` (human gate),
    ``"deny"`` (blocked). The governance policy engine is consulted first —
    a denied action stays denied at every level.
    """

    def __init__(self, policy_engine: Any = None):
        if policy_engine is None:
            from food_ingredients_ai.governance.policy import PolicyEngine

            policy_engine = PolicyEngine()
        self._policies = policy_engine

    def decide(
        self,
        *,
        agent: str,
        action: str,
        policy: AutonomyPolicy,
        impact: str = "low",
    ) -> Dict[str, Any]:
        """Decide whether *agent* may perform *action* under *policy*."""
        if impact not in _IMPACT_ORDER:
            raise ValueError(f"unknown impact: {impact!r}")

        allowed, reason = self._policies.check(agent, action)
        if not allowed:
            return {
                "decision": "deny",
                "level": LEVEL_NAMES[policy.level],
                "reasons": [f"governance policy: {reason}"],
            }

        if policy.level >= L2_AUGMENT and not policy.guardrails_required:
            return {
                "decision": "deny",
                "level": LEVEL_NAMES[policy.level],
                "reasons": ["L2+ requires guardrails_required=True"],
            }
        if policy.level >= L3_AUTONOMOUS:
            if not policy.audit_required or not policy.rollback_plan.strip():
                return {
                    "decision": "deny",
                    "level": LEVEL_NAMES[policy.level],
                    "reasons": ["L3 requires audit_required=True and a rollback_plan"],
                }

        if policy.level == L0_MANUAL:
            return {
                "decision": "require_approval",
                "level": LEVEL_NAMES[policy.level],
                "reasons": ["L0-manual: agent drafts only; human decides and acts"],
            }

        # Above the policy's max impact -> human gate, regardless of level.
        if _IMPACT_ORDER[impact] > _IMPACT_ORDER[policy.max_impact]:
            return {
                "decision": "require_approval",
                "level": LEVEL_NAMES[policy.level],
                "reasons": [
                    f"impact {impact!r} exceeds policy max_impact {policy.max_impact!r}"
                ],
            }

        if impact == "high":
            # High-impact actions keep a human gate even when autonomous.
            return {
                "decision": "require_approval",
                "level": LEVEL_NAMES[policy.level],
                "reasons": ["high-impact actions always require approval"],
            }

        return {
            "decision": "proceed",
            "level": LEVEL_NAMES[policy.level],
            "reasons": [f"{LEVEL_NAMES[policy.level]} permits {impact}-impact action"],
        }
