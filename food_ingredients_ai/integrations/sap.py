"""SAP adapter: abstract interface + synthetic offline double (demo).

The supply chain agent uses the SAP adapter for planning data: material
masters, plant inventory levels, and open purchase orders. The demo double
serves fixed synthetic records; a real implementation (SAP S/4HANA OData /
RFC) subclasses ``SAPAdapter`` and reads credentials from the environment
(see docs/integrations.md).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class SAPAdapter(ABC):
    """Abstract SAP interface used by the supply chain agent."""

    @abstractmethod
    def get_material(self, material_id: str) -> Dict[str, Any]:
        """Return the material master record for *material_id*."""

    @abstractmethod
    def get_inventory(self, plant_id: str) -> Dict[str, Dict[str, float]]:
        """Return ``{sku: {"on_hand_tonnes": x}}`` for *plant_id*."""

    @abstractmethod
    def list_purchase_orders(self, plant_id: str) -> List[Dict[str, Any]]:
        """Return open purchase orders for *plant_id*."""

    @abstractmethod
    def list_plants(self) -> List[Dict[str, Any]]:
        """Return the demo plant master list."""


# -- synthetic demo data ----------------------------------------------------

_DEMO_MATERIALS: Dict[str, Dict[str, Any]] = {
    "PF-200": {"material_id": "PF-200", "description": "PureField Starch PF-200 (demo)",
               "base_uom": "TON", "shelf_life_days": 365, "demo": True},
    "FS-40": {"material_id": "FS-40", "description": "FruitSweet Blend FS-40 (demo)",
              "base_uom": "TON", "shelf_life_days": 270, "demo": True},
    "VP-80": {"material_id": "VP-80", "description": "VerdantPea Protein VP-80 (demo)",
              "base_uom": "TON", "shelf_life_days": 365, "demo": True},
}

_DEMO_INVENTORY: Dict[str, Dict[str, Dict[str, float]]] = {
    "PLANT-NA-01": {
        "PF-200": {"on_hand_tonnes": 12.5},
        "FS-40": {"on_hand_tonnes": 4.0},
        "VP-80": {"on_hand_tonnes": 0.8},
    },
    "PLANT-NA-02": {
        "PF-200": {"on_hand_tonnes": 30.0},
        "FS-40": {"on_hand_tonnes": 9.5},
        "VP-80": {"on_hand_tonnes": 6.0},
    },
}

_DEMO_POS: Dict[str, List[Dict[str, Any]]] = {
    "PLANT-NA-01": [
        {"po_id": "PO-9001", "sku": "VP-80", "qty_tonnes": 5.0,
         "status": "open", "demo": True},
    ],
    "PLANT-NA-02": [],
}


class DemoSAPAdapter(SAPAdapter):
    """Synthetic offline SAP double (demo only — no real data)."""

    def get_material(self, material_id: str) -> Dict[str, Any]:
        try:
            return dict(_DEMO_MATERIALS[material_id])
        except KeyError:
            raise KeyError(f"unknown demo material: {material_id}") from None

    def get_inventory(self, plant_id: str) -> Dict[str, Dict[str, float]]:
        try:
            return {sku: dict(v) for sku, v in _DEMO_INVENTORY[plant_id].items()}
        except KeyError:
            raise KeyError(f"unknown demo plant: {plant_id}") from None

    def list_purchase_orders(self, plant_id: str) -> List[Dict[str, Any]]:
        if plant_id not in _DEMO_INVENTORY:
            raise KeyError(f"unknown demo plant: {plant_id}")
        return [dict(po) for po in _DEMO_POS.get(plant_id, [])]

    def list_plants(self) -> List[Dict[str, Any]]:
        return [
            {"plant_id": pid, "region": "NA", "demo": True}
            for pid in sorted(_DEMO_INVENTORY)
        ]


def sap_from_env() -> SAPAdapter:
    """Select the SAP adapter from the environment (demo default).

    ``SAP_ADAPTER=demo`` (default) -> synthetic double.
    Any other value raises with guidance (wire a real connector here).
    """
    which = os.environ.get("SAP_ADAPTER", "demo").strip().lower()
    if which == "demo":
        return DemoSAPAdapter()
    raise RuntimeError(
        f"unknown SAP_ADAPTER={which!r}; 'demo' is the only offline option — "
        "see docs/integrations.md to wire a real SAP connector"
    )
