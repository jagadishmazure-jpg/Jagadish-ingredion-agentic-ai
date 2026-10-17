"""Loaders for the synthetic demo datasets."""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

_DATA_DIR = Path(__file__).resolve().parent


def _read_json(name: str) -> Any:
    with open(_DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def load_ingredients() -> List[Dict[str, Any]]:
    """All synthetic ingredients in the demo database."""
    return _read_json("ingredients.json")


@lru_cache(maxsize=1)
def _ingredient_index() -> Dict[str, Dict[str, Any]]:
    return {ing["id"]: ing for ing in load_ingredients()}


def get_ingredient(ingredient_id: str) -> Dict[str, Any]:
    """Look up one synthetic ingredient by id (KeyError if unknown)."""
    try:
        return _ingredient_index()[ingredient_id]
    except KeyError:
        raise KeyError(f"unknown demo ingredient: {ingredient_id}") from None


@lru_cache(maxsize=1)
def load_formulas() -> List[Dict[str, Any]]:
    """All synthetic sample formulas."""
    return _read_json("formulas.json")


def get_formula(formula_id: str) -> Dict[str, Any]:
    """Look up one synthetic formula by id (KeyError if unknown)."""
    for formula in load_formulas():
        if formula["id"] == formula_id:
            return formula
    raise KeyError(f"unknown demo formula: {formula_id}")


@lru_cache(maxsize=1)
def load_demand() -> List[Dict[str, Any]]:
    """Synthetic weekly demand series per SKU."""
    rows: List[Dict[str, Any]] = []
    with open(_DATA_DIR / "demand.csv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append(
                {
                    "sku": row["sku"],
                    "week": int(row["week"]),
                    "demand_tonnes": float(row["demand_tonnes"]),
                    "demo": row["demo"] == "true",
                }
            )
    return rows


@lru_cache(maxsize=1)
def load_esg_readings() -> List[Dict[str, Any]]:
    """Synthetic ESG readings per demo plant per quarter."""
    return _read_json("esg_readings.json")
