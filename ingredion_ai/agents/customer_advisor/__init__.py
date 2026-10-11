"""Customer advisor agent: recommendations, samples, claims, pricing (demo)."""

from __future__ import annotations

from typing import Any, Dict

from ingredion_ai.agents.customer_advisor import (
    claims,
    formulation,
    pricing,
    recommender,
    tech_sheet,
)
from ingredion_ai.core.agent import Agent
from ingredion_ai.core.fake_llm import FakeLLM
from ingredion_ai.core.tools import Tool

__all__ = ["CustomerAdvisorAgent"]


class CustomerAdvisorAgent(Agent):
    """Specialist for customer-facing formulation advice (demo)."""

    name = "customer_advisor"
    role = "Customer formulation advisor"
    description = (
        "Recommends ingredients, generates sample formulations, validates "
        "claims, estimates pricing, produces technical sheets."
    )

    def __init__(self, llm: FakeLLM | None = None) -> None:
        super().__init__(llm)
        self.tools.register(
            Tool(
                "recommend_ingredients",
                "Recommend demo ingredients",
                recommender.recommend,
                {"category": "optional category filter"},
            )
        )
        self.tools.register(
            Tool(
                "estimate_pricing",
                "Estimate pricing bands",
                pricing.estimate_pricing,
                {"formula": "formula dict", "valid_claims": "validated claims"},
            )
        )

    def execute(self, task_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        bb = payload.get("blackboard", {})

        if task_name == "recommend_ingredients":
            recs = recommender.recommend(
                category=payload.get("category"),
                claims=tuple(payload.get("claims", ("clean_label",))),
                region=payload.get("region", "NA"),
                max_results=payload.get("max_results", 10),
            )
            return {"recommendations": recs}

        if task_name == "generate_sample_formula":
            formula = formulation.generate_sample_formula(
                payload.get("ingredient_ids", []),
                name=payload.get("name", "Demo Sample Formula"),
            )
            return {"sample_formula": formula}

        if task_name == "validate_customer_claims":
            formula = payload.get("formula") or bb.get("generate_sample_formula", {}).get(
                "sample_formula"
            )
            if formula is None:
                raise ValueError("no formula available for claim validation")
            results = claims.validate(
                formula,
                payload.get("target_claims", []),
                region=payload.get("region", "NA"),
                baseline_sugar_g=payload.get("baseline_sugar_g"),
            )
            return {"claims": results}

        if task_name == "estimate_pricing":
            bb = payload.get("blackboard", {})
            formula = payload.get("formula") or bb.get("suggest_substitutes", {}).get(
                "reformulated_formula"
            )
            if formula is None:
                raise ValueError("estimate_pricing needs a formula in payload")
            valid_claims = payload.get("valid_claims")
            if valid_claims is None:
                claim_results = bb.get("validate_claims", {}).get("claims", [])
                valid_claims = [c["claim"] for c in claim_results if c["valid"]]
            return {"pricing": pricing.estimate_pricing(formula, valid_claims)}

        if task_name == "generate_tech_sheet":
            formula = payload["formula"]
            sheet = tech_sheet.generate_customer_tech_sheet(
                formula,
                payload.get("claims", []),
                payload.get("pricing", pricing.estimate_pricing(formula, [])),
            )
            return {"tech_sheet_markdown": sheet}

        raise ValueError(f"unknown task for {self.name}: {task_name}")
