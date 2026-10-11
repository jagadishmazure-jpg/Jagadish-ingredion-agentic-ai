"""Human-in-the-loop approval gates for high-impact demo outputs.

Agents propose; humans approve. In offline/demo mode the gate auto-approves
with a clearly-marked simulated approver so the demo stays runnable without
a human present. In a real deployment the gate would block until a human
responds (see docs/governance.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Output types that must not ship without human approval.
HIGH_IMPACT_OUTPUTS = {
    "new_formulation",
    "customer_proposal",
    "esg_report",
    "production_schedule",
    "procurement_plan",
}


def requires_approval(output_type: str) -> bool:
    """Whether *output_type* needs human approval before release."""
    return output_type in HIGH_IMPACT_OUTPUTS


@dataclass
class ApprovalRecord:
    output_type: str
    summary: str
    approved: bool
    approver: str
    decided_at: str
    simulated: bool
    notes: str = ""


@dataclass
class ApprovalGate:
    """Approval gate; ``auto_approve=True`` simulates a human for demos."""

    auto_approve: bool = True
    records: List[ApprovalRecord] = field(default_factory=list)

    def request(
        self,
        output_type: str,
        summary: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRecord:
        """Request approval for *output_type*; returns the recorded decision."""
        if not requires_approval(output_type):
            record = ApprovalRecord(
                output_type=output_type,
                summary=summary,
                approved=True,
                approver="policy",
                decided_at=datetime.now(timezone.utc).isoformat(),
                simulated=False,
                notes="no approval required by demo policy",
            )
        elif self.auto_approve:
            record = ApprovalRecord(
                output_type=output_type,
                summary=summary,
                approved=True,
                approver="simulated-human-approver",
                decided_at=datetime.now(timezone.utc).isoformat(),
                simulated=True,
                notes="demo mode: simulated approval, not a real human sign-off",
            )
        else:
            record = ApprovalRecord(
                output_type=output_type,
                summary=summary,
                approved=False,
                approver="pending",
                decided_at=datetime.now(timezone.utc).isoformat(),
                simulated=False,
                notes="blocked: waiting for human approval",
            )
        self.records.append(record)
        return record

    def approved(self, output_type: str) -> bool:
        """Whether the latest decision for *output_type* was an approval."""
        for record in reversed(self.records):
            if record.output_type == output_type:
                return record.approved
        return False
