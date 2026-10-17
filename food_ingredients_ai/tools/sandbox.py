"""Tool sandbox: JSON-schema validation + timeout enforcement (demo).

- :func:`validate_against_schema` — minimal JSON-Schema validator covering
  the subset this project generates: ``type`` (object/array/string/number/
  integer/boolean/null), ``required``, ``properties``, ``items``, ``enum``,
  ``minimum``/``maximum``, ``minLength``/``maxLength``,
  ``additionalProperties``.
- :func:`run_sandboxed` — validate args, run with a timeout, validate the
  result, and shape every failure into a uniform error envelope. Never raises
  for tool failures.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Dict, List, Optional

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate_against_schema(value: Any, schema: Dict[str, Any], *, path: str = "$") -> List[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: List[str] = []
    if not isinstance(schema, dict):
        return errors

    expected = schema.get("type")
    if expected is not None:
        check = _TYPE_CHECKS.get(expected)
        if check is None:
            errors.append(f"{path}: unknown type {expected!r}")
            return errors
        if not check(value):
            errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
            return errors

    if expected == "object" and isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing required property {name!r}")
        props = schema.get("properties", {})
        for name, subschema in props.items():
            if name in value:
                errors.extend(
                    validate_against_schema(value[name], subschema, path=f"{path}.{name}")
                )
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in props:
                    errors.append(f"{path}: additional property {name!r} not allowed")

    if expected == "array" and isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(value):
                errors.extend(validate_against_schema(item, items, path=f"{path}[{i}]"))

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength {schema['maxLength']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > maximum {schema['maximum']}")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum {schema['enum']!r}")

    return errors


class ToolTimeout(Exception):
    """Raised internally when a sandboxed tool exceeds its timeout."""


def run_sandboxed(
    fn: Callable[..., Any],
    args: Dict[str, Any],
    *,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    timeout_s: float = 10.0,
    tool_name: str = "tool",
) -> Dict[str, Any]:
    """Run *fn* with validated args/results inside a timeout.

    Returns ``{"ok": True, "result": ...}`` or ``{"ok": False, "error":
    {"code", "message", "stage"}}`` where stage is one of ``args``,
    ``timeout``, ``exec``, ``result``.
    """
    if input_schema:
        arg_errors = validate_against_schema(args, input_schema)
        if arg_errors:
            return {
                "ok": False,
                "tool": tool_name,
                "error": {
                    "code": "INVALID_ARGS",
                    "message": "; ".join(arg_errors),
                    "stage": "args",
                },
            }
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(fn, **args).result(timeout=timeout_s)
    except FuturesTimeoutError:
        return {
            "ok": False,
            "tool": tool_name,
            "error": {
                "code": "TIMEOUT",
                "message": f"exceeded {timeout_s}s",
                "stage": "timeout",
            },
        }
    except Exception as exc:  # noqa: BLE001 - shaped into envelope
        return {
            "ok": False,
            "tool": tool_name,
            "error": {"code": "EXEC_FAILED", "message": str(exc), "stage": "exec"},
        }
    if output_schema:
        result_errors = validate_against_schema(result, output_schema)
        if result_errors:
            return {
                "ok": False,
                "tool": tool_name,
                "error": {
                    "code": "INVALID_RESULT",
                    "message": "; ".join(result_errors),
                    "stage": "result",
                },
            }
    return {"ok": True, "tool": tool_name, "result": result}
