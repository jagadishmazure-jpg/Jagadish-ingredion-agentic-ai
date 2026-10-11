"""Behavior-drift detection: flag when an agent starts acting out of character.

The detector keeps a per-agent histogram of action types. The first
``baseline_minimum`` actions establish the baseline (what this agent
normally does); the most recent ``recent_window`` actions are then
compared against it. When the fraction of *unseen* action types in the
recent window exceeds ``unseen_threshold``, the agent is flagged as
drifting.

This catches the "overstepping" failure mode: an agent that suddenly
starts calling tools it never used before — a compromised prompt, a
misconfigured deployment, or a model update that changed behavior.
"""

from __future__ import annotations

from collections import Counter, deque
from typing import Deque, Dict, Tuple


class BehaviorDrift:
    """Unseen-action-ratio drift detector per agent."""

    def __init__(
        self,
        baseline_minimum: int = 20,
        recent_window: int = 10,
        unseen_threshold: float = 0.3,
    ) -> None:
        if baseline_minimum <= 0 or recent_window <= 0:
            raise ValueError("window sizes must be positive")
        if not 0 < unseen_threshold <= 1:
            raise ValueError("unseen_threshold must be in (0, 1]")
        self.baseline_minimum = baseline_minimum
        self.recent_window = recent_window
        self.unseen_threshold = unseen_threshold
        self._histories: Dict[str, Deque[str]] = {}

    def _history(self, agent_id: str) -> Deque[str]:
        # Keep enough history for baseline + recent window.
        return self._histories.setdefault(
            agent_id, deque(maxlen=self.baseline_minimum + self.recent_window)
        )

    def record(self, agent_id: str, action: str) -> None:
        """Record one executed action type for *agent_id*."""
        self._history(agent_id).append(action)

    def histogram(self, agent_id: str) -> Dict[str, int]:
        """Baseline action-type histogram (excludes the recent window)."""
        history = list(self._history(agent_id))
        baseline = history[: max(0, len(history) - self.recent_window)]
        return dict(Counter(baseline))

    def check(self, agent_id: str) -> Tuple[bool, str]:
        """Return ``(drifted, reason)`` for *agent_id*.

        Needs at least ``baseline_minimum`` baseline actions plus one
        recent action; otherwise reports insufficient data (never a
        false positive on a cold start).
        """
        history = list(self._history(agent_id))
        if len(history) < self.baseline_minimum + 1:
            return False, (
                f"insufficient data for {agent_id!r}: "
                f"{len(history)} actions recorded, need "
                f"{self.baseline_minimum + 1}"
            )
        baseline = history[:- self.recent_window] or history[: -1]
        baseline_types = set(baseline)
        recent = history[-self.recent_window :]
        unseen = [a for a in recent if a not in baseline_types]
        ratio = len(unseen) / len(recent)
        if ratio > self.unseen_threshold:
            return True, (
                f"behavior drift for {agent_id!r}: {ratio:.0%} of the last "
                f"{len(recent)} actions ({sorted(set(unseen))}) unseen in "
                f"baseline of {len(baseline)} actions"
            )
        return False, (
            f"no drift for {agent_id!r}: {ratio:.0%} unseen "
            f"(threshold {self.unseen_threshold:.0%})"
        )

    def reset(self, agent_id: str) -> None:
        """Clear history (e.g. after a deliberate behavior change ships)."""
        self._histories.pop(agent_id, None)
