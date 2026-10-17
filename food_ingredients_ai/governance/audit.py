"""Immutable audit trail: append-only JSONL log of agent actions.

Each entry carries an ISO timestamp, the actor, the action, a JSON payload,
the governance decision, and a SHA-256 hash chained to the previous entry,
so tampering with any earlier entry invalidates every later hash.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


def _entry_hash(previous_hash: str, body: str) -> str:
    return hashlib.sha256(f"{previous_hash}|{body}".encode("utf-8")).hexdigest()


class AuditTrail:
    """Append-only audit log backed by a JSONL file."""

    GENESIS_HASH = "0" * 64

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._last_hash = self.GENESIS_HASH
        # Resume the chain if the file already exists.
        if self.path.exists():
            for entry in self.read():
                self._last_hash = entry["hash"]

    def log(
        self,
        actor: str,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
        decision: str = "allowed",
    ) -> Dict[str, Any]:
        """Append one audit entry; returns the entry dict."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "payload": payload or {},
            "decision": decision,
        }
        body = json.dumps(entry, sort_keys=True, default=str)
        entry["previous_hash"] = self._last_hash
        entry["hash"] = _entry_hash(self._last_hash, body)
        self._last_hash = entry["hash"]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
        return entry

    def read(self) -> Iterator[Dict[str, Any]]:
        """Yield entries in file order."""
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def verify_chain(self) -> bool:
        """Verify hash-chain integrity; False on any tampering or gap."""
        previous = self.GENESIS_HASH
        for entry in self.read():
            body_entry = {k: v for k, v in entry.items() if k not in ("hash", "previous_hash")}
            body = json.dumps(body_entry, sort_keys=True, default=str)
            if entry.get("previous_hash") != previous:
                return False
            if entry.get("hash") != _entry_hash(previous, body):
                return False
            previous = entry["hash"]
        return True

    def close(self) -> None:
        """No-op kept for API symmetry (file is closed after every write)."""
