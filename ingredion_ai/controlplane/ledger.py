"""Control ledger: append-only, hash-chained log of enforcement decisions.

Every decision the
:class:`~ingredion_ai.controlplane.enforcement.EnforcementGate` makes is
recorded here — timestamp, agent, action, estimated cost, allowed/denied,
reason, and per-check detail. Entries are SHA-256 hash-chained like
:mod:`ingredion_ai.governance.audit` so tampering with any entry
invalidates every later hash.

The ledger answers the question every incident review asks first:
"exactly what was allowed, what was denied, and why?"
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List


def _entry_hash(previous_hash: str, body: str) -> str:
    return hashlib.sha256(f"{previous_hash}|{body}".encode("utf-8")).hexdigest()


class ControlLedger:
    """In-memory append-only log of enforcement decisions."""

    GENESIS_HASH = "0" * 64

    def __init__(self) -> None:
        self._entries: List[Dict[str, Any]] = []
        self._last_hash = self.GENESIS_HASH
        self._seq = 0

    def record(
        self,
        agent_id: str,
        action: str,
        allowed: bool,
        reason: str,
        checks: List[Dict[str, Any]] | None = None,
        estimated_cost_usd: float = 0.0,
    ) -> Dict[str, Any]:
        """Append one decision entry; returns the entry dict."""
        self._seq += 1
        entry = {
            "seq": self._seq,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "action": action,
            "estimated_cost_usd": estimated_cost_usd,
            "allowed": allowed,
            "reason": reason,
            "checks": checks or [],
        }
        body = json.dumps(entry, sort_keys=True, default=str)
        entry["previous_hash"] = self._last_hash
        entry["hash"] = _entry_hash(self._last_hash, body)
        self._last_hash = entry["hash"]
        self._entries.append(entry)
        return entry

    def read(self) -> Iterator[Dict[str, Any]]:
        """Yield entries in sequence order."""
        yield from self._entries

    def denials(self, agent_id: str | None = None) -> List[Dict[str, Any]]:
        """Denied decisions, optionally filtered to one agent."""
        return [
            e
            for e in self._entries
            if not e["allowed"] and (agent_id is None or e["agent_id"] == agent_id)
        ]

    def verify_chain(self) -> bool:
        """Verify hash-chain integrity; False on any tampering or gap."""
        previous = self.GENESIS_HASH
        for entry in self._entries:
            body_entry = {
                k: v
                for k, v in entry.items()
                if k not in ("hash", "previous_hash")
            }
            body = json.dumps(body_entry, sort_keys=True, default=str)
            if entry.get("previous_hash") != previous:
                return False
            if entry.get("hash") != _entry_hash(previous, body):
                return False
            previous = entry["hash"]
        return True

    def to_jsonl(self, path: str) -> int:
        """Persist entries to a JSONL file; returns entries written."""
        with open(path, "w", encoding="utf-8") as fh:
            for entry in self._entries:
                fh.write(json.dumps(entry, default=str) + "\n")
        return len(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
