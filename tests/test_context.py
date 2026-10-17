"""Tests for the context-engineering package (assembler + budget)."""

from food_ingredients_ai.context import ContextAssembler, ContextBudget, summarize_blackboard


def test_assembler_includes_all_sections():
    assembler = ContextAssembler()
    prompt = assembler.assemble(
        instructions="You are a demo advisor.",
        glossary_terms={"clean label": "no artificial additives"},
        rag_chunks=["Chunk one.", "Chunk two."],
        blackboard={"task_a": {"score": 0.9}},
        query="What should I do?",
    )
    assert "[SYSTEM INSTRUCTIONS]" in prompt
    assert "[GLOSSARY]" in prompt
    assert "[RETRIEVED KNOWLEDGE]" in prompt
    assert "[WORKFLOW STATE]" in prompt
    assert "[USER QUERY]" in prompt
    assert "You are a demo advisor." in prompt
    assert "- clean label: no artificial additives" in prompt
    assert "[1] Chunk one." in prompt
    assert "task_a: score=0.9" in prompt
    assert "What should I do?" in prompt
    # fixed section order
    positions = [
        prompt.index(h)
        for h in (
            "[SYSTEM INSTRUCTIONS]",
            "[GLOSSARY]",
            "[RETRIEVED KNOWLEDGE]",
            "[WORKFLOW STATE]",
            "[USER QUERY]",
        )
    ]
    assert positions == sorted(positions)


def test_assembler_omits_empty_sections():
    assembler = ContextAssembler()
    prompt = assembler.assemble(instructions="Just do it.", query="Go?")
    assert "[SYSTEM INSTRUCTIONS]" in prompt
    assert "[USER QUERY]" in prompt
    assert "[GLOSSARY]" not in prompt
    assert "[RETRIEVED KNOWLEDGE]" not in prompt
    assert "[WORKFLOW STATE]" not in prompt


def test_summarize_blackboard_deterministic():
    board = {
        "zeta": {"b": 2, "a": 1},
        "alpha": ["x", "y"],
        "mid": "plain string",
    }
    first = summarize_blackboard(board)
    second = summarize_blackboard(board)
    assert first == second
    lines = first.splitlines()
    assert lines[0].startswith("alpha:")
    assert lines[1].startswith("mid:")
    assert lines[2].startswith("zeta:")
    assert "a=1; b=2" in lines[2]  # mapping keys sorted too


def test_estimate_tokens_heuristic_sane():
    budget = ContextBudget()
    assert budget.estimate_tokens("a" * 400) == 100
    assert budget.estimate_tokens("") == 0
    # monotonic: longer text never estimates fewer tokens
    assert budget.estimate_tokens("a" * 1000) >= budget.estimate_tokens("a" * 100)


def test_fit_truncates_lowest_priority_first():
    budget = ContextBudget(max_tokens=20)
    sections = {
        "instructions": "do X",  # ~1 token, highest priority: must survive
        "query": "q?",  # ~1 token: must survive
        "state": "s" * 400,  # ~100 tokens: lowest priority, gets summarized
    }
    fitted = budget.fit(sections)
    assert fitted.was_truncated is True
    assert fitted["instructions"] == "do X"
    assert fitted["query"] == "q?"
    assert len(fitted["state"]) < 400
    assert fitted["state"].endswith("…[truncated]")
    total = sum(budget.estimate_tokens(v) for v in fitted.values())
    assert total <= 20


def test_fit_summarizer_hook_called():
    calls = []

    def custom_summarizer(text, target_tokens):
        calls.append((len(text), target_tokens))
        return f"SUMMARY({target_tokens})"

    budget = ContextBudget(max_tokens=5, summarizer=custom_summarizer)
    fitted = budget.fit({"instructions": "ok", "state": "x" * 400})
    assert calls, "summarizer hook was never called"
    assert fitted["state"].startswith("SUMMARY(")
    assert fitted.was_truncated is True


def test_fit_was_truncated_flag():
    budget = ContextBudget(max_tokens=1000)
    under = budget.fit({"instructions": "short", "query": "q"})
    assert under.was_truncated is False
    assert under["instructions"] == "short"

    over = budget.fit({"instructions": "short", "state": "y" * 8000})
    assert over.was_truncated is True
