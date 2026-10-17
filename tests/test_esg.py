"""Tests for the ESG agent (all offline, deterministic)."""

import pytest

from food_ingredients_ai.agents.esg import ESGAgent, carbon, collector, intensity, report


def _agent():
    return ESGAgent()


def test_collect_all_readings():
    out = collector.collect()
    assert out["reading_count"] == 6
    assert out["demo"] is True


def test_collect_filter_by_plant():
    out = collector.collect(plant="Demo Plant Alpha (Illinois)")
    assert out["reading_count"] == 2
    assert all(r["plant"] == "Demo Plant Alpha (Illinois)" for r in out["readings"])


def test_carbon_totals():
    calc = carbon.carbon_footprint(collector.collect()["readings"])
    assert calc["total_tco2e"] == 504.0
    assert calc["total_production_tonnes"] == 3120.0
    assert calc["intensity_tco2e_per_tonne"] == 0.1615


def test_carbon_by_plant():
    calc = carbon.carbon_footprint(collector.collect()["readings"])
    alpha = calc["by_plant"]["Demo Plant Alpha (Illinois)"]
    assert alpha["emissions_tco2e"] == 167.0
    assert alpha["production_tonnes"] == 1020.0
    assert alpha["intensity_tco2e_per_tonne"] == 0.1637


def test_intensities():
    intens = intensity.intensities(collector.collect()["readings"])
    assert intens["energy_kwh_per_tonne"] == 224.68
    assert intens["water_m3_per_tonne"] == 8.494


def test_intensities_empty_safe():
    intens = intensity.intensities([])
    assert intens["energy_kwh_per_tonne"] == 0.0
    calc = carbon.carbon_footprint([])
    assert calc["intensity_tco2e_per_tonne"] == 0.0


def test_report_contains_sections():
    readings = collector.collect()["readings"]
    calc = carbon.carbon_footprint(readings)
    intens = intensity.intensities(readings)
    md = report.generate_esg_report(readings, calc, intens)
    assert "# ESG Report" in md
    assert "504.0 tCO2e" in md
    assert "Demo Plant Beta (Iowa)" in md
    assert "Traceability" in md
    assert "synthetic data only" in md


def test_agent_collect_task():
    out = _agent().execute("collect_esg", {})
    assert out["reading_count"] == 6


def test_agent_carbon_task_uses_blackboard():
    agent = _agent()
    collected = agent.execute("collect_esg", {})
    out = agent.execute("calculate_carbon", {"blackboard": {"collect_esg": collected}})
    assert out["carbon"]["total_tco2e"] == 504.0
    assert "intensities" in out["carbon"]


def test_agent_report_task():
    agent = _agent()
    collected = agent.execute("collect_esg", {})
    carbon_out = agent.execute("calculate_carbon", {"blackboard": {"collect_esg": collected}})
    out = agent.execute(
        "esg_report",
        {"blackboard": {"collect_esg": collected, "calculate_carbon": carbon_out}},
    )
    assert "# ESG Report" in out["report_markdown"]


def test_agent_report_task_standalone():
    out = _agent().execute("esg_report", {})
    assert "# ESG Report" in out["report_markdown"]


def test_agent_unknown_task_raises():
    with pytest.raises(ValueError):
        _agent().execute("nope", {})
