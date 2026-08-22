"""Skill tool — invoke another skill as a subagent, in-process.

Calls run_skill() directly (not a subprocess): the singleton model stays
resident and each subagent still gets a fresh, isolated context window (a new
messages list inside run_skill).

After the subagent returns, an authoritative on-disk cross-check runs (see
rad.step_output_check). If the subagent did not self-report SUCCESS but the
step's expected output files are present and valid on disk, the cross-check
overrides the result so the orchestrator does not retry/give-up on work that
actually succeeded."""
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
from rad.tools._base import Tool, ToolResult
from rad.step_output_check import outputs_valid, project_root_from


class SkillArgs(BaseModel):
    name: str = Field(..., description="Name of the skill to invoke (e.g., 'rad-5-bwa').")
    args: str = Field("", description="Arguments string passed to the subagent's $ARGUMENTS.")


class SkillTool(Tool):
    name = "Skill"
    description = (
        "Invoke another skill as a subagent. Returns the subagent's final structured response. "
        "The subagent gets a fresh, isolated context window."
    )
    args_model = SkillArgs

    def __init__(self, parent_session_dir: str):
        self._parent_session_dir = parent_session_dir

    def run(self, args: SkillArgs) -> ToolResult:
        from rad.runtime import run_skill  # lazy import avoids runtime<->skill cycle
        root = project_root_from(self._parent_session_dir)
        try:
            result = run_skill(
                skill_name=args.name,
                args=args.args,
                session_dir=Path(self._parent_session_dir),
                is_orchestrator=False,
            )
        except Exception as e:
            valid, detail = outputs_valid(args.name, root)
            if valid:
                return ToolResult(text=(
                    f"[RUNTIME CROSS-CHECK] Subagent {args.name} raised {type(e).__name__}: {e}, "
                    f"but expected output files are present and valid on disk: {detail}. "
                    f"Treating as SUCCESS.\n\n"
                    f"**Status**: SUCCESS (verified on disk after exception)"
                ))
            return ToolResult(
                text=f"Subagent {args.name} raised {type(e).__name__}: {e}\n\n"
                     f"On-disk cross-check also failed: {detail}",
                is_error=True,
            )

        out_text = result.text
        if result.status != "SUCCESS":
            valid, detail = outputs_valid(args.name, root)
            if valid:
                out_text = (
                    f"[RUNTIME CROSS-CHECK] Subagent {args.name} did not self-report SUCCESS "
                    f"(status={result.status}), but the step's expected output files are present "
                    f"and valid on disk: {detail}. Overriding to SUCCESS.\n\n"
                    f"**Status**: SUCCESS (verified on disk by runtime cross-check)\n\n"
                    f"--- Original subagent output below ---\n{out_text}"
                )
        return ToolResult(text=out_text)
