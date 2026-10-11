"""Retriever: embedder + vector store combined for document retrieval.

Documents are chunked at index time; every chunk becomes a searchable
item whose ``id`` is ``<doc_id>#chunk<i>`` and whose source keeps the
original document path, so answers can cite the originating file.

All indexed content is **synthetic demo data**.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ingredion_ai.rag.embeddings import HashEmbedding
from ingredion_ai.rag.ingest import chunk_text
from ingredion_ai.rag.store import InMemoryVectorStore

Document = Dict[str, str]  # {"id", "title", "text", "source"}
Hit = Dict[str, object]  # {"document": Document, "score": float}


class Retriever:
    """Index documents (chunked) and retrieve the top-k relevant chunks.

    Args:
        embedder: Embedding model; defaults to :class:`HashEmbedding`
            (deterministic, offline). Swap in
            :class:`~ingredion_ai.rag.embeddings.AzureOpenAIEmbedding`
            for live mode.
        store: Vector store; defaults to :class:`InMemoryVectorStore`.
            Swap in an Azure AI Search client for production.
        max_chars: Chunk size passed to :func:`chunk_text`.
        overlap: Chunk overlap passed to :func:`chunk_text`.
    """

    def __init__(
        self,
        embedder: Optional[HashEmbedding] = None,
        store: Optional[InMemoryVectorStore] = None,
        max_chars: int = 500,
        overlap: int = 100,
    ) -> None:
        self.embedder = embedder if embedder is not None else HashEmbedding()
        self.store = store if store is not None else InMemoryVectorStore()
        self.max_chars = max_chars
        self.overlap = overlap

    def index(self, documents: List[Document]) -> int:
        """Chunk and index *documents*; returns the chunk count."""
        chunks: List[Document] = []
        for doc in documents:
            for i, piece in enumerate(
                chunk_text(doc["text"], self.max_chars, self.overlap)
            ):
                chunks.append(
                    {
                        "id": f"{doc['id']}#chunk{i}",
                        "title": doc["title"],
                        "text": piece,
                        "source": doc["source"],
                    }
                )
        if chunks:
            self.store.add(chunks, self.embedder.embed_many([c["text"] for c in chunks]))
        return len(chunks)

    def retrieve(self, query: str, top_k: int = 3) -> List[Hit]:
        """Return the top-k chunks for *query*, ranked by cosine score.

        Each hit is ``{"document": <chunk dict>, "score": <float>}``.
        Empty for an empty store; deterministic for a fixed index.
        """
        query_vector = self.embedder.embed(query)
        return [
            {"document": doc, "score": score}
            for doc, score in self.store.search(query_vector, top_k)
        ]
