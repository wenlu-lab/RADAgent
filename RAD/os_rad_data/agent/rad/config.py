"""Centralized configuration: paths and in-process model settings."""
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass


def project_root() -> Path:
    """Return the project root directory (where .claude/skills/ lives)."""
    env = os.environ.get("RAD_PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    # Walk up from cwd until we find .claude/skills
    p = Path.cwd().resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".claude" / "skills").is_dir():
            return candidate
    raise RuntimeError(
        "Cannot locate project root (no .claude/skills/ found in cwd or ancestors). "
        "Set RAD_PROJECT_ROOT env var to override."
    )


@dataclass(frozen=True)
class Config:
    project_root: Path
    skills_dir: Path
    transcripts_dir: Path
    runtime_log: Path
    model_id: str
    torch_dtype: str
    device_map: str
    max_context_tokens: int
    model_label: str
    max_tool_calls: int
    max_nudges: int
    bash_max_timeout_ms: int
    subagent_timeout_sec: int

    @classmethod
    def load(cls) -> "Config":
        root = project_root()
        return cls(
            project_root=root,
            skills_dir=root / ".claude" / "skills",
            transcripts_dir=root / ".rad" / "transcripts",
            runtime_log=root / ".rad" / "runtime.log",
            # bf16 checkpoint: loads on Ampere (A100, compute 8.0). The -FP8 variant
            # needs compute >= 8.9 (Ada/Hopper) in transformers; override via RAD_MODEL_ID there.
            model_id=os.environ.get("RAD_MODEL_ID", "microsoft/Phi-4"),
            torch_dtype=os.environ.get("RAD_TORCH_DTYPE", "auto"),
            device_map=os.environ.get("RAD_DEVICE_MAP", "auto"),
            max_context_tokens=int(os.environ.get("RAD_MAX_CONTEXT_TOKENS", "32768")),
            model_label=os.environ.get("RAD_MODEL_LABEL", "phi-4"),
            max_tool_calls=int(os.environ.get("RAD_MAX_TOOL_CALLS", "200")),
            max_nudges=int(os.environ.get("RAD_MAX_NUDGES", "3")),
            bash_max_timeout_ms=int(os.environ.get("RAD_BASH_MAX_TIMEOUT_MS", "3600000")),
            subagent_timeout_sec=int(os.environ.get("RAD_SUBAGENT_TIMEOUT_SEC", "86400")),
        )
