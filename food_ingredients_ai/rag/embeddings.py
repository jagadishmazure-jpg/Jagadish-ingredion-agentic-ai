"""Embeddings: deterministic offline hash embeddings + the live Azure swap.

:mod:`HashEmbedding` is the default: a purely synthetic, deterministic
embedding for offline demos and tests. No model weights, no network.

:mod:`AzureOpenAIEmbedding` is the **live swap** — it reads the Azure
OpenAI endpoint from the environment and raises a clear error when
unavailable. This codebase deliberately makes no network calls; see
the class docstring for the live-mode wiring point.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import List

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())


def _ngrams(tokens: List[str]) -> List[str]:
    """Unigrams plus word bigrams (better phrase matching)."""
    grams = list(tokens)
    grams.extend(f"{a} {b}" for a, b in zip(tokens, tokens[1:]))
    return grams


class HashEmbedding:
    """Deterministic hash-based synthetic embeddings (offline, stdlib-only).

    Each token n-gram is hashed with SHA-256 and mapped into one of
    ``dim`` buckets; bucket counts are L2-normalized. The same input
    text always produces the identical vector, and no network or model
    weights are required.

    This is a demo/test convenience, not a semantic embedding — related
    texts only score well when they share tokens. In production, swap
    in :class:`AzureOpenAIEmbedding`.
    """

    def __init__(self, dim: int = 64) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim

    def embed(self, text: str) -> List[float]:
        """Return the L2-normalized embedding vector for *text*."""
        vector = [0.0] * self.dim
        for gram in _ngrams(_tokenize(text)):
            digest = hashlib.sha256(gram.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:8], "big") % self.dim
            vector[bucket] += 1.0
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0.0:
            return vector  # empty/tokenless text -> zero vector
        return [x / norm for x in vector]

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts."""
        return [self.embed(t) for t in texts]


class AzureOpenAIEmbedding:
    """Azure OpenAI embeddings for live mode (no network calls here).

    Reads ``AZURE_OPENAI_ENDPOINT`` (and optionally
    ``AZURE_OPENAI_API_KEY``) from the environment. Intended as the
    production/live swap for :class:`HashEmbedding`.

    Live wiring point: replace :meth:`embed` with an
    ``openai.AzureOpenAI`` client call to
    ``client.embeddings.create(model=<deployment>, input=text)`` using
    ``self.endpoint`` / ``self.api_key``. Until that wiring exists,
    :meth:`embed` raises a clear error so offline runs never attempt
    hidden network calls.
    """

    def __init__(self, deployment: str = "text-embedding-3-small") -> None:
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
        if not endpoint:
            raise EnvironmentError(
                "AzureOpenAIEmbedding requires the AZURE_OPENAI_ENDPOINT "
                "environment variable, which is not set. This demo runs "
                "offline; set the endpoint (and AZURE_OPENAI_API_KEY) to "
                "enable live Azure OpenAI embeddings."
            )
        self.endpoint = endpoint
        self.api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        self.deployment = deployment

    def embed(self, text: str) -> List[float]:  # noqa: ARG002 - demo stub
        """Not implemented: network calls are disabled in this codebase."""
        raise RuntimeError(
            "AzureOpenAIEmbedding.embed() would call the Azure OpenAI "
            f"embeddings API at {self.endpoint} (deployment "
            f"'{self.deployment}'), but network calls are disabled in this "
            "offline demo codebase. Wire an openai.AzureOpenAI client here "
            "to enable live mode."
        )

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        return [self.embed(t) for t in texts]
