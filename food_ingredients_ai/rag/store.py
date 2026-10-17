"""In-memory vector store with cosine similarity search.

Production swap: `Azure AI Search <https://learn.microsoft.com/azure/search/>`_.
Replace :class:`InMemoryVectorStore` with a thin client over an Azure AI
Search index — the interface is intentionally small (``add`` /
``search``) so the swap is mechanical:

- ``add(documents, vectors)`` -> ``search_client.upload_documents(...)``
  with the vector stored in an ``Edm.Collection(Edm.Single)`` field.
- ``search(query_vector, top_k)`` -> a vector query against the index's
  vector field, returning ``(document, score)`` pairs.

All documents indexed here are **synthetic demo data**.
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

Document = Dict[str, str]  # {"id", "title", "text", "source"}


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryVectorStore:
    """Minimal cosine-similarity vector store for offline demos/tests.

    Documents and their precomputed vectors are kept in parallel lists.
    ``add`` appends; ``search`` ranks everything by cosine similarity.
    Suitable for small demo corpora; production uses Azure AI Search
    (see module docstring).
    """

    def __init__(self) -> None:
        self.documents: List[Document] = []
        self.vectors: List[List[float]] = []

    def add(self, documents: List[Document], vectors: List[List[float]]) -> None:
        """Append *documents* with their embedding *vectors*.

        Raises:
            ValueError: If the two lists differ in length.
        """
        if len(documents) != len(vectors):
            raise ValueError(
                f"documents ({len(documents)}) and vectors "
                f"({len(vectors)}) must have the same length"
            )
        self.documents.extend(documents)
        self.vectors.extend([list(v) for v in vectors])

    def __len__(self) -> int:
        return len(self.documents)

    def search(
        self, query_vector: Sequence[float], top_k: int = 3
    ) -> List[Tuple[Document, float]]:
        """Return ``[(document, cosine_score), ...]`` ranked by score.

        Scores are sorted descending; at most ``top_k`` results are
        returned (fewer if the store holds fewer documents).
        """
        if top_k <= 0:
            return []
        scored = [
            (doc, _cosine(query_vector, vec))
            for doc, vec in zip(self.documents, self.vectors)
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
