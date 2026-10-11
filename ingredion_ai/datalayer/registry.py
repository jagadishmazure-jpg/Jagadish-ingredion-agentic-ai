"""Versioned dataset registry: pin versions, validate on load, track lineage."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ingredion_ai.datalayer.connectors import (
    Connector,
    FileConnector,
    GlossaryConnector,
)
from ingredion_ai.datalayer.lineage import Lineage, compute_content_hash
from ingredion_ai.datalayer.schema import FieldSpec, validate_all

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"

_NUM = (int, float)


@dataclass
class DatasetVersion:
    """One pinned version of a dataset."""

    name: str
    version: str
    connector: Connector
    schema: List[FieldSpec] = field(default_factory=list)
    transform: Optional[Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]] = None


@dataclass
class LoadedDataset:
    """Validated records plus their lineage."""

    name: str
    version: str
    records: List[Dict[str, Any]]
    lineage: Lineage


def _coerce_demand(
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """CSV yields strings; coerce to the demo's typed shape."""
    out = []
    for row in rows:
        out.append(
            {
                "sku": row["sku"],
                "week": int(row["week"]),
                "demand_tonnes": float(row["demand_tonnes"]),
                "demo": row["demo"] == "true",
            }
        )
    return out


class DatasetRegistry:
    """Register named dataset versions; load validated data with lineage."""

    def __init__(self) -> None:
        self._versions: Dict[str, Dict[str, DatasetVersion]] = {}

    def register(self, dataset: DatasetVersion) -> None:
        """Register (or override) one dataset version."""
        self._versions.setdefault(dataset.name, {})[dataset.version] = dataset

    def versions(self, name: str) -> List[str]:
        """Sorted registered versions for *name* (KeyError if unknown)."""
        try:
            return sorted(self._versions[name])
        except KeyError:
            raise KeyError(f"unknown dataset: {name!r}") from None

    def get(self, name: str, version: Optional[str] = None) -> LoadedDataset:
        """Load, transform, validate (fail-fast), and hash a dataset.

        *version* pins an exact version; omitted → latest registered.
        """
        available = self.versions(name)
        chosen = version or available[-1]
        if chosen not in self._versions[name]:
            raise KeyError(
                f"dataset {name!r} has no version {chosen!r}; "
                f"available: {available}"
            )
        spec = self._versions[name][chosen]
        records = spec.connector.read()
        if spec.transform is not None:
            records = spec.transform(records)
        validate_all(records, spec.schema, f"{name}@{chosen}")
        lineage = Lineage(
            dataset=name,
            version=chosen,
            content_sha256=compute_content_hash(records),
            record_count=len(records),
            source=spec.connector.describe(),
        )
        return LoadedDataset(
            name=name, version=chosen, records=records, lineage=lineage
        )


def default_registry() -> DatasetRegistry:
    """Registry pre-loaded with the demo's synthetic datasets (pinned)."""
    reg = DatasetRegistry()
    reg.register(
        DatasetVersion(
            name="ingredients",
            version="v3",
            connector=FileConnector(_DATA_DIR / "ingredients.json"),
            schema=[
                FieldSpec("id", (str,)),
                FieldSpec("name", (str,)),
                FieldSpec("category", (str,)),
                FieldSpec("clean_label", (bool,)),
                FieldSpec("natural", (bool,)),
                FieldSpec("cost_index", _NUM),
                FieldSpec("function", (str,)),
                FieldSpec("regions", (list,)),
                FieldSpec("usage_min", _NUM),
                FieldSpec("usage_max", _NUM),
                FieldSpec("texture_impact", _NUM),
                FieldSpec("nutrition", (dict,)),
            ],
        )
    )
    reg.register(
        DatasetVersion(
            name="formulas",
            version="v2",
            connector=FileConnector(_DATA_DIR / "formulas.json"),
            schema=[
                FieldSpec("id", (str,)),
                FieldSpec("name", (str,), required=False),
                FieldSpec("category", (str,), required=False),
                FieldSpec("demo", (bool,), required=False),
                FieldSpec("ingredients", (list,)),
            ],
        )
    )
    reg.register(
        DatasetVersion(
            name="demand",
            version="v1",
            connector=FileConnector(_DATA_DIR / "demand.csv", format="csv"),
            transform=_coerce_demand,
            schema=[
                FieldSpec("sku", (str,)),
                FieldSpec("week", (int,)),
                FieldSpec("demand_tonnes", _NUM),
                FieldSpec("demo", (bool,)),
            ],
        )
    )
    reg.register(
        DatasetVersion(
            name="esg_readings",
            version="v1",
            connector=FileConnector(_DATA_DIR / "esg_readings.json"),
            schema=[
                FieldSpec("plant", (str,)),
                FieldSpec("quarter", (str,)),
                FieldSpec("demo", (bool,), required=False),
                FieldSpec("emissions_tco2e", _NUM),
                FieldSpec("energy_kwh", _NUM),
                FieldSpec("water_m3", _NUM),
                FieldSpec("production_tonnes", _NUM),
            ],
        )
    )
    reg.register(
        DatasetVersion(
            name="glossary",
            version="v1",
            connector=GlossaryConnector(_DOCS_DIR / "glossary.md"),
            schema=[
                FieldSpec("term", (str,)),
                FieldSpec("definition", (str,)),
            ],
        )
    )
    return reg
