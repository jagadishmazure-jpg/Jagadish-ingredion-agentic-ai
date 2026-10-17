"""Reliability machinery for the agent service (demo).

- **Retry with exponential backoff + jitter** for transient failures
  (e.g. Azure OpenAI timeouts / connection errors).
- **Circuit breaker** (reused from :mod:`food_ingredients_ai.harness.runner`)
  around the live-LLM path: repeated failures fail fast instead of
  hammering the dependency.
- **Graceful degradation**: when the live LLM is unreachable, the service
  automatically falls back to the offline fake client and marks the
  response (``degraded: true`` + ``X-Service-Degraded`` header) instead of
  failing the request.
- **Per-client rate limiting** (fixed window, in-memory) → HTTP 429.
- **Idempotency keys** on POST endpoints: ``Idempotency-Key`` header;
  replays return the stored response without re-executing.

All demo data is synthetic. Stdlib only (FastAPI/HTTPException are
imported lazily so this module stays importable without the service deps).
"""

from __future__ import annotations

import os
import random
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple, Type

from food_ingredients_ai.harness.runner import CircuitBreaker

# ---------------------------------------------------------------------------
# Retry with exponential backoff + jitter
# ---------------------------------------------------------------------------

try:  # optional: richer transient-error coverage when httpx is installed
    import httpx as _httpx

    _HTTPX_TRANSIENT: Tuple[Type[BaseException], ...] = (
        _httpx.TimeoutException,
        _httpx.ConnectError,
        _httpx.RemoteProtocolError,
    )
except Exception:  # noqa: BLE001 - httpx optional
    _HTTPX_TRANSIENT = ()

DEFAULT_TRANSIENT: Tuple[Type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    *_HTTPX_TRANSIENT,
)


class RetryExhausted(Exception):
    """Raised when all retry attempts failed; carries the last error."""

    def __init__(self, last_error: BaseException, attempts: int) -> None:
        super().__init__(f"retries exhausted after {attempts} attempts: {last_error}")
        self.last_error = last_error
        self.attempts = attempts


def backoff_delay(attempt: int, base_delay: float, max_delay: float, jitter: bool) -> float:
    """Exponential backoff for *attempt* (1-based), optionally jittered.

    ``delay = min(max_delay, base_delay * 2**(attempt-1))``; with jitter the
    actual sleep is ``uniform(0, delay)`` (full jitter).
    """
    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
    return random.uniform(0, delay) if jitter else delay


def retry_sync(
    fn: Callable[[], Any],
    *,
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    jitter: bool = True,
    transient: Tuple[Type[BaseException], ...] = DEFAULT_TRANSIENT,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Call ``fn()`` with retries on transient errors.

    Non-transient exceptions propagate immediately. After ``max_retries``
    retries, raises :class:`RetryExhausted` wrapping the last error.
    """
    last_error: Optional[BaseException] = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except transient as exc:
            last_error = exc
            if attempt < max_retries:
                sleep(backoff_delay(attempt + 1, base_delay, max_delay, jitter))
    assert last_error is not None
    raise RetryExhausted(last_error, max_retries + 1)


#: Circuit breaker around the live-LLM path (shared process-wide).
live_llm_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)


# ---------------------------------------------------------------------------
# Per-client rate limiting (fixed window, in-memory)
# ---------------------------------------------------------------------------


class RateLimitExceeded(Exception):
    """Raised when a client exceeds its request quota."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(f"rate limit exceeded; retry after {retry_after_seconds}s")
        self.retry_after_seconds = retry_after_seconds


class RateLimiter:
    """Fixed-window rate limiter keyed by client id (e.g. token subject)."""

    def __init__(self, per_minute: int = 60) -> None:
        if per_minute < 1:
            raise ValueError("per_minute must be >= 1")
        self.per_minute = per_minute
        self._windows: Dict[str, Tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Record one request for *key*; raise RateLimitExceeded if over quota."""
        now = time.monotonic()
        with self._lock:
            start, count = self._windows.get(key, (now, 0))
            if now - start >= 60.0:
                start, count = now, 0
            count += 1
            self._windows[key] = (start, count)
            if count > self.per_minute:
                raise RateLimitExceeded(max(1, int(60.0 - (now - start))))


# ---------------------------------------------------------------------------
# Idempotency keys (in-memory, TTL)
# ---------------------------------------------------------------------------


class IdempotencyStore:
    """Remember POST responses by ``(client, Idempotency-Key)``.

    Replays return the stored ``(status_code, body)`` without re-executing
    the handler. Entries expire after ``ttl_seconds``.
    """

    def __init__(self, ttl_seconds: float = 3600.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: Dict[Tuple[str, str], Tuple[float, int, Dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get(self, client: str, key: Optional[str]) -> Optional[Tuple[int, Dict[str, Any]]]:
        """Return the stored ``(status, body)`` or ``None`` (missing/expired)."""
        if not key:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._store.get((client, key))
            if entry is None:
                return None
            stored_at, status, body = entry
            if now - stored_at > self.ttl_seconds:
                del self._store[(client, key)]
                return None
            return status, body

    def put(self, client: str, key: Optional[str], status: int, body: Dict[str, Any]) -> None:
        """Store a response for later replay."""
        if not key:
            return
        with self._lock:
            self._store[(client, key)] = (time.monotonic(), status, body)


# ---------------------------------------------------------------------------
# Service-level configuration (env-overridable)
# ---------------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


SERVICE_RATE_LIMIT_PER_MIN = _env_int("SERVICE_RATE_LIMIT_PER_MIN", 60)
SERVICE_REQUEST_TIMEOUT_S = _env_int("SERVICE_REQUEST_TIMEOUT_S", 300)
SERVICE_RETRY_MAX = _env_int("SERVICE_RETRY_MAX", 3)

rate_limiter = RateLimiter(per_minute=SERVICE_RATE_LIMIT_PER_MIN)
idempotency_store = IdempotencyStore()

__all__ = [
    "DEFAULT_TRANSIENT",
    "IdempotencyStore",
    "RateLimitExceeded",
    "RateLimiter",
    "RetryExhausted",
    "backoff_delay",
    "idempotency_store",
    "live_llm_breaker",
    "rate_limiter",
    "retry_sync",
    "SERVICE_RATE_LIMIT_PER_MIN",
    "SERVICE_REQUEST_TIMEOUT_S",
    "SERVICE_RETRY_MAX",
]
