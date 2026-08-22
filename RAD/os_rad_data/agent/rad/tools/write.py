"""Write tool — overwrites a file, creates parent dirs as needed."""
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
from rad.tools._base import Tool, ToolResult


class WriteArgs(BaseModel):
    file_path: str = Field(..., description="Absolute path to write.")
    content: str = Field(..., description="File contents (overwrites if exists).")


class WriteTool(Tool):
    name = "Write"
    description = "Write content to a file (overwrites existing). Creates parent dirs."
    args_model = WriteArgs

    def run(self, args: WriteArgs) -> ToolResult:
        p = Path(args.file_path)
        if not p.is_absolute():
            return ToolResult(text=f"Path must be absolute: {args.file_path}", is_error=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args.content)
        return ToolResult(text=f"Wrote {len(args.content)} bytes to {p}")
