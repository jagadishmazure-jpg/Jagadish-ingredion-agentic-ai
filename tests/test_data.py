"""Tests for the synthetic demo datasets."""

import pytest

from ingredion_ai.data import loader

REQUIRED_FIELDS = {
    "id",
    "name",
    "category",
    "function",
    "clean_label",
    "natural",
    "usage_min",
    "usage_max",
    "cost_index",
    "texture_impact",
    "regions",
    "nutrition",
    "note",
}


def test_ingredient_db_size():
    assert len(loader.load_ingredients()) >= 40


def test_ingredient_fields_present():
    for ing in loader.load_ingredients():
        assert REQUIRED_FIELDS <= set(ing), f"missing fields in {ing['id']}"


def test_ingredients_labeled_demo():
    for ing in loader.load_ingredients():
        assert "demo" in ing["note"].lower() or "synthetic" in ing["note"].lower(), ing["id"]


def test_ingredient_ids_unique():
    ids = [i["id"] for i in loader.load_ingredients()]
    assert len(ids) == len(set(ids))


def test_get_ingredient_unknown_raises():
    with pytest.raises(KeyError):
        loader.get_ingredient("NOPE")


def test_formulas_valid_and_sum_to_100():
    formulas = loader.load_formulas()
    assert len(formulas) == 3
    for formula in formulas:
        total = sum(i["pct"] for i in formula["ingredients"])
        assert abs(total - 100.0) < 0.01, formula["id"]
        for item in formula["ingredients"]:
            loader.get_ingredient(item["id"])  # every id must exist


def test_get_formula_unknown_raises():
    with pytest.raises(KeyError):
        loader.get_formula("NOPE")


def test_demand_series_shape():
    rows = loader.load_demand()
    assert len(rows) == 36
    skus = {r["sku"] for r in rows}
    assert skus == {"PF-200", "HB-10", "VP-80"}
    assert all(r["demo"] for r in rows)


def test_esg_readings_shape():
    readings = loader.load_esg_readings()
    assert len(readings) == 6
    assert {r["plant"] for r in readings} == {
        "Demo Plant Alpha (Illinois)",
        "Demo Plant Beta (Iowa)",
        "Demo Plant Gamma (Nebraska)",
    }
