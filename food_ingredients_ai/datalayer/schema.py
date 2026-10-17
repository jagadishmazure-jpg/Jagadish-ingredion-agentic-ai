"""Schema validation for datasets: fail-fast with clear errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


class SchemaValidationError(ValueError):
    """A dataset record failed schema validation (fail-fast on load)."""


@dataclass(frozen=True)
class FieldSpec:
    """One field's contract: expected type(s) and whether it is required."""

    name: str
    types: Tuple[type, ...]
    required: bool = True


def _type_names(types: Tuple[type, ...]) -> str:
    return "/".join(t.__name__ for t in types)


def validate_record(
    record: Dict[str, Any],
    schema: List[FieldSpec],
    dataset_name: str,
    index: int = 0,
) -> None:
    """Validate one record; raise :class:`SchemaValidationError` on failure."""
    if not isinstance(record, dict):
        raise SchemaValidationError(
            f"{dataset_name}[{index}]: expected a mapping, got "
            f"{type(record).__name__}"
        )
    for spec in schema:
        if spec.name not in record:
            if spec.required:
                raise SchemaValidationError(
                    f"{dataset_name}[{index}]: missing required field "
                    f"'{spec.name}'"
                )
            continue
        value = record[spec.name]
        if value is None and not spec.required:
            continue
        if not isinstance(value, spec.types):
            raise SchemaValidationError(
                f"{dataset_name}[{index}]: field '{spec.name}' expected "
                f"{_type_names(spec.types)}, got {type(value).__name__}"
            )


def validate_all(
    records: List[Dict[str, Any]],
    schema: List[FieldSpec],
    dataset_name: str,
) -> List[Dict[str, Any]]:
    """Validate every record (fail-fast); return *records* unchanged."""
    for i, record in enumerate(records):
        validate_record(record, schema, dataset_name, i)
    return records
