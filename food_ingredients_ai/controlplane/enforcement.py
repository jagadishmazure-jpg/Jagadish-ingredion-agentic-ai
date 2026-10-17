"""Enforcement gate: the single choke point for agent actions.

Every tool call an agent wants to make passes through
:meth:`EnforcementGate.authorize` first. Checks run in a fixed order and
**short-circuit on the first denial** — a halted agent never consumes
budget, and a tripped circuit never reaches the spend check:

1. **kill switch** — is this agent (or the whole fleet) halted?
2. **circuit breaker** — is this agent currently unhealthy?
3. **budgets** — does this action fit the rate limits and spend caps?

The returned decision dict records every check that ran::

    {
        "allowed": True,
        "reason": "killswitch clear; circuit closed; budget ok for action 'x'",
        "checks": [
            {"name": "killswitch", "allowed": True, "reason": "..."},
            {"name": "circuit", "allowed": True, "reason": "..."},
            {"name": "budget", "allowed": True, "reason": "..."},
        ],
    }

Every decision — allow or deny — is written to the control ledger.
"""

from __future__ import annotations

from typing import Any, Dict, List

from food_ingredients_ai.controlplane.budgets import BudgetManager
from food_ingredients_ai.controlplane.circuit import CircuitBreaker
from food_ingredients_ai.controlplane.killswitch import KillSwitch
from food_ingredients_ai.controlplane.ledger import ControlLedger


class EnforcementGate:
    """Single choke point combining kill switch, circuit, and budgets."""

    def __init__(
        self,
        killswitch: KillSwitch | None = None,
        circuit: CircuitBreaker | None = None,
        budgets: BudgetManager | None = None,
        ledger: ControlLedger | None = None,
    ) -> None:
        self.killswitch = killswitch or KillSwitch()
        self.circuit = circuit or CircuitBreaker()
        self.budgets = budgets or BudgetManager()
        self.ledger = ledger or ControlLedger()

    def authorize(
        self,
        agent_id: str,
        action: str,
        estimated_cost: float = 0.0,
        run_id: str = "default",
    ) -> Dict[str, Any]:
        """Authorize one action; short-circuit on the first denial."""
        checks: List[Dict[str, Any]] = []

        # 1. Kill switch — the emergency brake beats everything.
        if self.killswitch.is_halted(agent_id):
            scope = (
                "global halt engaged"
                if self.killswitch.is_global_halt()
                else f"agent {agent_id!r} halted"
            )
            checks.append(
                {"name": "killswitch", "allowed": False, "reason": scope}
            )
            return self._decide(agent_id, action, estimated_cost, checks)

        checks.append(
            {"name": "killswitch", "allowed": True, "reason": "no halt engaged"}
        )

        # 2. Circuit breaker — unhealthy agents don't get more rope.
        circuit_ok, circuit_reason = self.circuit.allows(agent_id)
        checks.append(
            {"name": "circuit", "allowed": circuit_ok, "reason": circuit_reason}
        )
        if not circuit_ok:
            return self._decide(agent_id, action, estimated_cost, checks)

        # 3. Budgets — rate limits and spend caps (records on allow).
        budget_ok, budget_reason = self.budgets.check(
            agent_id, action, estimated_cost, run_id
        )
        checks.append(
            {"name": "budget", "allowed": budget_ok, "reason": budget_reason}
        )
        return self._decide(agent_id, action, estimated_cost, checks)

    def _decide(
        self,
        agent_id: str,
        action: str,
        estimated_cost: float,
        checks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        failed = next((c for c in checks if not c["allowed"]), None)
        if failed is not None:
            allowed = False
            reason = f"denied by {failed['name']}: {failed['reason']}"
        else:
            allowed = True
            reason = "; ".join(
                f"{c['name']}: {c['reason']}" for c in checks
            )
        decision = {
            "allowed": allowed,
            "reason": reason,
            "checks": checks,
        }
        self.ledger.record(
            agent_id=agent_id,
            action=action,
            allowed=allowed,
            reason=reason,
            checks=checks,
            estimated_cost_usd=estimated_cost,
        )
        return decision

    def report_outcome(
        self, agent_id: str, action: str, success: bool
    ) -> None:
        """Feed an action's outcome back to the circuit breaker.

        Call this after executing an allowed action so the breaker can
        count failures. (Denials never reach the breaker.)
        """
        if success:
            self.circuit.record_success(agent_id)
        else:
            self.circuit.record_failure(agent_id)
