"""Command-line entry point: ./gbs <subcommand> [args...]"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
from gbs.config import Config
from gbs.transcript import fresh_session_id
from gbs.runtime import run_skill, BudgetExhausted


def _vllm_alive(base_url: str, timeout: float = 5.0) -> bool:
    url = base_url.rstrip("/") + "/models"
    try:
        with urlopen(Request(url), timeout=timeout) as resp:
            return resp.status == 200
    except URLError:
        return False


def _gpu_free_mb() -> int | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return None
        return int(out.stdout.strip().splitlines()[0])
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None


def _preflight(cfg: Config) -> None:
    """Pre-flight checks before running the orchestrator. Exits with helpful message on failure."""
    if not _vllm_alive(cfg.vllm_base_url):
        sys.exit(
            f"vLLM not reachable at {cfg.vllm_base_url}.\n"
            f"Start it with: ./infra/vllm_serve.sh   (or `./gbs serve`)"
        )
    if not (cfg.project_root / "02-raw").is_dir() or not (cfg.project_root / "00-scripts").is_dir():
        sys.exit(f"Not in project root (no 02-raw/ or 00-scripts/): {cfg.project_root}")
    # Note: when vLLM is running with --gpu-memory-utilization 0.92, "free" GPU
    # memory will be small (~5 GB on an 80 GB card) — that's the system overhead
    # left over after vLLM reserves model weights + KV cache budget. Only fail
    # if the card is essentially full (another GPU process is hogging memory).
    free = _gpu_free_mb()
    if free is not None and free < 500:
        sys.exit(f"GPU has only {free}MB free; another GPU process may be running.")


def cmd_status(args, cfg: Config) -> int:
    print(f"Project root: {cfg.project_root}")
    print(f"Skills dir:   {cfg.skills_dir}")
    print(f"vLLM URL:     {cfg.vllm_base_url}")
    print(f"vLLM alive:   {_vllm_alive(cfg.vllm_base_url)}")
    print(f"Model name:   {cfg.vllm_model_name}")
    free = _gpu_free_mb()
    print(f"GPU free MB:  {free if free is not None else '(nvidia-smi unavailable)'}")
    transcripts = cfg.transcripts_dir
    if transcripts.is_dir():
        recent = sorted(transcripts.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        print(f"Recent sessions ({len(recent)}):")
        for r in recent:
            print(f"  - {r.name}")
    return 0


def cmd_view(args, cfg: Config) -> int:
    """./gbs view [session_id] [--no-live] — browse pipeline runs in a live TUI."""
    from gbs.viewer.app import GBSViewer
    gbs_dir = cfg.transcripts_dir.parent  # the .gbs/ directory
    if not (gbs_dir / "transcripts").is_dir():
        sys.exit(f"No transcripts found under {gbs_dir}/transcripts.")
    app = GBSViewer(gbs_dir, live=not args.no_live, session_id=args.session)
    app.run()
    return 0


def cmd_serve(args, cfg: Config) -> int:
    if _vllm_alive(cfg.vllm_base_url):
        print(f"vLLM already responding at {cfg.vllm_base_url}")
        return 0
    script = cfg.project_root / "infra" / "vllm_serve.sh"
    if not script.is_file():
        sys.exit(f"vLLM serve script not found: {script}")
    print(f"Starting vLLM via {script}...")
    os.execvp("bash", ["bash", str(script)])  # exec replaces current process


def _make_session_dir(cfg: Config, session_id: str | None = None) -> Path:
    sid = session_id or fresh_session_id()
    d = cfg.transcripts_dir / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_run(args, cfg: Config) -> int:
    """./gbs run <skill-name> [args...] — run any skill standalone (treated as orchestrator-level)."""
    session_dir = _make_session_dir(cfg)
    print(f"Session: {session_dir.name}", file=sys.stderr)
    try:
        result = run_skill(
            skill_name=args.skill,
            args=" ".join(args.skill_args),
            session_dir=session_dir,
            is_orchestrator=True,
            config=cfg,
        )
    except BudgetExhausted as e:
        print(f"Budget exhausted: {e}", file=sys.stderr)
        return 2
    print(result.text)
    return 0 if result.status == "SUCCESS" else 1


def cmd_subagent(args, cfg: Config) -> int:
    """./gbs subagent --skill X --args ... --session-dir D — internal, called by Skill tool."""
    session_dir = Path(args.session_dir)
    try:
        result = run_skill(
            skill_name=args.skill,
            args=args.args,
            session_dir=session_dir,
            is_orchestrator=False,
            config=cfg,
        )
    except BudgetExhausted as e:
        print(f"Budget exhausted: {e}", file=sys.stderr)
        return 2
    print(result.text)
    return 0 if result.status == "SUCCESS" else 1


def cmd_orchestrator(args, cfg: Config) -> int:
    """./gbs orchestrator [start-step] [--clean] [--only] — runs the gbs-orchestrator skill."""
    _preflight(cfg)
    parts: list[str] = []
    if args.start_step is not None:
        parts.append(str(args.start_step))
    if args.clean:
        parts.append("--clean")
    if args.only:
        parts.append("--only")
    skill_args = " ".join(parts)
    session_dir = _make_session_dir(cfg)
    print(f"Session: {session_dir.name}", file=sys.stderr)
    try:
        result = run_skill(
            skill_name="gbs-orchestrator",
            args=skill_args,
            session_dir=session_dir,
            is_orchestrator=True,
            config=cfg,
        )
    except BudgetExhausted as e:
        print(f"Budget exhausted: {e}", file=sys.stderr)
        return 2
    print(result.text)
    return 0 if result.status == "SUCCESS" else 1


def cmd_debugger(args, cfg: Config) -> int:
    """./gbs debugger N [error] — manual invocation of gbs-debugger."""
    _preflight(cfg)
    skill_args = f"{args.step} {args.error or ''}".strip()
    session_dir = _make_session_dir(cfg)
    try:
        result = run_skill(
            skill_name="gbs-debugger",
            args=skill_args,
            session_dir=session_dir,
            is_orchestrator=True,
            config=cfg,
        )
    except BudgetExhausted as e:
        print(f"Budget exhausted: {e}", file=sys.stderr)
        return 2
    print(result.text)
    return 0 if result.status == "SUCCESS" else 1


def cmd_capture_reference(args, cfg: Config) -> int:
    """Walk current outputs through each step comparator; write tests/reference/step_N.json."""
    import importlib
    import json as _json
    out_dir = cfg.project_root / "tests" / "reference"
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(cfg.project_root))  # so we can import tests.comparators.*
    failures = []
    for n in range(16):
        try:
            mod = importlib.import_module(f"tests.comparators.step_{n}")
        except ImportError as e:
            print(f"step_{n}: comparator module missing — skipping ({e})")
            continue
        try:
            actual = mod.comparator(cfg.project_root)
        except Exception as e:
            print(f"step_{n}: comparator raised {type(e).__name__}: {e}")
            failures.append(n)
            continue
        # Write as exact-match reference (no min/max ranges yet — tighten later if flaky)
        target = out_dir / f"step_{n}.json"
        target.write_text(_json.dumps(actual, indent=2, sort_keys=True))
        print(f"step_{n}: captured → {target}")
    if failures:
        print(f"WARNING: {len(failures)} comparator(s) failed: {failures}", file=sys.stderr)
        return 1
    return 0


def _mask_proc_title() -> None:
    """Set this process's title to a generic name so SKILL.md `pgrep -f` checks
    do not self-match (the original argv contains the skill name, e.g.
    `python -m gbs.cli run gbs-6-gstacks`, which would falsely match
    `pgrep -f 'gstacks'` from inside the gstacks skill)."""
    try:
        from setproctitle import setproctitle
        setproctitle("gbs-agent")
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    _mask_proc_title()
    cfg = Config.load()
    parser = argparse.ArgumentParser(prog="gbs", description="GBS pipeline open-source agentic CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("serve").set_defaults(func=cmd_serve)

    p_view = sub.add_parser("view", help="Browse pipeline runs in a live TUI")
    p_view.add_argument("session", nargs="?", default=None,
                        help="Session id (prefix) to open; default: live or most-recent run")
    p_view.add_argument("--no-live", action="store_true", help="Disable live auto-refresh")
    p_view.set_defaults(func=cmd_view)

    p_run = sub.add_parser("run", help="Run any skill standalone")
    p_run.add_argument("skill")
    p_run.add_argument("skill_args", nargs="*")
    p_run.set_defaults(func=cmd_run)

    p_sub = sub.add_parser("subagent", help="(internal) invoked by the Skill tool")
    p_sub.add_argument("--skill", required=True)
    p_sub.add_argument("--args", default="")
    p_sub.add_argument("--session-dir", required=True)
    p_sub.set_defaults(func=cmd_subagent)

    p_orch = sub.add_parser("orchestrator", help="Run the gbs-orchestrator skill")
    p_orch.add_argument("start_step", nargs="?", type=int, default=None)
    p_orch.add_argument("--clean", action="store_true")
    p_orch.add_argument("--only", action="store_true")
    p_orch.set_defaults(func=cmd_orchestrator)

    p_dbg = sub.add_parser("debugger", help="Manually invoke gbs-debugger")
    p_dbg.add_argument("step", type=int)
    p_dbg.add_argument("error", nargs="?", default=None)
    p_dbg.set_defaults(func=cmd_debugger)

    p_test = sub.add_parser("test", help="Test utilities")
    test_sub = p_test.add_subparsers(dest="test_cmd", required=True)
    p_capture = test_sub.add_parser("capture-reference", help="Capture per-step comparator outputs as reference fixtures")
    p_capture.set_defaults(func=cmd_capture_reference)

    args = parser.parse_args(argv)
    return args.func(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
