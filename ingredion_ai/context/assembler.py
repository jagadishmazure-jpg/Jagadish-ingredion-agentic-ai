"""Context assembly: build sectioned prompts for agent calls (demo).

The assembler turns the raw inputs an agent needs — system instructions, a
domain glossary, retrieved (RAG) chunks, shared workflow/blackboard state, and
the user query — into a single, deterministically sectioned prompt string.
Empty sections are omitted so the model never sees placeholder headers.

All demo data is synthetic and fictional.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional

SECTION_HEADERS = {
    "instructions": "[SYSTEM INSTRUCTIONS]",
    "glossary": "[GLOSSARY]",
    "rag": "[RETRIEVED KNOWLEDGE]",
    "state": "[WORKFLOW STATE]",
    "query": "[USER QUERY]",
}


def summarize_blackboard(blackboard: Mapping[str, object]) -> str:
    """Condense a blackboard dict to one line per task (deterministic).

    Each blackboard entry maps a task name to whatever the owning agent
    posted. The summary renders ``task_name: <one-line key facts>`` with
    tasks sorted alphabetically so output is stable across runs.
    """
    lines: List[str] = []
    for task_name in sorted(blackboard):
        facts = _one_line(blackboard[task_name])
        lines.append(f"{task_name}: {facts}")
    return "\n".join(lines)


def _one_line(value: object) -> str:
    """Render a blackboard value as a single line of key facts."""
    if value is None:
        return "(no result posted)"
    if isinstance(value, Mapping):
        parts = [f"{k}={v}" for k, v in sorted(value.items())]
        return "; ".join(parts) if parts else "(empty)"
    if isinstance(value, (list, tuple)):
        items = ", ".join(str(v) for v in value)
        return f"[{items}]" if items else "(empty)"
    text = str(value).replace("\n", " ").strip()
    return text if text else "(empty)"


class ContextAssembler:
    """Assemble a sectioned prompt string from agent inputs."""

    def assemble(
        self,
        instructions: str,
        glossary_terms: Optional[Iterable[str] | Mapping[str, str]] = None,
        rag_chunks: Optional[Iterable[str]] = None,
        blackboard: Optional[Mapping[str, object]] = None,
        query: Optional[str] = None,
    ) -> str:
        """Build the prompt; sections with no content are omitted.

        Args:
            instructions: System / developer instructions for the agent.
            glossary_terms: Domain terms — either an iterable of pre-formatted
                ``"term: definition"`` lines or a mapping of term → definition.
            rag_chunks: Retrieved knowledge snippets, rendered as a numbered list.
            blackboard: Shared workflow state mapping task name → posted result.
            query: The user's request.

        Returns:
            A prompt string with ``[SECTION]`` headers, in a fixed order:
            instructions, glossary, retrieved knowledge, workflow state, query.
        """
        sections: List[str] = []

        instructions = (instructions or "").strip()
        if instructions:
            sections.append(f"{SECTION_HEADERS['instructions']}\n{instructions}")

        glossary = self._format_glossary(glossary_terms)
        if glossary:
            sections.append(f"{SECTION_HEADERS['glossary']}\n{glossary}")

        rag = self._format_rag(rag_chunks)
        if rag:
            sections.append(f"{SECTION_HEADERS['rag']}\n{rag}")

        if blackboard:
            state = summarize_blackboard(blackboard)
            if state:
                sections.append(f"{SECTION_HEADERS['state']}\n{state}")

        query = (query or "").strip()
        if query:
            sections.append(f"{SECTION_HEADERS['query']}\n{query}")

        return "\n\n".join(sections)

    @staticmethod
    def _format_glossary(
        glossary_terms: Optional[Iterable[str] | Mapping[str, str]],
    ) -> str:
        if not glossary_terms:
            return ""
        if isinstance(glossary_terms, Mapping):
            terms = [f"{term}: {definition}" for term, definition in sorted(glossary_terms.items())]
        else:
            terms = [str(t).strip() for t in glossary_terms if str(t).strip()]
        return "\n".join(f"- {term}" for term in terms)

    @staticmethod
    def _format_rag(rag_chunks: Optional[Iterable[str]]) -> str:
        if not rag_chunks:
            return ""
        chunks = [str(c).strip() for c in rag_chunks if str(c).strip()]
        return "\n".join(f"[{i}] {chunk}" for i, chunk in enumerate(chunks, start=1))


__all__ = ["ContextAssembler", "summarize_blackboard", "SECTION_HEADERS"]
