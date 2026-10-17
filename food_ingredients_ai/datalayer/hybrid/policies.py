"""Location-aware policy engine: policies travel with the data.

A policy is attached to the dataset at placement time and evaluated at
query time against the *requesting* environment — never at registration.
That is what makes the policy travel: wherever the dataset (or a request
for it) goes, the same rules apply.

Rules:
- PUBLIC: queryable from any environment.
- CONFIDENTIAL: cannot be queried from edge environments.
- RESTRICTED: cannot be queried from outside its residency zone.
- SOVEREIGN: only from sovereign environments in the same zone.
"""

from __future__ import annotations

from typing import Tuple

from food_ingredients_ai.datalayer.hybrid.environments import EnvironmentRegistry
from food_ingredients_ai.datalayer.hybrid.placement import PlacementRegistry, ResidencyClass


class HybridPolicyEngine:
    """Evaluate dataset policies against requesting environments."""

    def __init__(
        self,
        envs: EnvironmentRegistry,
        placements: PlacementRegistry,
    ) -> None:
        self._envs = envs
        self._placements = placements

    def check_access(
        self, dataset_id: str, requesting_env_id: str, purpose: str = "query"
    ) -> Tuple[bool, str]:
        """Return ``(allowed, reason)`` for *requesting_env_id* touching *dataset_id*."""
        try:
            placement = self._placements.get(dataset_id)
        except KeyError:
            return False, f"no placement registered for {dataset_id!r}"
        try:
            env = self._envs.get(requesting_env_id)
        except KeyError:
            return False, f"unknown requesting environment: {requesting_env_id!r}"

        cls = placement.residency_class
        if cls is ResidencyClass.PUBLIC:
            return True, f"{dataset_id!r} is PUBLIC: {purpose} allowed from anywhere"
        if cls is ResidencyClass.CONFIDENTIAL:
            if env.kind == "edge":
                return (
                    False,
                    f"{dataset_id!r} is CONFIDENTIAL: {purpose} denied from edge "
                    f"environment {requesting_env_id!r}",
                )
            return True, (
                f"{dataset_id!r} is CONFIDENTIAL: {purpose} allowed from "
                f"{requesting_env_id!r} (not edge)"
            )
        zone = self._placements.residency_zone(dataset_id)
        if cls is ResidencyClass.RESTRICTED:
            if env.residency_zone != zone:
                return (
                    False,
                    f"{dataset_id!r} is RESTRICTED to zone {zone}: {purpose} denied "
                    f"from {requesting_env_id!r} (zone {env.residency_zone})",
                )
            return True, (
                f"{dataset_id!r} is RESTRICTED: {purpose} allowed from "
                f"{requesting_env_id!r} (in-zone {zone})"
            )
        # SOVEREIGN
        if env.kind != "sovereign" or env.residency_zone != zone:
            return (
                False,
                f"{dataset_id!r} is SOVEREIGN: {purpose} denied from "
                f"{requesting_env_id!r} (requires sovereign environment in zone {zone})",
            )
        return True, (
            f"{dataset_id!r} is SOVEREIGN: {purpose} allowed from sovereign "
            f"{requesting_env_id!r} (zone {zone})"
        )
