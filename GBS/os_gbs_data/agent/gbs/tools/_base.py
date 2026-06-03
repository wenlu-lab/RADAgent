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


def build_tool_schema(tool: Tool) -> dict[str, Any]:
    """Convert a Tool to function-calling JSON schema."""
    json_schema = tool.args_model.model_json_schema()
    # Pydantic emits "title" and "$defs" we don't need; strip noise.
    for key in ("title",):
        json_schema.pop(key, None)
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
