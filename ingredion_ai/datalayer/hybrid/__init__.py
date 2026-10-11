"""Hybrid data plane: bring AI to the data, wherever it lives.

Data placement, residency-aware policy enforcement, workload routing, and
movement auditing across environments (public cloud, private cloud,
on-prem, edge, sovereign). Extends the governed dataset layer
(:mod:`ingredion_ai.datalayer`) without changing it.
"""

from ingredion_ai.datalayer.hybrid.environments import (
    Environment,
    EnvironmentRegistry,
    default_environments,
)
from ingredion_ai.datalayer.hybrid.movement import MovementLog
from ingredion_ai.datalayer.hybrid.placement import (
    DataPlacement,
    PlacementRegistry,
    ResidencyClass,
)
from ingredion_ai.datalayer.hybrid.policies import HybridPolicyEngine
from ingredion_ai.datalayer.hybrid.routing import route_workload

__all__ = [
    "Environment",
    "EnvironmentRegistry",
    "default_environments",
    "DataPlacement",
    "PlacementRegistry",
    "ResidencyClass",
    "HybridPolicyEngine",
    "route_workload",
    "MovementLog",
]
