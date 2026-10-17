"""Deeper tool calling: OpenAPI generation, composition, resilience (demo).

Submodules:

- :mod:`sandbox` — JSON-schema validation of tool args/results + timeouts.
- :mod:`openapi` — generate typed function-tools from OpenAPI 3.x documents.
- :mod:`composition` — sequential chains (output→input mapping) and parallel
  fan-out with result merging.
- :mod:`resilience` — per-tool retry policies, fallback chains, and partial-
  success envelopes.

All demo data is synthetic and fictional. Stdlib only.
"""

from food_ingredients_ai.tools.composition import chain, fan_out
from food_ingredients_ai.tools.openapi import (
    GeneratedTool,
    load_lims_openapi,
    synthetic_lims_transport,
    tools_from_openapi,
)
from food_ingredients_ai.tools.resilience import FallbackChain, RetryPolicy, call_with_retry, partial_envelope
from food_ingredients_ai.tools.sandbox import ToolTimeout, run_sandboxed, validate_against_schema

__all__ = [
    "chain",
    "fan_out",
    "GeneratedTool",
    "load_lims_openapi",
    "synthetic_lims_transport",
    "tools_from_openapi",
    "FallbackChain",
    "RetryPolicy",
    "call_with_retry",
    "partial_envelope",
    "ToolTimeout",
    "run_sandboxed",
    "validate_against_schema",
]
