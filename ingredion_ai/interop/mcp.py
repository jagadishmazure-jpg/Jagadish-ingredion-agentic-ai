"""Model Context Protocol (MCP) server facade (demo, dependency-light).

Exposes the domain agents' deterministic ``execute()`` task paths as MCP
tools so external MCP clients can invoke them. Implements the core MCP
message shapes over JSON-RPC 2.0:

- ``initialize`` → capability handshake (server name/version/capabilities)
- ``tools/list`` → tool names, descriptions, JSON-Schema input schemas
- ``tools/call`` → invoke a tool, returns ``CallToolResult``-shaped content

The message core (``MCPServer.handle_message``) is transport-agnostic:
``serve_stdio()`` wires it to stdin/stdout today; a Streamable HTTP/SSE
transport can wrap the same method later (see docs/integrations.md).
``InProcessClient`` is an in-memory client for offline tests.

Stdlib only. All data synthetic; everything runs offline.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, Dict, List, Optional

from ingredion_ai.agents import (
    CustomerAdvisorAgent,
    ESGAgent,
    RDFormulationAgent,
    SupplyChainAgent,
)
from ingredion_ai.data.loader import get_formula

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "ingredion-agentic-ai-mcp"
SERVER_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Tool definitions: name -> (description, JSON Schema, payload builder)
# Each builder maps client arguments to the domain agent's execute() payload,
# reusing the exact tested code paths.
# ---------------------------------------------------------------------------

_rd = RDFormulationAgent()
_sc = SupplyChainAgent()
_esg = ESGAgent()
_ca = CustomerAdvisorAgent()


def _rd_payload(formula_id: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "formula_id": formula_id,
        "target_claims": [],
        "region": "NA",
        "adjustments": None,
        "additions": None,
        "blackboard": {},
    }
    payload.update(extra)
    return payload


def _tool_analyze_ingredients(args: Dict[str, Any]) -> Dict[str, Any]:
    return _rd.execute("analyze_ingredients", _rd_payload(args["formula_id"]))


def _tool_suggest_substitutes(args: Dict[str, Any]) -> Dict[str, Any]:
    return _rd.execute("suggest_substitutes", _rd_payload(args["formula_id"]))


def _tool_validate_claims(args: Dict[str, Any]) -> Dict[str, Any]:
    return _rd.execute(
        "validate_claims",
        _rd_payload(
            args["formula_id"],
            target_claims=args.get("target_claims", []),
            region=args.get("region", "NA"),
        ),
    )


def _tool_forecast_demand(args: Dict[str, Any]) -> Dict[str, Any]:
    return _sc.execute(
        "forecast_demand",
        {"skus": args.get("skus", ["PF-200"]), "periods": args.get("periods", 4)},
    )


def _tool_optimize_inventory(args: Dict[str, Any]) -> Dict[str, Any]:
    # Chain forecast -> optimize, pulling inventory from the (demo) SAP adapter.
    from ingredion_ai.data.loader import load_demand
    from ingredion_ai.integrations.sap import sap_from_env

    plant_id = args.get("plant_id", "PLANT-NA-01")
    inv = sap_from_env().get_inventory(plant_id)
    demand_skus = {r["sku"] for r in load_demand()}
    skus = args.get("skus") or [s for s in inv if s in demand_skus]
    periods = args.get("periods", 4)
    fc = _sc.execute("forecast_demand", {"skus": skus, "periods": periods})
    forecasts_weekly = {
        sku: f["forecast"] for sku, f in fc["forecasts"].items()
    }
    return _sc.execute(
        "optimize_inventory",
        {"plant_id": plant_id, "forecasts_weekly": forecasts_weekly},
    )


def _tool_generate_esg_report(args: Dict[str, Any]) -> Dict[str, Any]:
    return _esg.execute("esg_report", {"period": args.get("period", "Q1-Q2 (demo)")})


def _tool_recommend_ingredients(args: Dict[str, Any]) -> Dict[str, Any]:
    return _ca.execute(
        "recommend_ingredients",
        {
            "category": args.get("category"),
            "claims": tuple(args.get("claims", ("clean_label",))),
            "region": args.get("region", "NA"),
            "max_results": args.get("max_results", 10),
        },
    )


def _tool_estimate_pricing(args: Dict[str, Any]) -> Dict[str, Any]:
    return _ca.execute(
        "estimate_pricing",
        {
            "formula": get_formula(args["formula_id"]),
            "valid_claims": args.get("valid_claims", []),
            "account_id": args.get("account_id"),
        },
    )


_TOOL_DEFS: List[Dict[str, Any]] = [
    {
        "name": "analyze_ingredients",
        "description": "Flag non-clean-label ingredients in a demo formula.",
        "inputSchema": {
            "type": "object",
            "properties": {"formula_id": {"type": "string"}},
            "required": ["formula_id"],
        },
        "handler": _tool_analyze_ingredients,
    },
    {
        "name": "suggest_substitutes",
        "description": "Recommend clean-label substitutes and build the reformulated formula.",
        "inputSchema": {
            "type": "object",
            "properties": {"formula_id": {"type": "string"}},
            "required": ["formula_id"],
        },
        "handler": _tool_suggest_substitutes,
    },
    {
        "name": "validate_claims",
        "description": "Validate label claims for a demo formula per region.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "formula_id": {"type": "string"},
                "target_claims": {"type": "array", "items": {"type": "string"}},
                "region": {"type": "string", "default": "NA"},
            },
            "required": ["formula_id"],
        },
        "handler": _tool_validate_claims,
    },
    {
        "name": "forecast_demand",
        "description": "Forecast weekly ingredient demand for demo SKUs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skus": {"type": "array", "items": {"type": "string"}},
                "periods": {"type": "integer", "default": 4},
            },
        },
        "handler": _tool_forecast_demand,
    },
    {
        "name": "optimize_inventory",
        "description": (
            "Suggest purchase orders using the demo SAP adapter inventory "
            "for a plant plus a demand forecast."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "plant_id": {"type": "string", "default": "PLANT-NA-01"},
                "skus": {"type": "array", "items": {"type": "string"}},
                "periods": {"type": "integer", "default": 4},
            },
        },
        "handler": _tool_optimize_inventory,
    },
    {
        "name": "generate_esg_report",
        "description": "Generate a markdown ESG report draft from synthetic plant readings.",
        "inputSchema": {
            "type": "object",
            "properties": {"period": {"type": "string", "default": "Q1-Q2 (demo)"}},
        },
        "handler": _tool_generate_esg_report,
    },
    {
        "name": "recommend_ingredients",
        "description": "Recommend demo ingredients filtered by category, claims, and region.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "claims": {"type": "array", "items": {"type": "string"}},
                "region": {"type": "string", "default": "NA"},
                "max_results": {"type": "integer", "default": 10},
            },
        },
        "handler": _tool_recommend_ingredients,
    },
    {
        "name": "estimate_pricing",
        "description": (
            "Estimate cost and willingness-to-pay pricing bands for a demo "
            "formula, optionally personalized with demo CRM account context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "formula_id": {"type": "string"},
                "valid_claims": {"type": "array", "items": {"type": "string"}},
                "account_id": {"type": "string"},
            },
            "required": ["formula_id"],
        },
        "handler": _tool_estimate_pricing,
    },
]


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


class MCPServer:
    """JSON-RPC 2.0 MCP server facade over the domain tools."""

    def __init__(
        self, name: str = SERVER_NAME, version: str = SERVER_VERSION
    ) -> None:
        self.name = name
        self.version = version
        self._tools: Dict[str, Dict[str, Any]] = {
            t["name"]: t for t in _TOOL_DEFS
        }

    # -- MCP methods ------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["inputSchema"],
            }
            for t in _TOOL_DEFS
        ]

    def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Invoke a tool; returns a CallToolResult-shaped dict."""
        tool = self._tools.get(name)
        if tool is None:
            return self._tool_error(f"unknown tool: {name!r}")
        try:
            result = tool["handler"](arguments or {})
            text = json.dumps(result, default=str)
            return {
                "content": [{"type": "text", "text": text}],
                "isError": False,
            }
        except Exception as exc:  # noqa: BLE001 - surfaced as tool error
            return self._tool_error(f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _tool_error(message: str) -> Dict[str, Any]:
        return {"content": [{"type": "text", "text": message}], "isError": True}

    # -- JSON-RPC dispatch (transport-agnostic) ----------------------------

    def handle_message(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle one JSON-RPC 2.0 message; None for notifications."""
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params", {}) or {}

        def ok(result: Any) -> Dict[str, Any]:
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}

        def err(code: int, message: str) -> Dict[str, Any]:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": code, "message": message},
            }

        if method == "initialize":
            return ok(
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": self.version},
                }
            )
        if method == "notifications/initialized":
            return None  # notification: no response
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": self.list_tools()})
        if method == "tools/call":
            name = params.get("name")
            if not name:
                return err(-32602, "tools/call requires params.name")
            return ok(self.call_tool(name, params.get("arguments")))
        return err(-32601, f"method not found: {method}")

    def serve_stdio(self) -> None:
        """Serve JSON-RPC over stdin/stdout (one message per line)."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                sys.stdout.write(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {"code": -32700, "message": "parse error"},
                        }
                    )
                    + "\n"
                )
                sys.stdout.flush()
                continue
            response = self.handle_message(msg)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()


# ---------------------------------------------------------------------------
# In-process client (offline tests)
# ---------------------------------------------------------------------------


class InProcessClient:
    """Minimal MCP client that talks to an MCPServer in-process."""

    def __init__(self, server: Optional[MCPServer] = None) -> None:
        self.server = server or MCPServer()
        self._next_id = 0

    def _request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self._next_id += 1
        response = self.server.handle_message(
            {"jsonrpc": "2.0", "id": self._next_id, "method": method,
             "params": params or {}}
        )
        assert response is not None, f"no response for {method}"
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        return response["result"]

    def initialize(self) -> Dict[str, Any]:
        result = self._request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "in-process-test-client", "version": "0.1.0"},
            },
        )
        self.server.handle_message(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        return self._request("tools/list")["tools"]

    def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return self._request(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
