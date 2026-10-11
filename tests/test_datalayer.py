"""Tests for the versioned data layer: registry, schema, lineage."""

import pytest

from ingredion_ai.datalayer import (
    DatasetRegistry,
    DatasetVersion,
    FieldSpec,
    FileConnector,
    SchemaValidationError,
    attach_lineage,
    compute_content_hash,
    default_registry,
    validate_all,
)


@pytest.fixture()
def registry():
    return default_registry()


def test_default_datasets_load_and_validate(registry):
    loaded = registry.get("ingredients")
    assert loaded.version == "v3"
    assert loaded.lineage.record_count == len(loaded.records) > 0
    assert loaded.lineage.dataset == "ingredients"
    assert len(loaded.lineage.content_sha256) == 64


def test_all_default_datasets_validate(registry):
    for name in ["ingredients", "formulas", "demand", "esg_readings", "glossary"]:
        loaded = registry.get(name)
        assert loaded.records, name


def test_demand_csv_coerced_to_typed(registry):
    loaded = registry.get("demand", version="v1")
    row = loaded.records[0]
    assert isinstance(row["week"], int)
    assert isinstance(row["demand_tonnes"], float)
    assert isinstance(row["demo"], bool)


def test_glossary_parsed_from_markdown(registry):
    loaded = registry.get("glossary")
    terms = {r["term"] for r in loaded.records}
    assert "clean label" in terms


def test_lineage_hash_is_deterministic(registry):
    a = registry.get("ingredients").lineage.content_sha256
    b = registry.get("ingredients").lineage.content_sha256
    assert a == b


def test_compute_content_hash_changes_with_data():
    h1 = compute_content_hash([{"a": 1}])
    h2 = compute_content_hash([{"a": 2}])
    assert h1 != h2 and len(h1) == 64


def test_unknown_dataset_raises(registry):
    with pytest.raises(KeyError):
        registry.get("nope")


def test_unknown_version_raises(registry):
    with pytest.raises(KeyError):
        registry.get("ingredients", version="v99")


def test_schema_missing_required_field_fails():
    with pytest.raises(SchemaValidationError, match="missing required field 'id'"):
        validate_all([{"name": "x"}], [FieldSpec("id", (str,))], "demo_ds")


def test_schema_wrong_type_fails():
    with pytest.raises(SchemaValidationError, match="expected str"):
        validate_all(
            [{"id": 123}], [FieldSpec("id", (str,))], "demo_ds"
        )


def test_schema_non_mapping_fails():
    with pytest.raises(SchemaValidationError, match="expected a mapping"):
        validate_all(["nope"], [FieldSpec("id", (str,))], "demo_ds")


def test_version_pinning_isolation():
    reg = DatasetRegistry()
    reg.register(DatasetVersion(name="d", version="v1",
                                connector=_ConstConnector([{"id": "a"}]),
                                schema=[FieldSpec("id", (str,))]))
    reg.register(DatasetVersion(name="d", version="v2",
                                connector=_ConstConnector([{"id": "b"}]),
                                schema=[FieldSpec("id", (str,))]))
    assert reg.get("d", version="v1").records == [{"id": "a"}]
    assert reg.get("d").records == [{"id": "b"}]  # latest
    assert reg.versions("d") == ["v1", "v2"]


def test_attach_lineage_appends_to_run_output(registry):
    loaded = registry.get("formulas")
    out: dict = {}
    attach_lineage(out, loaded.lineage)
    assert out["data_lineage"][0]["dataset"] == "formulas"
    assert out["data_lineage"][0]["version"] == "v2"


def test_file_connector_missing_file():
    with pytest.raises(FileNotFoundError):
        FileConnector("/tmp/does-not-exist-xyz.json").read()


class _ConstConnector:
    """Minimal in-memory connector for registry tests."""

    def __init__(self, records):
        self._records = records

    def read(self):
        return list(self._records)

    def describe(self):
        return {"connector": "ConstConnector"}
