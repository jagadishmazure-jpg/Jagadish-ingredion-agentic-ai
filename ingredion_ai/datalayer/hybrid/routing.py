"""Workload routing: bring the AI to the data, not the data to the AI.

``route_workload`` picks the environment an AI workload should run in:
policy-violating environments are eliminated first (a workload can never
be routed somewhere its datasets are not allowed), survivors are scored
by data locality, and ties break toward the lowest-cost environment kind.
Every rejection carries its reason, so routing decisions are explainable.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ingredion_ai.datalayer.hybrid.environments import EnvironmentRegistry
from ingredion_ai.datalayer.hybrid.placement import PlacementRegistry
from ingredion_ai.datalayer.hybrid.policies import HybridPolicyEngine

# Cheapest-first tie-break among policy-allowed environments.
_KIND_COST_RANK = {
    "edge": 0,
    "public_cloud": 1,
    "private_cloud": 2,
    "on_prem": 3,
    "sovereign": 4,
}


def route_workload(
    dataset_ids: List[str],
    candidate_env_ids: List[str],
    envs: EnvironmentRegistry,
    placements: PlacementRegistry,
    policies: HybridPolicyEngine,
) -> Dict[str, Any]:
    """Choose where to run a workload touching *dataset_ids*.

    Returns ``{"environment_id": str | None, "rationale": [...],
    "rejected": [{"env": ..., "reason": ...}]}``. ``environment_id`` is
    None only when no candidate satisfies every dataset's policy.
    """
    rejected: List[Dict[str, str]] = []
    scored: List[Dict[str, Any]] = []

    for env_id in candidate_env_ids:
        try:
            env = envs.get(env_id)
        except KeyError:
            rejected.append({"env": env_id, "reason": "unknown environment"})
            continue
        deny_reasons = []
        for ds in dataset_ids:
            allowed, reason = policies.check_access(ds, env_id, purpose="workload")
            if not allowed:
                deny_reasons.append(reason)
        if deny_reasons:
            rejected.append({"env": env_id, "reason": "; ".join(deny_reasons)})
            continue
        locality = 0
        for ds in dataset_ids:
            try:
                placement = placements.get(ds)
            except KeyError:
                placement = None
            if placement and env_id in placement.locations:
                locality += 1
        scored.append(
            {
                "env_id": env_id,
                "locality": locality,
                "cost_rank": _KIND_COST_RANK[env.kind],
            }
        )

    if not scored:
        return {
            "environment_id": None,
            "rationale": [
                "no candidate environment satisfies the residency policy of "
                f"every requested dataset: {dataset_ids}"
            ],
            "rejected": rejected,
        }

    scored.sort(key=lambda s: (-s["locality"], s["cost_rank"], s["env_id"]))
    winner = scored[0]
    rationale = [
        f"routed to {winner['env_id']}: holds {winner['locality']}/"
        f"{len(dataset_ids)} required datasets locally "
        "(bring AI to the data)",
    ]
    if len(scored) > 1:
        rationale.append(
            "tie-break by cost: "
            + ", ".join(
                f"{s['env_id']} (locality {s['locality']})" for s in scored[1:]
            )
            + " ranked lower"
        )
    return {
        "environment_id": winner["env_id"],
        "rationale": rationale,
        "rejected": rejected,
    }
