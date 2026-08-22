"""The core tool-calling loop. Used identically by orchestrator and subagent."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from rad.config import Config
from rad.skill_loader import load_skill, build_system_prompt, Skill
from rad.llm_client import LLMClient
from rad.transcript import TranscriptWriter, fresh_agent_id
from rad.tools._base import Tool, ToolRuntime
from rad.tools.bash import BashTool
from rad.tools.read import ReadTool
from rad.tools.write import WriteTool
from rad.tools.edit import EditTool
from rad.tools.glob import GlobTool
from rad.tools.grep import GrepTool
from rad.tools.skill import SkillTool


class BudgetExhausted(Exception):
    pass


# Conservative cap on total chars in `messages`. In-process transformers has no
# PagedAttention, so the effective window is much smaller than vLLM's 262144.
# At ~3.5 chars/token, the per-run budget is derived from cfg.max_context_tokens
# (see run_skill); this default is only a fallback when no budget is passed.
_DEFAULT_CONTEXT_CHAR_BUDGET = 100_000
_CHARS_PER_TOKEN = 3.5


def _trim_messages(messages: list[dict], char_budget: int = _DEFAULT_CONTEXT_CHAR_BUDGET) -> list[dict]:
    """If `messages` exceeds the char budget, replace the BODY of the oldest
    tool-result messages with a placeholder. Keep the system prompt, the
    initial user message, and never trim the most recent few exchanges.
    Mutates and returns `messages`."""
    total = sum(len(str(m.get("content", "") or "")) for m in messages)
    if total <= char_budget:
        return messages
    # Walk from the front (after system + first user), trimming tool results.
    placeholder = "[older tool result trimmed to keep context within model's window]"
    # Don't trim the last 6 messages (≈ last 2-3 turns).
    cutoff = max(2, len(messages) - 6)
    for i in range(cutoff):
        m = messages[i]
        if m.get("role") == "tool" and m.get("content") != placeholder:
            m["content"] = placeholder
            total = sum(len(str(mm.get("content", "") or "")) for mm in messages)
            if total <= char_budget:
                return messages
    return messages


@dataclass
class SkillResult:
    text: str
    status: Literal["SUCCESS", "FAILURE", "UNKNOWN"]
    transcript_path: Path


_STATUS_RE = re.compile(r"\*\*Status\*\*:\s*(SUCCESS|FAILURE|FIX_APPLIED|UNFIXABLE)", re.IGNORECASE)


def parse_status(text: str) -> str:
    """Extract status marker from skill output. Treats FIX_APPLIED as SUCCESS for orchestrator parsing."""
    m = _STATUS_RE.search(text)
    if not m:
        return "UNKNOWN"
    raw = m.group(1).upper()
    if raw in ("SUCCESS", "FIX_APPLIED"):
        return "SUCCESS"
    if raw in ("FAILURE", "UNFIXABLE"):
        return "FAILURE"
    return "UNKNOWN"


def _build_all_tools(parent_session_dir: Path) -> list[Tool]:
    return [
        BashTool(),
        ReadTool(),
        WriteTool(),
        EditTool(),
        GlobTool(),
        GrepTool(),
        SkillTool(parent_session_dir=str(parent_session_dir)),
    ]


def run_skill(
    skill_name: str,
    args: str,
    session_dir: Path,
    *,
    is_orchestrator: bool,
    config: Config | None = None,
) -> SkillResult:
    """Execute one skill end-to-end. Returns the structured response and parsed status."""
    cfg = config or Config.load()
    skill = load_skill(skill_name, config=cfg)
    all_tools = _build_all_tools(parent_session_dir=session_dir)
    runtime = ToolRuntime(tools=all_tools, allowed=skill.allowed_tools)
    system_prompt = build_system_prompt(skill, runtime.descriptions())

    agent_id = fresh_agent_id()
    transcript = TranscriptWriter(
        skill_name=skill_name,
        session_dir=Path(session_dir),
        agent_id=agent_id,
        is_orchestrator=is_orchestrator,
    )
    user_msg = f"$ARGUMENTS: {args}"
    transcript.record_user(user_msg)

    client = LLMClient(
        model_id=cfg.model_id,
        torch_dtype=cfg.torch_dtype,
        device_map=cfg.device_map,
        max_context_tokens=cfg.max_context_tokens,
    )
    char_budget = int(cfg.max_context_tokens * _CHARS_PER_TOKEN)
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    recent_sigs: list[tuple] = []
    nudges_used = 0

    for _ in range(cfg.max_tool_calls):
        _trim_messages(messages, char_budget)
        response = client.chat(
            messages=messages,
            tools=runtime.tool_schemas(),
        )
        transcript.record_assistant(response, model_label=skill.model_label)

        if not response.tool_calls:
            transcript.close()
            return SkillResult(
                text=response.content,
                status=parse_status(response.content),
                transcript_path=transcript.path,
            )

        # Append assistant message (with tool calls) to message history
        assistant_msg: dict = {"role": "assistant", "content": response.content or None}
        if response.tool_calls:
            # Phi-4's in-process chat template calls .items() on each tool call's
            # `arguments`, so it must be a dict (not the OpenAI/vLLM JSON string).
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in response.tool_calls
            ]
        messages.append(assistant_msg)

        for tc in response.tool_calls:
            transcript.record_tool_use(tc)
            tool_result = runtime.execute(name=tc.name, arguments=tc.arguments)
            transcript.record_tool_result(tool_use_id=tc.id, content=tool_result.text)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result.text,
            })

        # Loop-detection nudge: open-source models like Phi-4 lack the
        # natural "task complete, summarize" instinct of Claude. If the same
        # tool call(s) repeat 3 turns in a row, inject a user message asking
        # for the structured summary.
        sig = tuple(sorted((tc.name, json.dumps(tc.arguments, sort_keys=True)) for tc in response.tool_calls))
        recent_sigs.append(sig)
        if len(recent_sigs) >= 3 and len(set(recent_sigs[-3:])) == 1 and nudges_used < cfg.max_nudges:
            nudges_used += 1
            nudge_msg = (
                "You have made the same tool call 3 turns in a row. The task is either "
                "complete or you are stuck. Stop calling tools. In your next message, "
                "output ONLY the structured summary required by the skill. Begin with a "
                "line:\n**Status**: SUCCESS\n(or FAILURE / FIX_APPLIED / UNFIXABLE.)"
            )
            messages.append({"role": "user", "content": nudge_msg})
            transcript.record_user(nudge_msg)
            recent_sigs = []

    transcript.close()
    raise BudgetExhausted(f"Skill {skill_name} exceeded {cfg.max_tool_calls} tool calls without final answer")
