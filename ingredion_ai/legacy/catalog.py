"""Capability catalog: legacy operations as versioned agent function-tools (demo).

Each legacy operation is registered as a :class:`ToolSpec` — a versioned,
JSON-schema-described tool. Agents discover tools through the catalog
instead of hard-coding integrations, and :meth:`CapabilityCatalog.get`
resolves the latest non-deprecated version by default.

Deprecation is a first-class signal: deprecated tools stay callable (with a
deprecation notice in the envelope) until removed, so consumers can migrate
on a schedule instead of breaking overnight.

All demo data is synthetic and fictional. Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ingredion_ai.legacy.bridge import LegacyBridge


@dataclass
class ToolSpec:
    """One versioned legacy operation exposed as an agent tool."""

    name: str
    version: str = "1.0"
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    deprecated: bool = False
    deprecation_message: str = ""
    bridge: Optional[LegacyBridge] = None
    operation: str = ""

    def key(self) -> Tuple[str, str]:
        return (self.name, self.version)


class CatalogError(Exception):
    """Raised for catalog misuse (unknown tool, ambiguous version, ...)."""


def _version_tuple(version: str) -> Tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (0,)


class CapabilityCatalog:
    """Registry of versioned legacy-operation tools."""

    def __init__(self) -> None:
        self._specs: Dict[str, List[ToolSpec]] = {}

    # -- registration ---------------------------------------------------

    def register(self, spec: ToolSpec) -> None:
        """Register *spec*; duplicate (name, version) pairs are rejected."""
        existing = self._specs.setdefault(spec.name, [])
        if any(s.version == spec.version for s in existing):
            raise CatalogError(
                f"duplicate registration: {spec.name} v{spec.version}"
            )
        existing.append(spec)
        existing.sort(key=lambda s: _version_tuple(s.version))

    def register_bridge_operations(
        self,
        bridge: LegacyBridge,
        operations: List[Dict[str, Any]],
        *,
        version: str = "1.0",
    ) -> None:
        """Bulk-register a bridge's operations.

        Each entry: ``{"name", "operation", "description", "input_schema",
        "output_schema"?}``. The tool name is prefixed with the bridge name
        (``crm.get_account``) to keep multi-system catalogs collision-free.
        """
        for entry in operations:
            self.register(
                ToolSpec(
                    name=f"{bridge.name}.{entry['name']}",
                    version=version,
                    description=entry.get("description", ""),
                    input_schema=entry.get("input_schema", {"type": "object"}),
                    output_schema=entry.get("output_schema", {"type": "object"}),
                    bridge=bridge,
                    operation=entry["operation"],
                )
            )

    # -- lookup ----------------------------------------------------------

    def get(
        self, name: str, version: Optional[str] = None, *, allow_deprecated: bool = False
    ) -> ToolSpec:
        """Resolve *name* to a spec.

        With no *version*, returns the latest non-deprecated version (or the
        latest overall when ``allow_deprecated=True`` and nothing else exists).
        """
        specs = self._specs.get(name)
        if not specs:
            raise CatalogError(f"unknown tool: {name!r}")
        if version is not None:
            for spec in specs:
                if spec.version == version:
                    if spec.deprecated and not allow_deprecated:
                        raise CatalogError(
                            f"tool {name} v{version} is deprecated: {spec.deprecation_message}"
                        )
                    return spec
            raise CatalogError(f"unknown version {version!r} for tool {name!r}")
        candidates = [s for s in specs if not s.deprecated] or (
            specs if allow_deprecated else []
        )
        if not candidates:
            raise CatalogError(
                f"tool {name!r} has only deprecated versions; "
                "pass allow_deprecated=True to use one"
            )
        return candidates[-1]  # sorted ascending -> latest

    def list(self, *, include_deprecated: bool = False) -> List[ToolSpec]:
        """All specs, optionally including deprecated ones."""
        out = []
        for specs in self._specs.values():
            out.extend(s for s in specs if include_deprecated or not s.deprecated)
        return sorted(out, key=lambda s: (s.name, _version_tuple(s.version)))

    def deprecate(self, name: str, version: str, message: str) -> None:
        """Mark one version deprecated with a migration message."""
        for spec in self._specs.get(name, []):
            if spec.version == version:
                spec.deprecated = True
                spec.deprecation_message = message
                return
        raise CatalogError(f"unknown tool version: {name} v{version}")

    # -- execution --------------------------------------------------------

    def call(
        self, name: str, args: Dict[str, Any], *, allow_deprecated: bool = False
    ) -> Dict[str, Any]:
        """Validate *args* against the input schema and invoke the bridge.

        Returns the bridge envelope, extended with ``tool``, ``tool_version``
        and (when deprecated) a ``deprecation`` notice.
        """
        from ingredion_ai.tools.sandbox import validate_against_schema

        spec = self.get(name, allow_deprecated=allow_deprecated)
        errors = validate_against_schema(args, spec.input_schema)
        if errors:
            return {
                "ok": False,
                "tool": spec.name,
                "tool_version": spec.version,
                "error": {"code": "INVALID_ARGS", "message": "; ".join(errors)},
            }
        if spec.bridge is None:
            return {
                "ok": False,
                "tool": spec.name,
                "tool_version": spec.version,
                "error": {"code": "NO_BRIDGE", "message": "tool has no bridge bound"},
            }
        envelope = spec.bridge.call(spec.operation, args)
        envelope["tool"] = spec.name
        envelope["tool_version"] = spec.version
        if spec.deprecated:
            envelope["deprecation"] = spec.deprecation_message or (
                f"{spec.name} v{spec.version} is deprecated"
            )
        return envelope

    def as_function_tools(
        self, *, allow_deprecated: bool = False
    ) -> Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]]:
        """``{tool_name: fn}`` where ``fn(args_dict)`` returns the envelope.

        Suitable for wiring catalog tools into agent tool lists.
        """
        return {
            spec.name: (
                lambda args, _name=spec.name: self.call(
                    _name, args, allow_deprecated=allow_deprecated
                )
            )
            for spec in self.list(include_deprecated=allow_deprecated)
        }
