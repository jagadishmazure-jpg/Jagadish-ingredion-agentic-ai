"""Logic Apps integration: callbacks + approval workflow support (demo).

Two pieces:

1. :class:`LogicAppCallbackReceiver` — the HTTP surface our service
   exposes for a Logic App to call *back* into (approval granted/denied,
   runbook step completion). Validates an HMAC-SHA256 signature
   (``compare_digest``; the demo secret is synthetic — production reads it
   from Key Vault) and routes to registered handlers.
2. ``infra/logicapps/reformulation-approval.json`` — a checked-in sample
   Logic Apps (Consumption) workflow definition: on-new-formula →
   call agent API → post approval card → wait for callback → write back
   the decision.

Production: front this receiver with APIM (JWT validation) and rotate
the HMAC secret via Key Vault; the Logic App uses the system-assigned
managed identity for the callback.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from food_ingredients_ai.azure_integration.events import (
    APPROVAL_DENIED,
    APPROVAL_GRANTED,
    APPROVAL_REQUESTED,
    emit_lifecycle_event,
)

#: Synthetic demo HMAC secret — NEVER a real secret; production reads from
#: Key Vault and rotates it.
DEMO_CALLBACK_SECRET = "demo-only-not-a-secret"

#: Callback actions the receiver understands.
ACTION_APPROVAL_GRANTED = "approval.granted"
ACTION_APPROVAL_DENIED = "approval.denied"
ACTION_STEP_COMPLETED = "runbook.step.completed"


class CallbackValidationError(Exception):
    """The Logic App callback failed validation."""


@dataclass
class ApprovalRequest:
    """An approval the agent asked a human (via Logic App) to decide."""

    approval_id: str
    subject: str  # e.g. "reformulation/job-123"
    action: str  # e.g. "approve new formulation"
    requested_by: str = "agent"
    context: Dict[str, Any] = field(default_factory=dict)


class LogicAppCallbackReceiver:
    """Validate + route callbacks from a Logic App workflow."""

    def __init__(self, secret: str = DEMO_CALLBACK_SECRET) -> None:
        self._secret = secret.encode()
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.received: List[Dict[str, Any]] = []

    # -- handler registration ----------------------------------------------

    def on(self, action: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self._handlers[action] = handler

    # -- validation ----------------------------------------------------------

    def _signature(self, canonical_body: str) -> str:
        return hmac.new(self._secret, canonical_body.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _canonical(payload: Dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def sign(self, payload: Dict[str, Any]) -> str:
        """Sign an outbound payload (used by tests / the Logic App side)."""
        return self._signature(self._canonical(payload))

    # -- entry point ----------------------------------------------------------

    def receive(self, payload: Dict[str, Any], signature: str) -> Dict[str, Any]:
        """Validate the callback and dispatch to the registered handler."""
        expected = self._signature(self._canonical(payload))
        if not hmac.compare_digest(expected, signature):
            raise CallbackValidationError("invalid callback signature")
        action = str(payload.get("action") or "")
        handler = self._handlers.get(action)
        if handler is None:
            raise CallbackValidationError(f"unknown callback action {action!r}")
        self.received.append({"action": action, "payload": dict(payload)})
        return handler(dict(payload.get("data") or {}))


def build_approval_request(
    *,
    approval_id: str,
    subject: str,
    action: str,
    context: Optional[Dict[str, Any]] = None,
    requested_by: str = "agent",
) -> ApprovalRequest:
    """Create an approval request and emit the lifecycle event for it."""
    req = ApprovalRequest(
        approval_id=approval_id,
        subject=subject,
        action=action,
        requested_by=requested_by,
        context=dict(context or {}),
    )
    emit_lifecycle_event(
        APPROVAL_REQUESTED,
        subject=subject,
        data={"approval_id": approval_id, "action": action, "context": req.context},
    )
    return req


def default_approval_handlers(receiver: LogicAppCallbackReceiver) -> None:
    """Register the standard approval granted/denied handlers."""

    def _granted(data: Dict[str, Any]) -> Dict[str, Any]:
        emit_lifecycle_event(
            APPROVAL_GRANTED,
            subject=str(data.get("subject", "")),
            data={"approval_id": data.get("approval_id"), "by": data.get("decided_by")},
        )
        return {"status": "resumed", "decision": "granted"}

    def _denied(data: Dict[str, Any]) -> Dict[str, Any]:
        emit_lifecycle_event(
            APPROVAL_DENIED,
            subject=str(data.get("subject", "")),
            data={"approval_id": data.get("approval_id"), "by": data.get("decided_by")},
        )
        return {"status": "halted", "decision": "denied"}

    receiver.on(ACTION_APPROVAL_GRANTED, _granted)
    receiver.on(ACTION_APPROVAL_DENIED, _denied)
