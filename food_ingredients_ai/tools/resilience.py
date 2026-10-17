"""Per-tool resilience: retries, fallback chains, partial success (demo).

- :class:`RetryPolicy` + :func:`call_with_retry` — bounded retries with
  deterministic backoff for transient tool failures.
- :class:`FallbackChain` — ordered tool attempts; the first success wins and
  the envelope records every attempt.
- :func:`partial_envelope` — merge parallel results into a degraded-result
  envelope instead of failing the whole batch when some tools fail.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class RetryPolicy:
    """Bounded retry configuration for one tool call."""

    max_attempts: int = 3
    backoff_s: float = 0.1
    backoff_factor: float = 2.0
    retry_on: Tuple[type, ...] = (Exception,)
    # When True, only retry errors the tool marks retryable in its envelope.
    respect_envelope: bool = True


def _envelope_retryable(envelope: Dict[str, Any]) -> bool:
    if not isinstance(envelope, dict) or envelope.get("ok"):
        return False
    error = envelope.get("error")
    if isinstance(error, dict) and "retryable" in error:
        return bool(error["retryable"])
    return True


def call_with_retry(
    fn: Callable[..., Dict[str, Any]],
    *args: Any,
    policy: Optional[RetryPolicy] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Call *fn* (returning an envelope) with bounded retries.

    Returns the first ``ok`` envelope, or the last envelope extended with
    ``attempts``. Non-envelope exceptions are shaped into an error envelope.
    """
    policy = policy or RetryPolicy()
    last: Dict[str, Any] = {
        "ok": False,
        "error": {"code": "NO_ATTEMPT", "message": "no attempts made"},
    }
    attempts = 0
    delay = policy.backoff_s
    while attempts < max(policy.max_attempts, 1):
        attempts += 1
        try:
            envelope = fn(*args, **kwargs)
        except policy.retry_on as exc:
            envelope = {
                "ok": False,
                "error": {"code": "EXCEPTION", "message": str(exc), "retryable": True},
            }
        except Exception as exc:  # noqa: BLE001 - non-retryable, shaped below
            envelope = {
                "ok": False,
                "error": {"code": "EXCEPTION", "message": str(exc), "retryable": False},
            }
            envelope["attempts"] = attempts
            return envelope
        if not isinstance(envelope, dict):
            envelope = {"ok": False, "error": {"code": "BAD_ENVELOPE", "message": "tool did not return a dict"}}
        last = envelope
        if envelope.get("ok"):
            envelope = dict(envelope)
            envelope["attempts"] = attempts
            return envelope
        if policy.respect_envelope and not _envelope_retryable(envelope):
            break
        if attempts < policy.max_attempts:
            time.sleep(delay)
            delay *= policy.backoff_factor
    last = dict(last)
    last["attempts"] = attempts
    return last


class FallbackChain:
    """Ordered tool attempts: the first ``ok`` envelope wins.

    Each entry is ``(name, fn)`` where ``fn(args_dict)`` returns an envelope.
    The returned envelope carries ``attempts`` (list of tried tool names) and
    ``used`` (the winning tool name, or ``None``).
    """

    def __init__(self, tools: List[Tuple[str, Callable[[Dict[str, Any]], Dict[str, Any]]]]):
        if not tools:
            raise ValueError("FallbackChain needs at least one tool")
        self._tools = list(tools)

    @property
    def tool_names(self) -> List[str]:
        return [name for name, _ in self._tools]

    def __call__(self, args: Dict[str, Any]) -> Dict[str, Any]:
        attempted: List[str] = []
        for name, fn in self._tools:
            attempted.append(name)
            try:
                envelope = fn(dict(args))
            except Exception as exc:  # noqa: BLE001 - try next tool
                envelope = {"ok": False, "error": {"code": "EXCEPTION", "message": str(exc)}}
            if isinstance(envelope, dict) and envelope.get("ok"):
                result = dict(envelope)
                result["attempts"] = attempted
                result["used"] = name
                return result
        return {
            "ok": False,
            "attempts": attempted,
            "used": None,
            "error": {"code": "ALL_FAILED", "message": "every fallback tool failed"},
        }


def partial_envelope(results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Merge parallel tool results into a degraded-result envelope.

    ``ok`` is True only when every result succeeded; ``partial`` is True
    when at least one succeeded and at least one failed — callers can still
    use the successful subset instead of failing the whole batch.
    """
    ok_map = {name: bool(r.get("ok")) for name, r in results.items()}
    all_ok = all(ok_map.values()) if ok_map else True
    any_ok = any(ok_map.values())
    return {
        "ok": all_ok,
        "partial": any_ok and not all_ok,
        "succeeded": sorted(n for n, ok in ok_map.items() if ok),
        "failed": sorted(n for n, ok in ok_map.items() if not ok),
        "results": results,
    }
