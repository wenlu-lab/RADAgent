"""Bash tool — runs shell commands with configurable timeout, output truncation."""
from __future__ import annotations
import os
import subprocess
import tempfile
from pydantic import BaseModel, Field
from rad.tools._base import Tool, ToolResult


_TRUNCATE_TOTAL = 30_000   # 30 KB head+tail combined
_TRUNCATE_HEAD = 15_000
_TRUNCATE_TAIL = 15_000
_DEFAULT_TIMEOUT_MS = 120_000           # 2 min default
_MAX_TIMEOUT_MS = 3_600_000              # 1 h ceiling (overridable via env)


def _max_timeout_ms() -> int:
    return int(os.environ.get("RAD_BASH_MAX_TIMEOUT_MS", _MAX_TIMEOUT_MS))


def _truncate(text: str) -> str:
    if len(text) <= _TRUNCATE_TOTAL:
        return text
    head = text[:_TRUNCATE_HEAD]
    tail = text[-_TRUNCATE_TAIL:]
    return f"{head}\n[... output truncated; {len(text) - _TRUNCATE_TOTAL} bytes omitted ...]\n{tail}"


class BashArgs(BaseModel):
    command: str = Field(..., description="The shell command to run.")
    timeout: int = Field(_DEFAULT_TIMEOUT_MS, description="Timeout in milliseconds (max 3,600,000 = 1 h).")
    description: str | None = Field(None, description="Optional one-line description (informational only).")


class BashTool(Tool):
    name = "Bash"
    description = (
        "Execute a shell command. Default timeout 120000ms; max 3600000ms (1h) for long polls. "
        "Returns combined stdout+stderr (truncated head+tail at 30KB)."
    )
    args_model = BashArgs

    def run(self, args: BashArgs) -> ToolResult:
        max_ms = _max_timeout_ms()
        timeout_ms = min(max(args.timeout, 1), max_ms)
        timeout_sec = timeout_ms / 1000.0
        # Write the command to a temp script file rather than passing it via
        # `bash -c`. This keeps the command text out of bash's argv, so SKILL
        # patterns like `pgrep -f 'gstacks'` don't self-match the wrapping
        # shell process. /proc/PID/cmdline of the subprocess will read
        # "bash /tmp/xxx.sh" — pgrep -f looks at cmdline, not file contents.
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
            f.write(args.command)
            if not args.command.endswith("\n"):
                f.write("\n")
            script_path = f.name
        try:
            proc = subprocess.run(
                ["/bin/bash", script_path],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                text=f"Bash command timed out after {timeout_sec:.0f}s: {args.command}",
                is_error=True,
            )
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass
        out = (proc.stdout or "") + (proc.stderr or "")
        out = _truncate(out)
        if proc.returncode != 0:
            out = f"[exit {proc.returncode}]\n{out}"
        return ToolResult(text=out or "(no output)")
