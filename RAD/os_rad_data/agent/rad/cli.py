"""Command-line entry point: ./rad <subcommand> [args...]"""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path
from rad.config import Config
from rad.transcript import fresh_session_id
from rad.runtime import run_skill, BudgetExhausted


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
    """Pre-flight checks before running the orchestrator. Eagerly loads the model
    so a load failure surfaces before any pipeline work starts."""
    if not (cfg.project_root / "02-raw").is_dir() or not (cfg.project_root / "00-scripts").is_dir():
        sys.exit(f"Not in project root (no 02-raw/ or 00-scripts/): {cfg.project_root}")
    free = _gpu_free_mb()
    if free is not None and free < 2000:
        sys.exit(f"GPU has only {free}MB free; cannot load the model. Free the GPU and retry.")
    try:
        from rad.model_backend import get_model
        get_model(cfg.model_id, cfg.torch_dtype, cfg.device_map)
    except Exception as e:
        sys.exit(
            f"Failed to load {cfg.model_id} in-process: {type(e).__name__}: {e}\n"
            f"If this is an FP8/kernel error on this GPU, install compressed-tensors or set "
            f"RAD_MODEL_ID to the bf16 checkpoint (microsoft/Phi-4)."
        )


def cmd_status(args, cfg: Config) -> int:
    print(f"Project root: {cfg.project_root}")
    print(f"Skills dir:   {cfg.skills_dir}")
    print(f"Model id:     {cfg.model_id}")
    print(f"Torch dtype:  {cfg.torch_dtype}")
    print(f"Device map:   {cfg.device_map}")
    print(f"Max ctx tok:  {cfg.max_context_tokens}")
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
    """./rad view [session_id] [--no-live] — browse pipeline runs in a live TUI."""
    from rad.viewer.app import RADViewer
    rad_dir = cfg.transcripts_dir.parent  # the .rad/ directory
    if not (rad_dir / "transcripts").is_dir():
        sys.exit(f"No transcripts found under {rad_dir}/transcripts.")
    app = RADViewer(rad_dir, live=not args.no_live, session_id=args.session)
    app.run()
    return 0


def _make_session_dir(cfg: Config, session_id: str | None = None) -> Path:
    sid = session_id or fresh_session_id()
    d = cfg.transcripts_dir / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_run(args, cfg: Config) -> int:
    """./rad run <skill-name> [args...] — run any skill standalone (treated as orchestrator-level)."""
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
    """./rad subagent --skill X --args ... --session-dir D — internal, called by Skill tool."""
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
    """./rad orchestrator [start-step] [--clean] [--only] — runs the rad-orchestrator skill."""
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
            skill_name="rad-orchestrator",
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
    """./rad debugger N [error] — manual invocation of rad-debugger."""
    _preflight(cfg)
    skill_args = f"{args.step} {args.error or ''}".strip()
    session_dir = _make_session_dir(cfg)
    try:
        result = run_skill(
            skill_name="rad-debugger",
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
    `python -m rad.cli run rad-6-gstacks`, which would falsely match
    `pgrep -f 'gstacks'` from inside the gstacks skill)."""
    try:
        from setproctitle import setproctitle
        setproctitle("rad-agent")
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    _mask_proc_title()
    cfg = Config.load()
    parser = argparse.ArgumentParser(prog="rad", description="RAD pipeline open-source agentic CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)

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

    p_orch = sub.add_parser("orchestrator", help="Run the rad-orchestrator skill")
    p_orch.add_argument("start_step", nargs="?", type=int, default=None)
    p_orch.add_argument("--clean", action="store_true")
    p_orch.add_argument("--only", action="store_true")
    p_orch.set_defaults(func=cmd_orchestrator)

    p_dbg = sub.add_parser("debugger", help="Manually invoke rad-debugger")
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
