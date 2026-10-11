"""Chat clients: live LLM (direct OpenAI or Azure OpenAI) and a scripted fake.

The fake implements the Microsoft Agent Framework 1.0 chat-client
interface (``BaseChatClient._inner_get_response``) so framework ``Agent``
runs work identically offline — no network, fully deterministic.

Live mode (``build_chat_client(live=True)``) prefers **direct OpenAI**
(``OPENAI_API_KEY``) and falls back to **Azure OpenAI** when that is not
set. See ``docs/real-llm.md`` for the go-live guide.
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

from agent_framework import (
    BaseChatClient,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
)

# Environment variables for the direct-OpenAI live path.
OPENAI_API_KEY_VAR = "OPENAI_API_KEY"
OPENAI_MODEL_VAR = "OPENAI_MODEL"
DEFAULT_OPENAI_MODEL = "gpt-4o"

# Environment variables for the live Azure OpenAI path.
AZURE_OPENAI_ENDPOINT_VAR = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_DEPLOYMENT_VAR = "AZURE_OPENAI_CHAT_DEPLOYMENT"
AZURE_OPENAI_API_KEY_VAR = "AZURE_OPENAI_API_KEY"
AZURE_OPENAI_API_VERSION_VAR = "AZURE_OPENAI_API_VERSION"
DEFAULT_API_VERSION = "2024-12-01-preview"


def _text_response(text: str) -> ChatResponse:
    return ChatResponse(
        messages=[Message(role="assistant", contents=[Content.from_text(text)])]
    )


def _tool_call_response(call_id: str, name: str, args: Mapping[str, Any]) -> ChatResponse:
    return ChatResponse(
        messages=[
            Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id=call_id, name=name, arguments=dict(args)
                    )
                ],
            )
        ]
    )


class FakeChatClient(FunctionInvocationLayer, BaseChatClient):
    """Deterministic scripted chat client for offline runs and tests.

    ``script`` is an ordered list of steps. Each step is either
    ``("tool", tool_name, args_dict)`` — emitted as a function call — or
    ``("text", text)`` — emitted as the final assistant message. Steps
    advance only when the framework feeds back *this* client's own tool
    results (matched by call id), so shared workflow histories from other
    agents never disturb the script. A script of N tool calls followed by
    a text step reproduces one full deterministic agent turn.
    """

    def __init__(self, script: Sequence[tuple] | None = None) -> None:
        # NOTE: FunctionInvocationLayer must precede BaseChatClient in the
        # MRO so its get_response (the tool-execution loop) is used.
        super().__init__()
        self._script = list(script or [])
        self._step = 0
        self._uid = f"fake-{id(self):x}"
        self._pending_call_id: str | None = None
        self.calls: list[str] = []

    def _own_result_seen(self, messages: Sequence[Message]) -> bool:
        if self._pending_call_id is None:
            return False
        for message in messages:
            for content in message.contents or []:
                if (
                    getattr(content, "type", None) == "function_result"
                    and getattr(content, "call_id", None) == self._pending_call_id
                ):
                    return True
        return False

    async def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        # Record a short fingerprint of the incoming user message for tests.
        for message in messages:
            if message.role == "user":
                for content in message.contents or []:
                    text = getattr(content, "text", "")
                    if text:
                        self.calls.append(str(text)[:120])
                        break
                break
        if self._own_result_seen(messages):
            self._pending_call_id = None
            self._step += 1
        if self._step >= len(self._script):
            return _text_response("Done.")
        step = self._script[self._step]
        if step[0] == "tool":
            _, name, args = step
            call_id = f"{self._uid}-call-{self._step}"
            self._pending_call_id = call_id
            return _tool_call_response(call_id, name, args or {})
        self._step += 1
        return _text_response(step[1])


def build_chat_client(live: bool = False) -> BaseChatClient:
    """Build the chat client for framework agents.

    - ``live=False`` (default): raises — offline runs must use an explicit
      :class:`FakeChatClient` with a script (see
      :mod:`ingredion_ai.framework.demo_script`).
    - ``live=True``: builds the framework's unified ``OpenAIChatClient``.
      Provider selection, in order:

      1. **Direct OpenAI** — when ``OPENAI_API_KEY`` is set. Uses
         ``OPENAI_MODEL`` (default ``"gpt-4o"``). No Azure resources needed;
         this is the simplest way to go live with a personal API key.
      2. **Azure OpenAI** — when the direct key is absent. Uses
         ``AZURE_OPENAI_ENDPOINT`` + ``AZURE_OPENAI_CHAT_DEPLOYMENT`` (both
         required), with ``AZURE_OPENAI_API_KEY`` when set, otherwise
         ``DefaultAzureCredential``.

      See ``docs/real-llm.md`` for the go-live guide and cost warning.
    """
    if not live:
        raise ValueError(
            "build_chat_client(live=False) is not supported; construct a "
            "FakeChatClient with an explicit script for offline runs."
        )
    from agent_framework.openai import OpenAIChatClient

    # 1. Direct OpenAI: a single API key, no Azure footprint.
    openai_api_key = os.environ.get(OPENAI_API_KEY_VAR)
    if openai_api_key:
        return OpenAIChatClient(
            model=os.environ.get(OPENAI_MODEL_VAR, DEFAULT_OPENAI_MODEL),
            api_key=openai_api_key,
        )

    # 2. Azure OpenAI fallback.
    endpoint = os.environ.get(AZURE_OPENAI_ENDPOINT_VAR)
    deployment = os.environ.get(AZURE_OPENAI_DEPLOYMENT_VAR)
    missing = [
        var
        for var, val in (
            (AZURE_OPENAI_ENDPOINT_VAR, endpoint),
            (AZURE_OPENAI_DEPLOYMENT_VAR, deployment),
        )
        if not val
    ]
    if missing:
        raise RuntimeError(
            "Live mode needs an LLM provider; either set OPENAI_API_KEY "
            "(direct OpenAI, simplest) or configure Azure OpenAI — missing: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in the values."
        )
    api_key = os.environ.get(AZURE_OPENAI_API_KEY_VAR)
    api_version = os.environ.get(AZURE_OPENAI_API_VERSION_VAR, DEFAULT_API_VERSION)
    if api_key:
        return OpenAIChatClient(
            model=deployment,
            azure_endpoint=endpoint,
            api_version=api_version,
            api_key=api_key,
        )
    from azure.identity import DefaultAzureCredential

    return OpenAIChatClient(
        model=deployment,
        azure_endpoint=endpoint,
        api_version=api_version,
        credential=DefaultAzureCredential(),
    )
