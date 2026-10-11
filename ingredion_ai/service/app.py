"""FastAPI agent service.

Serves the Microsoft Agent Framework 1.0 reformulation workflow and the
four domain agents over HTTP, plus a demo web UI at ``GET /``.

Auth: write/run endpoints require a Bearer <redacted> verified by
:mod:`ingredion_ai.interop.auth` (demo synthetic JWT offline; swap
``verify_token`` for Entra ID OIDC/JWKS validation in production — the
interface and exceptions are unchanged). Discovery endpoints
(``/api/health``, ``/api/scenarios``, ``/api/agent-cards``,
``/.well-known/agent.json``) are public, matching A2A card discovery.

Reliability (see :mod:`ingredion_ai.service.reliability` and
``docs/reliability.md``): per-client rate limiting (429), idempotency
keys on POST endpoints, request timeouts (504), retry with exponential
backoff + jitter and a circuit breaker around the live-LLM path, and
graceful degradation — when the live LLM is unreachable the service
falls back to the offline fake client and marks the response
(``degraded: true`` + ``X-Service-Degraded`` header) instead of failing.

All data is synthetic demo data. Runs offline by default; ``live=true``
uses Azure OpenAI (needs ``.env`` — see ``.env.example``).
"""

from __future__ import annotations

import asyncio
import functools
import json
import time
from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ingredion_ai.demo import SCENARIOS
from ingredion_ai.framework.agents import AGENT_ORDER, build_framework_agents
from ingredion_ai.framework.runner import build_demo_context, run_reformulation
from ingredion_ai.interop.a2a import build_agent_cards
from ingredion_ai.interop.auth import (
    AuthenticationError,
    AuthorizationError,
    authenticate_and_authorize,
    required_scopes_for,
)
from ingredion_ai.service import reliability
from ingredion_ai.service.pipeline import AgenticPipeline, PipelineRejected
from ingredion_ai.service.ui import INDEX_HTML

SERVICE_NAME = "ingredion-agentic-ai-demo"
SERVICE_VERSION = "0.1.0"

#: Skill invoked by POST /api/agents/{agent}/run (matches interop/auth.py).
AGENT_SKILL: Dict[str, str] = {
    "rd_formulation": "reformulate",
    "supply_chain": "forecast-demand",
    "esg": "esg-report",
    "customer_advisor": "estimate-pricing",
}

#: Prefix of the RuntimeError raised when live-mode env config is missing.
_LIVE_CONFIG_PREFIX = "Live mode needs Azure OpenAI configuration"

app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ReformulateRequest(BaseModel):
    """Run the full reformulation workflow.

    Either ``scenario`` (one of GET /api/scenarios) or explicit
    ``formula_id``/``target_claims``/``region``. Explicit fields override
    the scenario's when both are given.
    """

    scenario: Optional[str] = Field(default=None, description="Scenario id, e.g. sweet_bakery_cake")
    formula_id: Optional[str] = None
    target_claims: Optional[List[str]] = None
    region: str = "NA"
    live: bool = Field(default=False, description="Use Azure OpenAI (needs .env)")


class AgentRunRequest(BaseModel):
    """Run a single domain agent (R&D pre-phase runs first when needed)."""

    message: str = Field(default="Run your demo task.", description="Prompt for the agent")
    formula_id: str = "sweet_bakery_cake"
    target_claims: Optional[List[str]] = None
    region: str = "NA"
    live: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def to_jsonable(obj: Any) -> Any:
    """Convert blackboard dicts to JSON-safe structures."""
    return json.loads(json.dumps(obj, default=str))


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def require_scopes(scopes: List[str]):
    """FastAPI dependency: verify bearer token + enforce *scopes*."""

    def _dep(authorization: Optional[str] = Header(default=None)):
        token = _bearer_token(authorization)
        try:
            return authenticate_and_authorize(token, scopes)
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=401,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return _dep


def protected(scopes: List[str]):
    """FastAPI dependency: bearer auth + scope check + per-client rate limit.

    Returns the verified ``CallerIdentity``. Rate-limit breaches → 429.
    """

    auth_dep = require_scopes(scopes)

    def _dep(identity=Depends(auth_dep)):
        try:
            reliability.rate_limiter.check(identity.subject)
        except reliability.RateLimitExceeded as exc:
            raise HTTPException(
                status_code=429,
                detail=str(exc),
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc
        return identity

    return _dep


def _idempotency_key(request: Request) -> Optional[str]:
    return request.headers.get("idempotency-key")


def _idempotent_replay(request: Request, subject: str) -> Optional[JSONResponse]:
    """Return the stored response if this idempotency key was already used."""
    stored = reliability.idempotency_store.get(subject, _idempotency_key(request))
    if stored is None:
        return None
    status, body = stored
    return JSONResponse(body, status_code=status, headers={"X-Idempotent-Replay": "true"})


def _remember_idempotent(request: Request, subject: str, status: int, body: Dict[str, Any]) -> None:
    reliability.idempotency_store.put(subject, _idempotency_key(request), status, body)


class _LiveConfigError(Exception):
    """Live mode was requested but Azure OpenAI env config is missing."""


def _live_guarded_call(run_fn: Callable[..., Any], *args: Any) -> Any:
    """Run *run_fn*; convert missing-config RuntimeErrors to _LiveConfigError."""
    try:
        return run_fn(*args)
    except RuntimeError as exc:
        if str(exc).startswith(_LIVE_CONFIG_PREFIX):
            raise _LiveConfigError(str(exc)) from exc
        raise


async def _run_resilient(
    run_fn: Callable[..., Any], *args: Any, live: bool = False
) -> tuple:
    """Run ``run_fn(*args, live=...)`` with the reliability policy.

    Returns ``(result, degraded: bool, degraded_reason: Optional[str])``.

    - ``live=False``: straight offline run with a request timeout.
    - ``live=True``: retry (backoff + jitter) + circuit breaker around the
      live call; a missing-config error → ``_LiveConfigError`` (the caller
      turns it into 503); any other live failure → graceful fallback to the
      offline fake client (``degraded=True``).
    """
    timeout = reliability.SERVICE_REQUEST_TIMEOUT_S
    if not live:
        result = await asyncio.wait_for(
            asyncio.to_thread(run_fn, *args, False), timeout=timeout
        )
        return result, False, None

    def _attempt() -> Any:
        return reliability.live_llm_breaker.call(
            lambda: reliability.retry_sync(
                lambda: _live_guarded_call(run_fn, *args, True),
                max_retries=reliability.SERVICE_RETRY_MAX,
                jitter=True,
            )
        )

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_attempt), timeout=timeout)
        return result, False, None
    except _LiveConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 - graceful degradation on live failure
        reason = f"{type(exc).__name__}: {exc}"
        degraded_result = await asyncio.to_thread(run_fn, *args, False)
        return degraded_result, True, reason


def _resolve_context(req: ReformulateRequest) -> Dict[str, Any]:
    """Build the workflow context from a reformulate request."""
    if req.scenario is not None:
        if req.scenario not in SCENARIOS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown scenario {req.scenario!r}; "
                f"valid: {sorted(SCENARIOS)}",
            )
        base = dict(SCENARIOS[req.scenario])
        formula_id = req.formula_id or base["formula_id"]
        target_claims = req.target_claims or base["target_claims"]
        region = req.region or base["region"]
        adjustments, additions = base["adjustments"], base["additions"]
    else:
        formula_id = req.formula_id or "sweet_bakery_cake"
        target_claims = req.target_claims or ["no artificial ingredients"]
        region = req.region
        adjustments, additions = {}, {}
    return build_demo_context(formula_id, target_claims, region, adjustments, additions)


def _run_workflow_sync(ctx: Dict[str, Any], live: bool) -> Dict[str, Any]:
    """Run the async workflow to completion in its own event loop.

    Executed inside ``asyncio.to_thread`` so the service's event loop is
    never blocked and the framework's async machinery gets a clean loop.
    """
    return asyncio.run(run_reformulation(ctx, live=live))


def _single_agent_sync(
    agent_name: str, message: str, ctx: Dict[str, Any], live: bool
) -> Dict[str, Any]:
    """Run one domain agent synchronously (R&D pre-phase first for supporters)."""

    async def _go():
        agents = build_framework_agents(ctx, live=live)
        if agent_name != "rd_formulation":
            # Supporters read R&D blackboard keys; populate them first.
            await agents["rd_formulation"].run("Run the R&D reformulation tool phase.")
        response = await agents[agent_name].run(message)
        return {"summary": response.text, "blackboard": to_jsonable(ctx["blackboard"])}

    return asyncio.run(_go())


# ---------------------------------------------------------------------------
# Public endpoints (discovery / probes)
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index() -> str:
    """Demo web UI (single page)."""
    return INDEX_HTML


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    """Liveness/readiness probe (public)."""
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.get("/api/scenarios")
async def scenarios() -> Dict[str, Any]:
    """Available demo scenarios (public)."""
    return {
        "scenarios": [
            {
                "id": sid,
                "formula_id": spec["formula_id"],
                "target_claims": spec["target_claims"],
                "region": spec["region"],
            }
            for sid, spec in sorted(SCENARIOS.items())
        ]
    }


@app.get("/api/agent-cards")
async def agent_cards() -> Dict[str, Any]:
    """The four A2A agent cards (public discovery)."""
    cards = build_agent_cards()
    return {name: card.to_dict() for name, card in cards.items()}


@app.get("/.well-known/agent.json", include_in_schema=False)
async def well_known_agent() -> Dict[str, Any]:
    """A2A discovery document (public)."""
    cards = build_agent_cards()
    return {"agents": [card.to_dict() for card in cards.values()]}


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------


@app.post("/api/reformulate")
async def reformulate(
    req: ReformulateRequest,
    request: Request,
    identity=Depends(protected(["formulation:write"])),
) -> JSONResponse:
    """Run the full 4-agent reformulation workflow (offline by default).

    Request flows through the 8-stage agentic pipeline
    (:mod:`ingredion_ai.service.pipeline`). Supports ``Idempotency-Key``.
    Live failures degrade gracefully to the offline fake client
    (``degraded: true`` + ``X-Service-Degraded``).
    """
    replay = _idempotent_replay(request, identity.subject)
    if replay is not None:
        return replay
    ctx = _resolve_context(req)  # validates scenario (400 on unknown)
    started = time.perf_counter()

    async def _executor(pctx):
        try:
            blackboard, degraded, reason = await _run_resilient(
                _run_workflow_sync, ctx, live=req.live
            )
        except _LiveConfigError as exc:
            # Live requested but Azure OpenAI env config missing: fail, don't degrade.
            raise PipelineRejected(503, str(exc)) from exc
        result = {
            "blackboard": to_jsonable(blackboard),
            "scenario": req.scenario,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
        return result, degraded, reason

    pipeline = AgenticPipeline()
    try:
        body = await pipeline.run(
            kind="reformulate",
            identity_subject=identity.subject,
            session_id=request.headers.get("x-session-id"),
            params={
                "scenario": req.scenario,
                "formula_id": ctx["formula_id"],
                "target_claims": ctx["target_claims"],
                "region": ctx["region"],
            },
            text_fields={
                "scenario": req.scenario or "",
                "formula_id": req.formula_id or "",
                "region": req.region,
            },
            live=req.live,
            agent_name=None,
            executor=_executor,
        )
    except PipelineRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    headers = {"X-Session-Id": body["session_id"]}
    if body.get("degraded"):
        headers["X-Service-Degraded"] = "true"
    _remember_idempotent(request, identity.subject, 200, body)
    return JSONResponse(body, headers=headers)


def _register_agent_routes() -> None:
    """Register POST /api/agents/{agent}/run — one route per agent so each
    carries its own skill scopes (declared on its A2A agent card)."""
    for name in AGENT_ORDER:
        skill = AGENT_SKILL[name]
        scopes = required_scopes_for(name, skill)

        async def _run(
            req: AgentRunRequest,
            request: Request,
            identity=Depends(protected(scopes)),
            _agent_name: str = name,
        ) -> JSONResponse:
            replay = _idempotent_replay(request, identity.subject)
            if replay is not None:
                return replay
            ctx = build_demo_context(
                req.formula_id,
                req.target_claims or ["no artificial ingredients"],
                req.region,
            )
            run_fn = functools.partial(_single_agent_sync, _agent_name, req.message)
            started = time.perf_counter()

            async def _executor(pctx):
                try:
                    result, degraded, reason = await _run_resilient(
                        run_fn, ctx, live=req.live
                    )
                except _LiveConfigError as exc:
                    raise PipelineRejected(503, str(exc)) from exc
                result["agent"] = _agent_name
                result["skill"] = AGENT_SKILL[_agent_name]
                result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
                return result, degraded, reason

            pipeline = AgenticPipeline()
            try:
                body = await pipeline.run(
                    kind="agent_run",
                    identity_subject=identity.subject,
                    session_id=request.headers.get("x-session-id"),
                    params={
                        "formula_id": req.formula_id,
                        "target_claims": req.target_claims,
                        "region": req.region,
                    },
                    text_fields={"message": req.message, "formula_id": req.formula_id},
                    live=req.live,
                    agent_name=_agent_name,
                    executor=_executor,
                )
            except PipelineRejected as exc:
                raise HTTPException(
                    status_code=exc.status_code, detail=exc.detail
                ) from exc
            headers = {"X-Session-Id": body["session_id"]}
            if body.get("degraded"):
                headers["X-Service-Degraded"] = "true"
            _remember_idempotent(request, identity.subject, 200, body)
            return JSONResponse(body, headers=headers)

        app.post(f"/api/agents/{name}/run", name=f"run_{name}")(_run)
        _run.__name__ = f"run_{name}_endpoint"  # unique OpenAPI operation ids


_register_agent_routes()
