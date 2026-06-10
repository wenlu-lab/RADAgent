"""JSONL transcript writer for skill executions.

Output shape mirrors Claude Code's transcripts so existing tools
(browse_transcripts.py, gbs_token_tracker.py) work with minimal patching.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from gbs.llm_client import ChatMessage, ToolCall


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def fresh_agent_id() -> str:
    return f"agent-{uuid.uuid4().hex[:12]}"


def fresh_session_id() -> str:
    return uuid.uuid4().hex


class TranscriptWriter:
    """Append-only JSONL writer for one skill invocation."""

    def __init__(
        self,
        *,
        skill_name: str,
        session_dir: Path,
        agent_id: str,
        is_orchestrator: bool,
    ):
        session_dir = Path(session_dir)
        session_dir.mkdir(parents=True, exist_ok=True)
        if is_orchestrator:
            self.path = session_dir / f"{skill_name}.jsonl"
        else:
            (session_dir / "subagents").mkdir(exist_ok=True)
            self.path = session_dir / "subagents" / f"{agent_id}.jsonl"
        self._fp = self.path.open("a", encoding="utf-8")
        self._skill_name = skill_name
        self._agent_id = agent_id
        self._session_id = session_dir.name

    def _write(self, obj: dict[str, Any]) -> None:
        obj.setdefault("timestamp", _now_iso())
        obj.setdefault("session_id", self._session_id)
        obj.setdefault("agent_id", self._agent_id)
        self._fp.write(json.dumps(obj) + "\n")
        self._fp.flush()

    def record_user(self, content: str) -> None:
        self._write({
            "type": "user",
            "message": {"role": "user", "content": content},
        })

    def record_assistant(self, msg: ChatMessage, model_label: str = "qwen3-coder") -> None:
        usage_obj = {
            "input_tokens": msg.usage.input_tokens if msg.usage else 0,
            "output_tokens": msg.usage.output_tokens if msg.usage else 0,
            # The in-process backend doesn't populate Anthropic-style cache fields; record 0.
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        self._write({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": msg.content,
                "model": model_label,
                "usage": usage_obj,
            },
        })

    def record_tool_use(self, tc: ToolCall) -> None:
        self._write({
            "type": "tool_use",
            "message": {
                "tool_name": tc.name,
                "tool_input": tc.arguments,
                "tool_use_id": tc.id,
            },
        })

    def record_tool_result(self, *, tool_use_id: str, content: str) -> None:
        self._write({
            "type": "tool_result",
            "message": {"tool_use_id": tool_use_id, "content": content},
        })

    def close(self) -> None:
        self._fp.close()

    def __enter__(self) -> "TranscriptWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
