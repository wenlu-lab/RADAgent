"""Parse Phi-4 native tool-call markup into structured ToolCalls.

Phi-4 emits tool calls in an XML-ish form (the same format vLLM's
--tool-call-parser coder consumes):

    <tool_call>
    <function=Bash>
    <parameter=command>
    ls -la
    </parameter>
    </function>
    </tool_call>

Every parameter value arrives as a string; we coerce it to the type declared
in the tool's JSON schema. Unknown/failed coercions keep the raw string so the
agent loop can recover rather than crash.
"""
from __future__ import annotations
import json
import re
import uuid
from typing import Any

from rad.llm_types import ToolCall

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
_FUNCTION_RE = re.compile(r"<function=([^>\s]+)>(.*)</function>", re.DOTALL)
_PARAM_RE = re.compile(r"<parameter=([^>\s]+)>(.*?)</parameter>", re.DOTALL)


def _coerce(value: str, param_type: str | None) -> Any:
    if param_type in (None, "string"):
        return value
    if param_type == "integer":
        try:
            return int(value.strip())
        except ValueError:
            return value
    if param_type == "number":
        try:
            return float(value.strip())
        except ValueError:
            return value
    if param_type == "boolean":
        s = value.strip().lower()
        if s in ("true", "1", "yes"):
            return True
        if s in ("false", "0", "no"):
            return False
        return value
    if param_type in ("object", "array"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if param_type == "null":
        return None
    return value


def _param_types(tools: list[dict], func_name: str) -> dict[str, str | None]:
    for t in tools:
        fn = t.get("function", {})
        if fn.get("name") == func_name:
            props = fn.get("parameters", {}).get("properties", {})
            return {k: v.get("type") for k, v in props.items()}
    return {}


def _strip_one_newline(raw: str) -> str:
    if raw.startswith("\n"):
        raw = raw[1:]
    if raw.endswith("\n"):
        raw = raw[:-1]
    return raw


def parse(text: str, tools: list[dict]) -> tuple[str, list[ToolCall]]:
    """Return (content, tool_calls). content is the text outside any <tool_call> block."""
    tool_calls: list[ToolCall] = []
    for block in _TOOL_CALL_RE.finditer(text):
        fmatch = _FUNCTION_RE.search(block.group(1))
        if not fmatch:
            continue
        func_name = fmatch.group(1).strip()
        types = _param_types(tools, func_name)
        args: dict[str, Any] = {}
        for pmatch in _PARAM_RE.finditer(fmatch.group(2)):
            key = pmatch.group(1).strip()
            raw = _strip_one_newline(pmatch.group(2))
            args[key] = _coerce(raw, types.get(key))
        tool_calls.append(ToolCall(id=f"call_{uuid.uuid4().hex[:24]}", name=func_name, arguments=args))
    content = _TOOL_CALL_RE.sub("", text).strip()
    return content, tool_calls
