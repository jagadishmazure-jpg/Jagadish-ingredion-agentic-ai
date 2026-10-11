"""Action-rate budgets and spend caps per agent (demo).

Where :mod:`ingredion_ai.observability.costs` *tracks* spend, this module
*enforces* it: every action must fit inside its agent's rate limits and
spend caps or it is denied before it executes.

All time handling goes through an injectable ``clock`` (a callable
returning ``datetime``) so tests can freeze or advance time
deterministically.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Callable, Deque, Dict, Tuple

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActionBudget:
    """Per-agent limits on tool-call volume.

    Three independent limiters, all checked on every action:

    - per-run: at most ``max_per_run`` actions within one ``run_id``
    - per-hour: sliding 60-minute window of action timestamps
    - per-day: calendar-day counter (resets at UTC midnight)

    Use :meth:`check_and_record` — it denies without recording, so denied
    actions never consume budget.
    """

    def __init__(
        self,
        max_per_run: int = 50,
        max_per_hour: int = 200,
        max_per_day: int = 1000,
        clock: Clock | None = None,
    ) -> None:
        if max_per_run <= 0 or max_per_hour <= 0 or max_per_day <= 0:
            raise ValueError("budget limits must be positive")
        self.max_per_run = max_per_run
        self.max_per_hour = max_per_hour
        self.max_per_day = max_per_day
        self._clock = clock or _utcnow
        self._per_run: Dict[Tuple[str, str], int] = defaultdict(int)
        self._hourly: Dict[str, Deque[datetime]] = defaultdict(deque)
        self._daily: Dict[Tuple[str, str], int] = defaultdict(int)

    def _prune_hourly(self, agent_id: str, now: datetime) -> None:
        window_start = now - timedelta(hours=1)
        stamps = self._hourly[agent_id]
        while stamps and stamps[0] <= window_start:
            stamps.popleft()

    def _day_key(self, now: datetime) -> str:
        return now.date().isoformat()

    def check(self, agent_id: str, run_id: str = "default") -> Tuple[bool, str]:
        """Return ``(allowed, reason)`` without consuming budget."""
        now = self._clock()
        if self._per_run[(agent_id, run_id)] >= self.max_per_run:
            return False, (
                f"run budget exhausted for {agent_id!r}: "
                f"{self.max_per_run} actions per run"
            )
        self._prune_hourly(agent_id, now)
        if len(self._hourly[agent_id]) >= self.max_per_hour:
            return False, (
                f"hourly budget exhausted for {agent_id!r}: "
                f"{self.max_per_hour} actions per hour"
            )
        if self._daily[(agent_id, self._day_key(now))] >= self.max_per_day:
            return False, (
                f"daily budget exhausted for {agent_id!r}: "
                f"{self.max_per_day} actions per day"
            )
        return True, "within action budget"

    def record(self, agent_id: str, run_id: str = "default") -> None:
        """Consume one action of budget (call only after :meth:`check`)."""
        now = self._clock()
        self._per_run[(agent_id, run_id)] += 1
        self._hourly[agent_id].append(now)
        self._daily[(agent_id, self._day_key(now))] += 1

    def check_and_record(
        self, agent_id: str, run_id: str = "default"
    ) -> Tuple[bool, str]:
        """Atomically check limits and consume one action if allowed."""
        allowed, reason = self.check(agent_id, run_id)
        if allowed:
            self.record(agent_id, run_id)
        return allowed, reason

    def usage(self, agent_id: str, run_id: str = "default") -> Dict[str, int]:
        """Current consumption snapshot (for dashboards/tests)."""
        now = self._clock()
        self._prune_hourly(agent_id, now)
        return {
            "run": self._per_run[(agent_id, run_id)],
            "hour": len(self._hourly[agent_id]),
            "day": self._daily[(agent_id, self._day_key(now))],
        }


class SpendCap:
    """Per-agent spend caps in USD (per run and per calendar day).

    Mirrors :class:`ActionBudget` semantics: :meth:`check_and_record`
    denies without recording, so a denied action never spends.
    """

    def __init__(
        self,
        max_usd_per_run: float = 5.0,
        max_usd_per_day: float = 50.0,
        clock: Clock | None = None,
    ) -> None:
        if max_usd_per_run <= 0 or max_usd_per_day <= 0:
            raise ValueError("spend caps must be positive")
        self.max_usd_per_run = max_usd_per_run
        self.max_usd_per_day = max_usd_per_day
        self._clock = clock or _utcnow
        self._run_spend: Dict[Tuple[str, str], float] = defaultdict(float)
        self._day_spend: Dict[Tuple[str, str], float] = defaultdict(float)

    def check(
        self, agent_id: str, cost_usd: float, run_id: str = "default"
    ) -> Tuple[bool, str]:
        """Return ``(allowed, reason)`` for spending *cost_usd*."""
        if cost_usd < 0:
            return False, "negative cost is invalid"
        now = self._clock()
        day_key = now.date().isoformat()
        if self._run_spend[(agent_id, run_id)] + cost_usd > self.max_usd_per_run:
            return False, (
                f"run spend cap exceeded for {agent_id!r}: "
                f"would reach ${self._run_spend[(agent_id, run_id)] + cost_usd:.4f} "
                f"(cap ${self.max_usd_per_run:.2f})"
            )
        if self._day_spend[(agent_id, day_key)] + cost_usd > self.max_usd_per_day:
            return False, (
                f"daily spend cap exceeded for {agent_id!r}: "
                f"would reach ${self._day_spend[(agent_id, day_key)] + cost_usd:.4f} "
                f"(cap ${self.max_usd_per_day:.2f})"
            )
        return True, "within spend cap"

    def record(self, agent_id: str, cost_usd: float, run_id: str = "default") -> None:
        """Record spend (call only after :meth:`check`)."""
        day_key = self._clock().date().isoformat()
        self._run_spend[(agent_id, run_id)] = round(
            self._run_spend[(agent_id, run_id)] + cost_usd, 6
        )
        self._day_spend[(agent_id, day_key)] = round(
            self._day_spend[(agent_id, day_key)] + cost_usd, 6
        )

    def check_and_record(
        self, agent_id: str, cost_usd: float, run_id: str = "default"
    ) -> Tuple[bool, str]:
        """Atomically check caps and record spend if allowed."""
        allowed, reason = self.check(agent_id, cost_usd, run_id)
        if allowed:
            self.record(agent_id, cost_usd, run_id)
        return allowed, reason

    def spend(self, agent_id: str, run_id: str = "default") -> Dict[str, float]:
        """Current spend snapshot (for dashboards/tests)."""
        day_key = self._clock().date().isoformat()
        return {
            "run_usd": self._run_spend[(agent_id, run_id)],
            "day_usd": self._day_spend[(agent_id, day_key)],
        }


class BudgetManager:
    """One-call enforcement combining action budget and spend cap.

    ``check(agent_id, action, cost, run_id)`` is the signature the
    :class:`~ingredion_ai.controlplane.enforcement.EnforcementGate` uses:
    it returns ``(allowed, reason)`` and records consumption only when
    the action is allowed.
    """

    def __init__(
        self,
        action_budget: ActionBudget | None = None,
        spend_cap: SpendCap | None = None,
    ) -> None:
        self.action_budget = action_budget or ActionBudget()
        self.spend_cap = spend_cap or SpendCap()

    def check(
        self,
        agent_id: str,
        action: str,
        cost: float = 0.0,
        run_id: str = "default",
    ) -> Tuple[bool, str]:
        """Check rate limits first, then spend caps; record on allow."""
        allowed, reason = self.action_budget.check(agent_id, run_id)
        if not allowed:
            return False, f"budget: {reason}"
        allowed, reason = self.spend_cap.check(agent_id, cost, run_id)
        if not allowed:
            return False, f"spend: {reason}"
        self.action_budget.record(agent_id, run_id)
        self.spend_cap.record(agent_id, cost, run_id)
        return True, f"budget ok for action {action!r}"
