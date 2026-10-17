"""Tool composition: chains and fan-out (demo).

- :func:`chain` — sequential execution where each step's input is mapped
  from prior results via ``"$step.field.path"`` references or callables.
- :func:`fan_out` — parallel execution with per-tool envelopes merged under
  tool names; failures are captured, never raised.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Tuple

# A step: (name, fn) where fn(args_dict) -> envelope dict.
Step = Tuple[str, Callable[[Dict[str, Any]], Dict[str, Any]]]
# arg value: literal | "$step.path.to.field" reference | callable(prior_results) -> value
ArgValue = Any


def _resolve(value: ArgValue, prior: Dict[str, Any]) -> Any:
    if callable(value):
        return value(prior)
    if isinstance(value, str) and value.startswith("$"):
        node, _, dotted = value[1:].partition(".")
        current: Any = prior.get(node, {})
        # Unwrap one envelope level: {"ok":..., "result": {...}}
        if isinstance(current, dict) and "result" in current and dotted:
            current = current["result"]
        for part in dotted.split(".") if dotted else []:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                current = current[int(part)]
            else:
                return None
        return current
    return value


def chain(
    steps: List[Step],
    arg_maps: Dict[str, Dict[str, ArgValue]] | None = None,
    *,
    stop_on_error: bool = True,
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Build a sequential tool chain.

    ``arg_maps[step_name]`` maps argument names to literals,
    ``"$step.field"`` references into earlier envelopes' ``result`` payloads,
    or callables receiving all prior results. The first step additionally
    receives the chain's input merged under its mapped args.

    Returns a callable ``(input_dict) -> {"ok", "steps": {name: envelope},
    "output": <last result>}``. With ``stop_on_error=True`` (default) the
    chain halts at the first failed step.
    """
    arg_maps = arg_maps or {}

    def _run(chain_input: Dict[str, Any]) -> Dict[str, Any]:
        prior: Dict[str, Any] = {"input": {"ok": True, "result": dict(chain_input)}}
        for name, fn in steps:
            mapping = arg_maps.get(name, {})
            args = {arg: _resolve(val, prior) for arg, val in mapping.items()}
            try:
                envelope = fn(args)
            except Exception as exc:  # noqa: BLE001 - captured per step
                envelope = {"ok": False, "error": {"code": "EXCEPTION", "message": str(exc)}}
            if not isinstance(envelope, dict):
                envelope = {"ok": False, "error": {"code": "BAD_ENVELOPE"}}
            prior[name] = envelope
            if not envelope.get("ok") and stop_on_error:
                break
        last_name = steps[-1][0] if steps else "input"
        last = prior.get(last_name, {})
        output = last.get("result") if isinstance(last, dict) else None
        ok = all(
            isinstance(prior.get(name), dict) and prior[name].get("ok")
            for name, _ in steps
            if name in prior
        )
        return {"ok": ok, "steps": {n: prior[n] for n, _ in steps if n in prior}, "output": output}

    return _run


def fan_out(
    calls: Dict[str, Tuple[Callable[[Dict[str, Any]], Dict[str, Any]], Dict[str, Any]]],
    *,
    timeout_s: float = 30.0,
) -> Dict[str, Dict[str, Any]]:
    """Run tools in parallel; return ``{name: envelope}``.

    Individual failures are captured into error envelopes — fan-out itself
    never raises for tool failures.
    """
    results: Dict[str, Dict[str, Any]] = {}
    if not calls:
        return results
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = {
            pool.submit(_safe_call, fn, args): name for name, (fn, args) in calls.items()
        }
        for future in as_completed(futures, timeout=timeout_s):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:  # noqa: BLE001 - captured per tool
                results[name] = {
                    "ok": False,
                    "error": {"code": "FANOUT_FAILED", "message": str(exc)},
                }
    return results


def _safe_call(
    fn: Callable[[Dict[str, Any]], Dict[str, Any]], args: Dict[str, Any]
) -> Dict[str, Any]:
    try:
        envelope = fn(dict(args))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"code": "EXCEPTION", "message": str(exc)}}
    return envelope if isinstance(envelope, dict) else {"ok": False, "error": {"code": "BAD_ENVELOPE"}}
