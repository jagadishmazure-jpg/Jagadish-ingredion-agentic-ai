"""Environments: where data lives and where AI workloads run.

The hybrid data plane treats location as a first-class property of every
dataset. An environment is a concrete place with a kind
(public_cloud | private_cloud | on_prem | edge | sovereign), a region, and
a residency zone (EU | US | APAC) that residency rules reason about.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Environment:
    """One place where data can live or an AI workload can run."""

    id: str
    kind: str  # public_cloud | private_cloud | on_prem | edge | sovereign
    region: str
    residency_zone: str  # EU | US | APAC

    def __post_init__(self) -> None:
        valid_kinds = {"public_cloud", "private_cloud", "on_prem", "edge", "sovereign"}
        if self.kind not in valid_kinds:
            raise ValueError(f"unknown environment kind: {self.kind!r}")
        if self.residency_zone not in {"EU", "US", "APAC"}:
            raise ValueError(f"unknown residency zone: {self.residency_zone!r}")


class EnvironmentRegistry:
    """Named environments; look up by id (KeyError on unknown)."""

    def __init__(self) -> None:
        self._envs: Dict[str, Environment] = {}

    def register(self, env: Environment) -> None:
        self._envs[env.id] = env

    def get(self, env_id: str) -> Environment:
        try:
            return self._envs[env_id]
        except KeyError:
            raise KeyError(f"unknown environment: {env_id!r}") from None

    def ids(self) -> List[str]:
        return sorted(self._envs)


def default_environments() -> EnvironmentRegistry:
    """Six realistic demo environments spanning the hybrid estate."""
    reg = EnvironmentRegistry()
    reg.register(Environment("azure-weu", "public_cloud", "West Europe", "EU"))
    reg.register(Environment("onprem-fra", "on_prem", "Frankfurt", "EU"))
    reg.register(Environment("eu-sovereign", "sovereign", "EU Sovereign Cloud", "EU"))
    reg.register(Environment("azure-use", "public_cloud", "East US", "US"))
    reg.register(Environment("edge-plant-07", "edge", "Plant 07 gateway", "EU"))
    reg.register(Environment("privatecloud-fra", "private_cloud", "Frankfurt", "EU"))
    return reg
