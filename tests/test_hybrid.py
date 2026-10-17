"""Tests for the hybrid data plane: placement, traveling policies,
workload routing, and the movement ledger."""

import pytest

from food_ingredients_ai.datalayer.hybrid import (
    DataPlacement,
    Environment,
    HybridPolicyEngine,
    MovementLog,
    PlacementRegistry,
    ResidencyClass,
    default_environments,
    route_workload,
)
from food_ingredients_ai.datalayer.hybrid.placement import PlacementError


@pytest.fixture()
def plane():
    envs = default_environments()
    placements = PlacementRegistry(envs)
    policies = HybridPolicyEngine(envs, placements)
    log = MovementLog(envs, placements, policies)
    return envs, placements, policies, log


def _seed(placements: PlacementRegistry) -> None:
    placements.register_placement(
        "ingredients", ["azure-weu", "onprem-fra"], ResidencyClass.PUBLIC
    )
    placements.register_placement(
        "formulas", ["onprem-fra"], ResidencyClass.CONFIDENTIAL
    )
    placements.register_placement(
        "customers_eu", ["onprem-fra"], ResidencyClass.RESTRICTED
    )
    placements.register_placement(
        "payroll_eu", ["eu-sovereign"], ResidencyClass.SOVEREIGN
    )


# -- environments ---------------------------------------------------------


def test_default_environments_have_six():
    assert len(default_environments().ids()) == 6


def test_environment_registry_lookup_and_unknown():
    envs = default_environments()
    env = envs.get("azure-weu")
    assert env.kind == "public_cloud" and env.residency_zone == "EU"
    with pytest.raises(KeyError):
        envs.get("nope")


def test_environment_rejects_bad_kind_and_zone():
    with pytest.raises(ValueError):
        Environment("x", "moon", "Nowhere", "EU")
    with pytest.raises(ValueError):
        Environment("x", "edge", "Nowhere", "MARS")


# -- placement ------------------------------------------------------------


def test_register_valid_placements(plane):
    _, placements, _, _ = plane
    p = placements.register_placement(
        "ingredients", ["azure-weu"], ResidencyClass.PUBLIC
    )
    assert isinstance(p, DataPlacement)
    assert p.locations == ["azure-weu"]
    assert placements.get("ingredients").residency_class is ResidencyClass.PUBLIC


def test_sovereign_must_live_in_sovereign_env(plane):
    _, placements, _, _ = plane
    with pytest.raises(PlacementError):
        placements.register_placement(
            "payroll", ["azure-weu"], ResidencyClass.SOVEREIGN
        )


def test_sovereign_must_stay_single_zone(plane):
    envs, placements, _, _ = plane
    envs.register(Environment("us-sovereign", "sovereign", "US Sovereign", "US"))
    with pytest.raises(PlacementError):
        placements.register_placement(
            "payroll", ["eu-sovereign", "us-sovereign"], ResidencyClass.SOVEREIGN
        )


def test_restricted_must_stay_single_zone(plane):
    _, placements, _, _ = plane
    with pytest.raises(PlacementError):
        placements.register_placement(
            "customers", ["onprem-fra", "azure-use"], ResidencyClass.RESTRICTED
        )


def test_placement_needs_location_and_known_env(plane):
    _, placements, _, _ = plane
    with pytest.raises(PlacementError):
        placements.register_placement("d", [], ResidencyClass.PUBLIC)
    with pytest.raises(KeyError):
        placements.register_placement("d", ["moon-base"], ResidencyClass.PUBLIC)


def test_add_and_remove_location(plane):
    _, placements, _, _ = plane
    placements.register_placement("d", ["onprem-fra"], ResidencyClass.PUBLIC)
    placements.add_location("d", "azure-weu")
    assert set(placements.get("d").locations) == {"onprem-fra", "azure-weu"}
    placements.remove_location("d", "azure-weu")
    assert placements.get("d").locations == ["onprem-fra"]
    with pytest.raises(PlacementError):
        placements.remove_location("d", "onprem-fra")  # would strand it


# -- policies -------------------------------------------------------------


def test_public_allowed_everywhere(plane):
    _, placements, policies, _ = plane
    _seed(placements)
    allowed, reason = policies.check_access("ingredients", "azure-use")
    assert allowed and "PUBLIC" in reason


def test_confidential_denied_from_edge_but_allowed_in_cloud(plane):
    _, placements, policies, _ = plane
    _seed(placements)
    allowed, reason = policies.check_access("formulas", "edge-plant-07")
    assert not allowed and "edge" in reason
    allowed, reason = policies.check_access("formulas", "azure-weu")
    assert allowed


def test_restricted_denied_cross_zone(plane):
    _, placements, policies, _ = plane
    _seed(placements)
    allowed, reason = policies.check_access("customers_eu", "azure-use")
    assert not allowed and "US" in reason
    allowed, reason = policies.check_access("customers_eu", "azure-weu")
    assert allowed and "in-zone EU" in reason


def test_sovereign_only_from_sovereign_in_zone(plane):
    _, placements, policies, _ = plane
    _seed(placements)
    allowed, reason = policies.check_access("payroll_eu", "azure-weu")
    assert not allowed and "sovereign" in reason.lower()
    allowed, _ = policies.check_access("payroll_eu", "eu-sovereign")
    assert allowed


def test_policy_unknown_dataset_and_env_denied(plane):
    _, placements, policies, _ = plane
    _seed(placements)
    allowed, _ = policies.check_access("ghost", "azure-weu")
    assert not allowed
    allowed, _ = policies.check_access("ingredients", "moon-base")
    assert not allowed


# -- routing --------------------------------------------------------------


def test_routing_picks_data_local_env(plane):
    envs, placements, policies, _ = plane
    _seed(placements)
    result = route_workload(
        ["customers_eu"], ["azure-use", "azure-weu", "onprem-fra"],
        envs, placements, policies,
    )
    assert result["environment_id"] == "onprem-fra"
    assert any("bring AI to the data" in r for r in result["rationale"])
    rejected_envs = {r["env"] for r in result["rejected"]}
    assert "azure-use" in rejected_envs  # RESTRICTED cross-zone


def test_routing_never_picks_violating_env(plane):
    envs, placements, policies, _ = plane
    _seed(placements)
    result = route_workload(
        ["payroll_eu"], ["azure-weu", "azure-use", "onprem-fra"],
        envs, placements, policies,
    )
    assert result["environment_id"] is None
    assert len(result["rejected"]) == 3
    assert any("sovereign" in r["reason"].lower() for r in result["rejected"])


def test_routing_single_candidate_trivial(plane):
    envs, placements, policies, _ = plane
    _seed(placements)
    result = route_workload(
        ["ingredients"], ["azure-use"], envs, placements, policies
    )
    assert result["environment_id"] == "azure-use"
    assert result["rejected"] == []


def test_routing_prefers_locality_over_cheap_kind(plane):
    envs, placements, policies, _ = plane
    placements.register_placement(
        "ingredients", ["onprem-fra"], ResidencyClass.PUBLIC
    )
    result = route_workload(
        ["ingredients"], ["edge-plant-07", "onprem-fra"],
        envs, placements, policies,
    )
    # edge is cheaper but holds nothing; onprem-fra holds the data
    assert result["environment_id"] == "onprem-fra"


# -- movement -------------------------------------------------------------


def test_approved_move_is_logged_and_replicates(plane):
    _, placements, _, log = plane
    _seed(placements)
    entry = log.request_move(
        "ingredients", "azure-weu", "azure-use", actor="etl-nightly"
    )
    assert entry["approved"] is True
    assert "azure-use" in placements.get("ingredients").locations
    assert log.verify_chain() is True


def test_move_mode_removes_source(plane):
    _, placements, _, log = plane
    placements.register_placement(
        "ingredients", ["azure-weu", "onprem-fra"], ResidencyClass.PUBLIC
    )
    entry = log.request_move(
        "ingredients", "azure-weu", "azure-use", mode="move"
    )
    assert entry["approved"] is True
    assert "azure-weu" not in placements.get("ingredients").locations


def test_residency_violating_move_denied_and_logged(plane):
    _, placements, _, log = plane
    _seed(placements)
    entry = log.request_move(
        "customers_eu", "onprem-fra", "azure-use", actor="etl-nightly"
    )
    assert entry["approved"] is False
    assert "RESTRICTED" in entry["reason"]
    assert placements.get("customers_eu").locations == ["onprem-fra"]
    assert len(log.denied()) == 1


def test_move_from_env_not_holding_dataset_denied(plane):
    _, placements, _, log = plane
    _seed(placements)
    entry = log.request_move("formulas", "azure-use", "azure-weu")
    assert entry["approved"] is False
    assert "not present" in entry["reason"]


def test_move_unknown_dataset_denied(plane):
    _, _, _, log = plane
    entry = log.request_move("ghost", "azure-weu", "azure-use")
    assert entry["approved"] is False


def test_movement_chain_tamper_detected(plane):
    _, placements, _, log = plane
    _seed(placements)
    log.request_move("ingredients", "azure-weu", "azure-use")
    assert log.verify_chain() is True
    log._entries[0]["reason"] = "tampered"
    assert log.verify_chain() is False
