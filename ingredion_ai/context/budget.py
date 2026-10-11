"""Context budgeting: keep assembled prompts under a token budget (demo).

Token counts here are a **heuristic** — ``estimate_tokens`` uses
``len(text) // 4`` (roughly 4 characters per token for English prose).
It is deliberately not a real tokenizer: it is fast, deterministic, and
offline, which is all the demo budgeter needs. For production, swap in a
model-accurate tokenizer via the ``summarizer``-style hook pattern.

All demo data is synthetic and fictional.
"""

from __future__ import annotations

from typing import Callable, Dict

# Highest priority first. When over budget, ``fit`` shrinks sections from
# the *end* of this list (lowest priority) toward the front.
PRIORITY = ["instructions", "query", "glossary", "rag", "state"]

#: Marks that a section was shortened by the default summarizer.
TRUNCATION_MARKER = "…[truncated]"

Summarizer = Callable[[str, int], str]


def default_summarizer(text: str, target_tokens: int) -> str:
    """Extractive fallback: keep the first ``target_tokens`` worth of chars.

    The cut is ``target_tokens * 4`` characters (inverse of the estimator),
    minus the marker length so the marked result still fits the target,
    followed by a truncation marker so readers can tell the section was
    shortened. Purely deterministic.
    """
    keep = max(target_tokens * 4 - len(TRUNCATION_MARKER), 0)
    return text[:keep] + TRUNCATION_MARKER


class FitResult(dict):
    """``fit()`` output: the fitted sections plus a ``was_truncated`` flag."""

    def __init__(self, sections: Dict[str, str], was_truncated: bool) -> None:
        super().__init__(sections)
        self.was_truncated = was_truncated


class ContextBudget:
    """Enforce a token budget on assembled context sections."""

    def __init__(
        self,
        max_tokens: int = 8000,
        summarizer: Summarizer | None = None,
    ) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        self.max_tokens = max_tokens
        self.summarizer: Summarizer = summarizer or default_summarizer

    def estimate_tokens(self, text: str) -> int:
        """Heuristic token estimate: ``len(text) // 4``.

        Documented as a heuristic — good enough for budgeting decisions,
        not a substitute for a real tokenizer.
        """
        return max(len(text or "") // 4, 0)

    def fit(self, sections: Dict[str, str]) -> FitResult:
        """Fit *sections* into the token budget.

        Sections are kept in ``PRIORITY`` order. If the total estimated
        tokens exceed ``max_tokens``, the lowest-priority sections are
        summarized (via the ``summarizer`` hook) to the size that makes the
        whole payload fit — one section at a time, from lowest priority up.
        Keys not in ``PRIORITY`` are carried through unchanged at the end.

        Returns a ``FitResult`` (a dict) whose ``was_truncated`` attribute is
        ``True`` iff any section was shortened.
        """
        known = {k: (sections.get(k) or "") for k in PRIORITY if k in sections}
        extra = {k: v for k, v in sections.items() if k not in PRIORITY}

        counts = {k: self.estimate_tokens(v) for k, v in known.items()}
        was_truncated = False

        # Shrink lowest-priority sections first until everything fits.
        while sum(counts.values()) > self.max_tokens:
            shrunk = False
            for key in reversed(PRIORITY):
                if key not in known:
                    continue
                others = sum(c2 for k2, c2 in counts.items() if k2 != key)
                target = self.max_tokens - others
                if target < 0:
                    target = 0
                if counts[key] > target:
                    summarized = self.summarizer(known[key], target)
                    new_count = self.estimate_tokens(summarized)
                    if new_count >= counts[key]:
                        # Summarizer made no progress on this section;
                        # try the next-lowest-priority one instead.
                        continue
                    known[key] = summarized
                    counts[key] = new_count
                    was_truncated = True
                    shrunk = True
                    break
            if not shrunk:
                # Nothing left to shrink (all sections already minimal);
                # bail out rather than loop forever.
                break

        fitted = {k: known[k] for k in PRIORITY if k in known}
        fitted.update(extra)
        return FitResult(fitted, was_truncated)


__all__ = ["ContextBudget", "FitResult", "PRIORITY", "default_summarizer", "TRUNCATION_MARKER"]
