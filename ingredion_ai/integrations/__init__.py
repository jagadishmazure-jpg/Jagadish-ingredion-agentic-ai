"""Enterprise integration adapters (demo doubles, offline).

Each adapter defines an abstract interface plus a synthetic implementation
for offline use and tests. Real connectors (Salesforce/Dynamics CRM, SAP
S/4HANA) plug in behind the same interface; see docs/integrations.md.
Config via environment; no real credentials anywhere in this repo.
"""

from ingredion_ai.integrations.crm import (
    CRMAdapter,
    DemoCRMAdapter,
    crm_from_env,
)
from ingredion_ai.integrations.sap import (
    SAPAdapter,
    DemoSAPAdapter,
    sap_from_env,
)

__all__ = [
    "CRMAdapter",
    "DemoCRMAdapter",
    "SAPAdapter",
    "DemoSAPAdapter",
    "crm_from_env",
    "sap_from_env",
]
