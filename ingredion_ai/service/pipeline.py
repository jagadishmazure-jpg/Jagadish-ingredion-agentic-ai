"""The 8-step agentic loop as an explicit service pipeline.

Mirrors the Microsoft Azure Agentic AI Stack reference loop:

1. **Request Intake** — normalize/auth/validate (auth + rate limiting live
   in the FastAPI dependencies; intake normalizes here).
2. **Intent Understanding + Guardrails** — classify intent; input
   guardrails via :mod:`ingredion_ai.guardrails` (prompt-injection,
   jailbreak, PII, domain-scope, and length checks; fail closed with 400).
3. **Memory/State read** — load session state from the
   :mod:`ingredion_ai.service.memory` store.
4. **Retrieve + Ground (RAG)** — retrieve grounding chunks from the
   project knowledge base (:mod:`ingredion_ai.rag`); attached as citations.
5. **Tool Selection & Execution** — run the agent workflow/tools through
   the resilient runner (retry + breaker + graceful fallback).
6. **Generate Response (+ output guardrails)** — assemble the response;
   output guardrails (:mod:`ingredion_ai.guardrails`) scrub PII, check
   claim grounding against RAG citations, and enforce confidence
   thresholds.
7. **Memory/State write** — persist session state (turn count, last intent,
   result keys).
8. **Feedback Loop (eval/log)** — structured JSON log line per request
   with stage latencies, outcome, and degradation flag.

All data is synthetic demo data. Stdlib + project modules only.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ingredion_ai.governance.audit import AuditTrail
from ingredion_ai.guardrails import check_input, check_output, load_policy
from ingredion_ai.observability.logging import get_json_logger
from ingredion_ai.rag.retrieval import Retriever
from ingredion_ai.service.memory import SessionStore, session_store as default_store

# Lifecycle events (Azure Event Grid in production; in-memory offline).
# Imported lazily inside methods to keep this module importable even if the
# integration package is absent, and so publisher swaps stay one-liners.

logger = get_json_logger("ingredion_ai.service.pipeline")

#: (stage_key, human label) in execution order.
STAGES: List[tuple] = [
    ("intake", "1. Request Intake"),
    ("intent_guardrails", "2. Intent Understanding + Guardrails"),
    ("memory_read", "3. Memory/State read"),
    ("retrieve_ground", "4. Retrieve + Ground (RAG)"),
    ("tool_execution", "5. Tool Selection & Execution"),
    ("generate_response", "6. Generate Response (+ output guardrails)"),
    ("memory_write", "7. Memory/State write"),
    ("feedback", "8. Feedback Loop (eval/log)"),
]


class PipelineRejected(Exception):
    """A pipeline stage rejected the request (maps to an HTTP error)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class PipelineRequest:
    """Normalized request entering the pipeline (stage 1 output)."""

    kind: str  # "reformulate" | "agent_run"
    agent_name: Optional[str]
    params: Dict[str, Any]
    text_fields: Dict[str, str]  # user-supplied strings to guardrail-check
    live: bool


@dataclass
class PipelineContext:
    """Mutable state threaded through the 8 stages."""

    request: PipelineRequest
    identity_subject: str
    session_id: str
    intent: str = ""
    guardrail_flags: List[str] = field(default_factory=list)
    session_state: Dict[str, Any] = field(default_factory=dict)
    grounding: List[Dict[str, Any]] = field(default_factory=list)
    result: Any = None
    degraded: bool = False
    degraded_reason: Optional[str] = None
    stage_latencies_ms: Dict[str, int] = field(default_factory=dict)
    response_body: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Grounding knowledge base (lazy singleton)
# ---------------------------------------------------------------------------

_grounding_retriever: Optional[Retriever] = None


def get_grounding_retriever() -> Retriever:
    """Retriever over the project glossary (offline, deterministic).

    Production path: swap the in-memory store for Azure AI Search and the
    hash embedder for Azure OpenAI embeddings (see ``rag/retrieval.py``).
    """
    global _grounding_retriever
    if _grounding_retriever is None:
        retriever = Retriever()
        docs_dir = Path(__file__).resolve().parent.parent.parent / "docs"
        documents = []
        for name in ("glossary.md", "usecases.md"):
            path = docs_dir / name
            if path.exists():
                documents.append(
                    {
                        "id": path.stem,
                        "title": path.stem.replace("_", " ").title(),
                        "text": path.read_text(encoding="utf-8"),
                        "source": f"docs/{name}",
                    }
                )
        if documents:
            retriever.index(documents)
        _grounding_retriever = retriever
    return _grounding_retriever


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

#: Async executor: ``(ctx) -> (result, degraded, degraded_reason)``.
Executor = Callable[[PipelineContext], Awaitable[tuple]]


class AgenticPipeline:
    """The 8-step agentic loop as named, testable stages."""

    def __init__(
        self,
        *,
        store: Optional[SessionStore] = None,
        retriever: Optional[Retriever] = None,
        audit_log_path: Optional[str] = None,
    ) -> None:
        self.store = store or default_store
        self.retriever = retriever  # None -> lazy grounding singleton
        self.audit_log_path = audit_log_path or os.environ.get("SERVICE_AUDIT_LOG")

    # -- orchestrator --------------------------------------------------------

    async def run(
        self,
        *,
        kind: str,
        identity_subject: str,
        session_id: Optional[str],
        params: Dict[str, Any],
        text_fields: Dict[str, str],
        live: bool,
        agent_name: Optional[str],
        executor: Executor,
    ) -> Dict[str, Any]:
        """Execute all 8 stages; return the response body."""
        ctx = PipelineContext(
            request=PipelineRequest(
                kind=kind,
                agent_name=agent_name,
                params=params,
                text_fields=text_fields,
                live=live,
            ),
            identity_subject=identity_subject,
            session_id=session_id or f"ses-{uuid.uuid4().hex[:12]}",
        )
        self._executor = executor
        self._emit_lifecycle("run.started", ctx)
        for key, _label in STAGES:
            start = time.perf_counter()
            await getattr(self, f"stage_{key}")(ctx)
            ctx.stage_latencies_ms[key] = int((time.perf_counter() - start) * 1000)
        # stages_ms was snapshotted mid-run in stage 6; finalize it here.
        ctx.response_body["stages_ms"] = dict(ctx.stage_latencies_ms)
        return ctx.response_body

    # -- stage 1: intake -----------------------------------------------------

    async def stage_intake(self, ctx: PipelineContext) -> None:
        """Normalize the request (auth/rate-limit already enforced upstream)."""
        # Canonicalize params: drop Nones, keep everything else as-is.
        ctx.request.params = {
            k: v for k, v in ctx.request.params.items() if v is not None
        }

    # -- stage 2: intent + input guardrails ----------------------------------

    async def stage_intent_guardrails(self, ctx: PipelineContext) -> None:
        """Classify intent; fail closed on guardrail violations."""
        req = ctx.request
        if req.kind == "reformulate":
            target = req.params.get("scenario") or req.params.get("formula_id", "?")
            ctx.intent = f"reformulation:{target}"
        else:
            ctx.intent = f"agent:{req.agent_name}"
        # Domain-scope enforcement applies to reformulate requests (checked
        # once over the combined inputs: identifiers alone like
        # "cola_soft_drink" carry little signal, but the request as a whole
        # must read as food-manufacturing). agent_run messages address an
        # already domain-scoped agent (its instructions are the scope), so
        # only injection/PII/length checks apply there.
        policy = load_policy(req.agent_name)
        flags: List[str] = []
        for field_name, text in req.text_fields.items():
            verdict = check_input(
                text or "", policy=policy, field_name=field_name,
                check_domain=False,
            )
            flags.extend(verdict.flags)
            if not verdict.allowed:
                ctx.guardrail_flags = sorted(set(flags))
                raise PipelineRejected(
                    400, verdict.refusal or "input rejected by guardrails",
                )
        if req.kind == "reformulate":
            combined = " ".join(str(v or "") for v in req.text_fields.values())
            domain_verdict = check_input(
                combined, policy=policy, field_name="request", check_domain=True,
            )
            flags.extend(domain_verdict.flags)
            if not domain_verdict.allowed:
                ctx.guardrail_flags = sorted(set(flags))
                raise PipelineRejected(
                    400, domain_verdict.refusal or "input rejected by guardrails",
                )
        ctx.guardrail_flags = sorted(set(flags))

    # -- stage 3: memory read -------------------------------------------------

    async def stage_memory_read(self, ctx: PipelineContext) -> None:
        ctx.session_state = self.store.get(ctx.session_id)

    # -- stage 4: retrieve + ground -------------------------------------------

    async def stage_retrieve_ground(self, ctx: PipelineContext) -> None:
        retriever = self.retriever or get_grounding_retriever()
        query = " ".join(
            [
                ctx.intent,
                str(ctx.request.params.get("formula_id", "")),
                " ".join(ctx.request.params.get("target_claims", []) or []),
                "clean label reformulation",
            ]
        ).strip()
        hits = retriever.retrieve(query, top_k=3)
        ctx.grounding = [
            {
                "source": h["document"]["source"],
                "title": h["document"]["title"],
                "score": round(float(h["score"]), 4),
                "excerpt": h["document"]["text"][:280],
            }
            for h in hits
        ]

    # -- stage 5: tool selection & execution -----------------------------------

    async def stage_tool_execution(self, ctx: PipelineContext) -> None:
        result, degraded, reason = await self._executor(ctx)
        ctx.result = result
        ctx.degraded = degraded
        ctx.degraded_reason = reason

    # -- stage 6: generate response (+ output guardrails) ----------------------

    async def stage_generate_response(self, ctx: PipelineContext) -> None:
        body: Dict[str, Any] = {
            "intent": ctx.intent,
            "session_id": ctx.session_id,
            "mode": "offline" if (ctx.degraded or not ctx.request.live) else "live",
            "degraded": ctx.degraded,
            "grounding": ctx.grounding,
            "stages_ms": ctx.stage_latencies_ms,
        }
        if ctx.degraded:
            body["degraded_reason"] = ctx.degraded_reason
        if isinstance(ctx.result, dict):
            body.update(ctx.result)
        else:
            body["result"] = ctx.result
        # Output guardrails: PII scrubbing, prompt-leak scan, claim
        # grounding against the RAG citations, confidence thresholds.
        out_verdict = check_output(
            json.dumps(body, default=str),
            citations=[g["excerpt"] for g in ctx.grounding],
            policy=load_policy(ctx.request.agent_name),
        )
        ctx.response_body = json.loads(out_verdict.text)
        if out_verdict.flags:
            ctx.response_body["output_guardrail_flags"] = sorted(
                set(out_verdict.flags)
            )

    # -- stage 7: memory write --------------------------------------------------

    async def stage_memory_write(self, ctx: PipelineContext) -> None:
        state = dict(ctx.session_state)
        state["turns"] = int(state.get("turns", 0)) + 1
        state["last_intent"] = ctx.intent
        result_keys = (
            list(ctx.result.keys()) if isinstance(ctx.result, dict) else []
        )
        state["last_result_keys"] = result_keys
        self.store.set(ctx.session_id, state)

    # -- lifecycle events (best-effort; never break the pipeline) ------------

    @staticmethod
    def _emit_lifecycle(kind: str, ctx: "PipelineContext") -> None:
        try:
            from ingredion_ai.azure_integration import events as lifecycle

            event_type = {
                "run.started": lifecycle.RUN_STARTED,
                "run.completed": lifecycle.RUN_COMPLETED,
            }[kind]
            lifecycle.emit_lifecycle_event(
                event_type,
                subject=f"pipeline/{ctx.session_id}",
                data={
                    "kind": ctx.request.kind,
                    "agent": ctx.request.agent_name,
                    "subject": ctx.identity_subject,
                    "session_id": ctx.session_id,
                    "live": ctx.request.live,
                    "degraded": ctx.degraded,
                },
            )
        except Exception:  # noqa: BLE001 - lifecycle events are best-effort
            pass

    # -- stage 8: feedback -------------------------------------------------------

    async def stage_feedback(self, ctx: PipelineContext) -> None:
        """Structured log line per request (eval/log feedback loop)."""
        self._emit_lifecycle("run.completed", ctx)
        logger.info(
            "pipeline_run",
            extra={
                "intent": ctx.intent,
                "subject": ctx.identity_subject,
                "session_id": ctx.session_id,
                "live": ctx.request.live,
                "degraded": ctx.degraded,
                "guardrail_flags": ctx.guardrail_flags,
                "stages_ms": ctx.stage_latencies_ms,
            },
        )
        if self.audit_log_path:
            trail = AuditTrail(self.audit_log_path)
            trail.log(
                actor=f"svc:{ctx.identity_subject}",
                action=f"pipeline:{ctx.request.kind}",
                payload={
                    "intent": ctx.intent,
                    "session_id": ctx.session_id,
                    "degraded": ctx.degraded,
                    "stages_ms": ctx.stage_latencies_ms,
                },
                decision="completed",
            )
            trail.close()


__all__ = [
    "STAGES",
    "AgenticPipeline",
    "PipelineContext",
    "PipelineRejected",
    "PipelineRequest",
    "get_grounding_retriever",
]
