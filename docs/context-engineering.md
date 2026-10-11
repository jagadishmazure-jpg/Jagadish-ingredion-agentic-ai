# Context Engineering

> Demo project. All data synthetic and fictional. Not affiliated with Ingredion.

Context engineering is everything that happens *around* the model call: what we
put into the prompt, in what order, and how we keep it under the token budget.
The `ingredion_ai.context` package implements this for the demo agents in two
steps: **assemble** the context, then **budget** it.

## What goes into the context

`ContextAssembler.assemble()` builds a single, sectioned prompt string from the
inputs a demo agent needs:

| Section | Header | Content |
|---|---|---|
| System instructions | `[SYSTEM INSTRUCTIONS]` | Role, rules, and output format for the agent |
| Glossary | `[GLOSSARY]` | Domain terms (`term: definition` lines) so the model uses vocabulary consistently |
| Retrieved knowledge | `[RETRIEVED KNOWLEDGE]` | Numbered RAG chunks backing the answer |
| Workflow state | `[WORKFLOW STATE]` | Condensed blackboard: one line per upstream task's key facts |
| User query | `[USER QUERY]` | The request being answered |

Sections with no content are **omitted** — the model never sees empty
placeholder headers. Order is fixed (instructions → glossary → retrieved →
state → query) so prompt construction is deterministic and easy to debug.

```python
from ingredion_ai.context import ContextAssembler

prompt = ContextAssembler().assemble(
    instructions="You are a formulation advisor. Answer concisely.",
    glossary_terms={"clean label": "no artificial additives or preservatives"},
    rag_chunks=["Starch X gives 20% better freeze-thaw stability."],
    blackboard={"analyze_ingredients": {"risk": "low", "flags": 2}},
    query="Suggest a clean-label substitute for starch X.",
)
```

### Blackboard summaries

`summarize_blackboard(blackboard)` condenses shared workflow state (task name →
posted result) into `task: key=value; ...` one-liners, sorted by task name for
determinism. This is what feeds `[WORKFLOW STATE]`: full upstream payloads are
too large for the prompt, so the assembler passes only key facts.

## Budgeting strategy

`ContextBudget(max_tokens=8000)` enforces a hard token ceiling *after*
assembly:

1. **Estimate** — `estimate_tokens(text)` uses a `len(text) // 4` heuristic
   (roughly 4 characters per token of English prose). It is deliberately not a
   real tokenizer: fast, deterministic, offline. Documented as a heuristic —
   for production, plug in a model-accurate counter the same way.
2. **Fit by priority** — `fit(sections)` keeps sections in priority order
   `[instructions, query, glossary, rag, state]`. If the total exceeds the
   budget, it summarizes the **lowest-priority** sections first (`state`, then
   `rag`, …), each reduced to exactly the size that makes the whole payload
   fit. Instructions and the user query — the two things the model must not
   lose — are shortened only as a last resort.
3. **Summarizer hook** — truncation is delegated to a `summarizer` callable
   `(text, target_tokens) -> str`. The default is extractive (first N
   characters + `…[truncated]`); swap in a real summarizer (e.g. an LLM call)
   by passing your own callable to the constructor.
4. **Signal** — `fit()` returns a `FitResult` dict with a `was_truncated` flag
   so the caller knows context was shortened and can, e.g., log it or warn.

```python
from ingredion_ai.context import ContextBudget

budget = ContextBudget(max_tokens=4000)
fitted = budget.fit({"instructions": "...", "query": "...", "state": "..."})
if fitted.was_truncated:
    print("workflow state was condensed to fit the budget")
```

## Hooks

- `ContextBudget(summarizer=...)` — custom truncation strategy; receives the
  section text and target token count, returns the shortened text.
- `Harness` eval hooks (see `docs/harness.md`) can record `was_truncated` per
  run, giving an observability signal for "was the agent starved of context?".
