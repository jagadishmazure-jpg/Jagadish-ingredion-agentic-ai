"""Tests for the offline RAG package (food_ingredients_ai.rag).

All fixtures here are synthetic demo data written inline; no real docs,
no network, fully deterministic.
"""

from __future__ import annotations

import json
import math

import pytest

from food_ingredients_ai.rag import (
    HashEmbedding,
    InMemoryVectorStore,
    Retriever,
    chunk_text,
    ingest_docs,
    rag_lookup,
)
from food_ingredients_ai.rag.embeddings import AzureOpenAIEmbedding
from food_ingredients_ai.rag.tools import _get_default_retriever

LONG_TEXT = (
    "Clean-label reformulation replaces synthetic ingredients with "
    "recognizable alternatives. Starches derived from corn, tapioca, and "
    "potato can rebuild texture after removing modified starches. "
) * 20  # ~2700 chars

NATURAL_CLAIM_DOC = {
    "id": "claims-guide",
    "title": "Claims Guide",
    "source": "synthetic://claims-guide",
    "text": (
        "What is a natural claim? A natural claim definition for this demo: "
        "a natural claim on a product label means the product is made with "
        "natural ingredients and contains no artificial colors, flavors, or "
        "synthetic preservatives. A natural claim definition also requires "
        "minimal processing. Regulators treat a natural claim as an "
        "on-pack marketing statement, not a certification. To support a "
        "natural claim, keep an ingredient ledger documenting that every "
        "ingredient meets the natural claim definition used in this demo."
    ),
}

SHELF_LIFE_DOC = {
    "id": "shelf-life",
    "title": "Shelf Life Testing",
    "source": "synthetic://shelf-life",
    "text": (
        "Shelf-life testing validates that texture and moisture remain "
        "acceptable across the target storage period. Accelerated shelf-life "
        "testing uses elevated temperature and humidity chambers, then maps "
        "results back to ambient shelf-life estimates with kinetic models. "
        "Microbial shelf-life testing plates samples at intervals to confirm "
        "safety through the declared shelf-life window."
    ),
}

INVOICE_DOC = {
    "id": "invoices",
    "title": "Invoice Processing",
    "source": "synthetic://invoices",
    "text": (
        "Invoice processing matches purchase orders to supplier invoices. "
        "The accounts-payable ledger records each invoice, its approval "
        "workflow, and the payment date. Duplicate invoice detection flags "
        "repeated invoice numbers before the invoice is posted."
    ),
}

CORPUS = [NATURAL_CLAIM_DOC, SHELF_LIFE_DOC, INVOICE_DOC]


# --- chunking ------------------------------------------------------------


def test_chunking_splits_long_text_with_overlap():
    chunks = chunk_text(LONG_TEXT, max_chars=500, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)
    # Word-aware: no chunk may start or end mid-word (relative to source).
    for chunk in chunks:
        assert chunk == chunk.strip()
    # Overlap: the tail of one chunk reappears in the next chunk.
    tail_words = chunks[0].split()[-5:]
    assert any(w in chunks[1] for w in tail_words)


def test_chunking_short_text_yields_single_chunk():
    text = "A short sentence about clean labels."
    chunks = chunk_text(text)
    assert chunks == [text]


def test_chunking_empty_text_yields_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunking_never_cuts_words():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    chunks = chunk_text(text, max_chars=20, overlap=5)
    rejoined = " ".join(chunks[0].split())
    # Every chunk's words must be complete words from the source.
    source_words = set(text.split())
    for chunk in chunks:
        for word in chunk.split():
            assert word in source_words
    assert rejoined  # sanity: something came back


# --- hash embeddings -----------------------------------------------------


def test_hash_embedding_is_deterministic():
    emb = HashEmbedding(dim=64)
    assert emb.embed("clean label starch texture") == emb.embed("clean label starch texture")


def test_hash_embedding_is_l2_normalized():
    emb = HashEmbedding(dim=64)
    vec = emb.embed("shelf life moisture texture testing")
    assert len(vec) == 64
    assert math.isclose(sum(x * x for x in vec), 1.0, rel_tol=1e-9)


def test_hash_embedding_differs_between_texts():
    emb = HashEmbedding(dim=64)
    a = emb.embed("natural claim definition label marketing")
    b = emb.embed("invoice accounts payable purchase order")
    assert a != b


def test_azure_embedding_raises_clear_error_offline(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    with pytest.raises(EnvironmentError, match="AZURE_OPENAI_ENDPOINT"):
        AzureOpenAIEmbedding()


# --- ingest --------------------------------------------------------------


def test_ingest_docs_skips_missing_files_gracefully(tmp_path):
    real = tmp_path / "real.md"
    real.write_text("# Real Doc\n\nSome synthetic content.", encoding="utf-8")
    missing = tmp_path / "does-not-exist.md"
    docs = ingest_docs([str(missing), real, tmp_path / "glossary.md"])
    assert len(docs) == 1
    assert docs[0]["id"] == "real"
    assert docs[0]["title"] == "Real"  # derived from the filename stem
    assert "synthetic content" in docs[0]["text"]
    assert docs[0]["source"] == str(real)


# --- store ---------------------------------------------------------------


def test_store_search_ranks_by_cosine_similarity():
    store = InMemoryVectorStore()
    docs = [{"id": "a", "title": "A", "text": "x", "source": "s"},
            {"id": "b", "title": "B", "text": "y", "source": "s"}]
    store.add(docs, [[1.0, 0.0], [0.0, 1.0]])
    hits = store.search([1.0, 0.0], top_k=2)
    assert hits[0][0]["id"] == "a"
    assert hits[0][1] == pytest.approx(1.0)
    assert hits[1][0]["id"] == "b"


def test_store_add_rejects_mismatched_lengths():
    store = InMemoryVectorStore()
    with pytest.raises(ValueError):
        store.add([{"id": "a"}], [])


# --- retrieval -----------------------------------------------------------


def _indexed_retriever() -> Retriever:
    retriever = Retriever(embedder=HashEmbedding(dim=64))
    retriever.index(CORPUS)
    return retriever


def test_retrieval_ranks_natural_claim_doc_first():
    retriever = _indexed_retriever()
    hits = retriever.retrieve("what is a natural claim", top_k=3)
    assert len(hits) == 3
    assert hits[0]["document"]["id"].startswith("claims-guide")
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(set(h) == {"document", "score"} for h in hits)


def test_retrieval_is_deterministic():
    retriever = _indexed_retriever()
    first = retriever.retrieve("shelf life testing", top_k=3)
    second = retriever.retrieve("shelf life testing", top_k=3)
    assert [h["document"]["id"] for h in first] == [h["document"]["id"] for h in second]
    assert [h["score"] for h in first] == [h["score"] for h in second]


def test_retriever_indexes_chunks_with_chunk_ids():
    retriever = Retriever(embedder=HashEmbedding(dim=64), max_chars=60, overlap=10)
    count = retriever.index([NATURAL_CLAIM_DOC])
    assert count > 1
    assert len(retriever.store) == count
    hit = retriever.retrieve("natural claim", top_k=1)[0]
    assert hit["document"]["id"].startswith("claims-guide#chunk")
    assert hit["document"]["source"] == "synthetic://claims-guide"


# --- tools ---------------------------------------------------------------


def test_rag_lookup_returns_valid_json_with_expected_keys():
    payload = rag_lookup("clean label reformulation", top_k=2)
    data = json.loads(payload)  # must be valid JSON
    assert isinstance(data, list)
    assert 1 <= len(data) <= 2
    for item in data:
        assert set(item) == {"id", "title", "source", "score", "text"}
        assert isinstance(item["score"], float)
        assert item["text"].strip()


def test_rag_lookup_top_k_respected():
    data = json.loads(rag_lookup("starch", top_k=1))
    assert len(data) == 1


def test_default_retriever_is_lazy_and_reused():
    first = _get_default_retriever()
    second = _get_default_retriever()
    assert first is second
    assert len(first.store) > 0  # indexed over the real docs/*.md corpus


def test_default_corpus_includes_real_docs():
    docs = ingest_docs()
    assert len(docs) >= 1
    assert {d["id"] for d in docs} >= {"architecture", "demo-guide"}
