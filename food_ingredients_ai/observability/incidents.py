"""Incident-style operational metrics for agent runs (demo).

Borrowed measurement framing from SOC practice and mapped onto agent
operations (see docs/soc-alignment.md for the honest framing: this is a
manufacturing demo, not a SOC — the *measurement discipline* transfers,
the domain does not):

- detection time  -> time for an agent to flag an issue (e.g. analyzer
  flagging a non-clean-label ingredient), measured per run;
- response time   -> time from flag to completed mitigation (e.g.
  reformulation with substitutes applied);
- false positives -> benign inputs flagged as issues;
- automation rate -> share of runs completing without human intervention.

All offline and deterministic; latencies are measured, everything else is
counted from labeled outcomes.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class IncidentRecord:
    """One tracked operational "incident" (an agent-run issue lifecycle)."""

    incident_id: str
    kind: str  # e.g. "flagged_ingredient", "claim_rejected", "risk_flag"
    detected_at_ms: float
    responded_at_ms: Optional[float] = None
    resolved: bool = False
    false_positive: bool = False
    automated: bool = True  # no human touched it
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def response_time_ms(self) -> Optional[float]:
        if self.responded_at_ms is None:
            return None
        return round(self.responded_at_ms - self.detected_at_ms, 3)


class IncidentTracker:
    """Track detection/response lifecycles and compute SOC-style metrics."""

    def __init__(self) -> None:
        self.incidents: List[IncidentRecord] = []
        self._counter = 0

    def detect(self, kind: str, attributes: Optional[Dict[str, Any]] = None) -> IncidentRecord:
        """Open an incident at "now" (detection)."""
        self._counter += 1
        record = IncidentRecord(
            incident_id=f"inc-{self._counter:04d}",
            kind=kind,
            detected_at_ms=time.perf_counter() * 1000,
            attributes=attributes or {},
        )
        self.incidents.append(record)
        return record

    def respond(
        self,
        record: IncidentRecord,
        resolved: bool = True,
        false_positive: bool = False,
        automated: bool = True,
    ) -> IncidentRecord:
        """Close the response phase for *record*."""
        record.responded_at_ms = time.perf_counter() * 1000
        record.resolved = resolved
        record.false_positive = false_positive
        record.automated = automated
        return record

    @contextmanager
    def track(
        self, kind: str, attributes: Optional[Dict[str, Any]] = None
    ) -> Iterator[IncidentRecord]:
        """Context manager: detect on entry, respond(resolved=True) on exit."""
        record = self.detect(kind, attributes)
        try:
            yield record
        except Exception:
            self.respond(record, resolved=False, automated=False)
            raise
        self.respond(record, resolved=True)

    def metrics(self) -> Dict[str, Any]:
        """Compute the SOC-style metric set over tracked incidents."""
        responded = [i for i in self.incidents if i.responded_at_ms is not None]
        response_times = [
            i.response_time_ms for i in responded if i.response_time_ms is not None
        ]
        fps = sum(1 for i in self.incidents if i.false_positive)
        automated = sum(1 for i in responded if i.automated)
        return {
            "incidents_total": len(self.incidents),
            "incidents_responded": len(responded),
            # MTTD analogue: detection is instantaneous in the demo pipeline,
            # so we report mean *response* time (MTTR analogue).
            "mean_response_time_ms": (
                round(sum(response_times) / len(response_times), 3)
                if response_times else 0.0
            ),
            "false_positive_rate": (
                round(fps / len(self.incidents), 4) if self.incidents else 0.0
            ),
            "automation_rate": (
                round(automated / len(responded), 4) if responded else 0.0
            ),
            "resolved_rate": (
                round(
                    sum(1 for i in responded if i.resolved) / len(responded), 4
                ) if responded else 0.0
            ),
        }
