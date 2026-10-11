"""CRM adapter: abstract interface + synthetic offline double (demo).

The customer advisor agent uses the CRM adapter to personalize proposals:
account tier, open opportunities, and recent cases shape recommendations
and pricing bands. The demo double serves fixed synthetic records; a real
implementation (Salesforce, Dynamics 365) subclasses ``CRMAdapter`` and
reads credentials from the environment (see docs/integrations.md).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class CRMAdapter(ABC):
    """Abstract CRM interface used by the customer advisor agent."""

    @abstractmethod
    def get_account(self, account_id: str) -> Dict[str, Any]:
        """Return account profile (tier, region, segment)."""

    @abstractmethod
    def list_contacts(self, account_id: str) -> List[Dict[str, Any]]:
        """Return contacts for *account_id*."""

    @abstractmethod
    def list_opportunities(self, account_id: str) -> List[Dict[str, Any]]:
        """Return open opportunities for *account_id*."""

    @abstractmethod
    def list_cases(self, account_id: str) -> List[Dict[str, Any]]:
        """Return recent support cases for *account_id*."""


# -- synthetic demo data ----------------------------------------------------

_DEMO_ACCOUNTS: Dict[str, Dict[str, Any]] = {
    "ACME-001": {
        "account_id": "ACME-001",
        "name": "Acme Bakery Co. (demo)",
        "tier": "gold",
        "region": "NA",
        "segment": "bakery",
        "demo": True,
    },
    "BEVCO-002": {
        "account_id": "BEVCO-002",
        "name": "BevCo Drinks (demo)",
        "tier": "silver",
        "region": "NA",
        "segment": "beverage",
        "demo": True,
    },
}

_DEMO_OPPORTUNITIES: Dict[str, List[Dict[str, Any]]] = {
    "ACME-001": [
        {"id": "OPP-101", "title": "Clean-label cake reformulation (demo)",
         "stage": "proposal", "value_usd": 120000, "demo": True},
    ],
    "BEVCO-002": [
        {"id": "OPP-202", "title": "Reduced-sugar energy drink (demo)",
         "stage": "discovery", "value_usd": 85000, "demo": True},
    ],
}

_DEMO_CASES: Dict[str, List[Dict[str, Any]]] = {
    "ACME-001": [
        {"id": "CASE-11", "subject": "Texture question on reformulated crumb (demo)",
         "status": "open", "demo": True},
    ],
    "BEVCO-002": [],
}


class DemoCRMAdapter(CRMAdapter):
    """Synthetic offline CRM double (demo only — no real data)."""

    def get_account(self, account_id: str) -> Dict[str, Any]:
        try:
            return dict(_DEMO_ACCOUNTS[account_id])
        except KeyError:
            raise KeyError(f"unknown demo account: {account_id}") from None

    def list_contacts(self, account_id: str) -> List[Dict[str, Any]]:
        self.get_account(account_id)  # validates the id
        return [
            {"id": f"{account_id}-C1", "name": "Demo Contact (demo)",
             "role": "R&D Manager", "demo": True}
        ]

    def list_opportunities(self, account_id: str) -> List[Dict[str, Any]]:
        self.get_account(account_id)
        return [dict(o) for o in _DEMO_OPPORTUNITIES.get(account_id, [])]

    def list_cases(self, account_id: str) -> List[Dict[str, Any]]:
        self.get_account(account_id)
        return [dict(c) for c in _DEMO_CASES.get(account_id, [])]


def crm_from_env() -> CRMAdapter:
    """Select the CRM adapter from the environment (demo default).

    ``CRM_ADAPTER=demo`` (default) -> synthetic double.
    Any other value raises with guidance (wire a real connector here).
    """
    which = os.environ.get("CRM_ADAPTER", "demo").strip().lower()
    if which == "demo":
        return DemoCRMAdapter()
    raise RuntimeError(
        f"unknown CRM_ADAPTER={which!r}; 'demo' is the only offline option — "
        "see docs/integrations.md to wire a real CRM connector"
    )
