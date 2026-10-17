# Governed Business Glossary (Semantic Layer)

> **Disclaimer.** Independent portfolio demo; all data synthetic; not
> affiliated with any real company. Definitions below are **demo
> simplifications** for the synthetic dataset — not legal or regulatory
> advice. Real claim rules vary by jurisdiction and product.

This glossary is the project's **semantic layer**: the single governed set
of business definitions shared by agents, validators, RAG retrieval, and
docs. When the regulatory checker says "natural," it means *this*.

## Claim definitions (demo)

| Term | Demo definition | Validator behavior |
|---|---|---|
| **clean label** | Formula contains no ingredient flagged non-clean-label by the analyzer | Analyzer flag list in `rd_formulation/analyzer.py` |
| **natural / all-natural** | All ingredients clean-label **and** no refined/added sugars, no synthetic processing aids (demo rule) | Fails while refined sugar remains — the demo's honest-rejection case |
| **no artificial ingredients** | No artificial colors, flavors, sweeteners, or preservatives | Passes after substitution of synthetics |
| **no artificial colors** | No synthetic colors (demo: fruit/vegetable juice concentrates allowed) | Per-ingredient flag check |
| **no artificial flavors** | No synthetic flavor compounds (demo: natural flavor systems allowed) | Per-ingredient flag check |
| **reduced sugar** | ≥25% less sugar vs. the baseline formula (demo threshold) | Compared against baseline in `regulatory.py` |
| **non-GMO** | No ingredients flagged as genetically-modified source (demo flag) | Dataset flag check |
| **plant-based** | No animal-derived ingredients (demo flag) | Dataset flag check |

## Claim hierarchy (validation priority)

`natural` → `no artificial ingredients` → `no artificial colors` →
`no artificial flavors` → `reduced sugar` → `non-GMO` → `plant-based`
(see `regulatory.py::CLAIM_PRIORITY`). Demo assumption: "natural"/"all-natural" is the most consumer-recognized claim,
so it is validated first and featured first.

## Ingredient function terms (demo)

| Term | Meaning in this dataset |
|---|---|
| **starch** | Texture/body builder (demo: functional starches) |
| **sweetener** | Provides sweetness; bulk vs. high-intensity |
| **hydrocolloid** | Viscosity/stability (demo: gums) |
| **protein** | Nutritional/structural (demo: plant proteins) |
| **acidulant** | pH control / preservation assist |
| **whitener** | Opacity (demo: calcium-carbonate whitener replaces titanium dioxide) |

## Business terms

| Term | Demo meaning |
|---|---|
| **willingness-to-pay (WTP) band** | Price range consumers accept for validated claims; demo: 10%+ premium band for valued claims (demo assumption) |
| **cycle time** | Reformulation project duration estimate; demo baseline 5–7 months (demo assumption) |
| **reorder point** | Inventory level triggering a purchase order (avg daily demand × lead time × safety factor) |
| **carbon intensity** | CO₂e per tonne of production (synthetic readings) |

## Governance of this glossary

Terms change here first, code second: validators and RAG chunks reference
these definitions. Proposed changes should add an eval case in
`evaluation/datasets.py` proving the new definition behaves as intended.
