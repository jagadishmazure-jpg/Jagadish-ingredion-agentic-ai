"""Tests for deeper tool calling: sandbox, OpenAPI gen, resilience, composition.

All offline, deterministic, synthetic data only.
"""

import time

import pytest

from ingredion_ai.tools import (
    FallbackChain,
    RetryPolicy,
    call_with_retry,
    chain,
    fan_out,
    load_lims_openapi,
    partial_envelope,
    run_sandboxed,
    synthetic_lims_transport,
    tools_from_openapi,
    validate_against_schema,
)


# -- sandbox -------------------------------------------------------------------


def test_validate_object_ok_and_errors():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
        "required": ["a"],
    }
    assert validate_against_schema({"a": "x", "b": 1}, schema) == []
    errors = validate_against_schema({"b": "nope"}, schema)
    assert any("missing required" in e for e in errors)
    assert any("expected integer" in e for e in errors)


def test_validate_array_enum_bounds():
    schema = {
        "type": "object",
        "properties": {
            "tags": {"type": "array", "items": {"type": "string"}},
            "level": {"enum": ["low", "high"]},
            "n": {"type": "number", "minimum": 0, "maximum": 10},
        },
    }
    assert validate_against_schema(
        {"tags": ["a"], "level": "low", "n": 5}, schema) == []
    errors = validate_against_schema(
        {"tags": [1], "level": "mid", "n": 99}, schema)
    assert len(errors) == 3


def test_validate_additional_properties_false():
    schema = {"type": "object", "properties": {"a": {"type": "string"}},
              "additionalProperties": False}
    errors = validate_against_schema({"a": "x", "b": 1}, schema)
    assert any("not allowed" in e for e in errors)


def test_run_sandboxed_success():
    env = run_sandboxed(lambda x: {"doubled": x * 2}, {"x": 21},
                        input_schema={"type": "object",
                                      "properties": {"x": {"type": "integer"}},
                                      "required": ["x"]},
                        output_schema={"type": "object",
                                       "properties": {"doubled": {"type": "integer"}},
                                       "required": ["doubled"]},
                        tool_name="doubler")
    assert env == {"ok": True, "tool": "doubler", "result": {"doubled": 42}}


def test_run_sandboxed_invalid_args():
    env = run_sandboxed(lambda x: x, {"x": "bad"},
                        input_schema={"type": "object",
                                      "properties": {"x": {"type": "integer"}},
                                      "required": ["x"]})
    assert env["ok"] is False
    assert env["error"]["stage"] == "args"
    assert env["error"]["code"] == "INVALID_ARGS"


def test_run_sandboxed_timeout():
    def slow(**kw):
        time.sleep(0.5)

    env = run_sandboxed(slow, {}, timeout_s=0.05)
    assert env["ok"] is False
    assert env["error"]["code"] == "TIMEOUT"
    assert env["error"]["stage"] == "timeout"


def test_run_sandboxed_invalid_result():
    env = run_sandboxed(lambda: {"wrong": 1}, {},
                        output_schema={"type": "object",
                                       "properties": {"right": {"type": "integer"}},
                                       "required": ["right"]})
    assert env["ok"] is False
    assert env["error"]["stage"] == "result"


def test_run_sandboxed_exception_shaped():
    def boom(**kw):
        raise RuntimeError("kaput")

    env = run_sandboxed(boom, {})
    assert env["ok"] is False
    assert env["error"]["code"] == "EXEC_FAILED"


# -- openapi ---------------------------------------------------------------------


def _lims_tools():
    return tools_from_openapi(load_lims_openapi(), synthetic_lims_transport)


def test_openapi_generates_expected_tools():
    tools = _lims_tools()
    assert set(tools) == {"getSample", "getTestResults", "registerSample"}
    assert tools["getSample"].method == "GET"
    assert tools["registerSample"].method == "POST"


def test_openapi_input_schema_required_params():
    tools = _lims_tools()
    schema = tools["getSample"].input_schema
    assert "sampleId" in schema["required"]
    assert schema["properties"]["sampleId"]["pattern"] == "^SMP-[0-9]+$"


def test_openapi_get_sample_roundtrip():
    env = _lims_tools()["getSample"](sampleId="SMP-1001")
    assert env["ok"] is True
    assert env["result"]["product"].startswith("Clean-label cake")


def test_openapi_get_test_results_with_filter():
    tools = _lims_tools()
    all_rows = tools["getTestResults"](sampleId="SMP-1002")
    assert all_rows["ok"] is True
    assert len(all_rows["result"]["results"]) == 2
    pending = tools["getTestResults"](sampleId="SMP-1002", status="pending")
    assert [r["test"] for r in pending["result"]["results"]] == ["viscosity"]


def test_openapi_unknown_sample_shaped_error():
    env = _lims_tools()["getSample"](sampleId="SMP-9999")
    assert env["ok"] is False
    assert env["error"]["code"] == "EXEC_FAILED"


def test_openapi_missing_required_arg_rejected():
    env = _lims_tools()["getSample"]()
    assert env["ok"] is False
    assert env["error"]["code"] == "INVALID_ARGS"


def test_openapi_post_body_tool():
    env = _lims_tools()["registerSample"](product="Demo bar", batch="B-99")
    assert env["ok"] is True
    assert env["result"]["sample_id"] == "SMP-9000"


# -- resilience ---------------------------------------------------------------------


def test_retry_succeeds_first_try():
    env = call_with_retry(lambda: {"ok": True, "result": 1},
                          policy=RetryPolicy(max_attempts=3, backoff_s=0))
    assert env["ok"] is True
    assert env["attempts"] == 1


def test_retry_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            return {"ok": False, "error": {"code": "TRANSIENT", "retryable": True}}
        return {"ok": True, "result": "recovered"}

    env = call_with_retry(flaky, policy=RetryPolicy(max_attempts=3, backoff_s=0))
    assert env["ok"] is True
    assert env["attempts"] == 3


def test_retry_exhausts_attempts():
    env = call_with_retry(
        lambda: {"ok": False, "error": {"code": "DOWN", "retryable": True}},
        policy=RetryPolicy(max_attempts=2, backoff_s=0),
    )
    assert env["ok"] is False
    assert env["attempts"] == 2


def test_retry_stops_on_non_retryable_envelope():
    calls = []

    def nope():
        calls.append(1)
        return {"ok": False, "error": {"code": "PERMANENT", "retryable": False}}

    env = call_with_retry(nope, policy=RetryPolicy(max_attempts=5, backoff_s=0))
    assert env["attempts"] == 1
    assert len(calls) == 1


def test_retry_shapes_exception():
    def boom():
        raise RuntimeError("bad")

    env = call_with_retry(boom, policy=RetryPolicy(max_attempts=2, backoff_s=0))
    assert env["ok"] is False
    assert env["attempts"] == 2


def test_fallback_chain_primary_wins():
    chain_ = FallbackChain([
        ("primary", lambda a: {"ok": True, "result": "p"}),
        ("backup", lambda a: {"ok": True, "result": "b"}),
    ])
    env = chain_({})
    assert env["used"] == "primary"
    assert env["attempts"] == ["primary"]


def test_fallback_chain_uses_backup():
    chain_ = FallbackChain([
        ("primary", lambda a: {"ok": False, "error": {"code": "X"}}),
        ("backup", lambda a: {"ok": True, "result": "b"}),
    ])
    env = chain_({})
    assert env["used"] == "backup"
    assert env["attempts"] == ["primary", "backup"]


def test_fallback_chain_all_fail():
    chain_ = FallbackChain([("a", lambda a: {"ok": False}), ("b", lambda a: {"ok": False})])
    env = chain_({})
    assert env["ok"] is False
    assert env["used"] is None
    assert env["error"]["code"] == "ALL_FAILED"


def test_fallback_chain_needs_a_tool():
    with pytest.raises(ValueError):
        FallbackChain([])


def test_partial_envelope_states():
    ok = {"ok": True}
    bad = {"ok": False}
    assert partial_envelope({"a": ok, "b": ok})["ok"] is True
    mixed = partial_envelope({"a": ok, "b": bad})
    assert mixed["ok"] is False and mixed["partial"] is True
    assert mixed["succeeded"] == ["a"] and mixed["failed"] == ["b"]
    none = partial_envelope({"a": bad})
    assert none["partial"] is False


# -- composition ---------------------------------------------------------------------


def _add(args):
    return {"ok": True, "result": {"sum": args["x"] + args["y"] }}


def _double(args):
    return {"ok": True, "result": {"doubled": args["n"] * 2}}


def test_chain_output_to_input_mapping():
    run = chain(
        [("add", _add), ("double", _double)],
        arg_maps={
            "add": {"x": 20, "y": 22},
            "double": {"n": "$add.sum"},
        },
    )
    env = run({})
    assert env["ok"] is True
    assert env["output"] == {"doubled": 84}
    assert env["steps"]["add"]["result"] == {"sum": 42}


def test_chain_callable_mapping():
    run = chain(
        [("add", _add), ("double", _double)],
        arg_maps={
            "add": {"x": 1, "y": 2},
            "double": {"n": lambda prior: prior["add"]["result"]["sum"] + 10},
        },
    )
    assert run({})["output"] == {"doubled": 26}


def test_chain_stops_on_error_by_default():
    def bad(args):
        return {"ok": False, "error": {"code": "X"}}

    run = chain([("bad", bad), ("double", _double)],
                arg_maps={"double": {"n": 1}})
    env = run({})
    assert env["ok"] is False
    assert "double" not in env["steps"]


def test_chain_continues_when_configured():
    def bad(args):
        return {"ok": False, "error": {"code": "X"}}

    run = chain([("bad", bad), ("double", _double)],
                arg_maps={"double": {"n": 5}}, stop_on_error=False)
    env = run({})
    assert env["ok"] is False  # one step failed overall
    assert env["steps"]["double"]["result"] == {"doubled": 10}


def test_fan_out_merges_results():
    results = fan_out({
        "a": (_add, {"x": 1, "y": 2}),
        "b": (_double, {"n": 4}),
    })
    assert results["a"]["result"] == {"sum": 3}
    assert results["b"]["result"] == {"doubled": 8}


def test_fan_out_captures_failure():
    def bad(args):
        raise RuntimeError("nope")

    results = fan_out({"good": (_double, {"n": 2}), "bad": (bad, {})})
    assert results["good"]["ok"] is True
    assert results["bad"]["ok"] is False


def test_fan_out_empty():
    assert fan_out({}) == {}


# -- framework wiring ------------------------------------------------------------------


def test_lims_tool_wired_into_rd_agent():
    import json

    from ingredion_ai.framework.runner import build_demo_context
    from ingredion_ai.framework.tools import build_tool_functions

    ctx = build_demo_context(
        "sweet_bakery_cake",
        ["no artificial ingredients", "reduced sugar"],
        "NA",
    )
    tools = build_tool_functions(ctx)
    names = [fn.__name__ for fn in tools["rd_formulation"]]
    assert "lims_quality_lookup" in names
    fn = next(f for f in tools["rd_formulation"] if f.__name__ == "lims_quality_lookup")
    result = json.loads(fn("SMP-1001"))
    assert result["ok"] is True
    assert result["output"]["sample_id"] == "SMP-1001"
    assert "lims_quality_lookup" in ctx["blackboard"]


def test_lims_tool_allowed_by_policy():
    from ingredion_ai.governance.policy import check_action

    allowed, _ = check_action("rd_formulation", "lims_quality_lookup")
    assert allowed is True
