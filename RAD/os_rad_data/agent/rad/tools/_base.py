"""Base classes for tool implementations + the runtime that dispatches calls."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, ClassVar
from pydantic import BaseModel, ValidationError


@dataclass
class ToolResult:
    text: str
    is_error: bool = False


class Tool:
    """Base class for tools. Subclasses set name/description/args_model and implement run()."""
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    args_model: ClassVar[type[BaseModel]]

    def run(self, args: BaseModel) -> ToolResult:  # pragma: no cover — abstract
        raise NotImplementedError


def _simplify_param(spec: dict[str, Any]) -> dict[str, Any]:
    """Flatten one Pydantic property schema into the simple shape Phi-4's chat
    template expects: a concrete `type` plus optional description/default.

    Pydantic emits Optional fields as `anyOf: [{type: X}, {type: null}]` — a list —
    which the Phi-4 Jinja template can't iterate (it does `.items()` on the
    type and raises "Can only get item pairs from a mapping"). Collapse it to the
    non-null variant. Also strips Pydantic `title` noise."""
    spec = {k: v for k, v in spec.items() if k != "title"}
    if "anyOf" in spec:
        variants = [v for v in spec.pop("anyOf") if v.get("type") != "null"]
        if variants:
            for k, v in variants[0].items():
                spec.setdefault(k, v)
        else:
            spec.setdefault("type", "string")
    return spec


def build_tool_schema(tool: Tool) -> dict[str, Any]:
    """Convert a Tool to a function-calling JSON schema, sanitized for Phi-4's chat template."""
    json_schema = tool.args_model.model_json_schema()
    json_schema.pop("title", None)
    json_schema.pop("$defs", None)
    props = json_schema.get("properties", {})
    json_schema["properties"] = {name: _simplify_param(spec) for name, spec in props.items()}
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": json_schema,
        },
    }


class ToolRuntime:
    """Holds a set of tools and dispatches calls to them, optionally filtered by allowlist."""

    def __init__(self, tools: list[Tool], allowed: list[str] | None = None):
        self._tools: dict[str, Tool] = {t.name: t for t in tools}
        self._allowed: set[str] | None = set(allowed) if allowed is not None else None

    def is_allowed(self, name: str) -> bool:
        return self._allowed is None or name in self._allowed

    def execute(self, *, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name not in self._tools:
            return ToolResult(text=f"Unknown tool: {name}", is_error=True)
        if not self.is_allowed(name):
            return ToolResult(text=f"Tool {name!r} is not allowed for this skill.", is_error=True)
        tool = self._tools[name]
        try:
            args = tool.args_model.model_validate(arguments)
        except ValidationError as e:
            return ToolResult(text=f"Invalid arguments for {name}: {e}", is_error=True)
        try:
            return tool.run(args)
        except Exception as e:
            return ToolResult(text=f"{name} raised {type(e).__name__}: {e}", is_error=True)

    def tool_schemas(self) -> list[dict[str, Any]]:
        return [build_tool_schema(t) for n, t in self._tools.items() if self.is_allowed(n)]

    def descriptions(self) -> dict[str, str]:
        return {n: t.description for n, t in self._tools.items() if self.is_allowed(n)}
