"""Tests for enterprise integration adapters (CRM/SAP demo doubles)."""

import pytest

from ingredion_ai.agents import CustomerAdvisorAgent, SupplyChainAgent
from ingredion_ai.integrations import (
    DemoCRMAdapter,
    DemoSAPAdapter,
    crm_from_env,
    sap_from_env,
)


# -- CRM -----------------------------------------------------------------------


def test_demo_crm_get_account():
    account = DemoCRMAdapter().get_account("ACME-001")
    assert account["tier"] == "gold"
    assert account["demo"] is True


def test_demo_crm_unknown_account_raises():
    with pytest.raises(KeyError):
        DemoCRMAdapter().get_account("NOPE")


def test_demo_crm_opportunities_and_cases():
    crm = DemoCRMAdapter()
    opps = crm.list_opportunities("ACME-001")
    assert len(opps) == 1 and opps[0]["demo"] is True
    assert isinstance(crm.list_cases("BEVCO-002"), list)


def test_demo_crm_contacts():
    contacts = DemoCRMAdapter().list_contacts("ACME-001")
    assert contacts and contacts[0]["demo"] is True


def test_crm_from_env_default_is_demo(monkeypatch):
    monkeypatch.delenv("CRM_ADAPTER", raising=False)
    assert isinstance(crm_from_env(), DemoCRMAdapter)


def test_crm_from_env_unknown_raises(monkeypatch):
    monkeypatch.setenv("CRM_ADAPTER", "salesforce")
    with pytest.raises(RuntimeError):
        crm_from_env()


# -- SAP -----------------------------------------------------------------------


def test_demo_sap_get_material():
    mat = DemoSAPAdapter().get_material("PF-200")
    assert mat["base_uom"] == "TON"
    assert mat["demo"] is True


def test_demo_sap_unknown_material_raises():
    with pytest.raises(KeyError):
        DemoSAPAdapter().get_material("NOPE")


def test_demo_sap_inventory_shape():
    inv = DemoSAPAdapter().get_inventory("PLANT-NA-01")
    assert inv["PF-200"]["on_hand_tonnes"] == 12.5


def test_demo_sap_unknown_plant_raises():
    with pytest.raises(KeyError):
        DemoSAPAdapter().get_inventory("PLANT-XX")


def test_demo_sap_purchase_orders_and_plants():
    sap = DemoSAPAdapter()
    pos = sap.list_purchase_orders("PLANT-NA-01")
    assert pos and pos[0]["demo"] is True
    plants = sap.list_plants()
    assert {p["plant_id"] for p in plants} == {"PLANT-NA-01", "PLANT-NA-02"}


def test_sap_from_env_default_is_demo(monkeypatch):
    monkeypatch.delenv("SAP_ADAPTER", raising=False)
    assert isinstance(sap_from_env(), DemoSAPAdapter)


def test_sap_from_env_unknown_raises(monkeypatch):
    monkeypatch.setenv("SAP_ADAPTER", "s4hana")
    with pytest.raises(RuntimeError):
        sap_from_env()


# -- agent wiring ----------------------------------------------------------------


def _formula_payload():
    from ingredion_ai.data.loader import get_formula

    return {"formula": get_formula("sweet_bakery_cake"), "valid_claims": []}


def test_customer_advisor_pricing_with_crm_account():
    agent = CustomerAdvisorAgent()
    out = agent.execute(
        "estimate_pricing", {**_formula_payload(), "account_id": "ACME-001"}
    )
    assert "pricing" in out
    ctx = out["account_context"]
    assert ctx["account"]["tier"] == "gold"
    assert "tier_note" in ctx
    assert isinstance(ctx["open_opportunities"], list)


def test_customer_advisor_pricing_without_account_unchanged():
    agent = CustomerAdvisorAgent()
    out = agent.execute("estimate_pricing", _formula_payload())
    assert "pricing" in out
    assert "account_context" not in out


def test_customer_advisor_pricing_unknown_account_raises():
    agent = CustomerAdvisorAgent()
    with pytest.raises(KeyError):
        agent.execute(
            "estimate_pricing", {**_formula_payload(), "account_id": "NOPE"}
        )


def test_supply_chain_optimize_inventory_via_sap():
    agent = SupplyChainAgent()
    fc = agent.execute("forecast_demand", {"skus": ["PF-200"], "periods": 4})
    out = agent.execute(
        "optimize_inventory",
        {
            "plant_id": "PLANT-NA-01",
            "blackboard": {"forecast_demand": fc},
        },
    )
    assert out["inventory_source"] == "sap:PLANT-NA-01"
    assert isinstance(out["purchases"], list)


def test_supply_chain_optimize_inventory_payload_unchanged():
    agent = SupplyChainAgent()
    fc = agent.execute("forecast_demand", {"skus": ["PF-200"], "periods": 4})
    out = agent.execute(
        "optimize_inventory",
        {
            "inventory": {"PF-200": {"on_hand_tonnes": 1.0}},
            "blackboard": {"forecast_demand": fc},
        },
    )
    assert out["inventory_source"] == "payload"
    assert len(out["purchases"]) == 1
