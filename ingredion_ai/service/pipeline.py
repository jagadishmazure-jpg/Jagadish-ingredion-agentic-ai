"""The 8-step agentic loop as an explicit service pipeline.

Mirrors the Microsoft Azure Agentic AI Stack reference loop:

1. **Request Intake** — normalize/auth/validate (auth + rate limiting live
   in the FastAPI dependencies; intake normalizes here).
2. **Intent Understanding + Guardrails** — classify intent; input
   guardrails via :mod:`ingredion_ai.governance.security` (prompt-injection
   patterns fail closed with 400).
3. **Memory/State read** — load session state from the
   :mod:`ingredion_ai.service.memory` store.
4. **Retrieve + Ground (RAG)** — retrieve grounding chunks from the
   project knowledge base (:mod:`ingredion_ai.rag`); attached as citations.
5. **Tool Selection & Execution** — run the agent workflow/tools through
   the resilient runner (retry + breaker + graceful fallback).
6. **Generate Response (+ output guardrails)** — assemble the response;
   output guardrails scrub PII-shaped strings.
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
from ingredion_ai.governance.security import sanitize_input, scrub_pii
from ingredion_ai.observability.logging import get_json_logger
from ingredion_ai.rag.retrieval import Retriever
from ingredion_ai.service.memory import SessionStore, session_store as default_store

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
        """Classify intent; fail closed on prompt-injection patterns."""
        req = ctx.request
        if req.kind == "reformulate":
            target = req.params.get("scenario") or req.params.get("formula_id", "?")
            ctx.intent = f"reformulation:{target}"
        else:
            ctx.intent = f"agent:{req.agent_name}"
        flags: List[str] = []
        for field_name, text in req.text_fields.items():
            _, found = sanitize_input(text or "")
            flags.extend(f"{field_name}:{f}" for f in found)
        ctx.guardrail_flags = flags
        if flags:
            raise PipelineRejected(
                400,
                "input rejected by guardrails: " + "; ".join(sorted(set(flags))),
            )

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
        # Output guardrails: scrub PII-shaped strings from the whole payload.
        ctx.response_body = json.loads(scrub_pii(json.dumps(body, default=str)))

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

    # -- stage 8: feedback -------------------------------------------------------

    async def stage_feedback(self, ctx: PipelineContext) -> None:
        """Structured log line per request (eval/log feedback loop)."""
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
