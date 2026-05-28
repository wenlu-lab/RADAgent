"""Skill tool — invoke another skill as a subagent in a fresh subprocess.

Each call gets its own Python process and its own LLMClient → fresh context window.
The parent only sees the subagent's final stdout (its structured response).

After the subagent returns, an authoritative on-disk cross-check runs (see
gbs.step_output_check). If the subagent reported FAILURE/UNKNOWN but the
step's expected output files are present and valid on disk, the cross-check
overrides the result so the orchestrator does not retry/give-up on work
that actually succeeded. This guards against Qwen judgment errors where
the bioinformatics work completed but the agent failed to summarize it.
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path
from pydantic import BaseModel, Field
from gbs.tools._base import Tool, ToolResult
from gbs.step_output_check import outputs_valid, project_root_from


_STATUS_RE = re.compile(r"\*\*Status\*\*:\s*(SUCCESS|FAILURE|FIX_APPLIED|UNFIXABLE)", re.IGNORECASE)


def _parse_status(text: str) -> str:
    m = _STATUS_RE.search(text)
    if not m:
        return "UNKNOWN"
    raw = m.group(1).upper()
    if raw in ("SUCCESS", "FIX_APPLIED"):
        return "SUCCESS"
    return "FAILURE"


class SkillArgs(BaseModel):
    name: str = Field(..., description="Name of the skill to invoke (e.g., 'gbs-5-bwa').")
    args: str = Field("", description="Arguments string passed to the subagent's $ARGUMENTS.")


class SkillTool(Tool):
    name = "Skill"
    description = (
        "Invoke another skill as a subagent. Returns the subagent's final structured response. "
        "The subagent gets a fresh, isolated context window."
    )
    args_model = SkillArgs

    def __init__(self, parent_session_dir: str, timeout_sec: int = 86400):
        self._parent_session_dir = parent_session_dir
        self._timeout_sec = timeout_sec

    def run(self, args: SkillArgs) -> ToolResult:
        cmd = [
            sys.executable, "-m", "gbs.cli", "subagent",
            "--skill", args.name,
            "--args", args.args,
            "--session-dir", str(self._parent_session_dir),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout_sec)
        except subprocess.TimeoutExpired:
            # Subagent timed out — still cross-check: it may have written outputs before timeout.
            root = project_root_from(self._parent_session_dir)
            valid, detail = outputs_valid(args.name, root)
            if valid:
                return ToolResult(text=(
                    f"[RUNTIME CROSS-CHECK] Subagent {args.name} exceeded {self._timeout_sec}s timeout, "
                    f"but expected output files are present on disk: {detail}. Treating as SUCCESS.\n\n"
                    f"**Status**: SUCCESS (verified on disk after timeout)"
                ))
            return ToolResult(text=f"Subagent {args.name} exceeded {self._timeout_sec}s timeout", is_error=True)

        out_text = proc.stdout

        # Authoritative cross-check: run regardless of subagent's self-report. The bioinformatics
        # work may have succeeded even when (a) the subagent reported FAILURE, (b) the subagent
        # crashed (returncode != 0), or (c) the subagent's output couldn't be parsed.
        subagent_ok = (proc.returncode == 0 and _parse_status(out_text) == "SUCCESS")
        if not subagent_ok:
            root = project_root_from(self._parent_session_dir)
            valid, detail = outputs_valid(args.name, root)
            if valid:
                reason = (
                    f"returncode={proc.returncode}" if proc.returncode != 0
                    else f"status={_parse_status(out_text)}"
                )
                out_text = (
                    f"[RUNTIME CROSS-CHECK] Subagent {args.name} did not self-report SUCCESS "
                    f"({reason}), but the step's expected output files are present and valid on disk: "
                    f"{detail}. Overriding to SUCCESS.\n\n"
                    f"**Status**: SUCCESS (verified on disk by runtime cross-check)\n\n"
                    f"--- Original subagent output below ---\n"
                    f"{out_text}"
                )
                return ToolResult(text=out_text)
            # Cross-check also failed → propagate the original error
            if proc.returncode != 0:
                return ToolResult(
                    text=f"Subagent {args.name} failed: {proc.stderr.strip()}\n\n"
                         f"On-disk cross-check also failed: {detail}",
                    is_error=True,
                )
        return ToolResult(text=out_text)
