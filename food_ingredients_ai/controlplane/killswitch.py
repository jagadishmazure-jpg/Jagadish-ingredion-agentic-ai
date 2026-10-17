"""Kill switch: immediate human halt for one agent or the whole fleet.

The kill switch is the emergency brake. It sits *above* every other
control-plane check: when engaged, the
:class:`~food_ingredients_ai.controlplane.enforcement.EnforcementGate` denies
everything for the halted scope without consulting circuits or budgets.

Scope:

- ``engage()`` / ``release()`` with no argument — global halt/resume.
- ``engage(agent_id)`` / ``release(agent_id)`` — per-agent halt/resume.

A global halt overrides per-agent state; releasing globally does not
clear per-agent halts (they were engaged deliberately).
"""

from __future__ import annotations

import threading
from typing import List


class KillSwitch:
    """Thread-safe global + per-agent halt flags."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._global_halted = False
        self._halted_agents: set[str] = set()

    def engage(self, agent_id: str | None = None) -> None:
        """Halt globally (``agent_id=None``) or for one agent."""
        with self._lock:
            if agent_id is None:
                self._global_halted = True
            else:
                self._halted_agents.add(agent_id)

    def release(self, agent_id: str | None = None) -> None:
        """Resume globally (``agent_id=None``) or for one agent."""
        with self._lock:
            if agent_id is None:
                self._global_halted = False
            else:
                self._halted_agents.discard(agent_id)

    def is_halted(self, agent_id: str) -> bool:
        """True when the agent is halted globally or individually."""
        with self._lock:
            return self._global_halted or agent_id in self._halted_agents

    def is_global_halt(self) -> bool:
        """True when the global halt is engaged."""
        with self._lock:
            return self._global_halted

    def halted_agents(self) -> List[str]:
        """Sorted list of individually halted agents."""
        with self._lock:
            return sorted(self._halted_agents)

    def reset(self) -> None:
        """Clear all halts (operator action, e.g. after an incident)."""
        with self._lock:
            self._global_halted = False
            self._halted_agents.clear()
