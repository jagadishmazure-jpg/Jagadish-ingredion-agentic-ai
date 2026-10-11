"""Circuit breaker: stop a misbehaving agent before it does more damage.

States:

- CLOSED — traffic flows; failures are counted in a sliding window.
- OPEN — traffic is blocked; the agent is presumed unhealthy.
- HALF_OPEN — after a cooldown, one probe action is allowed through to
  test recovery. Success closes the circuit; failure re-opens it.

A circuit trips when ``failure_threshold`` failures occur inside
``window_seconds``. This catches runaway loops, poisoned tools, and
cascading failures — the failure modes unit tests cannot see.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable, Deque, Dict, Tuple

from ingredion_ai.controlplane.budgets import Clock, _utcnow

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class _CircuitState:
    __slots__ = ("failures", "state", "opened_at", "probe_in_flight")

    def __init__(self) -> None:
        self.failures: Deque[datetime] = deque()
        self.state: str = CLOSED
        self.opened_at: datetime | None = None
        self.probe_in_flight: bool = False


class CircuitBreaker:
    """Per-agent circuit breaker with sliding-window failure counting."""

    def __init__(
        self,
        failure_threshold: int = 5,
        window_seconds: int = 60,
        cooldown_seconds: int = 30,
        clock: Clock | None = None,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock or _utcnow
        self._states: Dict[str, _CircuitState] = {}

    def _state_for(self, agent_id: str) -> _CircuitState:
        return self._states.setdefault(agent_id, _CircuitState())

    def _prune(self, state: _CircuitState, now: datetime) -> None:
        cutoff = now - timedelta(seconds=self.window_seconds)
        while state.failures and state.failures[0] <= cutoff:
            state.failures.popleft()

    def record_success(self, agent_id: str) -> None:
        """Record a successful action; may close a half-open circuit."""
        state = self._state_for(agent_id)
        now = self._clock()
        if state.state == HALF_OPEN:
            state.state = CLOSED
            state.failures.clear()
            state.opened_at = None
            state.probe_in_flight = False
        elif state.state == CLOSED:
            self._prune(state, now)

    def record_failure(self, agent_id: str) -> None:
        """Record a failed action; may trip the circuit open."""
        state = self._state_for(agent_id)
        now = self._clock()
        if state.state == HALF_OPEN:
            # Failed probe: back to open with a fresh cooldown.
            state.state = OPEN
            state.opened_at = now
            state.probe_in_flight = False
            return
        state.failures.append(now)
        self._prune(state, now)
        if state.state == CLOSED and len(state.failures) >= self.failure_threshold:
            state.state = OPEN
            state.opened_at = now

    def allows(self, agent_id: str) -> Tuple[bool, str]:
        """Return ``(allowed, reason)`` for the next action."""
        state = self._state_for(agent_id)
        now = self._clock()
        if state.state == CLOSED:
            self._prune(state, now)
            return True, "circuit closed"
        if state.state == OPEN:
            assert state.opened_at is not None
            elapsed = (now - state.opened_at).total_seconds()
            if elapsed >= self.cooldown_seconds:
                state.state = HALF_OPEN
                state.probe_in_flight = True
                return True, "circuit half-open: probe allowed"
            remaining = int(self.cooldown_seconds - elapsed)
            return False, f"circuit open for {agent_id!r} (cooldown {remaining}s left)"
        # HALF_OPEN
        if state.probe_in_flight:
            return False, f"circuit half-open probe already in flight for {agent_id!r}"
        state.probe_in_flight = True
        return True, "circuit half-open: probe allowed"

    def status(self, agent_id: str) -> Dict[str, object]:
        """Current state snapshot (for dashboards/tests)."""
        state = self._state_for(agent_id)
        self._prune(state, self._clock())
        return {
            "state": state.state,
            "failures_in_window": len(state.failures),
            "failure_threshold": self.failure_threshold,
        }

    def reset(self, agent_id: str) -> None:
        """Force-close the circuit (operator action, e.g. after a fix)."""
        state = self._state_for(agent_id)
        state.state = CLOSED
        state.failures.clear()
        state.opened_at = None
        state.probe_in_flight = False
