"""Pure (UI-free) parser for RAD pipeline run transcripts under .rad/.

Reads the JSONL transcripts written by agent/rad/transcript.py plus the
orchestrator-*.log files, and exposes them as Run -> Step -> Event dataclasses.
No Textual import here, so this layer can be exercised directly on real data.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LIVE_WINDOW_SEC = 60  # a file touched within this window may be a live run

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

_SKILL_STEP_RE = re.compile(r"rad-(\d+)-")
_EXIT_RE = re.compile(r"^\[exit (\d+)\]")
_AWARE_MIN = datetime.min.replace(tzinfo=timezone.utc)
_AWARE_MAX = datetime.max.replace(tzinfo=timezone.utc)


def _parse_ts(s) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Event:
    kind: str                       # "user" | "assistant" | "tool_use" | "tool_result"
    ts: datetime | None = None
    text: str | None = None         # user/assistant content
    tool_name: str | None = None    # tool_use
    tool_input: dict | None = None  # tool_use
    tool_use_id: str | None = None
    output: str | None = None       # tool_result content (paired onto its tool_use)
    exit_code: int | None = None    # parsed from "[exit N]" prefix
    is_error: bool = False


@dataclass
class Step:
    number: int | None              # 0..15, or None for the orchestrator lane
    skill_name: str
    title: str
    attempt: int
    kind: str                       # "step" | "debugger" | "orchestrator"
    status: str                     # SUCCESS | FAILED | RUNNING | UNKNOWN
    start_ts: datetime | None
    end_ts: datetime | None
    duration_s: int
    tokens_in: int
    tokens_out: int
    error_count: int
    events: list[Event]
    subagent_path: Path | None


@dataclass
class Run:
    session_id: str
    start_time: datetime | None     # display only (may be naive local from log name)
    status: str                     # COMPLETE | STOPPED | RUNNING | UNKNOWN
    is_live: bool
    steps: list[Step]               # orchestrator lane first, then steps in order
    log_path: Path | None


def _read_jsonl(path) -> list[dict]:
    """Parse JSONL, tolerating a partial trailing line (live writes)."""
    path = Path(path)
    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # last line mid-write; skip
    return rows


def _classify_output(out) -> tuple[str, int | None, bool]:
    """Return (text, exit_code, is_error) for a tool_result content value."""
    text = out if isinstance(out, str) else json.dumps(out)
    exit_code = None
    is_error = False
    m = _EXIT_RE.match(text)
    if m:
        exit_code = int(m.group(1))
        is_error = True
    elif "timed out after" in text[:120].lower():
        is_error = True
    return text, exit_code, is_error


def _events_from_rows(rows: list[dict]) -> list[Event]:
    """Build display events, pairing each tool_result back onto its tool_use."""
    events: list[Event] = []
    by_id: dict[str, Event] = {}
    for row in rows:
        typ = row.get("type")
        msg = row.get("message", {}) or {}
        ts = _parse_ts(row.get("timestamp"))
        if typ == "user":
            content = msg.get("content")
            events.append(Event(kind="user", ts=ts,
                                text=content if isinstance(content, str) else json.dumps(content)))
        elif typ == "assistant":
            content = msg.get("content")
            text = content if isinstance(content, str) else json.dumps(content)
            events.append(Event(kind="assistant", ts=ts, text=text or ""))
        elif typ == "tool_use":
            ev = Event(kind="tool_use", ts=ts,
                       tool_name=msg.get("tool_name"),
                       tool_input=msg.get("tool_input") or {},
                       tool_use_id=msg.get("tool_use_id"))
            events.append(ev)
            if ev.tool_use_id:
                by_id[ev.tool_use_id] = ev
        elif typ == "tool_result":
            tuid = msg.get("tool_use_id")
            text, exit_code, is_error = _classify_output(msg.get("content"))
            paired = by_id.get(tuid)
            if paired is not None:
                paired.output = text
                paired.exit_code = exit_code
                paired.is_error = is_error
            else:
                events.append(Event(kind="tool_result", ts=ts, output=text,
                                    exit_code=exit_code, is_error=is_error, tool_use_id=tuid))
    return events


def _sum_tokens(rows: list[dict]) -> tuple[int, int]:
    tin = tout = 0
    for row in rows:
        if row.get("type") == "assistant":
            u = (row.get("message", {}) or {}).get("usage") or {}
            tin += int(u.get("input_tokens", 0) or 0)
            tout += int(u.get("output_tokens", 0) or 0)
    return tin, tout


def _first_last_ts(rows: list[dict]) -> tuple[datetime | None, datetime | None]:
    ts = [t for t in (_parse_ts(r.get("timestamp")) for r in rows) if t]
    return (ts[0], ts[-1]) if ts else (None, None)


def _count_errors(events: list[Event]) -> int:
    return sum(1 for e in events if e.is_error)


def _status_from_result(result_text, has_errors: bool) -> str:
    """Best-effort per-attempt status from the orchestrator's Skill result text."""
    if not result_text or not isinstance(result_text, str):
        return "FAILED" if has_errors else "UNKNOWN"
    low = result_text.lower()
    if re.search(r"\bfailed\b", low) and "overriding" not in low:
        return "FAILED"
    if "success" in low:
        return "SUCCESS"
    return "FAILED" if has_errors else "UNKNOWN"


def _index_logs(rad_dir: Path) -> dict[str, Path]:
    """Map session_id -> orchestrator-*.log by scanning for 'Session: <id>'."""
    out: dict[str, Path] = {}
    for log in sorted(rad_dir.glob("orchestrator-*.log")):
        try:
            text = log.read_text(errors="replace")
        except OSError:
            continue
        m = re.search(r"Session:\s*([0-9a-f]+)", text)
        if m:
            out[m.group(1)] = log
    return out


def _parse_log(log_text: str) -> tuple[str, dict[int, str]]:
    """Return (run_status, {step_number: STATUS}) from an orchestrator log."""
    step_status: dict[int, str] = {}
    for line in log_text.splitlines():
        m = re.match(r"\s*\|\s*(\d+)\s*\|[^|]*\|\s*([A-Z]+)\s*\|", line)
        if m:
            step_status[int(m.group(1))] = m.group(2)
    if "Pipeline status: **COMPLETE**" in log_text or "Pipeline Complete!" in log_text:
        run_status = "COMPLETE"
    elif "Pipeline Stopped" in log_text or "PIPELINE STOPPED" in log_text:
        run_status = "STOPPED"
    else:
        run_status = "UNKNOWN"
    return run_status, step_status


def _session_mtime(session_dir: Path) -> float:
    files = list(session_dir.glob("*.jsonl")) + list((session_dir / "subagents").glob("*.jsonl"))
    return max((f.stat().st_mtime for f in files), default=0.0)


def _classify_session(session_dir: Path, log_index: dict[str, Path]) -> Run:
    session_id = session_dir.name
    root_files = sorted(session_dir.glob("*.jsonl"))
    root_rows = _read_jsonl(root_files[0]) if root_files else []
    root_events = _events_from_rows(root_rows)

    # Skill calls in time order, paired with their result text.
    result_by_id: dict[str, object] = {}
    for row in root_rows:
        if row.get("type") == "tool_result":
            m = row.get("message", {}) or {}
            result_by_id[m.get("tool_use_id")] = m.get("content")
    skill_calls = []  # (ts, skill_name, result_text)
    for row in root_rows:
        if row.get("type") == "tool_use":
            m = row.get("message", {}) or {}
            if m.get("tool_name") == "Skill":
                name = (m.get("tool_input") or {}).get("name", "")
                skill_calls.append((_parse_ts(row.get("timestamp")), name,
                                    result_by_id.get(m.get("tool_use_id"))))
    skill_calls.sort(key=lambda c: c[0] or _AWARE_MIN)

    # Subagents sorted by first timestamp.
    sub_dir = session_dir / "subagents"
    sub_files = sorted(sub_dir.glob("*.jsonl")) if sub_dir.is_dir() else []
    subs = []  # (first_ts, path, rows, last_ts)
    for f in sub_files:
        rows = _read_jsonl(f)
        first, last = _first_last_ts(rows)
        subs.append((first, f, rows, last))
    subs.sort(key=lambda s: s[0] or _AWARE_MAX)

    log_path = log_index.get(session_id)
    run_status, log_step_status = "UNKNOWN", {}
    if log_path:
        run_status, log_step_status = _parse_log(log_path.read_text(errors="replace"))

    newest = _session_mtime(session_dir)
    recent = bool(newest) and (time.time() - newest) < LIVE_WINDOW_SEC

    steps: list[Step] = []
    o_first, o_last = _first_last_ts(root_rows)
    o_tin, o_tout = _sum_tokens(root_rows)
    steps.append(Step(
        number=None, skill_name="orchestrator", title="Orchestrator", attempt=1,
        kind="orchestrator", status=run_status,
        start_ts=o_first, end_ts=o_last,
        duration_s=int((o_last - o_first).total_seconds()) if o_first and o_last else 0,
        tokens_in=o_tin, tokens_out=o_tout, error_count=_count_errors(root_events),
        events=root_events, subagent_path=root_files[0] if root_files else None,
    ))

    n = max(len(skill_calls), len(subs))
    attempts: dict[tuple, int] = {}
    for i in range(n):
        call = skill_calls[i] if i < len(skill_calls) else None
        sub = subs[i] if i < len(subs) else None
        skill_name = (call[1] if call else None) or "unknown"
        result_text = call[2] if call else None
        if sub:
            first, fpath, rows, last = sub
            events = _events_from_rows(rows)
            tin, tout = _sum_tokens(rows)
        else:
            first = last = fpath = None
            rows, events = [], []
            tin = tout = 0
        kind = "debugger" if skill_name == "rad-debugger" else "step"
        m = _SKILL_STEP_RE.search(skill_name)
        number = int(m.group(1)) if m else None
        title = "debugger" if kind == "debugger" else STEP_TITLES.get(number, skill_name)
        akey = (kind, number)
        attempts[akey] = attempts.get(akey, 0) + 1
        attempt = attempts[akey]
        errs = _count_errors(events)
        # Per-attempt status: prefer the orchestrator's Skill result text (faithful to
        # each attempt), then the log table (final per-step), then live/unknown.
        if result_text is not None:
            status = _status_from_result(result_text, errs > 0)
        elif number is not None and number in log_step_status:
            status = log_step_status[number]
        elif sub is not None and recent and i == n - 1:
            status = "RUNNING"
        else:
            status = "UNKNOWN"
        steps.append(Step(
            number=number, skill_name=skill_name, title=title, attempt=attempt,
            kind=kind, status=status, start_ts=first, end_ts=last,
            duration_s=int((last - first).total_seconds()) if first and last else 0,
            tokens_in=tin, tokens_out=tout, error_count=errs,
            events=events, subagent_path=fpath,
        ))

    start_time = None
    if log_path:
        m = re.search(r"orchestrator-(\d{8}-\d{6})\.log", log_path.name)
        if m:
            try:
                start_time = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
            except ValueError:
                pass
    if start_time is None:
        start_time = o_first

    is_live = recent and run_status not in ("COMPLETE", "STOPPED")
    if is_live and run_status == "UNKNOWN":
        run_status = "RUNNING"

    return Run(session_id=session_id, start_time=start_time, status=run_status,
               is_live=is_live, steps=steps, log_path=log_path)


def load_runs(rad_dir) -> list[Run]:
    """Load all runs under <rad_dir>/transcripts/, most-recent first."""
    rad_dir = Path(rad_dir)
    troot = rad_dir / "transcripts"
    if not troot.is_dir():
        return []
    log_index = _index_logs(rad_dir)
    pairs = []
    for d in sorted(troot.iterdir()):
        if d.is_dir() and any(d.glob("*.jsonl")):
            pairs.append((_session_mtime(d), _classify_session(d, log_index)))
    pairs.sort(key=lambda x: x[0], reverse=True)
    return [run for _, run in pairs]
