# Architecture Alignment (Agentic-AI Architecture Principles)

> **Disclaimer.** Independent portfolio demo; synthetic data only. Principles
> below are paraphrased in our own words from the agentic-AI architecture
> ebook — no passages copied.

## 1. Outcome-first design

Start from the business outcome, not the model. Each agent exists because of
a named outcome:

| Agent | Outcome it owns |
|---|---|
| R&D Formulation | A manufacturable clean-label formula + validated claims |
| Supply Chain | Right inventory at the right plant, no stockout, no waste |
| ESG | A traceable, auditable sustainability report draft |
| Customer Advisor | A priced, claim-validated proposal a customer can act on |

The demo's regression eval (`evals/`) pins these outcomes as numbers, not
vibes — the same instinct as "define the done state before building."

## 2. Data / semantic layer

AI is only as smart as its data layer. The project's semantic layer:

- **`docs/glossary.md`** — governed business definitions (clean label,
  natural, no-artificial, reduced sugar, …) that agents and validators share.
- **`ingredion_ai/data/`** — the synthetic dataset (ingredients, formulas,
  demand, ESG readings) with a single loader; one source of truth.
- **`ingredion_ai/rag/`** — retrieval over project knowledge so agents
  ground answers in docs/glossary instead of hallucinating definitions.
  Production swap: Azure AI Search (documented in `rag/store.py`).

## 3. Governance as the engine, paved paths

Governance here is not a brake — it's what lets the system run unattended:

- **Paved paths:** the policy engine (`governance/policy.py`) defines
  allowed/disallowed actions per agent; the happy path (read/analyze/
  recommend) flows freely, high-impact actions route to HITL gates.
- **Guardrails as code:** input sanitization (prompt-injection patterns),
  PII scrubbing on outputs, secret checks (`governance/security.py`).
- **Audit by default:** hash-chained JSONL trail of every agent action
  (`governance/audit.py`).

## 4. Agents as data assets with lifecycles

Treat agents like data assets: versioned, evaluated, observable.

- **Versioned:** agent cards (`interop/a2a.py`) carry versions; the MCP
  server reports its version on `initialize`.
- **Evaluated from day one:** `evaluation/` (claim precision/recall,
  substitution top-1) + demo regression (`evals/`) run in CI, not as an
  afterthought.
- **Observable:** structured JSON logs, OTel-compatible tracing spans per
  agent/tool call, cost/latency tracking (`observability/`), incident-style
  metrics (`observability/incidents.py`).

## 5. Evaluation from day one

`python -m ingredion_ai.evaluation.runner` → 20 labeled synthetic cases
with a pass/fail summary. New capabilities ship with new eval cases
(datasets in `evaluation/datasets.py`), mirroring the "eval from day one"
discipline: if you can't measure it, you can't ship it.

## What's intentionally small

This is a demo, so the "data layer" is JSON files and the "semantic layer"
is a markdown glossary — the production equivalents (Fabric, Azure AI
Search, Purview) are documented as swaps, not implemented. The architecture
*shape* is what transfers.
