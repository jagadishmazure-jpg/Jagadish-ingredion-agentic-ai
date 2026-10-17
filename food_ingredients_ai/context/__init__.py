"""Context engineering: assemble and budget the prompt context for agents.

Demo project. All data synthetic and fictional. Not affiliated with any real company.
"""

from food_ingredients_ai.context.assembler import ContextAssembler, summarize_blackboard
from food_ingredients_ai.context.budget import ContextBudget, FitResult

__all__ = ["ContextAssembler", "summarize_blackboard", "ContextBudget", "FitResult"]
