"""Shared LLM result types. Kept separate from llm_client so the tool-call
parser can import ToolCall without a circular import."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage | None = None
