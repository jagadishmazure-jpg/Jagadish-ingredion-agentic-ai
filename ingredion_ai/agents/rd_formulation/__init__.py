"""R&D formulation agent: clean-label analysis, substitution, prediction, docs."""

from __future__ import annotations

from typing import Any, Dict

from ingredion_ai.agents.rd_formulation import (
    analyzer,
    cycle_time,
    documentation,
    nutrition,
    predictor,
    regulatory,
    substitution,
)
from ingredion_ai.core.agent import Agent
from ingredion_ai.core.fake_llm import FakeLLM
from ingredion_ai.core.tools import Tool
from ingredion_ai.data.loader import get_formula

__all__ = ["RDFormulationAgent"]


class RDFormulationAgent(Agent):
    """Specialist for clean-label reformulation workflows (demo)."""

    name = "rd_formulation"
    role = "Clean-label R&D formulation specialist"
    description = (
        "Analyzes formulas, recommends clean-label substitutions, predicts "
        "texture/shelf-life, computes nutrition, validates claims, generates docs."
    )

    def __init__(self, llm: FakeLLM | None = None) -> None:
        super().__init__(llm)
        self.tools.register(
            Tool(
                "analyze_ingredients",
                "Flag non-clean-label ingredients",
                analyzer.analyze_formula,
                {"formula": "formula dict"},
            )
        )
        self.tools.register(
            Tool(
                "suggest_substitutes",
                "Recommend clean-label swaps",
                substitution.suggest_substitutes,
                {"flagged": "flagged ingredient list"},
            )
        )
        self.tools.register(
            Tool(
                "predict_texture_shelf_life",
                "Predict texture & shelf-life impact",
                predictor.predict,
                {"formula": "formula dict", "substitutions": "substitution list"},
            )
        )
        self.tools.register(
            Tool(
                "calculate_nutrition",
                "Compute nutritional panel",
                nutrition.calculate_nutrition,
                {"formula": "formula dict"},
            )
        )
        self.tools.register(
            Tool(
                "validate_claims",
                "Validate label claims per region",
                regulatory.validate_claims,
                {"formula": "formula dict", "claims": "claim list"},
            )
        )
        self.tools.register(
            Tool(
                "estimate_cycle_time",
                "Estimate reformulation cycle time vs demo baseline",
                cycle_time.estimate_cycle_time,
                {
                    "formula": "formula dict",
                    "substitutions": "substitution list",
                    "prediction": "prediction dict",
                },
            )
        )

    def _baseline_sugar(self, payload: Dict[str, Any], bb: Dict[str, Any]) -> float:
        if "calculate_nutrition" in bb:
            return bb["calculate_nutrition"]["nutrition_original"]["per_100g"]["sugar_g"]
        original = nutrition.calculate_nutrition(
            get_formula(payload["formula_id"])
        )
        return original["per_100g"]["sugar_g"]

    def execute(self, task_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        bb = payload.get("blackboard", {})
        formula_id = payload["formula_id"]
        formula = get_formula(formula_id)

        if task_name == "analyze_ingredients":
            return analyzer.analyze_formula(formula)

        if task_name == "suggest_substitutes":
            analysis = bb.get("analyze_ingredients") or analyzer.analyze_formula(formula)
            subs = substitution.suggest_substitutes(analysis["flagged"])
            new_formula = substitution.apply_substitutions(
                formula,
                subs,
                adjustments=payload.get("adjustments"),
                additions=payload.get("additions"),
            )
            return {
                "substitutions": subs,
                "reformulated_formula": new_formula,
                "substituted_count": sum(
                    1 for s in subs if s["action"] == "substitute"
                ),
                "removed_count": sum(1 for s in subs if s["action"] == "remove"),
            }

        if task_name == "predict_texture_shelf_life":
            subs = (
                bb["suggest_substitutes"]["substitutions"]
                if "suggest_substitutes" in bb
                else substitution.suggest_substitutes(
                    analyzer.analyze_formula(formula)["flagged"]
                )
            )
            return {"prediction": predictor.predict(formula, subs)}

        if task_name == "calculate_nutrition":
            if "suggest_substitutes" in bb:
                new_formula = bb["suggest_substitutes"]["reformulated_formula"]
            else:
                analysis = analyzer.analyze_formula(formula)
                subs = substitution.suggest_substitutes(analysis["flagged"])
                new_formula = substitution.apply_substitutions(
                    formula,
                    subs,
                    adjustments=payload.get("adjustments"),
                    additions=payload.get("additions"),
                )
            return {
                "nutrition_original": nutrition.calculate_nutrition(formula),
                "nutrition_reformulated": nutrition.calculate_nutrition(new_formula),
            }

        if task_name == "validate_claims":
            if "suggest_substitutes" in bb:
                new_formula = bb["suggest_substitutes"]["reformulated_formula"]
                new_nutrition = bb.get("calculate_nutrition", {}).get(
                    "nutrition_reformulated"
                ) or nutrition.calculate_nutrition(new_formula)
            else:
                analysis = analyzer.analyze_formula(formula)
                subs = substitution.suggest_substitutes(analysis["flagged"])
                new_formula = substitution.apply_substitutions(
                    formula,
                    subs,
                    adjustments=payload.get("adjustments"),
                    additions=payload.get("additions"),
                )
                new_nutrition = nutrition.calculate_nutrition(new_formula)
            claims = regulatory.validate_claims(
                new_formula,
                payload.get("target_claims", []),
                region=payload.get("region", "NA"),
                nutrition=new_nutrition,
                baseline_sugar_g=self._baseline_sugar(payload, bb),
            )
            return {"claims": claims}

        if task_name == "generate_documentation":
            suggest = bb.get("suggest_substitutes") or self.execute(
                "suggest_substitutes", payload
            )
            prediction = (
                bb.get("predict_texture_shelf_life", {}).get("prediction")
                or predictor.predict(
                    formula, suggest["substitutions"]
                )
            )
            calc = bb.get("calculate_nutrition") or self.execute(
                "calculate_nutrition", payload
            )
            claims_out = bb.get("validate_claims") or self.execute(
                "validate_claims", payload
            )
            analysis = bb.get("analyze_ingredients") or analyzer.analyze_formula(formula)
            spec = documentation.generate_formulation_spec(
                suggest["reformulated_formula"],
                analysis,
                suggest["substitutions"],
                prediction,
                calc["nutrition_reformulated"],
                claims_out["claims"],
            )
            sheet = documentation.generate_technical_sheet(
                suggest["reformulated_formula"],
                claims_out["claims"],
                calc["nutrition_reformulated"],
            )
            return {"spec_markdown": spec, "tech_sheet_markdown": sheet}

        if task_name == "estimate_cycle_time":
            suggest = bb.get("suggest_substitutes") or self.execute(
                "suggest_substitutes", payload
            )
            prediction = (
                bb.get("predict_texture_shelf_life", {}).get("prediction")
                or predictor.predict(formula, suggest["substitutions"])
            )
            return {
                "cycle_time": cycle_time.estimate_cycle_time(
                    formula, suggest["substitutions"], prediction
                )
            }

        raise ValueError(f"unknown task for {self.name}: {task_name}")
