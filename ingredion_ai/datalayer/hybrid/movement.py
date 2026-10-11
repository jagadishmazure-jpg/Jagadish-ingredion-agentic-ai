"""Movement log: every data movement between environments, decided and recorded.

Enterprises move data between environments constantly; each movement is a
governance event. :class:`MovementLog` runs the location-aware policy
check *before* the move, denies residency violations, and records every
approved and denied movement in a hash-chained ledger (same mechanics as
:mod:`ingredion_ai.controlplane.ledger`) so the full movement history is
auditable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List

from ingredion_ai.datalayer.hybrid.environments import EnvironmentRegistry
from ingredion_ai.datalayer.hybrid.placement import PlacementRegistry
from ingredion_ai.datalayer.hybrid.policies import HybridPolicyEngine


def _entry_hash(previous_hash: str, body: str) -> str:
    return hashlib.sha256(f"{previous_hash}|{body}".encode("utf-8")).hexdigest()


class MovementLog:
    """Policy-gated, hash-chained log of cross-environment data movements."""

    GENESIS_HASH = "0" * 64

    def __init__(
        self,
        envs: EnvironmentRegistry,
        placements: PlacementRegistry,
        policies: HybridPolicyEngine,
    ) -> None:
        self._envs = envs
        self._placements = placements
        self._policies = policies
        self._entries: List[Dict[str, Any]] = []
        self._last_hash = self.GENESIS_HASH
        self._seq = 0

    def request_move(
        self,
        dataset_id: str,
        from_env: str,
        to_env: str,
        actor: str = "data-plane",
        mode: str = "copy",
    ) -> Dict[str, Any]:
        """Request moving *dataset_id* from *from_env* to *to_env*.

        The policy check runs first. Denied moves are recorded with their
        reason and change nothing. Approved ``copy`` moves replicate the
        dataset; approved ``move`` moves replicate then remove the source.
        Returns the ledger entry.
        """
        if mode not in ("copy", "move"):
            raise ValueError(f"mode must be 'copy' or 'move', got {mode!r}")
        try:
            placement = self._placements.get(dataset_id)
        except KeyError:
            return self._record(
                dataset_id, from_env, to_env, actor, False,
                f"no placement registered for {dataset_id!r}",
            )
        if from_env not in placement.locations:
            return self._record(
                dataset_id, from_env, to_env, actor, False,
                f"{dataset_id!r} is not present in {from_env!r}; cannot move from there",
            )
        allowed, reason = self._policies.check_access(
            dataset_id, to_env, purpose="data movement"
        )
        if not allowed:
            return self._record(dataset_id, from_env, to_env, actor, False, reason)
        self._placements.add_location(dataset_id, to_env)
        if mode == "move":
            self._placements.remove_location(dataset_id, from_env)
        return self._record(
            dataset_id, from_env, to_env, actor, True,
            f"{mode} approved: {reason}",
        )

    def _record(
        self,
        dataset_id: str,
        from_env: str,
        to_env: str,
        actor: str,
        approved: bool,
        reason: str,
    ) -> Dict[str, Any]:
        self._seq += 1
        entry = {
            "seq": self._seq,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "dataset_id": dataset_id,
            "from_env": from_env,
            "to_env": to_env,
            "approved": approved,
            "reason": reason,
        }
        body = json.dumps(entry, sort_keys=True, default=str)
        entry["previous_hash"] = self._last_hash
        entry["hash"] = _entry_hash(self._last_hash, body)
        self._last_hash = entry["hash"]
        self._entries.append(entry)
        return entry

    def entries(self) -> Iterator[Dict[str, Any]]:
        """All movement entries in order."""
        return iter(self._entries)

    def denied(self) -> List[Dict[str, Any]]:
        """Denied movements only."""
        return [e for e in self._entries if not e["approved"]]

    def verify_chain(self) -> bool:
        """Verify hash-chain integrity; False on any tampering or gap."""
        previous = self.GENESIS_HASH
        for entry in self._entries:
            body_entry = {
                k: v for k, v in entry.items() if k not in ("hash", "previous_hash")
            }
            body = json.dumps(body_entry, sort_keys=True, default=str)
            if entry.get("previous_hash") != previous:
                return False
            if entry.get("hash") != _entry_hash(previous, body):
                return False
            previous = entry["hash"]
        return True
