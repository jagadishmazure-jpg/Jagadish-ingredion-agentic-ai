"""Context engineering: assemble and budget the prompt context for agents.

Demo project. All data synthetic and fictional. Not affiliated with Ingredion.
"""

from ingredion_ai.context.assembler import ContextAssembler, summarize_blackboard
from ingredion_ai.context.budget import ContextBudget, FitResult

__all__ = ["ContextAssembler", "summarize_blackboard", "ContextBudget", "FitResult"]
