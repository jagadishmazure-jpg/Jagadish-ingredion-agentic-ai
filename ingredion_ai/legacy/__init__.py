"""Intelligence layer over legacy systems: wrap, don't replace (demo).

Submodules:

- :mod:`bridge` — uniform envelope for calling traditional systems.
- :mod:`catalog` — versioned capability catalog of legacy operations as tools.
- :mod:`cdc` — change-data-capture poller + webhook receiver → agent triggers.
- :mod:`autonomy` — L0→L3 autonomy ladder with promotion criteria.

All demo data is synthetic and fictional. Stdlib only.
"""

from ingredion_ai.legacy.autonomy import (
    L0_MANUAL,
    L1_ASSIST,
    L2_AUGMENT,
    L3_AUTONOMOUS,
    AutonomyController,
    AutonomyPolicy,
    PromotionCriteria,
    WorkflowHistory,
    promotion_eligible,
)
from ingredion_ai.legacy.bridge import (
    BridgeHealth,
    CRMBridge,
    LegacyBridge,
    LegacyError,
    SAPBridge,
    SyntheticLegacyBridge,
)
from ingredion_ai.legacy.catalog import CapabilityCatalog, CatalogError, ToolSpec
from ingredion_ai.legacy.cdc import (
    ChangeFeed,
    EventSource,
    LegacyEvent,
    SimulatedEventSource,
    WebhookError,
    WebhookReceiver,
)

__all__ = [
    "L0_MANUAL",
    "L1_ASSIST",
    "L2_AUGMENT",
    "L3_AUTONOMOUS",
    "AutonomyController",
    "AutonomyPolicy",
    "PromotionCriteria",
    "WorkflowHistory",
    "promotion_eligible",
    "BridgeHealth",
    "CRMBridge",
    "LegacyBridge",
    "LegacyError",
    "SAPBridge",
    "SyntheticLegacyBridge",
    "CapabilityCatalog",
    "CatalogError",
    "ToolSpec",
    "ChangeFeed",
    "EventSource",
    "LegacyEvent",
    "SimulatedEventSource",
    "WebhookError",
    "WebhookReceiver",
]
