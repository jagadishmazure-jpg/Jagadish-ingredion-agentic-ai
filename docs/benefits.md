# Agent → Business Pain-Point Mapping

> **Disclaimer.** This is an independent portfolio demo, not affiliated with
> Ingredion Incorporated. All data is synthetic. The ebook stats below are
> **paraphrased public findings** used only as *commented rationale* for
> demo heuristics — they are not copied from the ebook and should not be
> cited as the ebook's claims.

Each of the four domain agents exists to address a documented industry pain
point from Ingredion's public "Unlocking growth through smarter clean label"
ebook (paraphrased):

| Agent | Ebook pain point (paraphrase) | What the agent does (demo) |
|---|---|---|
| **R&D Formulation** | Reformulation expertise gap (~1 in 3 teams report it) and multi-month project timelines (roughly 5–7 months average) | Analyzer flags non-clean-label ingredients; substitution engine ranks clean-label swaps **cost-aware** (cost is the #1 reported barrier); texture/stability predictor flags shelf-life risk up front; `cycle_time.py` estimates a project timeline off the 5–7 month baseline |
| **R&D Formulation** | Shelf-life anxiety when removing familiar functional ingredients | `predictor.py` emits explicit stability risk flags — stronger for bakery, where crumb/chew textures are most affected |
| **Supply Chain** | Ingredient cost as the #1 reported barrier (~40% cite it) | Cost-aware substitution ranking + inventory reorder math that avoids over-ordering; SAP adapter shows how planning would consume real plant inventory |
| **ESG** | Growing ESG/regenerative-agriculture expectations on manufacturers | Carbon, water, and energy intensity from synthetic plant readings; traceable markdown ESG report draft |
| **Customer Advisor** | Claim strategy: "natural"/"all-natural" is the top consumer-recognized claim; half of consumers will pay 10%+ more for claims they value | Claim hierarchy (`natural` → `no artificial` → `reduced sugar` → …) drives validation priority; `pricing.py` adds a willingness-to-pay band (10%+ premium) to cost estimates; CRM adapter personalizes proposals by account tier |

## Where the rationale lives in code

- `ingredion_ai/agents/rd_formulation/substitution.py` — cost-barrier comment + cost-aware ranking
- `ingredion_ai/agents/rd_formulation/predictor.py` — shelf-life risk flags (bakery-strong)
- `ingredion_ai/agents/rd_formulation/cycle_time.py` — 5–7 month baseline estimator
- `ingredion_ai/agents/rd_formulation/regulatory.py` — claim hierarchy / priority
- `ingredion_ai/agents/customer_advisor/pricing.py` — willingness-to-pay band

## Scope and honest framing

This demo *illustrates* where agents would attack the pain points; it does
not prove ROI. The numbers in the demo (92.2% texture match, 8.2-day
shelf-life) are outputs of documented demo heuristics over synthetic data,
not food-science measurements.
