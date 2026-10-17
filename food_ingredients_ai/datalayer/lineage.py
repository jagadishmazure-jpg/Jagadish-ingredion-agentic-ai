"""Data lineage: version + content hash recorded into run outputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


def compute_content_hash(records: List[Dict[str, Any]]) -> str:
    """Deterministic SHA-256 over the canonical JSON of *records*."""
    canonical = json.dumps(records, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Lineage:
    """Provenance for one loaded dataset version."""

    dataset: str
    version: str
    content_sha256: str
    record_count: int
    source: Dict[str, Any] = field(default_factory=dict)
    loaded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset": self.dataset,
            "version": self.version,
            "content_sha256": self.content_sha256,
            "record_count": self.record_count,
            "source": self.source,
            "loaded_at": self.loaded_at,
        }


def attach_lineage(run_output: Dict[str, Any], lineage: Lineage) -> Dict[str, Any]:
    """Attach *lineage* to a run-output dict (under ``data_lineage``).

    Returns *run_output* for chaining. The audit trail writer can call
    this so every audited run carries its dataset provenance.
    """
    entries = run_output.setdefault("data_lineage", [])
    entries.append(lineage.to_dict())
    return run_output
