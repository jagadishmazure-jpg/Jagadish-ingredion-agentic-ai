"""Loop engineering patterns: reflection loops and human-in-the-loop gates."""

from food_ingredients_ai.loops.hitl import hitl_gate
from food_ingredients_ai.loops.reflection import reflection_loop, reflective_reformulate

__all__ = ["hitl_gate", "reflection_loop", "reflective_reformulate"]
