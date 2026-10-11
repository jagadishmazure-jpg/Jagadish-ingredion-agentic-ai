# Attachments Coverage Map

Every uploaded reference is paraphrased (never copied at length) and
covered *somewhere* concrete. Scope → coverage:

## 1. Ingredion "Unlocking growth through smarter clean label" ebook

Public stats used only as *commented rationale* for demo heuristics.

| Ebook scope (paraphrase) | Covered in |
|---|---|
| Clean-label conversion lifts pricing/margins/revenue | `docs/benefits.md`, pricing WTP band (`customer_advisor/pricing.py`) |
| Cost = #1 barrier → cost-aware decisions | `rd_formulation/substitution.py` (`rank_cost_aware`) |
| Shelf-life anxiety, esp. bakery | `rd_formulation/predictor.py` (`bakery_stability_advisory`) |
| 5–7 month reformulation baseline | `rd_formulation/cycle_time.py` |
| Claim hierarchy (natural top) | `rd_formulation/regulatory.py` (`CLAIM_PRIORITY`, `prioritize_claims`) |
| 10%+ WTP premium for valued claims | `customer_advisor/pricing.py` (`wtp_band`) |
| Priority categories: bakery + beverages | Demo scenarios (`demo.py::SCENARIOS`), new formulas/dataset entries |
| ATLAS-style consumer insights | `docs/usecases.md` (ATLAS-style insights use case) |
| ESG / regenerative-ag focus | `agents/esg/`, `docs/usecases.md` |

## 2. AI-powered SOC guide (Conifers)

Principles mapped, not domain force-fit (manufacturing demo ≠ SOC).

| Guide scope (paraphrase) | Covered in |
|---|---|
| Triage / prioritization | `docs/soc-alignment.md`; claim prioritization, cost-aware ranking |
| Investigation quality / evidence trails | Blackboard + traceable ESG report; `docs/soc-alignment.md` |
| Human-AI force multiplier | HITL gates (`governance/approvals.py`, `loops/hitl.py`) |
| Metrics beyond basic MTTR | `observability/incidents.py` (detection/response analogues, false-positive + automation rates) |
| Phased rollout | Eval → demo → Foundry phases; `docs/soc-alignment.md` |

## 3. Auth0 omnichannel identity + identity-for-AI-agents ebook

| Ebook scope (paraphrase) | Covered in |
|---|---|
| User auth, session context | `docs/identity.md` §1 (Entra ID/OIDC for the agent API) |
| Short-lived scoped tokens | `interop/auth.py` (`issue_token`/`verify_token`), `governance/identity.py` (`ScopedToken`) |
| Fine-grained runtime authorization | Per-skill scope enforcement in `interop/a2a.py::message_send` |
| Human-in-the-loop approvals | `governance/approvals.py` + `loops/hitl.py` |
| Identity-attributed audit trails | `governance/audit.py` + caller attribution on A2A tasks |
| Managed identity / RBAC for services | `docs/identity.md` §1+§3, `docs/foundry-deployment.md` (RBAC section) |

## 4. Databricks "The New Architecture of Agentic AI" ebook

| Ebook scope (paraphrase) | Covered in |
|---|---|
| Outcome-first design | `docs/architecture-alignment.md` §1 |
| Data / semantic layer | `docs/glossary.md`, `ingredion_ai/data/`, `ingredion_ai/rag/` |
| Governance as engine, paved paths | `governance/`, `docs/architecture-alignment.md` §3 |
| Agents as data assets with lifecycles | Agent cards, evals, observability; `docs/architecture-alignment.md` §4 |
| Evaluation from day one | `evaluation/`, `docs/architecture-alignment.md` §5 |

## 5. Playwright QA PDFs (3 files)

Queued as a **later phase** (API + UI E2E tests against the agent service
once it exists). Noted in project memory; not covered in this codebase yet.
