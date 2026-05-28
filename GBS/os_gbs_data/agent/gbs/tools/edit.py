"""Edit tool — exact-string replacement in a file."""
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
from gbs.tools._base import Tool, ToolResult


class EditArgs(BaseModel):
    file_path: str = Field(..., description="Absolute path to the file to edit.")
    old_string: str = Field(..., description="The text to replace.")
    new_string: str = Field(..., description="The replacement text. Must differ from old_string.")
    replace_all: bool = Field(False, description="If true, replace every occurrence; else require unique.")


class EditTool(Tool):
    name = "Edit"
    description = "Replace exact string in a file. Fails if old_string is not unique unless replace_all=true."
    args_model = EditArgs

    def run(self, args: EditArgs) -> ToolResult:
        p = Path(args.file_path)
        if not p.is_absolute():
            return ToolResult(text=f"Path must be absolute: {args.file_path}", is_error=True)
        if not p.is_file():
            return ToolResult(text=f"File not found: {args.file_path}", is_error=True)
        if args.old_string == args.new_string:
            return ToolResult(text="old_string and new_string are identical; no-op rejected.", is_error=True)
        text = p.read_text()
        count = text.count(args.old_string)
        if count == 0:
            return ToolResult(text=f"old_string not found in {p}", is_error=True)
        if count > 1 and not args.replace_all:
            return ToolResult(
                text=f"old_string occurs {count} times in {p}; pass replace_all=true or make it unique.",
                is_error=True,
            )
        new_text = text.replace(args.old_string, args.new_string) if args.replace_all else text.replace(args.old_string, args.new_string, 1)
        p.write_text(new_text)
        return ToolResult(text=f"Replaced {count if args.replace_all else 1} occurrence(s) in {p}")
