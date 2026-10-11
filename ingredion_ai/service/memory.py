"""Session state store for the agent service (Memory/State box).

Abstraction over conversation/session state so the service never depends
on a concrete backend:

- :class:`SessionStore`: the interface (get/set/append/clear).
- :class:`InMemorySessionStore`: default for offline/dev/tests.
- Production backends (documented, not implemented here): Azure Cosmos DB
  (partitioned by ``session_id``, TTL on documents) or Azure Cache for
  Redis (hash per session, ``EXPIRE`` for TTL). Either implements the
  three methods below; the service code is unchanged.

All data is synthetic demo data.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class SessionStore(ABC):
    """Interface for per-session state (conversation memory)."""

    @abstractmethod
    def get(self, session_id: str) -> Dict[str, Any]:
        """Return the session dict (empty dict when unknown)."""

    @abstractmethod
    def set(self, session_id: str, state: Dict[str, Any]) -> None:
        """Replace the session dict."""

    @abstractmethod
    def append(self, session_id: str, key: str, value: Any) -> None:
        """Append *value* to the list at ``state[key]`` (creates it)."""

    @abstractmethod
    def clear(self, session_id: str) -> None:
        """Drop the session."""


class InMemorySessionStore(SessionStore):
    """Thread-safe in-memory session store (offline default).

    Args:
        ttl_seconds: sessions idle longer than this are treated as
            expired on read (lazy expiry).
        max_sessions: hard cap; oldest sessions are evicted first.
    """

    def __init__(self, ttl_seconds: float = 3600.0, max_sessions: int = 10_000) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._touched: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            self._expire_locked(session_id)
            state = self._sessions.get(session_id)
            if state is None:
                return {}
            self._touched[session_id] = time.monotonic()
            return dict(state)

    def set(self, session_id: str, state: Dict[str, Any]) -> None:
        with self._lock:
            self._sessions[session_id] = dict(state)
            self._touched[session_id] = time.monotonic()
            self._evict_if_needed_locked()

    def append(self, session_id: str, key: str, value: Any) -> None:
        with self._lock:
            self._expire_locked(session_id)
            state = self._sessions.setdefault(session_id, {})
            items: List[Any] = state.get(key, [])
            items.append(value)
            state[key] = items
            self._touched[session_id] = time.monotonic()
            self._evict_if_needed_locked()

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
            self._touched.pop(session_id, None)

    # -- internals ----------------------------------------------------------

    def _expire_locked(self, session_id: str) -> None:
        touched = self._touched.get(session_id)
        if touched is not None and time.monotonic() - touched > self.ttl_seconds:
            self._sessions.pop(session_id, None)
            self._touched.pop(session_id, None)

    def _evict_if_needed_locked(self) -> None:
        while len(self._sessions) > self.max_sessions:
            oldest = min(self._touched, key=self._touched.get)
            self._sessions.pop(oldest, None)
            self._touched.pop(oldest, None)


#: Process-wide default store used by the service.
session_store: SessionStore = InMemorySessionStore()


__all__ = ["SessionStore", "InMemorySessionStore", "session_store"]
