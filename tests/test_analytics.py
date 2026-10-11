"""Tests for the analytics package: aggregates, benchmarking, trends, suggestions."""

import asyncio

import pytest

from ingredion_ai.analytics import (
    AggregateStore,
    PeerBenchmark,
    SYNTHETIC_LABEL,
    delta_vs_previous,
    extract_run_summary,
    flag_anomalies,
    moving_average,
)
from ingredion_ai.analytics.aggregates import RunSummary
from ingredion_ai.framework.runner import build_demo_context, run_reformulation


@pytest.fixture()
def blackboard():
    ctx = build_demo_context("sweet_bakery_cake", ["no artificial ingredients"], "NA")
    return asyncio.run(run_reformulation(ctx, live=False))


def test_extract_run_summary_from_real_blackboard(blackboard):
    s = extract_run_summary(blackboard, scenario="s1", formula_id="sweet_bakery_cake", region="NA")
    assert s.substituted_count > 0
    assert s.cost_per_kg_usd is not None and s.cost_per_kg_usd > 0
    assert s.texture_match_pct is not None
    assert s.shelf_life_days is not None
    assert s.claims_total >= 1
    assert s.claim_coverage_pct is not None
    assert s.cycle_weeks is not None  # cycle-time estimator wired in


def test_extract_run_summary_defensive_on_empty():
    s = extract_run_summary({}, scenario="x")
    assert s.substituted_count == 0
    assert s.cost_per_kg_usd is None
    assert s.claim_coverage_pct is None


def test_aggregate_store_math():
    store = AggregateStore()
    store.record(RunSummary(scenario="a", formula_id="f", region="NA", cost_per_kg_usd=10.0,
                            texture_match_pct=90.0, shelf_life_days=8.0,
                            claims_valid=1, claims_total=1, claim_coverage_pct=100.0,
                            substituted_count=2))
    store.record(RunSummary(scenario="a", formula_id="f", region="NA", cost_per_kg_usd=12.0,
                            texture_match_pct=80.0, shelf_life_days=6.0,
                            claims_valid=0, claims_total=1, claim_coverage_pct=0.0,
                            substituted_count=1))
    agg = store.summary()
    assert agg["run_count"] == 2
    assert agg["avg_cost_per_kg_usd"] == 11.0
    assert agg["min_cost_per_kg_usd"] == 10.0
    assert agg["max_cost_per_kg_usd"] == 12.0
    assert agg["avg_claim_coverage_pct"] == 50.0
    assert agg["total_substitutions"] == 3
    assert agg["runs_by_scenario"] == {"a": 2}


def test_benchmark_is_deterministic_and_labeled():
    b1, b2 = PeerBenchmark(), PeerBenchmark()
    r1 = b1.compare("cost_per_kg_usd", 9.13)
    r2 = b2.compare("cost_per_kg_usd", 9.13)
    assert r1 == r2
    assert r1["data_label"] == SYNTHETIC_LABEL
    assert r1["peer_p50"] > 0 and r1["peer_p90"] >= r1["peer_p50"]
    assert r1["verdict"] in {"better than peers", "in line with peers", "worse than peers"}


def test_benchmark_direction():
    b = PeerBenchmark()
    cheap = b.compare("cost_per_kg_usd", 1.0)
    pricey = b.compare("cost_per_kg_usd", 999.0)
    assert cheap["verdict"] == "better than peers"
    assert pricey["verdict"] == "worse than peers"
    long_life = b.compare("shelf_life_days", 999.0)
    assert long_life["verdict"] == "better than peers"  # higher is better


def test_benchmark_unknown_metric():
    with pytest.raises(KeyError):
        PeerBenchmark().compare("nope", 1.0)


def test_moving_average_and_deltas():
    assert moving_average([1.0, 2.0, 3.0, 4.0], window=2) == [None, 1.5, 2.5, 3.5]
    assert delta_vs_previous([1.0, 3.0, 2.0]) == [None, 2.0, -1.0]
    with pytest.raises(ValueError):
        moving_average([1.0], window=0)


def test_flag_anomalies_cost_spike():
    s = RunSummary(scenario="a", formula_id="f", region="NA", cost_per_kg_usd=999.0)
    codes = {f.code for f in flag_anomalies(s)}
    assert "COST_SPIKE" in codes


def test_flag_anomalies_claim_gap_and_low_texture():
    s = RunSummary(scenario="a", formula_id="f", region="NA",
                   claims_valid=0, claims_total=2, texture_match_pct=50.0)
    codes = {f.code for f in flag_anomalies(s)}
    assert {"CLAIM_GAP", "LOW_TEXTURE"} <= codes


def test_flag_anomalies_shelf_life_risk():
    s = RunSummary(scenario="a", formula_id="f", region="NA",
                   shelf_life_days=5.0, shelf_life_risk_flags=2)
    flags = {f.code: f for f in flag_anomalies(s)}
    assert flags["SHELF_LIFE_RISK"].severity == "critical"


def test_flag_anomalies_healthy_run_is_quiet():
    s = RunSummary(scenario="a", formula_id="f", region="NA", cost_per_kg_usd=5.0,
                   texture_match_pct=95.0, shelf_life_days=10.0,
                   claims_valid=1, claims_total=1)
    assert flag_anomalies(s) == []
