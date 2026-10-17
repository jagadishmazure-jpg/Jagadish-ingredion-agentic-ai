# Agent → Business Pain-Point Mapping

> **Disclaimer.** Independent portfolio demo, not affiliated with any real
> company. All data is synthetic. The figures below (team expertise gaps,
> cost as the main barrier, 5–7 month reformulation timelines, a 10%+ price
> premium for valued claims) are **demo assumptions** that drive the
> heuristics. They were inspired by public industry reading on clean-label
> reformulation but are not sourced claims and should not be cited.

Each of the four domain agents exists to address a common pain point in
clean-label reformulation:

| Agent | Pain point (demo assumption) | What the agent does (demo) |
|---|---|---|
| **R&D Formulation** | Reformulation expertise gap (~1 in 3 teams report it) and multi-month project timelines (roughly 5–7 months average) | Analyzer flags non-clean-label ingredients; substitution engine ranks clean-label swaps **cost-aware** (cost is the #1 reported barrier); texture/stability predictor flags shelf-life risk up front; `cycle_time.py` estimates a project timeline off the 5–7 month baseline |
| **R&D Formulation** | Shelf-life anxiety when removing familiar functional ingredients | `predictor.py` emits explicit stability risk flags — stronger for bakery, where crumb/chew textures are most affected |
| **Supply Chain** | Ingredient cost as the #1 reported barrier (~40% cite it) | Cost-aware substitution ranking + inventory reorder math that avoids over-ordering; SAP adapter shows how planning would consume real plant inventory |
| **ESG** | Growing ESG/regenerative-agriculture expectations on manufacturers | Carbon, water, and energy intensity from synthetic plant readings; traceable markdown ESG report draft |
| **Customer Advisor** | Claim strategy: "natural"/"all-natural" is the top consumer-recognized claim; half of consumers will pay 10%+ more for claims they value | Claim hierarchy (`natural` → `no artificial` → `reduced sugar` → …) drives validation priority; `pricing.py` adds a willingness-to-pay band (10%+ premium) to cost estimates; CRM adapter personalizes proposals by account tier |

## Where the rationale lives in code

- `food_ingredients_ai/agents/rd_formulation/substitution.py` — cost-barrier comment + cost-aware ranking
- `food_ingredients_ai/agents/rd_formulation/predictor.py` — shelf-life risk flags (bakery-strong)
- `food_ingredients_ai/agents/rd_formulation/cycle_time.py` — 5–7 month baseline estimator
- `food_ingredients_ai/agents/rd_formulation/regulatory.py` — claim hierarchy / priority
- `food_ingredients_ai/agents/customer_advisor/pricing.py` — willingness-to-pay band

## Scope and honest framing

This demo *illustrates* where agents would attack the pain points; it does
not prove ROI. The numbers in the demo (92.2% texture match, 8.2-day
shelf-life) are outputs of documented demo heuristics over synthetic data,
not food-science measurements.
