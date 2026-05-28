"""Centralized configuration: paths, model, vLLM endpoint."""
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass


def project_root() -> Path:
    """Return the project root directory (where .claude/skills/ lives)."""
    env = os.environ.get("GBS_PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    # Walk up from cwd until we find .claude/skills
    p = Path.cwd().resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".claude" / "skills").is_dir():
            return candidate
    raise RuntimeError(
        "Cannot locate project root (no .claude/skills/ found in cwd or ancestors). "
        "Set GBS_PROJECT_ROOT env var to override."
    )


@dataclass(frozen=True)
class Config:
    project_root: Path
    skills_dir: Path
    transcripts_dir: Path
    runtime_log: Path
    vllm_base_url: str
    vllm_model_name: str
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
            transcripts_dir=root / ".gbs" / "transcripts",
            runtime_log=root / ".gbs" / "runtime.log",
            vllm_base_url=os.environ.get("GBS_VLLM_URL", "http://127.0.0.1:8000/v1"),
            vllm_model_name=os.environ.get("GBS_MODEL_NAME", "qwen3-coder"),
            max_tool_calls=int(os.environ.get("GBS_MAX_TOOL_CALLS", "200")),
            max_nudges=int(os.environ.get("GBS_MAX_NUDGES", "3")),
            bash_max_timeout_ms=int(os.environ.get("GBS_BASH_MAX_TIMEOUT_MS", "3600000")),
            subagent_timeout_sec=int(os.environ.get("GBS_SUBAGENT_TIMEOUT_SEC", "86400")),
        )
