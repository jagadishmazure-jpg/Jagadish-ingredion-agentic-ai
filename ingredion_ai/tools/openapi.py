"""Generate function-tools from OpenAPI 3.x documents (demo).

:func:`tools_from_openapi` walks ``paths`` and builds one
:class:`GeneratedTool` per operation with an ``operationId``:

- path/query parameters and the JSON request body become the tool's input
  JSON schema (types preserved; ``required`` honored),
- the tool calls a *transport* callable ``transport(method, path, params,
  body)`` — tests and the offline demo use a synthetic transport, production
  wires real HTTP,
- path templates (``/samples/{sampleId}``) are filled from arguments.

:func:`load_lims_openapi` loads the bundled synthetic LIMS document used as
the demo source.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# transport(method, path, params, body) -> parsed response (dict/list/...)
Transport = Callable[[str, str, Dict[str, Any], Any], Any]


def _param_schema(param: Dict[str, Any]) -> Dict[str, Any]:
    schema = dict(param.get("schema", {"type": "string"}))
    if param.get("required"):
        return schema, True
    return schema, False


def _operation_input_schema(operation: Dict[str, Any]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for param in operation.get("parameters", []):
        name = param["name"]
        schema, is_required = _param_schema(param)
        properties[name] = schema
        if is_required:
            required.append(name)
    body = operation.get("requestBody", {}).get("content", {}).get("application/json", {})
    body_schema = body.get("schema")
    if isinstance(body_schema, dict):
        for name, subschema in body_schema.get("properties", {}).items():
            properties[name] = subschema
        required.extend(body_schema.get("required", []))
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = sorted(set(required))
    return schema


@dataclass
class GeneratedTool:
    """One OpenAPI operation as a callable, schema-validated tool."""

    name: str
    description: str
    method: str
    path_template: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    transport: Optional[Transport] = None
    timeout_s: float = 10.0

    def __call__(self, **kwargs: Any) -> Dict[str, Any]:
        """Validate args, fill the path template, and call the transport."""
        from ingredion_ai.tools.sandbox import run_sandboxed

        def _invoke(**validated: Any) -> Any:
            path = self.path_template
            params: Dict[str, Any] = {}
            body: Dict[str, Any] = {}
            for key, value in validated.items():
                placeholder = "{" + key + "}"
                if placeholder in path:
                    path = path.replace(placeholder, str(value))
                elif self.method in ("GET", "DELETE"):
                    params[key] = value
                else:
                    body[key] = value
            if self.transport is None:
                raise RuntimeError(f"tool {self.name!r} has no transport bound")
            return self.transport(self.method, path, params, body or None)

        return run_sandboxed(
            _invoke,
            dict(kwargs),
            input_schema=self.input_schema,
            timeout_s=self.timeout_s,
            tool_name=self.name,
        )


def tools_from_openapi(
    doc: Dict[str, Any], transport: Transport, *, timeout_s: float = 10.0
) -> Dict[str, GeneratedTool]:
    """Build ``{operationId: GeneratedTool}`` from an OpenAPI 3.x document."""
    tools: Dict[str, GeneratedTool] = {}
    for path, item in (doc.get("paths") or {}).items():
        for method in ("get", "post", "put", "patch", "delete"):
            operation = item.get(method)
            if not isinstance(operation, dict):
                continue
            op_id = operation.get("operationId")
            if not op_id:
                continue
            tools[op_id] = GeneratedTool(
                name=op_id,
                description=operation.get("summary", operation.get("description", "")),
                method=method.upper(),
                path_template=path,
                input_schema=_operation_input_schema(operation),
                transport=transport,
                timeout_s=timeout_s,
            )
    return tools


def load_lims_openapi() -> Dict[str, Any]:
    """Load the bundled synthetic LIMS OpenAPI document."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "lims_openapi.json"), encoding="utf-8") as fh:
        return json.load(fh)


def synthetic_lims_transport(
    method: str, path: str, params: Dict[str, Any], body: Any
) -> Any:
    """Deterministic fake transport for the synthetic LIMS (offline demo).

    Serves fixed records; raises on unknown sample ids so error paths are
    exercisable.
    """
    samples = {
        "SMP-1001": {"sample_id": "SMP-1001", "product": "Clean-label cake (demo)",
                     "batch": "B-42", "received": "2026-10-01"},
        "SMP-1002": {"sample_id": "SMP-1002", "product": "Oat drink (demo)",
                     "batch": "B-43", "received": "2026-10-03"},
    }
    results = {
        "SMP-1001": [
            {"test": "moisture", "value": 21.4, "status": "pass"},
            {"test": "water_activity", "value": 0.82, "status": "pass"},
            {"test": "mold_7d", "value": 0.0, "status": "pass"},
        ],
        "SMP-1002": [
            {"test": "ph", "value": 6.8, "status": "pass"},
            {"test": "viscosity", "value": 42.0, "status": "pending"},
        ],
    }
    if method == "GET" and path.startswith("/samples/") and not path.endswith("/tests"):
        sample_id = path.rsplit("/", 1)[-1]
        if sample_id not in samples:
            raise ValueError(f"LIMS: sample {sample_id!r} not found")
        return dict(samples[sample_id])
    if method == "GET" and path.endswith("/tests"):
        sample_id = path.split("/")[-2]
        rows = results.get(sample_id)
        if rows is None:
            raise ValueError(f"LIMS: sample {sample_id!r} not found")
        status = (params or {}).get("status")
        if status:
            rows = [r for r in rows if r["status"] == status]
        return {"sample_id": sample_id, "results": rows}
    if method == "POST" and path == "/samples":
        new_id = "SMP-9000"
        return {"sample_id": new_id, "status": "registered"}
    raise ValueError(f"LIMS: unsupported {method} {path}")
