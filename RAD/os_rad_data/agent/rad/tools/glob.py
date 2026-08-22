"""Glob tool — return files matching a pattern, sorted by mtime descending."""
from __future__ import annotations
import glob as _glob
from pathlib import Path
from pydantic import BaseModel, Field
from rad.tools._base import Tool, ToolResult


class GlobArgs(BaseModel):
    pattern: str = Field(..., description="Glob pattern (e.g., '/path/to/*.py' or '/repo/**/*.tsx').")


class GlobTool(Tool):
    name = "Glob"
    description = "Find files matching a glob pattern. Returns paths sorted by modification time (newest first)."
    args_model = GlobArgs

    def run(self, args: GlobArgs) -> ToolResult:
        matches = _glob.glob(args.pattern, recursive=True)
        if not matches:
            return ToolResult(text=f"No files matched pattern: {args.pattern}")
        matches_with_mtime = [(p, Path(p).stat().st_mtime) for p in matches if Path(p).exists()]
        matches_with_mtime.sort(key=lambda x: x[1], reverse=True)
        return ToolResult(text="\n".join(p for p, _ in matches_with_mtime))
