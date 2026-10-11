"""Versioned data layer: dataset registry, schema validation, lineage.

All datasets are synthetic demo data. The registry pins dataset versions so
runs are reproducible; every load is schema-validated (fail-fast) and
records lineage (version + content hash) that callers attach to run outputs
and the audit trail.

Connector abstraction: :class:`FileConnector` reads local JSON/CSV now.
Production path (documented in ``docs/stack-alignment.md``): implement
``Connector.read()`` against Microsoft Fabric/OneLake, Azure Blob Storage,
or Azure SQL — the registry, schemas, and lineage are unchanged.
"""

from ingredion_ai.datalayer.connectors import Connector, FileConnector
from ingredion_ai.datalayer.lineage import (
    Lineage,
    attach_lineage,
    compute_content_hash,
)
from ingredion_ai.datalayer.registry import (
    DatasetRegistry,
    DatasetVersion,
    LoadedDataset,
    default_registry,
)
from ingredion_ai.datalayer.schema import (
    FieldSpec,
    SchemaValidationError,
    validate_all,
    validate_record,
)

__all__ = [
    "Connector",
    "FileConnector",
    "Lineage",
    "attach_lineage",
    "compute_content_hash",
    "DatasetRegistry",
    "DatasetVersion",
    "LoadedDataset",
    "default_registry",
    "FieldSpec",
    "SchemaValidationError",
    "validate_all",
    "validate_record",
]
