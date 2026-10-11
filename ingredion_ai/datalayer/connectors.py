"""Connector abstraction: how datasets are read.

:class:`Connector` is the interface. :class:`FileConnector` reads local
JSON/CSV (demo). Production path: subclass ``Connector`` and implement
``read()`` against Microsoft Fabric/OneLake, Azure Blob Storage, or
Azure SQL — the registry, schemas, and lineage stay identical.
"""

from __future__ import annotations

import abc
import csv
import json
from pathlib import Path
from typing import Any, Dict, List


class Connector(abc.ABC):
    """Source of dataset records."""

    @abc.abstractmethod
    def read(self) -> List[Dict[str, Any]]:
        """Return all records as a list of mappings."""

    def describe(self) -> Dict[str, Any]:
        """Human-readable source description (for lineage/debugging)."""
        return {"connector": type(self).__name__}


class FileConnector(Connector):
    """Read a local JSON (list) or CSV file (demo connector)."""

    def __init__(self, path: str | Path, format: str = "json") -> None:
        self.path = Path(path)
        if format not in ("json", "csv"):
            raise ValueError(f"unsupported format: {format!r}")
        self.format = format

    def read(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            raise FileNotFoundError(f"dataset file not found: {self.path}")
        if self.format == "json":
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                raise ValueError(
                    f"expected a JSON list in {self.path}, got "
                    f"{type(data).__name__}"
                )
            return data
        with open(self.path, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def describe(self) -> Dict[str, Any]:
        return {
            "connector": "FileConnector",
            "path": str(self.path),
            "format": self.format,
        }


class GlossaryConnector(Connector):
    """Parse the governed glossary markdown into term/definition records.

    Reads the ``| **term** | definition | ... |`` tables in
    ``docs/glossary.md`` so the semantic layer is itself a versioned,
    validated dataset.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            raise FileNotFoundError(f"glossary file not found: {self.path}")
        records: List[Dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("| **"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 2:
                continue
            term = cells[0].strip("*").strip()
            records.append({"term": term, "definition": cells[1]})
        return records

    def describe(self) -> Dict[str, Any]:
        return {"connector": "GlossaryConnector", "path": str(self.path)}
