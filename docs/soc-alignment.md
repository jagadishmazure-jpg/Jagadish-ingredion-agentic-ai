# SOC Principles → Project Mapping

> **Honest framing first.** This is a **manufacturing demo**, not a security
> operations center. Nothing below claims the project *is* a SOC. What it
> does is map the *principles* from the AI-powered SOC guide (triage,
> investigation quality, human-AI collaboration, richer metrics, phased
> rollout — paraphrased in our own words) onto the project's
> governance/observability layer, so the same engineering habits transfer.

## Principle → project mapping

| SOC principle (paraphrase) | Project analogue | Where |
|---|---|---|
| **Triage & prioritization:** not every alert deserves the same response; rank by severity/impact | Claim validation prioritizes the claim hierarchy (`natural` first); substitution ranking is cost-aware; the policy engine classifies actions by impact tier | `regulatory.py` (`prioritize_claims`), `substitution.py`, `governance/policy.py` |
| **Investigation quality:** gather evidence before concluding; keep the reasoning trace | Every agent result carries its inputs; the blackboard keeps the full tool-result chain; ESG reports show traceable calculations | `framework/workflow.py` (blackboard), `esg/report.py` |
| **Human-AI force multiplier:** AI drafts, humans decide on high-impact actions | HITL approval gates for new formulations, customer proposals, ESG reports; simulated approver offline, human approver in production | `governance/approvals.py`, `loops/hitl.py` |
| **Metrics beyond basic MTTR:** measure detection quality, false positives, automation rate — not just speed | `observability/incidents.py`: detection/response-time analogues per agent run, false-positive tracking on claim validation, automation rate of guardrail decisions | `observability/incidents.py`, `observability/costs.py` |
| **Phased rollout:** crawl → walk → run; prove value in a contained scope before expanding | Offline deterministic demo → eval suites → Foundry deployment guide; each phase has its own verification (pytest, eval runner, deployment checklist) | `evaluation/runner.py`, `docs/foundry-deployment.md` |
| **Auditability:** every investigation step attributable | Hash-chained append-only audit trail with actor + timestamp + caller identity | `governance/audit.py`, `interop/auth.py` |

## What we deliberately do NOT claim

- No threat detection, no alert pipeline, no SIEM integration — the
  "incident" metrics are *analogues* (agent-run detection/response timing,
  claim-validation false positives), useful for demonstrating measurement
  discipline, not for defending a network.
- The SOC guide's "cognitive AI" framing is about security reasoning; here
  the analogue is the reflection loop (`loops/reflection.py`) — draft →
  critique → revise — applied to formulation quality, not threat hunting.

## Why this transfers

"If you can build triage, evidence trails, human gates, and honest metrics
for a manufacturing demo, you can build them for a SOC — the engineering
pattern is the same, only the domain changes."
