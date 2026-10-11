"""Data placement: which environments physically hold each dataset.

A :class:`DataPlacement` tags a dataset with the environments it lives in
and a residency class. SOVEREIGN datasets must live only in sovereign
environments of a single residency zone; RESTRICTED datasets must stay in
a single zone. Placement is validated at registration — a misplaced
dataset never enters the plane.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

from ingredion_ai.datalayer.hybrid.environments import EnvironmentRegistry


class ResidencyClass(str, Enum):
    PUBLIC = "PUBLIC"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"
    SOVEREIGN = "SOVEREIGN"


@dataclass
class DataPlacement:
    """Where a dataset physically lives and how sensitive it is."""

    dataset_id: str
    locations: List[str] = field(default_factory=list)
    residency_class: ResidencyClass = ResidencyClass.PUBLIC


class PlacementError(ValueError):
    """Raised when a placement violates residency rules."""


class PlacementRegistry:
    """Placements per dataset, validated against the environment registry."""

    def __init__(self, envs: EnvironmentRegistry) -> None:
        self._envs = envs
        self._placements: Dict[str, DataPlacement] = {}

    def register_placement(
        self,
        dataset_id: str,
        locations: List[str],
        residency_class: ResidencyClass = ResidencyClass.PUBLIC,
    ) -> DataPlacement:
        """Tag *dataset_id* with locations; validate residency rules."""
        if not locations:
            raise PlacementError(f"{dataset_id!r}: placement needs at least one location")
        envs = [self._envs.get(eid) for eid in locations]  # KeyError on unknown
        zones = {e.residency_zone for e in envs}
        if residency_class is ResidencyClass.SOVEREIGN:
            if any(e.kind != "sovereign" for e in envs):
                raise PlacementError(
                    f"{dataset_id!r}: SOVEREIGN data must live only in "
                    "sovereign environments"
                )
            if len(zones) != 1:
                raise PlacementError(
                    f"{dataset_id!r}: SOVEREIGN data must stay in a single zone"
                )
        if residency_class is ResidencyClass.RESTRICTED and len(zones) != 1:
            raise PlacementError(
                f"{dataset_id!r}: RESTRICTED data must stay in a single zone"
            )
        placement = DataPlacement(
            dataset_id=dataset_id,
            locations=list(locations),
            residency_class=residency_class,
        )
        self._placements[dataset_id] = placement
        return placement

    def get(self, dataset_id: str) -> DataPlacement:
        try:
            return self._placements[dataset_id]
        except KeyError:
            raise KeyError(f"no placement registered for {dataset_id!r}") from None

    def residency_zone(self, dataset_id: str) -> str:
        """Primary residency zone of a dataset (single zone for RESTRICTED/SOVEREIGN)."""
        placement = self.get(dataset_id)
        zones = [self._envs.get(eid).residency_zone for eid in placement.locations]
        return max(set(zones), key=zones.count)

    def add_location(self, dataset_id: str, env_id: str) -> DataPlacement:
        """Replicate a dataset to one more environment (re-validated)."""
        placement = self.get(dataset_id)
        if env_id in placement.locations:
            return placement
        return self.register_placement(
            dataset_id,
            placement.locations + [env_id],
            placement.residency_class,
        )

    def remove_location(self, dataset_id: str, env_id: str) -> DataPlacement:
        """Remove one replica (refuses to strand the dataset with none)."""
        placement = self.get(dataset_id)
        remaining = [e for e in placement.locations if e != env_id]
        if not remaining:
            raise PlacementError(
                f"{dataset_id!r}: cannot remove last location {env_id!r}"
            )
        return self.register_placement(
            dataset_id, remaining, placement.residency_class
        )
