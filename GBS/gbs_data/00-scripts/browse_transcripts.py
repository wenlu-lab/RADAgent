#!/usr/bin/env python3
"""Browse GBS pipeline skill transcripts stored by Claude Code.

Usage:
    python3 00-scripts/browse_transcripts.py                  # List all sessions with pipeline runs
    python3 00-scripts/browse_transcripts.py list             # List steps from the latest pipeline run
    python3 00-scripts/browse_transcripts.py list SESSION_ID  # List steps from a specific session
    python3 00-scripts/browse_transcripts.py list --run 1     # List steps from the 1st pipeline run in this session
    python3 00-scripts/browse_transcripts.py show 5           # Show step 5 transcript (latest run)
    python3 00-scripts/browse_transcripts.py show 5 --run 1   # Show step 5 from a specific pipeline run
    python3 00-scripts/browse_transcripts.py show 5 --attempt 1  # Show specific attempt (if retried)
    python3 00-scripts/browse_transcripts.py show 5 --commands   # Show only bash commands run
    python3 00-scripts/browse_transcripts.py show 5 --errors     # Show only errors/failures
    python3 00-scripts/browse_transcripts.py show 5 --summary    # Show condensed summary
    python3 00-scripts/browse_transcripts.py path 5           # Print the raw .jsonl file path

If a session contains multiple pipeline runs (e.g., you ran /gbs-orchestrator twice),
the script auto-detects each run and defaults to the latest. Use --run N to select.
"""

import argparse
import json
import os
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path.home() / ".claude" / "projects" / "-home-mreddy1-gbs-data"

# Step titles for display
STEP_TITLES = {
    0: "Prepare Lane Info",
    1: "Cutadapt Adapter Trimming",
    2: "process_radtags Enzyme Filtering",
    3: "Rename Samples",
    4: "Prepare Population Map",
    5: "BWA Alignment",
    6: "gstacks Genotyping",
    7: "Stacks populations",
    8: "VCF Filtering + Chr Selection",
    9: "SNP Duplication + HWE",
    10: "LD Clumping",
    11: "Remove A/T and G/C SNPs",
    12: "MAF 0.1 Filter",
    13: "Flanking Variants Filter",
    14: "BLAST Mapping",
    15: "Even Distribution",
}

# Keywords to detect which step a transcript belongs to
STEP_SIGNATURES = {
    0: ["Step 0", "Lane Info", "lane_info"],
    1: ["Step 1", "Cutadapt", "cutadapt"],
    2: ["Step 2", "process_radtags", "radtags"],
    3: ["Step 3", "Rename Samples", "rename"],
    4: ["Step 4", "Population Map", "popmap"],
    5: ["Step 5", "BWA Alignment", "bwa mem"],
    6: ["Step 6", "gstacks", "Genotyping"],
    7: ["Step 7", "Stacks populations"],
    8: ["Step 8", "VCF Filtering", "vcftools"],
    9: ["Step 9", "SNP Duplication", "HWE"],
    10: ["Step 10", "LD Clumping", "ld_clump"],
    11: ["Step 11", "Remove A/T", "AT_CG", "no_AT_CG"],
    12: ["Step 12", "MAF 0.1", "maf10"],
    13: ["Step 13", "Flanking", "flanking"],
    14: ["Step 14", "BLAST Mapping", "blast_map"],
    15: ["Step 15", "Even Distribution", "even_dist"],
}


def detect_step(content: str) -> int:
    """Detect which pipeline step a transcript belongs to, based on the skill prompt."""
    # Check for explicit "Step N:" pattern first
    match = re.search(r"Step\s+(\d+)\s*[:\u2014—]", content[:500])
    if match:
        return int(match.group(1))
    # Fall back to keyword matching
    for step, keywords in STEP_SIGNATURES.items():
        for kw in keywords:
            if kw in content[:1000]:
                return step
    return -1


def find_sessions():
    """Find all session directories that have subagent transcripts."""
    sessions = []
    for item in PROJECT_DIR.iterdir():
        subagents = item / "subagents"
        if item.is_dir() and subagents.is_dir():
            jsonl_files = list(subagents.glob("*.jsonl"))
            if jsonl_files:
                mtime = max(f.stat().st_mtime for f in jsonl_files)
                sessions.append((item.name, mtime, len(jsonl_files)))
    sessions.sort(key=lambda x: x[1], reverse=True)
    return sessions


def get_session_dir(session_id=None):
    """Get the session directory, defaulting to the most recent."""
    if session_id:
        d = PROJECT_DIR / session_id
        if not d.is_dir():
            print(f"Error: Session '{session_id}' not found.")
            sys.exit(1)
        return d
    sessions = find_sessions()
    if not sessions:
        print("No sessions with transcripts found.")
        sys.exit(1)
    return PROJECT_DIR / sessions[0][0]


def parse_transcript(jsonl_path: Path):
    """Parse a JSONL transcript into structured entries."""
    entries = []
    with open(jsonl_path) as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def classify_transcripts(session_dir: Path):
    """Map each transcript file to a pipeline step, grouped by pipeline run.

    A new pipeline run is detected when we see step 0 after having already
    seen a step >= 1 (i.e., step 0 reappears mid-sequence). Returns a list
    of runs, where each run is a list of
    (step_num, attempt, filepath, size, mtime, line_count, run_number) tuples.
    """
    subagents = session_dir / "subagents"
    all_classified = []  # flat list with run_number added

    files = sorted(subagents.glob("*.jsonl"), key=lambda f: f.stat().st_mtime)

    # First pass: classify each file to a step
    classified = []
    for fpath in files:
        entries = parse_transcript(fpath)
        if not entries:
            continue
        content = entries[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            content = str(content)
        step = detect_step(content)
        if step < 0:
            continue
        mtime = datetime.fromtimestamp(fpath.stat().st_mtime)
        classified.append((step, fpath, fpath.stat().st_size, mtime, len(entries)))

    # Second pass: split into runs by detecting step 0 restarts
    runs = []  # list of lists
    current_run = []
    max_step_seen = -1

    for step, fpath, size, mtime, line_count in classified:
        # A new run starts when step 0 appears after we've progressed past it
        if step == 0 and max_step_seen >= 1:
            if current_run:
                runs.append(current_run)
            current_run = []
            max_step_seen = -1
        current_run.append((step, fpath, size, mtime, line_count))
        if step > max_step_seen:
            max_step_seen = step

    if current_run:
        runs.append(current_run)

    # Third pass: assign attempt numbers per step within each run
    for run_idx, run in enumerate(runs):
        run_num = run_idx + 1
        step_counts = {}
        for step, fpath, size, mtime, line_count in run:
            attempt = step_counts.get(step, 0) + 1
            step_counts[step] = attempt
            all_classified.append((step, attempt, fpath, size, mtime, line_count, run_num))

    return all_classified, len(runs)


def cmd_sessions(args):
    """List all sessions."""
    sessions = find_sessions()
    if not sessions:
        print("No sessions with transcripts found.")
        return
    print(f"{'Session ID':<45} {'Last Modified':>20} {'Transcripts':>12}")
    print("-" * 80)
    for sid, mtime, count in sessions:
        ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{sid:<45} {ts:>20} {count:>12}")
    print(f"\nUse: python3 00-scripts/browse_transcripts.py list {sessions[0][0]}")


def filter_by_run(transcripts, total_runs, run_num=None):
    """Filter transcripts to a specific run. Default: latest run."""
    if run_num is None:
        run_num = total_runs  # latest
    return [(s, a, f, sz, mt, lc, r) for s, a, f, sz, mt, lc, r in transcripts if r == run_num], run_num


def cmd_list(args):
    """List all steps from a session."""
    session_dir = get_session_dir(args.session_id)
    transcripts, total_runs = classify_transcripts(session_dir)

    if not transcripts:
        print("No pipeline step transcripts found in this session.")
        return

    run_num = getattr(args, "run", None)
    if run_num is not None or total_runs > 1:
        filtered, run_num = filter_by_run(transcripts, total_runs, run_num)
    else:
        filtered = transcripts
        run_num = 1

    print(f"Session: {session_dir.name}")
    if total_runs > 1:
        print(f"Pipeline run: {run_num} of {total_runs} (use --run N to select)")
    print(f"{'Step':<6} {'Att':>3} {'Title':<35} {'Size':>8} {'Lines':>6} {'Time':>20} {'Agent File'}")
    print("-" * 130)
    for step, attempt, fpath, size, mtime, lines, rn in filtered:
        title = STEP_TITLES.get(step, "Unknown")
        size_str = f"{size // 1024}KB"
        ts = mtime.strftime("%H:%M:%S")
        print(f"{step:<6} {attempt:>3} {title:<35} {size_str:>8} {lines:>6} {ts:>20}  {fpath.name}")

    print(f"\nUse: python3 00-scripts/browse_transcripts.py show <step>")


def format_duration(seconds):
    """Format seconds to human-readable."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}h {m}m {s}s"


def cmd_show(args):
    """Show a step's transcript."""
    session_dir = get_session_dir(args.session_id)
    transcripts, total_runs = classify_transcripts(session_dir)

    # Filter to requested run
    run_num = getattr(args, "run", None)
    filtered, run_num = filter_by_run(transcripts, total_runs, run_num)

    # Filter to requested step
    step_transcripts = [(s, a, f, sz, mt, lc, r) for s, a, f, sz, mt, lc, r in filtered if s == args.step]

    if not step_transcripts:
        print(f"No transcript found for step {args.step} in run {run_num}.")
        if total_runs > 1:
            print(f"This session has {total_runs} pipeline runs. Try --run N to select a different one.")
        return

    # Pick the attempt(s) to show
    if args.attempt:
        matches = [t for t in step_transcripts if t[1] == args.attempt]
        if not matches:
            print(f"No attempt {args.attempt} found for step {args.step}. Available: {[t[1] for t in step_transcripts]}")
            return
        targets = matches
    else:
        targets = step_transcripts  # show ALL attempts

    for idx, target in enumerate(targets):
        step, attempt, fpath, size, mtime, line_count, rn = target
        entries = parse_transcript(fpath)
        title = STEP_TITLES.get(step, "Unknown")

        if idx > 0:
            print()
            print()

        print(f"=" * 80)
        run_label = f" | Run {rn}/{total_runs}" if total_runs > 1 else ""
        print(f"Step {step}: {title} (attempt {attempt} of {len(step_transcripts)}{run_label})")
        print(f"File: {fpath}")
        print(f"Size: {size // 1024}KB | Turns: {line_count} | Ended: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"=" * 80)
        print()

        if args.commands:
            show_commands(entries)
        elif args.errors:
            show_errors(entries)
        elif args.summary:
            show_summary(entries, step, title)
        else:
            show_full(entries)


def show_full(entries):
    """Show the full conversation, formatted for readability."""
    for i, entry in enumerate(entries):
        msg = entry.get("message", {})
        role = msg.get("role", entry.get("type", "?"))
        content = msg.get("content", "")

        if role == "user":
            if isinstance(content, str):
                # Truncate the initial skill prompt (it's huge)
                if i == 0 and len(content) > 500:
                    print(f"[Turn {i+1}] USER (skill prompt)")
                    print(f"  {content[:300]}...")
                    print(f"  ... ({len(content)} chars total)")
                else:
                    print(f"[Turn {i+1}] USER")
                    for line in content.split("\n")[:20]:
                        print(f"  {line}")
            elif isinstance(content, list):
                # Tool results
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        result_content = item.get("content", "")
                        is_error = item.get("is_error", False)
                        label = "ERROR" if is_error else "RESULT"
                        print(f"[Turn {i+1}] TOOL {label}")
                        if isinstance(result_content, str):
                            lines = result_content.split("\n")
                            for line in lines[:30]:
                                print(f"  {line}")
                            if len(lines) > 30:
                                print(f"  ... ({len(lines)} lines total)")
                        elif isinstance(result_content, list):
                            for sub in result_content:
                                if isinstance(sub, dict):
                                    text = sub.get("text", sub.get("content", str(sub)))
                                    for line in str(text).split("\n")[:30]:
                                        print(f"  {line}")

        elif role == "assistant":
            if isinstance(content, str) and content:
                print(f"[Turn {i+1}] ASSISTANT")
                for line in content.split("\n"):
                    print(f"  {line}")
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text" and item.get("text"):
                            print(f"[Turn {i+1}] ASSISTANT")
                            for line in item["text"].split("\n"):
                                print(f"  {line}")
                        elif item.get("type") == "tool_use":
                            tool = item.get("name", "?")
                            inp = item.get("input", {})
                            print(f"[Turn {i+1}] TOOL CALL: {tool}")
                            if tool == "Bash":
                                cmd = inp.get("command", "")
                                desc = inp.get("description", "")
                                if desc:
                                    print(f"  # {desc}")
                                print(f"  $ {cmd}")
                            elif tool == "Read":
                                print(f"  file: {inp.get('file_path', '?')}")
                            elif tool == "Write":
                                print(f"  file: {inp.get('file_path', '?')} ({len(inp.get('content', ''))} chars)")
                            elif tool == "Edit":
                                print(f"  file: {inp.get('file_path', '?')}")
                            elif tool == "Grep":
                                print(f"  pattern: {inp.get('pattern', '?')} path: {inp.get('path', '.')}")
                            elif tool == "Glob":
                                print(f"  pattern: {inp.get('pattern', '?')}")
                            else:
                                print(f"  {json.dumps(inp)[:200]}")
        print()


def show_commands(entries):
    """Show only bash commands that were executed."""
    cmd_num = 0
    for entry in entries:
        msg = entry.get("message", {})
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_use" and item.get("name") == "Bash":
                    cmd_num += 1
                    cmd = item["input"].get("command", "")
                    desc = item["input"].get("description", "")
                    print(f"[{cmd_num}] {desc}" if desc else f"[{cmd_num}]")
                    print(f"  $ {cmd}")
                    print()
    if cmd_num == 0:
        print("No bash commands found in this transcript.")
    else:
        print(f"Total: {cmd_num} bash commands")


def show_errors(entries):
    """Show only errors and failures."""
    found = 0
    for i, entry in enumerate(entries):
        msg = entry.get("message", {})
        content = msg.get("content", "")

        # Check for tool errors
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("is_error"):
                        found += 1
                        print(f"[Turn {i+1}] TOOL ERROR")
                        result = item.get("content", "")
                        if isinstance(result, str):
                            print(f"  {result[:500]}")
                        elif isinstance(result, list):
                            for sub in result:
                                print(f"  {sub.get('text', str(sub))[:500]}")
                        print()
                    # Check for error exit codes in tool results
                    elif item.get("type") == "tool_result":
                        text = item.get("content", "")
                        if isinstance(text, str) and ("error" in text.lower() or "Error" in text or "FAIL" in text or "Exit code" in text):
                            found += 1
                            print(f"[Turn {i+1}] POSSIBLE ERROR IN OUTPUT")
                            for line in text.split("\n")[:20]:
                                print(f"  {line}")
                            print()

        # Check for synthetic/crash messages
        model = msg.get("model", "")
        if model == "<synthetic>":
            found += 1
            print(f"[Turn {i+1}] SYNTHETIC MESSAGE (API crash/timeout)")
            stop = msg.get("stop_reason", "")
            print(f"  stop_reason: {stop}")
            print()

    if found == 0:
        print("No errors found in this transcript.")
    else:
        print(f"Total: {found} error(s) found")


def show_summary(entries, step, title):
    """Show a condensed summary of the transcript."""
    bash_count = 0
    read_count = 0
    edit_count = 0
    write_count = 0
    grep_count = 0
    other_tools = 0
    errors = 0
    assistant_texts = []
    commands = []
    has_synthetic = False

    for entry in entries:
        msg = entry.get("message", {})
        content = msg.get("content", "")
        model = msg.get("model", "")

        if model == "<synthetic>":
            has_synthetic = True

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "tool_use":
                        name = item.get("name", "")
                        if name == "Bash":
                            bash_count += 1
                            commands.append(item["input"].get("command", "")[:100])
                        elif name == "Read":
                            read_count += 1
                        elif name == "Edit":
                            edit_count += 1
                        elif name == "Write":
                            write_count += 1
                        elif name == "Grep":
                            grep_count += 1
                        else:
                            other_tools += 1
                    elif item.get("type") == "text" and item.get("text"):
                        assistant_texts.append(item["text"])
                    elif item.get("is_error"):
                        errors += 1
                    elif item.get("type") == "tool_result":
                        text = item.get("content", "")
                        if isinstance(text, str) and ("error" in text.lower() or "FAIL" in text):
                            errors += 1

    total_tools = bash_count + read_count + edit_count + write_count + grep_count + other_tools

    print(f"Step {step}: {title}")
    print(f"  Conversation turns: {len(entries)}")
    print(f"  Tool calls: {total_tools} (Bash: {bash_count}, Read: {read_count}, Edit: {edit_count}, Write: {write_count}, Grep: {grep_count}, Other: {other_tools})")
    print(f"  Errors detected: {errors}")
    print(f"  API crash: {'YES' if has_synthetic else 'No'}")
    print()

    if commands:
        print("  Key commands run:")
        for cmd in commands[:15]:
            print(f"    $ {cmd}")
        if len(commands) > 15:
            print(f"    ... and {len(commands) - 15} more")
    print()

    # Show the last assistant text (usually the summary)
    if assistant_texts:
        last = assistant_texts[-1]
        if len(last) > 100:
            print("  Final output (last assistant message):")
            for line in last.split("\n")[:20]:
                print(f"    {line}")


def cmd_path(args):
    """Print the raw file path for a step's transcript."""
    session_dir = get_session_dir(args.session_id)
    transcripts, total_runs = classify_transcripts(session_dir)

    run_num = getattr(args, "run", None)
    filtered, run_num = filter_by_run(transcripts, total_runs, run_num)

    step_transcripts = [(s, a, f, sz, mt, lc, r) for s, a, f, sz, mt, lc, r in filtered if s == args.step]

    if not step_transcripts:
        print(f"No transcript found for step {args.step} in run {run_num}.")
        return

    if args.attempt:
        matches = [t for t in step_transcripts if t[1] == args.attempt]
        if matches:
            print(matches[0][2])
        else:
            print(f"No attempt {args.attempt}. Available: {[t[1] for t in step_transcripts]}")
    else:
        for s, a, f, sz, mt, lc, r in step_transcripts:
            print(f"Attempt {a}: {f}")


def main():
    parser = argparse.ArgumentParser(description="Browse GBS pipeline skill transcripts")
    subparsers = parser.add_subparsers(dest="command")

    # sessions
    subparsers.add_parser("sessions", help="List all sessions with transcripts")

    # list
    p_list = subparsers.add_parser("list", help="List steps from a session")
    p_list.add_argument("session_id", nargs="?", help="Session ID (default: latest)")
    p_list.add_argument("--run", type=int, help="Pipeline run number within session (default: latest)")

    # show
    p_show = subparsers.add_parser("show", help="Show a step's transcript")
    p_show.add_argument("step", type=int, help="Step number (0-15)")
    p_show.add_argument("--attempt", type=int, help="Specific attempt number")
    p_show.add_argument("--run", type=int, help="Pipeline run number within session (default: latest)")
    p_show.add_argument("--commands", action="store_true", help="Show only bash commands")
    p_show.add_argument("--errors", action="store_true", help="Show only errors")
    p_show.add_argument("--summary", action="store_true", help="Show condensed summary")
    p_show.add_argument("--session-id", help="Session ID (default: latest)")

    # path
    p_path = subparsers.add_parser("path", help="Print raw .jsonl file path")
    p_path.add_argument("step", type=int, help="Step number (0-15)")
    p_path.add_argument("--attempt", type=int, help="Specific attempt number")
    p_path.add_argument("--run", type=int, help="Pipeline run number within session (default: latest)")
    p_path.add_argument("--session-id", help="Session ID (default: latest)")

    args = parser.parse_args()

    if args.command is None or args.command == "sessions":
        cmd_sessions(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "path":
        cmd_path(args)


if __name__ == "__main__":
    main()
