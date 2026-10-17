"""Offline retrieval-augmented generation (RAG) utilities.

Deterministic, stdlib-only building blocks used by the demo agents to
retrieve project documentation:

- :mod:`food_ingredients_ai.rag.ingest` — chunking + document ingestion
- :mod:`food_ingredients_ai.rag.embeddings` — synthetic hash embeddings (offline)
  and the Azure OpenAI live-mode swap
- :mod:`food_ingredients_ai.rag.store` — in-memory cosine vector store
- :mod:`food_ingredients_ai.rag.retrieval` — embedder + store combined
- :mod:`food_ingredients_ai.rag.tools` — ``rag_lookup`` agent tool

All data handled here is **synthetic demo data** (fictional docs and
fixtures), never real customer data or real trademarks. No network
calls are made anywhere in this package: the default embedder is a
deterministic hash function, and the Azure classes are documented
live-mode swaps.
"""

from __future__ import annotations

from food_ingredients_ai.rag.embeddings import AzureOpenAIEmbedding, HashEmbedding
from food_ingredients_ai.rag.ingest import chunk_text, ingest_docs
from food_ingredients_ai.rag.retrieval import Retriever
from food_ingredients_ai.rag.store import InMemoryVectorStore
from food_ingredients_ai.rag.tools import rag_lookup, register_rag_tools

__all__ = [
    "AzureOpenAIEmbedding",
    "HashEmbedding",
    "InMemoryVectorStore",
    "Retriever",
    "chunk_text",
    "ingest_docs",
    "rag_lookup",
    "register_rag_tools",
]
