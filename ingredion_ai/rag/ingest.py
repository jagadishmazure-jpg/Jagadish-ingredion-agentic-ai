"""Document ingestion: word-aware chunking and markdown corpus loading.

All documents processed here are **synthetic demo data** (fictional
project documentation), not real customer data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

PathLike = Union[str, Path]
Document = Dict[str, str]  # {"id", "title", "text", "source"}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"


def default_corpus_paths() -> List[Path]:
    """Return the default demo corpus: every ``docs/*.md`` file.

    ``docs/glossary.md`` is included automatically if it exists (it may
    be written by another contributor); missing files are skipped, never
    treated as errors.
    """
    paths = sorted(DOCS_DIR.glob("*.md"))
    glossary = DOCS_DIR / "glossary.md"
    if glossary.exists() and glossary not in paths:
        paths.append(glossary)
    return paths


def chunk_text(text: str, max_chars: int = 500, overlap: int = 100) -> List[str]:
    """Split *text* into word-aware chunks of at most *max_chars*.

    Chunks never split a word: when the ``max_chars`` window would cut
    mid-word, the chunk boundary is moved back to the previous
    whitespace. Successive chunks overlap by up to *overlap* characters
    of shared content, so context spanning a boundary is retrievable
    from either side.

    Args:
        text: The text to chunk. Empty/whitespace-only text yields ``[]``.
        max_chars: Maximum chunk length in characters (> 0).
        overlap: Desired overlap between consecutive chunks, in
            characters. Clamped to be non-negative and smaller than a
            full chunk step so chunking always makes progress.

    Returns:
        A list of stripped, non-empty chunk strings.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    overlap = max(0, min(overlap, max_chars - 1)) if max_chars > 1 else 0

    n = len(text)
    chunks: List[str] = []
    start = 0
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            # Back up to the previous whitespace so we don't cut a word.
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        # Overlap: restart before the end of this chunk, but always move
        # forward to guarantee termination. Snap back to the previous word
        # boundary so a chunk never starts mid-word.
        new_start = max(end - overlap, start + 1)
        if new_start > start + 1:
            space = text.rfind(" ", start, new_start)
            if space >= start:
                new_start = space + 1
        start = new_start
    return chunks


def _read_markdown(path: Path) -> Optional[Document]:
    """Read one markdown file; return ``None`` if it can't be read."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.strip():
        return None
    title = path.stem.replace("-", " ").replace("_", " ").title()
    return {"id": path.stem, "title": title, "text": text, "source": str(path)}


def ingest_docs(paths: Optional[Iterable[PathLike]] = None) -> List[Document]:
    """Ingest documents into ``{\"id\", \"title\", \"text\", \"source\"}`` dicts.

    Args:
        paths: Files to ingest. Defaults to :func:`default_corpus_paths`
            (the project's ``docs/*.md`` files).

    Missing or unreadable files are silently skipped — ingestion never
    crashes on a missing optional file such as ``docs/glossary.md``.
    Each file becomes one ``Document``; chunking happens later, at index
    time, via :func:`chunk_text`.
    """
    if paths is None:
        paths = default_corpus_paths()
    documents: List[Document] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            continue  # skip missing files gracefully
        doc = _read_markdown(path)
        if doc is not None:
            documents.append(doc)
    return documents
