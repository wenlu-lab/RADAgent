#!/usr/bin/env python3
"""
GBS Pipeline Token Tracker — standalone utility for all token counting and tracking.

Usage:
  python3 00-scripts/gbs_token_tracker.py --init                          # Create/reset timing CSV
  python3 00-scripts/gbs_token_tracker.py --record-step <N> <TITLE> <STATUS> <START> <END>  # Record step timing + tokens
  python3 00-scripts/gbs_token_tracker.py --summary                       # Full token/timing report
  python3 00-scripts/gbs_token_tracker.py --newest-subagent               # Tokens from most recent subagent
  python3 00-scripts/gbs_token_tracker.py --main-only                     # Orchestrator (Opus) tokens only
  python3 00-scripts/gbs_token_tracker.py --cumulative                    # Main + all subagents combined

Output (for --newest-subagent, --main-only, --cumulative):
  input,output,cache_create,cache_read,total,model
"""
import json, glob, os, sys, csv

TIMING_CSV = "gbs-pipeline-timing.csv"
CSV_HEADER = "STEP,TITLE,STATUS,START_EPOCH,END_EPOCH,DURATION_SEC,TOKENS_INPUT,TOKENS_OUTPUT,TOKENS_CACHE_CREATE,TOKENS_CACHE_READ,TOKENS_TOTAL,MODEL"


def find_project_dir():
    """Locate the transcript root.

    New (open-source agent runtime): <cwd>/.gbs/transcripts/
    Legacy (Claude Code): ~/.claude/projects/<slug>/

    Prefer .gbs/transcripts/ if it exists; fall back to Claude Code paths.
    """
    cwd = os.getcwd()
    local = os.path.join(cwd, ".gbs", "transcripts")
    if os.path.isdir(local):
        # Treat the most-recent session dir as "project_dir" so the rest of the script works.
        sessions = glob.glob(os.path.join(local, "*"))
        if sessions:
            project_dir = max(sessions, key=os.path.getmtime)
            return local, project_dir, os.path.basename(project_dir)
    # Legacy fallback
    home = os.path.expanduser("~")
    claude_base = os.path.join(home, ".claude", "projects")
    project_slug = cwd.replace("/", "-")
    if not project_slug.startswith("-"):
        project_slug = "-" + project_slug
    project_dir = os.path.join(claude_base, project_slug)
    if not os.path.isdir(project_dir):
        all_projects = glob.glob(os.path.join(claude_base, "*"))
        project_dir = max(all_projects, key=os.path.getmtime) if all_projects else ""
    if not project_dir or not os.path.isdir(project_dir):
        return None, None, None
    return claude_base, project_dir, project_slug


def find_transcript_and_subagents(project_dir):
    """Return (orchestrator_transcript_path, subagents_dir).

    Works for both layouts:
      - .gbs/transcripts/<session>/  (new)
      - ~/.claude/projects/<slug>/<session-id>.jsonl + <session-id>/subagents/  (legacy)
    """
    if not project_dir:
        return None, None

    # New layout: project_dir IS the session dir
    direct_jsonl = glob.glob(os.path.join(project_dir, "*.jsonl"))
    sub_dir = os.path.join(project_dir, "subagents")
    if direct_jsonl and os.path.isdir(sub_dir):
        return max(direct_jsonl, key=os.path.getmtime), sub_dir

    # Legacy layout
    candidates = glob.glob(os.path.join(project_dir, "*.jsonl"))
    if not candidates:
        return None, None
    transcript = max(candidates, key=os.path.getmtime)
    session_id = os.path.splitext(os.path.basename(transcript))[0]
    subagent_dir = os.path.join(project_dir, session_id, "subagents")
    return transcript, subagent_dir


def parse_jsonl(path):
    t_in = t_out = t_cc = t_cr = 0
    model = "unknown"
    with open(path) as f:
        for line in f:
            try:
                msg = json.loads(line)
                usage = msg.get("message", {}).get("usage", {})
                t_in += usage.get("input_tokens", 0)
                t_out += usage.get("output_tokens", 0)
                t_cc += usage.get("cache_creation_input_tokens", 0)
                t_cr += usage.get("cache_read_input_tokens", 0)
                m = msg.get("message", {}).get("model", "")
                if m:
                    model = m
            except:
                continue
    return t_in, t_out, t_cc, t_cr, model


def cmd_init():
    with open(TIMING_CSV, "w") as f:
        f.write(CSV_HEADER + "\n")


def cmd_record_step(args):
    # args: N TITLE STATUS START_EPOCH END_EPOCH
    if len(args) < 5:
        print("Usage: --record-step N TITLE STATUS START_EPOCH END_EPOCH", file=sys.stderr)
        sys.exit(1)
    step_n = args[0]
    title = args[1]
    status = args[2]
    start_epoch = args[3]
    end_epoch = args[4]
    duration = int(end_epoch) - int(start_epoch)

    _, project_dir, _ = find_project_dir()
    t_in = t_out = t_cc = t_cr = 0
    model = "unknown"
    if project_dir:
        transcript, subagent_dir = find_transcript_and_subagents(project_dir)
        # Try new layout first (subagents directly under project_dir), then legacy (one level deeper)
        new_layout = glob.glob(os.path.join(project_dir, "subagents", "agent-*.jsonl"))
        legacy_layout = glob.glob(os.path.join(project_dir, "*/subagents/agent-*.jsonl"))
        all_sa_files = new_layout or legacy_layout
        if all_sa_files:
            newest = max(all_sa_files, key=os.path.getmtime)
            t_in, t_out, t_cc, t_cr, model = parse_jsonl(newest)

    total = t_in + t_out + t_cc + t_cr
    row = f"{step_n},{title},{status},{start_epoch},{end_epoch},{duration},{t_in},{t_out},{t_cc},{t_cr},{total},{model}"
    with open(TIMING_CSV, "a") as f:
        f.write(row + "\n")


def fmt_tokens(n):
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def fmt_duration(secs):
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    elif secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    else:
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        return f"{h}h {m}m {s}s"


def cmd_summary():
    if not os.path.isfile(TIMING_CSV):
        print("No timing data found (gbs-pipeline-timing.csv missing).")
        return

    rows = []
    with open(TIMING_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("No step data recorded yet.")
        return

    print("## Token & Timing Report")
    print()
    print("| Step | Name | Status | Duration | Tokens | Model |")
    print("|------|------|--------|----------|--------|-------|")

    grand_in = grand_out = grand_cc = grand_cr = 0
    grand_duration = 0
    for r in rows:
        dur = fmt_duration(r.get("DURATION_SEC", 0))
        tok = fmt_tokens(r.get("TOKENS_TOTAL", 0))
        model = r.get("MODEL", "unknown")
        # shorten model name
        if "sonnet" in model:
            model = "sonnet"
        elif "opus" in model:
            model = "opus"
        elif "haiku" in model:
            model = "haiku"
        elif "qwen" in model.lower():
            model = "qwen"
        print(f"| {r['STEP']} | {r['TITLE']} | {r['STATUS']} | {dur} | {tok} | {model} |")
        grand_in += int(r.get("TOKENS_INPUT", 0))
        grand_out += int(r.get("TOKENS_OUTPUT", 0))
        grand_cc += int(r.get("TOKENS_CACHE_CREATE", 0))
        grand_cr += int(r.get("TOKENS_CACHE_READ", 0))
        grand_duration += int(r.get("DURATION_SEC", 0))

    grand_total = grand_in + grand_out + grand_cc + grand_cr
    print()
    print(f"**Steps total**: {fmt_tokens(grand_total)} tokens ({fmt_duration(grand_duration)})")
    print(f"  input={fmt_tokens(grand_in)}, output={fmt_tokens(grand_out)}, cache_create={fmt_tokens(grand_cc)}, cache_read={fmt_tokens(grand_cr)}")

    # Try to get orchestrator overhead
    _, project_dir, _ = find_project_dir()
    if project_dir:
        transcript, _ = find_transcript_and_subagents(project_dir)
        if transcript:
            o_in, o_out, o_cc, o_cr, o_model = parse_jsonl(transcript)
            o_total = o_in + o_out + o_cc + o_cr
            if "sonnet" in o_model:
                o_model = "sonnet"
            elif "opus" in o_model:
                o_model = "opus"
            elif "qwen" in o_model.lower():
                o_model = "qwen"
            print(f"**Orchestrator ({o_model})**: {fmt_tokens(o_total)} tokens")
            print(f"  input={fmt_tokens(o_in)}, output={fmt_tokens(o_out)}, cache_create={fmt_tokens(o_cc)}, cache_read={fmt_tokens(o_cr)}")
            print(f"**Grand total**: {fmt_tokens(grand_total + o_total)} tokens")


def cmd_newest_subagent():
    _, project_dir, _ = find_project_dir()
    if not project_dir:
        print("0,0,0,0,0,unknown")
        return
    new_layout = glob.glob(os.path.join(project_dir, "subagents", "agent-*.jsonl"))
    legacy_layout = glob.glob(os.path.join(project_dir, "*/subagents/agent-*.jsonl"))
    all_sa_files = new_layout or legacy_layout
    if all_sa_files:
        newest = max(all_sa_files, key=os.path.getmtime)
        t_in, t_out, t_cc, t_cr, model = parse_jsonl(newest)
        total = t_in + t_out + t_cc + t_cr
        print(f"{t_in},{t_out},{t_cc},{t_cr},{total},{model}")
    else:
        print("0,0,0,0,0,unknown")


def cmd_main_only():
    _, project_dir, _ = find_project_dir()
    if not project_dir:
        print("0,0,0,0,0,unknown")
        return
    transcript, _ = find_transcript_and_subagents(project_dir)
    if not transcript:
        print("0,0,0,0,0,unknown")
        return
    t_in, t_out, t_cc, t_cr, model = parse_jsonl(transcript)
    total = t_in + t_out + t_cc + t_cr
    print(f"{t_in},{t_out},{t_cc},{t_cr},{total},{model}")


def cmd_cumulative():
    _, project_dir, _ = find_project_dir()
    if not project_dir:
        print("0,0,0,0,0,unknown")
        return
    transcript, subagent_dir = find_transcript_and_subagents(project_dir)
    if not transcript:
        print("0,0,0,0,0,unknown")
        return
    t_in, t_out, t_cc, t_cr, model = parse_jsonl(transcript)
    if os.path.isdir(subagent_dir):
        for sa in glob.glob(os.path.join(subagent_dir, "*.jsonl")):
            s_in, s_out, s_cc, s_cr, _ = parse_jsonl(sa)
            t_in += s_in
            t_out += s_out
            t_cc += s_cc
            t_cr += s_cr
    total = t_in + t_out + t_cc + t_cr
    print(f"{t_in},{t_out},{t_cc},{t_cr},{total},{model}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "--init":
        cmd_init()
    elif cmd == "--record-step":
        cmd_record_step(sys.argv[2:])
    elif cmd == "--summary":
        cmd_summary()
    elif cmd == "--newest-subagent":
        cmd_newest_subagent()
    elif cmd == "--main-only":
        cmd_main_only()
    elif cmd in ("--cumulative", ):
        cmd_cumulative()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)
