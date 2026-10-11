"""Human-in-the-loop gate loop built on ``ingredion_ai.governance.approvals``.

The gate loop consults the demo approval policy
(:func:`~ingredion_ai.governance.approvals.requires_approval`): low-risk
actions pass through immediately; high-impact actions are requested from an
approver each round until approved, rejected, or ``max_rounds`` is reached.

The default approver is the governance module's simulated approver
(``ApprovalGate(auto_approve=True)``), so the offline demo never blocks. In
a real deployment the approver would be a human-facing gate
(``ApprovalGate(auto_approve=False)``) and the loop would wait for a human
between rounds instead of re-requesting immediately (see docs/governance.md).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ingredion_ai.governance.approvals import (
    ApprovalGate,
    ApprovalRecord,
    requires_approval,
)


def _summary(action_name: str, payload: Optional[Dict[str, Any]]) -> str:
    if isinstance(payload, dict) and payload.get("summary"):
        return str(payload["summary"])
    return f"HITL gate request for action '{action_name}' (demo)"


def hitl_gate(
    action_name: str,
    payload: Optional[Dict[str, Any]] = None,
    approver: Optional[ApprovalGate] = None,
    max_rounds: int = 3,
) -> Dict[str, Any]:
    """Run the approval gate loop for *action_name*.

    Returns ``{"decision", "rounds", "requires_approval", "record", "action"}``
    where ``decision`` is ``"approved"`` or ``"rejected"``, ``rounds`` counts
    approval requests made (0 when no approval was required), and ``record``
    is the last :class:`ApprovalRecord` (``None`` when the policy skipped
    approval entirely).
    """
    gate = approver if approver is not None else ApprovalGate()
    if not requires_approval(action_name):
        return {
            "decision": "approved",
            "rounds": 0,
            "requires_approval": False,
            "record": None,
            "action": action_name,
            "notes": "no approval required by demo policy",
        }

    summary = _summary(action_name, payload)
    rounds = 0
    record: Optional[ApprovalRecord] = None
    while rounds < max_rounds:
        rounds += 1
        record = gate.request(action_name, summary, payload)
        if record.approved:
            return {
                "decision": "approved",
                "rounds": rounds,
                "requires_approval": True,
                "record": record,
                "action": action_name,
                "notes": f"approved by {record.approver} in round {rounds}",
            }

    return {
        "decision": "rejected",
        "rounds": rounds,
        "requires_approval": True,
        "record": record,
        "action": action_name,
        "notes": (
            f"not approved after {rounds} round(s); "
            "in a real deployment a human would be paged between rounds"
        ),
    }
