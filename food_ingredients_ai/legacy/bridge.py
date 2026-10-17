"""Legacy system bridges: wrap-don't-replace integration (demo).

A :class:`LegacyBridge` wraps one traditional system (SAP, CRM, LIMS, PLM,
MES) behind a uniform request/response envelope so agents can call legacy
operations as tools without knowing transport details:

- request mapping (agent-shaped payload -> legacy-shaped payload),
- timeout enforcement,
- error translation (anything the legacy system raises becomes
  :class:`LegacyError` with a stable ``code``),
- response mapping (legacy-shaped result -> agent-shaped dict),
- health checks.

The existing CRM/SAP adapters are migrated onto this abstraction as the
first two bridges (:class:`CRMBridge`, :class:`SAPBridge`) via composition —
the adapters themselves are unchanged.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


class LegacyError(Exception):
    """Translated legacy-system failure with a stable code."""

    def __init__(self, message: str, *, code: str = "LEGACY_ERROR", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass
class BridgeHealth:
    """Result of a bridge health check."""

    system: str
    healthy: bool
    latency_ms: float = 0.0
    detail: str = ""


class LegacyBridge(ABC):
    """Abstract wrapper around one traditional system."""

    def __init__(self, *, name: str, timeout_s: float = 5.0):
        self.name = name
        self.timeout_s = timeout_s

    # -- mapping hooks (override per system) ---------------------------

    def map_request(self, operation: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Agent-shaped payload -> legacy-shaped payload. Default: copy."""
        return dict(payload)

    def map_response(self, operation: str, raw: Any) -> Dict[str, Any]:
        """Legacy-shaped result -> agent-shaped dict. Default: wrap."""
        if isinstance(raw, dict):
            return raw
        return {"value": raw}

    # -- core ----------------------------------------------------------

    @abstractmethod
    def invoke(self, operation: str, payload: Dict[str, Any]) -> Any:
        """Raw call into the legacy system. May raise; translated by call()."""

    def call(self, operation: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Invoke *operation* and return a uniform envelope.

        ``{"ok": True, "system", "operation", "latency_ms", "data": ...}`` on
        success, or ``{"ok": False, ..., "error": {"code", "message",
        "retryable"}}`` on failure. Never raises for legacy failures.
        """
        payload = payload or {}
        started = time.monotonic()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.invoke, operation, self.map_request(operation, payload))
                raw = future.result(timeout=self.timeout_s)
            data = self.map_response(operation, raw)
            return {
                "ok": True,
                "system": self.name,
                "operation": operation,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "data": data,
            }
        except FuturesTimeoutError:
            err = LegacyError(
                f"{self.name}.{operation} timed out after {self.timeout_s}s",
                code="TIMEOUT",
                retryable=True,
            )
        except LegacyError as exc:  # already translated (rebind: `as` target is cleared)
            err = exc
        except Exception as exc:  # translate unknown transport errors
            err = LegacyError(f"{self.name}.{operation} failed: {exc}", code="TRANSPORT")
        return {
            "ok": False,
            "system": self.name,
            "operation": operation,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "error": {"code": err.code, "message": str(err), "retryable": err.retryable},
        }

    # -- health ---------------------------------------------------------

    def ping(self) -> None:
        """Liveness probe. Default no-op (assumed healthy); override per system."""
        return None

    def health_check(self) -> BridgeHealth:
        """Run :meth:`ping` and report a :class:`BridgeHealth`."""
        started = time.monotonic()
        try:
            self.ping()
            return BridgeHealth(
                system=self.name,
                healthy=True,
                latency_ms=round((time.monotonic() - started) * 1000, 2),
                detail="ping ok",
            )
        except Exception as exc:
            return BridgeHealth(
                system=self.name,
                healthy=False,
                latency_ms=round((time.monotonic() - started) * 1000, 2),
                detail=str(exc),
            )


class SyntheticLegacyBridge(LegacyBridge):
    """Deterministic demo bridge: operations served from scripted handlers.

    ``operations`` maps operation name -> ``handler(payload_dict)``.
    ``fail_operations`` names operations that always raise a retryable
    :class:`LegacyError` (to exercise fallback paths in tests).
    """

    def __init__(
        self,
        name: str,
        operations: Dict[str, Callable[[Dict[str, Any]], Any]],
        *,
        timeout_s: float = 5.0,
        fail_operations: List[str] | None = None,
    ):
        super().__init__(name=name, timeout_s=timeout_s)
        self._operations = dict(operations)
        self._fail = set(fail_operations or [])

    def invoke(self, operation: str, payload: Dict[str, Any]) -> Any:
        if operation in self._fail:
            raise LegacyError(
                f"simulated failure for {self.name}.{operation}",
                code="SIMULATED",
                retryable=True,
            )
        handler = self._operations.get(operation)
        if handler is None:
            raise LegacyError(
                f"unknown operation {operation!r} on {self.name}",
                code="UNKNOWN_OPERATION",
            )
        return handler(dict(payload))

    @property
    def operations(self) -> List[str]:
        """Names of the scripted operations."""
        return sorted(self._operations)


def _not_found(system: str, kind: str, key: str) -> LegacyError:
    return LegacyError(f"{system}: {kind} {key!r} not found", code="NOT_FOUND")


class CRMBridge(LegacyBridge):
    """The existing CRM adapter, migrated onto the bridge abstraction.

    Operations: ``get_account``, ``list_contacts``, ``list_opportunities``,
    ``list_cases``. Payload keys mirror the adapter method arguments.
    """

    OPERATIONS = ("get_account", "list_contacts", "list_opportunities", "list_cases")

    def __init__(self, adapter: Any = None, **kwargs: Any):
        from food_ingredients_ai.integrations.crm import crm_from_env

        super().__init__(name="crm", **kwargs)
        self.adapter = adapter or crm_from_env()

    def map_response(self, operation: str, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, list):
            return {"items": raw}
        return super().map_response(operation, raw)

    def invoke(self, operation: str, payload: Dict[str, Any]) -> Any:
        account_id = payload.get("account_id", "")
        try:
            if operation == "get_account":
                result = self.adapter.get_account(account_id)
            elif operation == "list_contacts":
                result = self.adapter.list_contacts(account_id)
            elif operation == "list_opportunities":
                result = self.adapter.list_opportunities(account_id)
            elif operation == "list_cases":
                result = self.adapter.list_cases(account_id)
            else:
                raise LegacyError(
                    f"unknown operation {operation!r} on crm", code="UNKNOWN_OPERATION"
                )
        except KeyError:
            raise _not_found("crm", "account", account_id) from None
        if result is None or result == {} or result == []:
            # Demo doubles return {} / [] for unknown accounts; translate.
            raise _not_found("crm", "account", account_id)
        return result


class SAPBridge(LegacyBridge):
    """The existing SAP adapter, migrated onto the bridge abstraction.

    Operations: ``get_material``, ``get_inventory``, ``list_purchase_orders``,
    ``list_plants``. Payload keys mirror the adapter method arguments.
    """

    OPERATIONS = (
        "get_material",
        "get_inventory",
        "list_purchase_orders",
        "list_plants",
    )

    def __init__(self, adapter: Any = None, **kwargs: Any):
        from food_ingredients_ai.integrations.sap import sap_from_env

        super().__init__(name="sap", **kwargs)
        self.adapter = adapter or sap_from_env()

    def map_response(self, operation: str, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, list):
            return {"items": raw}
        return super().map_response(operation, raw)

    def invoke(self, operation: str, payload: Dict[str, Any]) -> Any:
        try:
            if operation == "get_material":
                result = self.adapter.get_material(payload.get("material_id", ""))
            elif operation == "get_inventory":
                result = self.adapter.get_inventory(payload.get("plant_id", ""))
            elif operation == "list_purchase_orders":
                result = self.adapter.list_purchase_orders(payload.get("plant_id", ""))
            elif operation == "list_plants":
                result = self.adapter.list_plants()
            else:
                raise LegacyError(
                    f"unknown operation {operation!r} on sap", code="UNKNOWN_OPERATION"
                )
        except KeyError:
            raise _not_found("sap", "record", str(payload)) from None
        if result is None or result == {} or result == []:
            raise _not_found("sap", "record", str(payload))
        return result
