"""Agent-facing RAG tool: ``rag_lookup(query, top_k=3)``.

Returns a JSON string of the top matching document chunks from the
project's markdown docs (``docs/*.md``, plus ``docs/glossary.md`` if it
exists). The index is built lazily on first call and reused afterwards.

AGENT WIRING (documented, not applied yet)
------------------------------------------
``rag_lookup`` is designed to be registered as an extra tool on the R&D
formulation agent (``food_ingredients_ai.agents.rd_formulation.RDFormulationAgent``)
and the customer advisor agent
(``food_ingredients_ai.agents.customer_advisor``), e.g.::

    from food_ingredients_ai.core.tools import Tool
    from food_ingredients_ai.rag.tools import register_rag_tools

    class RDFormulationAgent(Agent):
        def __init__(self, llm=None):
            super().__init__(llm)
            ...
            register_rag_tools(self.tools)  # adds the "rag_lookup" tool

It is intentionally NOT wired into the agent classes yet: existing tests
(``tests/test_framework.py::test_build_framework_agents_has_four_domains_with_tools``)
assert the exact tool-name lists per agent, and adding the tool would
require updating those tests — which is out of scope for this change.
``register_rag_tools()`` below provides the wiring helper for when the
tests are ready to be extended.

All indexed content is **synthetic demo data**.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, List, Optional

from food_ingredients_ai.rag.ingest import default_corpus_paths, ingest_docs

if TYPE_CHECKING:  # pragma: no cover
    from food_ingredients_ai.rag.retrieval import Retriever

_default_retriever: Optional["Retriever"] = None


def _get_default_retriever() -> "Retriever":
    """Build (lazily, once) the shared retriever over the docs corpus."""
    global _default_retriever
    if _default_retriever is None:
        from food_ingredients_ai.rag.embeddings import HashEmbedding
        from food_ingredients_ai.rag.retrieval import Retriever

        retriever = Retriever(embedder=HashEmbedding())
        documents = ingest_docs(default_corpus_paths())
        if documents:
            retriever.index(documents)
        _default_retriever = retriever
    return _default_retriever


def rag_lookup(query: str, top_k: int = 3) -> str:
    """Look up *query* in the project docs; return hits as a JSON string.

    The JSON is a list of objects with keys ``id``, ``title``,
    ``source``, ``score`` and ``text`` (the chunk text). Deterministic
    and fully offline — safe to register as an agent tool.
    """
    hits = _get_default_retriever().retrieve(query, top_k=top_k)
    payload: List[Any] = []
    for hit in hits:
        doc = hit["document"]
        payload.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "source": doc["source"],
                "score": round(float(hit["score"]), 4),
                "text": doc["text"],
            }
        )
    return json.dumps(payload, indent=2)


def register_rag_tools(tools: Any) -> None:
    """Register ``rag_lookup`` on an agent's tool registry.

    Args:
        tools: The agent's tool registry (anything with a ``register``
            method compatible with
            :class:`food_ingredients_ai.core.tools.Tool` instances).

    Adds a single tool named ``"rag_lookup"`` with signature
    ``{"query": "natural-language question", "top_k": "max chunks (default 3)"}``.
    """
    from food_ingredients_ai.core.tools import Tool

    tools.register(
        Tool(
            "rag_lookup",
            "Retrieve relevant passages from the project's documentation",
            rag_lookup,
            {"query": "natural-language question", "top_k": "max chunks (default 3)"},
        )
    )
