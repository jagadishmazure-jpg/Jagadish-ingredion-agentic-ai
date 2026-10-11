"""Google Agent2Agent (A2A) protocol adapter (demo, dependency-light).

Implements the core A2A shapes used for agent-to-agent interop:

- **Agent cards**: JSON metadata (name, description, skills, input/output
  modes, capabilities, authentication) discoverable at
  ``/.well-known/agent.json`` in a real deployment.
- **Task protocol** (JSON-RPC style): ``message/send`` creates a task from
  an incoming message, ``tasks/get`` polls it, ``tasks/cancel`` aborts it.
  Tasks move ``submitted -> working -> completed | failed`` and carry
  **artifacts** (typed result parts).

The adapter translates an incoming A2A message into the demo framework
workflow (``run_reformulation``) and formats the blackboard results as A2A
artifacts. ``FakeTransport`` provides an in-memory transport for offline
tests; a real deployment would bind these handlers to an HTTP server.

All data is synthetic demo data; no network is used here.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from ingredion_ai.interop.auth import (
    SKILL_SCOPES,
    AuthenticationError,
    AuthorizationError,
    authenticate_and_authorize,
    required_scopes_for,
)

# ---------------------------------------------------------------------------
# Agent card shapes (A2A-style)
# ---------------------------------------------------------------------------


@dataclass
class AgentSkill:
    """One capability advertised on an agent card."""

    id: str
    name: str
    description: str
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    input_modes: List[str] = field(default_factory=lambda: ["text/plain"])
    output_modes: List[str] = field(default_factory=lambda: ["text/plain", "application/json"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "examples": self.examples,
            "inputModes": self.input_modes,
            "outputModes": self.output_modes,
        }


@dataclass
class AgentCard:
    """A2A-style agent card for one demo domain agent."""

    name: str
    description: str
    url: str
    version: str = "0.1.0"
    skills: List[AgentSkill] = field(default_factory=list)
    default_input_modes: List[str] = field(default_factory=lambda: ["text/plain"])
    default_output_modes: List[str] = field(
        default_factory=lambda: ["text/plain", "application/json"]
    )
    streaming: bool = False
    auth_schemes: List[str] = field(
        default_factory=lambda: [
            "bearer (demo synthetic JWT)",
            "oidc (Entra ID, production)",
        ]
    )
    # Required scopes per skill id, e.g. {"reformulate": ["formulation:write"]}.
    skill_scopes: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "skills": [s.to_dict() for s in self.skills],
            "defaultInputModes": self.default_input_modes,
            "defaultOutputModes": self.default_output_modes,
            "capabilities": {"streaming": self.streaming},
            "authentication": {
                "schemes": self.auth_schemes,
                "skillScopes": self.skill_scopes,
            },
        }


def build_agent_cards(base_url: str = "https://demo.invalid/a2a") -> Dict[str, AgentCard]:
    """Build the four domain-agent cards for the demo system."""
    text_json = ["text/plain", "application/json"]
    cards = {
        "rd_formulation": AgentCard(
            name="rd-formulation-agent",
            description=(
                "Clean-label R&D formulation specialist (demo): analyzes "
                "formulas, recommends substitutions, predicts texture and "
                "shelf-life, validates label claims, generates documentation."
            ),
            url=f"{base_url}/rd-formulation",
            skills=[
                AgentSkill(
                    id="reformulate",
                    name="reformulate",
                    description="Run the full clean-label reformulation workflow for a formula.",
                    tags=["reformulation", "clean-label", "r-and-d"],
                    examples=["Reformulate the demo sweet bakery cake to clean label"],
                    input_modes=text_json,
                    output_modes=text_json,
                ),
                AgentSkill(
                    id="validate-claims",
                    name="validate-claims",
                    description="Validate label claims against demo regional rules.",
                    tags=["regulatory", "claims"],
                    examples=["Is 'natural' valid for this formula in NA?"],
                ),
            ],
        ),
        "supply_chain": AgentCard(
            name="supply-chain-agent",
            description=(
                "Supply-chain planning specialist (demo): demand forecasting, "
                "inventory and procurement optimization, production scheduling."
            ),
            url=f"{base_url}/supply-chain",
            skills=[
                AgentSkill(
                    id="forecast-demand",
                    name="forecast-demand",
                    description="Forecast weekly ingredient demand for demo SKUs.",
                    tags=["forecasting", "demand"],
                    examples=["Forecast PF-200 demand for the next 4 weeks"],
                    input_modes=text_json,
                    output_modes=text_json,
                ),
            ],
        ),
        "esg": AgentCard(
            name="esg-agent",
            description=(
                "ESG reporting specialist (demo): collects synthetic plant "
                "readings, computes carbon and intensity metrics, generates "
                "traceable ESG reports."
            ),
            url=f"{base_url}/esg",
            skills=[
                AgentSkill(
                    id="esg-report",
                    name="esg-report",
                    description="Generate an ESG report draft with traceable calculations.",
                    tags=["esg", "sustainability", "reporting"],
                    examples=["Generate the quarterly ESG report draft"],
                    input_modes=text_json,
                    output_modes=text_json,
                ),
            ],
        ),
        "customer_advisor": AgentCard(
            name="customer-advisor-agent",
            description=(
                "Customer formulation advisor (demo): recommends ingredients, "
                "builds sample formulations, validates claims, estimates "
                "pricing bands."
            ),
            url=f"{base_url}/customer-advisor",
            skills=[
                AgentSkill(
                    id="estimate-pricing",
                    name="estimate-pricing",
                    description="Estimate cost and willingness-to-pay pricing bands.",
                    tags=["pricing", "customer"],
                    examples=["Price the reformulated formula with validated claims"],
                    input_modes=text_json,
                    output_modes=text_json,
                ),
            ],
        ),
    }
    # Attach the declared per-skill auth requirements to each card.
    for agent_name, card in cards.items():
        card.skill_scopes = {k: list(v) for k, v in SKILL_SCOPES[agent_name].items()}
    return cards


# ---------------------------------------------------------------------------
# Task protocol (JSON-RPC style, in-memory)
# ---------------------------------------------------------------------------

TASK_STATES = ("submitted", "working", "completed", "failed", "canceled")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class A2AAdapter:
    """Translate A2A task requests into demo workflow runs.

    ``executor`` maps an agent name to a callable
    ``(message_text, context) -> blackboard dict``. The default executor
    runs the framework reformulation workflow offline.
    """

    def __init__(
        self,
        executor: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        self.executor = executor or self._default_executor
        self.cards = build_agent_cards()
        self._tasks: Dict[str, Dict[str, Any]] = {}

    # -- task endpoints ----------------------------------------------------

    def message_send(
        self,
        agent_name: str,
        message_text: str,
        context: Optional[Dict[str, Any]] = None,
        *,
        token: Optional[str] = None,
        skill_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``message/send``: create a task from an incoming message.

        The caller must present a bearer token; the token is verified and
        the requested skill's scopes (declared on the agent card) are
        enforced. Unauthenticated callers get a 401-style error,
        out-of-scope requests a 403-style error.
        """
        card = self.cards.get(agent_name)
        if card is None:
            return self._error_response(None, f"unknown agent: {agent_name!r}")
        skill = skill_id or (card.skills[0].id if card.skills else "")
        try:
            required = required_scopes_for(agent_name, skill)
        except KeyError:
            return self._error_response(None, f"unknown skill: {skill!r}")
        try:
            identity = authenticate_and_authorize(token, required)
        except AuthenticationError as exc:
            return {"error": {"code": 401, "message": str(exc)}, "task_id": None}
        except AuthorizationError as exc:
            return {"error": {"code": 403, "message": str(exc)}, "task_id": None}
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        task = {
            "id": task_id,
            "agent": agent_name,
            "skill": skill,
            # Identity attribution for the audit trail (see governance/audit.py).
            "caller": {"subject": identity.subject, "scopes": sorted(identity.scopes)},
            "status": {"state": "submitted", "timestamp": _now()},
            "message": {"role": "user", "parts": [{"type": "text", "text": message_text}]},
            "artifacts": [],
        }
        self._tasks[task_id] = task
        self._run(task, message_text, context or {})
        return {"task": self._public_task(task)}

    def _check_task_access(
        self, task_id: str, token: Optional[str]
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Authorize access to a task.

        Returns ``(task, None)`` when allowed, ``(None, error_dict)``
        otherwise. The caller must present the token whose subject created
        the task, or hold the ``a2a:admin`` scope. Task IDs are unguessable
        (48-bit) but that is defense-in-depth, not authorization.
        """
        task = self._tasks.get(task_id)
        if task is None:
            return None, self._error_response(task_id, "task not found")
        try:
            identity = authenticate_and_authorize(token, [])
        except AuthenticationError as exc:
            return None, {"error": {"code": 401, "message": str(exc)},
                          "task_id": task_id}
        owner = (task.get("caller") or {}).get("subject")
        if identity.subject != owner and "a2a:admin" not in identity.scopes:
            return None, {"error": {"code": 403, "message":
                                    "not the task owner"}, "task_id": task_id}
        return task, None

    def tasks_get(
        self, task_id: str, *, token: Optional[str] = None
    ) -> Dict[str, Any]:
        """``tasks/get``: poll a task's status and artifacts.

        Requires the Bearer <redacted> of the task's creator (or ``a2a:admin``).
        """
        task, error = self._check_task_access(task_id, token)
        if error is not None:
            return error
        return {"task": self._public_task(task)}

    def tasks_cancel(
        self, task_id: str, *, token: Optional[str] = None
    ) -> Dict[str, Any]:
        """``tasks/cancel``: mark a non-terminal task canceled.

        Requires the Bearer <redacted> of the task's creator (or ``a2a:admin``).
        """
        task, error = self._check_task_access(task_id, token)
        if error is not None:
            return error
        if task["status"]["state"] in ("completed", "failed", "canceled"):
            return {"task": self._public_task(task)}
        task["status"] = {"state": "canceled", "timestamp": _now()}
        return {"task": self._public_task(task)}

    def get_agent_card(self, agent_name: str) -> Dict[str, Any]:
        """Return the agent card dict (served at /.well-known/agent.json)."""
        card = self.cards.get(agent_name)
        if card is None:
            return {"error": f"unknown agent: {agent_name!r}"}
        return card.to_dict()

    # -- internals ----------------------------------------------------------

    def _run(
        self, task: Dict[str, Any], message_text: str, context: Dict[str, Any]
    ) -> None:
        task["status"] = {"state": "working", "timestamp": _now()}
        try:
            blackboard = self.executor(message_text, context)
            task["artifacts"] = self._blackboard_to_artifacts(blackboard)
            task["status"] = {"state": "completed", "timestamp": _now()}
        except Exception as exc:  # noqa: BLE001 - surfaced as task failure
            task["status"] = {
                "state": "failed",
                "timestamp": _now(),
                "message": f"{type(exc).__name__}: {exc}",
            }

    @staticmethod
    def _default_executor(
        message_text: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run the offline framework reformulation workflow (demo)."""
        from ingredion_ai.framework.runner import build_demo_context, run_reformulation

        formula_id = context.get("formula_id", "sweet_bakery_cake")
        ctx = build_demo_context(
            formula_id,
            context.get("target_claims", ["no artificial ingredients"]),
            context.get("region", "NA"),
        )
        return asyncio.run(run_reformulation(ctx, live=False))

    @staticmethod
    def _blackboard_to_artifacts(blackboard: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format blackboard results as A2A artifacts (data parts)."""
        artifacts = []
        for key, value in blackboard.items():
            artifacts.append(
                {
                    "name": key,
                    "parts": [{"type": "data", "data": value}],
                }
            )
        return artifacts

    @staticmethod
    def _public_task(task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": task["id"],
            "status": task["status"],
            "artifacts": task["artifacts"],
            # Identity attribution for the audit trail.
            "caller": task.get("caller"),
        }

    @staticmethod
    def _error_response(task_id: Optional[str], message: str) -> Dict[str, Any]:
        return {"error": {"code": -32602, "message": message}, "task_id": task_id}


class FakeTransport:
    """In-memory JSON-RPC transport for offline A2A tests (demo)."""

    def __init__(self, adapter: Optional[A2AAdapter] = None) -> None:
        self.adapter = adapter or A2AAdapter()
        self.sent: List[Dict[str, Any]] = []

    def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch one JSON-RPC-style call and record it."""
        self.sent.append({"method": method, "params": params})
        if method == "message/send":
            return self.adapter.message_send(
                params["agent"],
                params["message"],
                params.get("context"),
                token=params.get("token"),
                skill_id=params.get("skill_id"),
            )
        if method == "tasks/get":
            return self.adapter.tasks_get(
                params["task_id"], token=params.get("token"))
        if method == "tasks/cancel":
            return self.adapter.tasks_cancel(
                params["task_id"], token=params.get("token"))
        return {"error": {"code": -32601, "message": f"unknown method: {method}"}}
