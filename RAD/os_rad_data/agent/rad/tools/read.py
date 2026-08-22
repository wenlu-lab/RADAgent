"""Read tool — line-numbered file reading with offset/limit."""
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
from rad.tools._base import Tool, ToolResult


class ReadArgs(BaseModel):
    file_path: str = Field(..., description="Absolute path to the file to read.")
    offset: int = Field(0, description="1-based line to start at (0 means start of file).")
    limit: int = Field(2000, description="Max number of lines to return.")


class ReadTool(Tool):
    name = "Read"
    description = "Read a file from the filesystem. Returns line-numbered output (1\\tcontent)."
    args_model = ReadArgs

    def run(self, args: ReadArgs) -> ToolResult:
        p = Path(args.file_path)
        if not p.is_absolute():
            return ToolResult(text=f"Path must be absolute: {args.file_path}", is_error=True)
        if not p.is_file():
            return ToolResult(text=f"File not found: {args.file_path}", is_error=True)
        lines = p.read_text(errors="replace").splitlines()
        start = max(args.offset, 1) - 1 if args.offset > 0 else 0
        end = start + args.limit
        sliced = lines[start:end]
        out = "\n".join(f"{start + i + 1}\t{line}" for i, line in enumerate(sliced))
        return ToolResult(text=out)
