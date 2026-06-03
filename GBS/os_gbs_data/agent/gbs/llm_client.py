"""Thin wrapper around Hugging Face InferenceClient pointed at vLLM.

Encapsulates: client construction, request timeouts (1h for long Bash polls),
and response normalization into our internal types.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any
from huggingface_hub import InferenceClient


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


class LLMClient:
    """Calls vLLM's /v1/chat/completions endpoint via Hugging Face InferenceClient."""

    def __init__(self, base_url: str, model_name: str, request_timeout: float = 3600.0):
        # api_key is required by the client but vLLM doesn't validate it.
        self._client = InferenceClient(base_url=base_url, api_key="not-needed", timeout=request_timeout)
        self._model_name = model_name

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> ChatMessage:
        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                # InferenceClient may return arguments as a JSON string or an
                # already-parsed dict (behavior varies by version); handle both.
                raw = tc.function.arguments
                if isinstance(raw, str):
                    try:
                        args = json.loads(raw)
                    except json.JSONDecodeError:
                        args = {"_raw": raw}
                elif isinstance(raw, dict):
                    args = raw
                else:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        usage = TokenUsage(
            input_tokens=getattr(response.usage, "prompt_tokens", 0),
            output_tokens=getattr(response.usage, "completion_tokens", 0),
        )
        return ChatMessage(content=msg.content or "", tool_calls=tool_calls, usage=usage)
