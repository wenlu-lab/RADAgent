"""Grep tool — wrapper around ripgrep (rg)."""
from __future__ import annotations
import shutil
import subprocess
from pydantic import BaseModel, Field
from rad.tools._base import Tool, ToolResult


_GREP_OUT_LIMIT = 10_000  # head+tail combined; recursive greps over the project can produce MBs


class GrepArgs(BaseModel):
    pattern: str = Field(..., description="The regex pattern to search for.")
    path: str = Field(".", description="Directory or file to search within.")
    case_insensitive: bool = Field(False, description="If true, ignore case.")
    glob: str | None = Field(None, description="Optional file glob filter (e.g., '*.py').")


class GrepTool(Tool):
    name = "Grep"
    description = "Search files for a regex pattern using ripgrep. Returns matches with file:line:content."
    args_model = GrepArgs

    def run(self, args: GrepArgs) -> ToolResult:
        rg = shutil.which("rg")
        if not rg:
            return ToolResult(text="ripgrep (rg) not installed. Install with `apt install ripgrep`.", is_error=True)
        cmd = [rg, "-n", "--no-heading"]
        if args.case_insensitive:
            cmd.append("-i")
        if args.glob:
            cmd.extend(["-g", args.glob])
        cmd.extend([args.pattern, args.path])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return ToolResult(text="Grep timed out after 30s", is_error=True)
        if proc.returncode == 1 and not proc.stdout.strip():
            return ToolResult(text=f"No matches for {args.pattern!r} in {args.path}")
        if proc.returncode not in (0, 1):
            return ToolResult(text=f"rg failed: {proc.stderr}", is_error=True)
        out = proc.stdout.strip() or "No matches."
        if len(out) > _GREP_OUT_LIMIT:
            half = _GREP_OUT_LIMIT // 2
            out = (
                f"{out[:half]}\n"
                f"[... grep output truncated; {len(out) - _GREP_OUT_LIMIT} bytes omitted; "
                f"narrow the pattern or path/glob ...]\n"
                f"{out[-half:]}"
            )
        return ToolResult(text=out)
