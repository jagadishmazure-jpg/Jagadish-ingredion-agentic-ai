"""Execution harness: retries, timeouts, circuit breaker, guardrails (demo).

The harness wraps agent ``execute()`` calls (or any callable) with the
reliability machinery a production agent loop needs:

- **Retries** with deterministic exponential backoff (no jitter).
- **Timeouts** via ``concurrent.futures.ThreadPoolExecutor``.
- **Circuit breaker** to stop hammering a persistently failing dependency.
- **Guardrail hooks** that can veto a run before it starts (pre-hooks) or
  observe results (post-hooks).
- **Eval hooks** (``on_run_end``) that receive a ``RunRecord`` for every
  terminal run — success, failure, or veto.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, TypedDict


class GuardrailViolation(Exception):
    """Raised when a pre-hook vetoes execution of a run."""


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit breaker is open."""


class RunRecord(TypedDict, total=False):
    """Eval record emitted to ``on_run_end`` callbacks after each run."""

    fn_name: str
    success: bool
    attempts: int
    latency_s: float
    error: Optional[str]


class CircuitBreaker:
    """Fail-fast guard for a repeatedly failing dependency.

    States: ``closed`` (calls flow), ``open`` (calls rejected immediately),
    ``half-open`` (one trial call allowed after the cooldown expires).

    A trial call that succeeds closes the circuit; one that fails re-opens it
    and restarts the cooldown.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = self.CLOSED
        self.consecutive_failures = 0
        self._opened_at: Optional[float] = None

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Call *fn*, enforcing the current circuit state."""
        if self.state == self.OPEN:
            assert self._opened_at is not None
            if time.monotonic() - self._opened_at < self.cooldown_seconds:
                raise CircuitOpenError(
                    f"circuit open: rejecting call to {getattr(fn, '__name__', fn)!r}"
                )
            self.state = self.HALF_OPEN  # cooldown expired: allow one trial call

        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return result

    def _record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.state == self.HALF_OPEN or self.consecutive_failures >= self.failure_threshold:
            self.state = self.OPEN
            self._opened_at = time.monotonic()

    def _record_success(self) -> None:
        self.consecutive_failures = 0
        self.state = self.CLOSED
        self._opened_at = None


class Harness:
    """Run a callable with retries, timeout, guardrails, and eval hooks.

    Args:
        max_retries: Number of retries *after* the first attempt.
        base_delay: Base backoff delay in seconds. The delay before retry
            ``n`` is ``base_delay * 2**(n-1)`` — deterministic, no jitter.
        timeout_seconds: Per-attempt wall-clock timeout. Exceeding it raises
            ``TimeoutError`` (which, like any other exception, is retried).
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.1,
        timeout_seconds: float = 30.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout_seconds = timeout_seconds
        #: Pre-hooks run before execution: ``hook(fn_name, *args, **kwargs)``.
        #: A hook returning ``False`` vetoes the run (raises GuardrailViolation).
        self.pre_hooks: List[Callable[..., Any]] = []
        #: Post-hooks observe results: ``hook(fn_name, result)``. Never veto.
        self.post_hooks: List[Callable[..., Any]] = []
        #: Eval callbacks: ``callback(run_record)`` after every terminal run.
        self.on_run_end: List[Callable[[RunRecord], None]] = []

    def backoff_delay(self, retry_number: int) -> float:
        """Deterministic exponential backoff: ``base_delay * 2**(n-1)``."""
        return self.base_delay * (2 ** (retry_number - 1))

    def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute *fn* with retries, timeout, guardrails, and eval hooks.

        Raises:
            GuardrailViolation: a pre-hook vetoed the run.
            TimeoutError: an attempt exceeded ``timeout_seconds`` (retried
                like any other failure; raised once retries are exhausted).
            Exception: the last attempt's error, after retries are exhausted.
        """
        fn_name = getattr(fn, "__name__", type(fn).__name__)

        # --- guardrail: pre-hooks can veto before anything runs ---
        for hook in self.pre_hooks:
            if hook(fn_name, *args, **kwargs) is False:
                record: RunRecord = {
                    "fn_name": fn_name,
                    "success": False,
                    "attempts": 0,
                    "latency_s": 0.0,
                    "error": f"GuardrailViolation: vetoed by pre-hook {getattr(hook, '__name__', hook)!r}",
                }
                self._emit_run_end(record)
                raise GuardrailViolation(
                    f"run of {fn_name!r} vetoed by pre-hook {getattr(hook, '__name__', hook)!r}"
                )

        # --- execute with retries ---
        start = time.monotonic()
        attempts = 0
        last_error: Optional[BaseException] = None
        while attempts <= self.max_retries:
            attempts += 1
            try:
                result = self._run_with_timeout(fn, args, kwargs)
            except Exception as exc:  # noqa: BLE001 - retried uniformly
                last_error = exc
                if attempts <= self.max_retries:
                    time.sleep(self.backoff_delay(attempts))
                continue
            latency = time.monotonic() - start
            for hook in self.post_hooks:
                hook(fn_name, result)
            self._emit_run_end(
                {
                    "fn_name": fn_name,
                    "success": True,
                    "attempts": attempts,
                    "latency_s": latency,
                    "error": None,
                }
            )
            return result

        # --- retries exhausted ---
        assert last_error is not None
        self._emit_run_end(
            {
                "fn_name": fn_name,
                "success": False,
                "attempts": attempts,
                "latency_s": time.monotonic() - start,
                "error": f"{type(last_error).__name__}: {last_error}",
            }
        )
        raise last_error

    def _run_with_timeout(
        self, fn: Callable[..., Any], args: tuple, kwargs: Dict[str, Any]
    ) -> Any:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)
            return future.result(timeout=self.timeout_seconds)

    def _emit_run_end(self, record: RunRecord) -> None:
        for callback in self.on_run_end:
            callback(record)


def policy_guardrail(
    action_name: str,
    agent: str = "orchestrator",
    reason_store: Optional[Dict[str, str]] = None,
) -> Callable[..., bool]:
    """Build a pre-hook that denies policy-disallowed actions.

    Consults ``food_ingredients_ai.governance.policy``: the hook returns ``True``
    (allow) when ``check_action(agent, action_name)`` allows the action, and
    ``False`` (veto → ``GuardrailViolation``) otherwise. The denial reason is
    recorded on the hook as ``last_reason`` and, if *reason_store* is given,
    under the action name.

    Note: the governance policy is keyed by ``(agent, action)``, so the agent
    name is required alongside the action name.
    """
    from food_ingredients_ai.governance.policy import check_action

    def _policy_pre_hook(fn_name: str, *args: Any, **kwargs: Any) -> bool:
        allowed, reason = check_action(agent, action_name)
        _policy_pre_hook.last_reason = reason  # type: ignore[attr-defined]
        if reason_store is not None:
            reason_store[action_name] = reason
        return allowed

    _policy_pre_hook.last_reason = ""  # type: ignore[attr-defined]
    _policy_pre_hook.agent = agent  # type: ignore[attr-defined]
    _policy_pre_hook.action_name = action_name  # type: ignore[attr-defined]
    return _policy_pre_hook


__all__ = [
    "CircuitBreaker",
    "CircuitOpenError",
    "GuardrailViolation",
    "Harness",
    "RunRecord",
    "policy_guardrail",
]
