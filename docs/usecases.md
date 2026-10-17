# Use Cases

> **Disclaimer.** Independent portfolio demo; all data synthetic; not
> affiliated with any real company. Figures quoted as pain points are demo
> assumptions, not sourced statistics.

Each use case: **user → business pain → implementing module(s)**.

## Knowledge layers

1. **Consumer insights:** claim recognition, willingness-to-pay, ingredient acceptability
2. **Formulation/R&D:** substitution rules, texture/shelf-life know-how
3. **Ingredient portfolio:** functional starches/flours, sweeteners, plant proteins, natural certifications
4. **Regulatory/claims:** per-region claim rules and hierarchy
5. **Supply chain:** plants, inventory, quality
6. **ESG:** regenerative ag, carbon/water/energy
7. **Customer:** CRM accounts, opportunities, cases

## The ten use cases

### 1. Reformulation copilot
- **User:** R&D food scientist. **Pain:** reformulation expertise gap (~1 in 3 teams) and 5–7 month timelines.
- **Modules:** `agents/rd_formulation/` (analyzer → substitution → predictor → regulatory), `rd_formulation/cycle_time.py`, `loops/reflection.py` (draft→critique→revise), `graph/reformulation_graph.py`.

### 2. Insights Q&A
- **User:** Product manager. **Pain:** "which claims do consumers actually value?"
- **Modules:** `rag/` (retrieval over docs/glossary), `context/assembler.py`, claim hierarchy in `regulatory.py`.

### 3. Claim compliance checker
- **User:** Regulatory affairs. **Pain:** mislabeled claims = recalls; "natural" is the top-recognized claim so it must be right.
- **Modules:** `rd_formulation/regulatory.py` (`prioritize_claims`, honest rejection), `evaluation/` (precision/recall on labeled cases), `docs/glossary.md`.

### 4. Cost-optimized substitution
- **User:** R&D + procurement. **Pain:** ingredient cost is the #1 reported barrier (~40%).
- **Modules:** `substitution.py` (`rank_cost_aware`), `customer_advisor/pricing.py`, `evaluation/datasets.py` (substitution relevance).

### 5. Shelf-life risk predictor
- **User:** Quality/R&D. **Pain:** shelf-life anxiety when removing familiar functional ingredients, especially bakery.
- **Modules:** `predictor.py` (`bakery_stability_advisory`), `supply_chain/quality.py`, `observability/incidents.py` (false-positive tracking).

### 6. Customer formulation advisor
- **User:** Key account manager. **Pain:** half of consumers pay 10%+ more for valued claims — proposals must connect claims to price.
- **Modules:** `agents/customer_advisor/` (recommender, claims, `pricing.wtp_band`), `integrations/crm.py` (account personalization), `governance/approvals.py` (proposal HITL gate).

### 7. Supply chain planner
- **User:** Supply planner. **Pain:** stockouts vs. waste on short-shelf-life inputs.
- **Modules:** `agents/supply_chain/` (forecaster, inventory, scheduler), `integrations/sap.py` (plant inventory), `harness/` (retries/circuit breaker around planning runs).

### 8. ESG reporter
- **User:** Sustainability lead. **Pain:** ESG/regenerative-ag expectations need auditable numbers.
- **Modules:** `agents/esg/` (collector, carbon, intensity, report), `governance/audit.py` (traceability), `governance/approvals.py` (publish gate).

### 9. Cross-functional orchestrated workflow
- **User:** Program manager. **Pain:** reformulation touches R&D, supply, ESG, and customers — coordination overhead.
- **Modules:** `framework/workflow.py` (WorkflowBuilder), `graph/` (explicit graph orchestration), `interop/a2a.py` (cross-agent task protocol).

### 10. Knowledge-grounded semantic search
- **User:** Any stakeholder. **Pain:** tribal knowledge; inconsistent claim definitions.
- **Modules:** `rag/` (chunking, hash embeddings, vector store; Azure AI Search as production swap), `docs/glossary.md` (semantic layer), `interop/mcp.py` (expose tools to external clients).
