"""Textual TUI for browsing GBS runs. A thin view over gbs.viewer.model."""
from __future__ import annotations

import json
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from gbs.viewer import model

POLL_INTERVAL = 1.0
GLYPH = {"SUCCESS": "✓", "COMPLETE": "✓", "FAILED": "✗", "STOPPED": "✗",
         "RUNNING": "⟳", "UNKNOWN": "·"}


def _fmt_dur(s: int) -> str:
    if s <= 0:
        return "-"
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def _fmt_tok(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n // 1000}K"
    return str(n)


def _tool_summary(ev: model.Event) -> str:
    inp = ev.tool_input or {}
    name = ev.tool_name or "?"
    if name == "Read":
        return f"[Read] {inp.get('file_path', '?')}"
    if name == "Write":
        return f"[Write] {inp.get('file_path', '?')} ({len(inp.get('content', ''))} chars)"
    if name == "Edit":
        return f"[Edit] {inp.get('file_path', '?')}"
    if name == "Grep":
        return f"[Grep] {inp.get('pattern', '?')}"
    if name == "Glob":
        return f"[Glob] {inp.get('pattern', '?')}"
    if name == "Skill":
        return f"[Skill] {inp.get('name', '?')}"
    return f"[{name}] {json.dumps(inp)[:120]}"


def render_detail(step: model.Step, *, commands_only=False, errors_only=False, query="") -> Text:
    """Build the right-pane renderable for a step. Faithful, verbatim output."""
    t = Text()
    if step.kind == "orchestrator":
        head = "Orchestrator"
    elif step.kind == "debugger":
        head = f"Debugger ({step.skill_name})"
    else:
        head = f"Step {step.number}: {step.title}"
    if step.attempt > 1:
        head += f"  (attempt {step.attempt})"
    t.append(head + "\n", style="bold")
    meta = f"{step.status} · {_fmt_dur(step.duration_s)} · {_fmt_tok(step.tokens_in + step.tokens_out)} tok"
    if step.error_count:
        meta += f" · {step.error_count} error(s)"
    t.append(meta + "\n", style="dim")
    t.append("─" * 58 + "\n", style="dim")

    q = query.lower()
    for ev in step.events:
        if ev.kind == "user":
            continue  # the "$ARGUMENTS:" skill prompt — noise
        if ev.kind == "assistant":
            if commands_only or errors_only:
                continue
            txt = (ev.text or "").strip()
            if not txt:
                continue
            if q and q not in txt.lower():
                continue
            t.append(txt + "\n\n")
        elif ev.kind == "tool_use" and ev.tool_name == "Bash":
            if errors_only and not ev.is_error:
                continue
            cmd = (ev.tool_input or {}).get("command", "")
            desc = (ev.tool_input or {}).get("description", "")
            out = ev.output or ""
            if q and q not in cmd.lower() and q not in out.lower():
                continue
            if desc:
                t.append(f"# {desc}\n", style="dim italic")
            t.append("$ ", style="bold green")
            t.append(cmd.rstrip() + "\n", style="bold")
            if not commands_only and out:
                t.append(out.rstrip("\n") + "\n", style="red" if ev.is_error else None)
            t.append("\n")
        elif ev.kind == "tool_use":
            if errors_only and not ev.is_error:
                continue
            summ = _tool_summary(ev)
            if q and q not in summ.lower():
                continue
            t.append(summ + "\n", style="cyan")
            if not commands_only and ev.output:
                t.append(ev.output.rstrip("\n") + "\n", style="red" if ev.is_error else "dim")
            t.append("\n")
        elif ev.kind == "tool_result":  # orphan result
            if commands_only:
                continue
            if errors_only and not ev.is_error:
                continue
            t.append((ev.output or "").rstrip("\n") + "\n", style="red" if ev.is_error else None)
    return t


class GBSViewer(App):
    CSS = """
    #runs { width: 26; border-right: solid $accent; }
    #steps { width: 48; border-right: solid $accent; }
    #detailscroll { padding: 0 1; }
    #statusbar { height: 1; background: $panel; padding: 0 1; }
    #search { dock: bottom; display: none; }
    #search.visible { display: block; }
    ListView { height: 1fr; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("l", "toggle_live", "Live"),
        Binding("c", "toggle_commands", "Cmds"),
        Binding("e", "toggle_errors", "Errors"),
        Binding("o", "orchestrator", "Orch"),
        Binding("r", "refresh", "Refresh"),
        Binding("slash", "search", "Search"),
        Binding("escape", "clear_search", "ClearSearch", show=False),
    ]

    def __init__(self, gbs_dir, *, live=True, session_id=None):
        super().__init__()
        self.gbs_dir = Path(gbs_dir)
        self.live_enabled = live
        self.initial_session = session_id
        self.runs: list[model.Run] = []
        self.cur_run: model.Run | None = None
        self._cur_step_index: int = 0
        self.commands_only = False
        self.errors_only = False
        self.query = ""
        self.follow_live = live
        self._mtimes: dict[str, float] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="statusbar")
        with Horizontal():
            yield ListView(id="runs")
            yield ListView(id="steps")
            with VerticalScroll(id="detailscroll"):
                yield Static(id="detail", expand=True)
        yield Input(placeholder="search… (Enter to apply, Esc to clear)", id="search")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "GBS Run Viewer"
        self._reload(initial=True)
        self._update_status()
        # Keep the hidden search box out of the focus chain, and focus the runs
        # list so key bindings (c/e/l/o/r) work from the first keystroke.
        self.query_one("#search", Input).can_focus = False
        self.query_one("#runs", ListView).focus()
        if self.live_enabled:
            self.set_interval(POLL_INTERVAL, self._poll)

    def _update_status(self) -> None:
        """Render the toggle-state bar so the active filters are always visible."""
        bar = Text()

        def chip(key: str, label: str, on: bool) -> None:
            bar.append(f"{key} {label}: ", style="dim")
            bar.append("ON" if on else "OFF", style="bold green" if on else "dim")
            bar.append("    ")

        chip("[c]", "commands-only", self.commands_only)
        chip("[e]", "errors-only", self.errors_only)
        if self.live_enabled:
            chip("[l]", "live-follow", self.follow_live)
        else:
            bar.append("[l] live-follow: ", style="dim")
            bar.append("OFF (--no-live)", style="dim")
            bar.append("    ")
        bar.append("[/] search: ", style="dim")
        if self.query:
            bar.append(f'"{self.query}"', style="bold yellow")
        else:
            bar.append("off", style="dim")
        try:
            self.query_one("#statusbar", Static).update(bar)
        except Exception:
            pass

    # ---- data flow ----
    def _reload(self, initial=False) -> None:
        prev_run = self.cur_run.session_id if self.cur_run else None
        prev_step = self._cur_step_index
        self.runs = model.load_runs(self.gbs_dir)
        troot = self.gbs_dir / "transcripts"
        self._mtimes = {r.session_id: model._session_mtime(troot / r.session_id) for r in self.runs}
        runs_lv = self.query_one("#runs", ListView)
        runs_lv.clear()
        for r in self.runs:
            g = GLYPH.get(r.status, "·")
            live = " ●" if r.is_live else ""
            when = r.start_time.strftime("%m-%d %H:%M") if r.start_time else r.session_id[:8]
            runs_lv.append(ListItem(Label(f"{g} {when}{live}")))
        if not self.runs:
            self.query_one("#detail", Static).update(Text("No runs found under .gbs/transcripts/"))
            self.cur_run = None
            return
        idx = 0
        if initial and self.initial_session:
            idx = next((i for i, r in enumerate(self.runs)
                        if r.session_id.startswith(self.initial_session)), 0)
        elif initial:
            idx = next((i for i, r in enumerate(self.runs) if r.is_live), 0)
        elif prev_run:
            idx = next((i for i, r in enumerate(self.runs) if r.session_id == prev_run), 0)
        runs_lv.index = idx
        self._select_run(self.runs[idx], restore_step=None if initial else prev_step)

    def _select_run(self, run: model.Run, restore_step=None) -> None:
        self.cur_run = run
        steps_lv = self.query_one("#steps", ListView)
        steps_lv.clear()
        for s in run.steps:
            g = GLYPH.get(s.status, "·")
            num = "··" if s.number is None else f"{s.number:>2}"
            att = f" #{s.attempt}" if s.attempt > 1 else ""
            steps_lv.append(ListItem(Label(
                f"{g} {num} {s.title[:22]:22} {_fmt_dur(s.duration_s):>6}{att}")))
        if not run.steps:
            return
        if self.follow_live and run.is_live:
            target = len(run.steps) - 1
        elif restore_step is not None and 0 <= restore_step < len(run.steps):
            target = restore_step
        else:
            target = 0
        steps_lv.index = target
        self._render_step_at(target)

    def _render_step_at(self, index: int) -> None:
        if not self.cur_run or not (0 <= index < len(self.cur_run.steps)):
            return
        self._cur_step_index = index
        step = self.cur_run.steps[index]
        self.query_one("#detail", Static).update(render_detail(
            step, commands_only=self.commands_only, errors_only=self.errors_only, query=self.query))
        if self.follow_live and self.cur_run.is_live:
            self.query_one("#detailscroll", VerticalScroll).scroll_end(animate=False)

    # ---- events ----
    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        idx = event.list_view.index
        if idx is None:
            return
        if event.list_view.id == "runs":
            if 0 <= idx < len(self.runs) and (
                not self.cur_run or self.runs[idx].session_id != self.cur_run.session_id
            ):
                self.follow_live = False
                self._select_run(self.runs[idx])
                self._update_status()
        elif event.list_view.id == "steps" and self.cur_run:
            if idx != self._cur_step_index and 0 <= idx < len(self.cur_run.steps):
                self.follow_live = False
                self._render_step_at(idx)
                self._update_status()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query = event.value.strip()
        self._render_step_at(self._cur_step_index)
        inp = self.query_one("#search", Input)
        inp.remove_class("visible")
        inp.can_focus = False
        self.query_one("#steps", ListView).focus()
        self._update_status()

    # ---- actions ----
    def action_toggle_commands(self) -> None:
        self.commands_only = not self.commands_only
        if self.commands_only:
            self.errors_only = False
        self._render_step_at(self._cur_step_index)
        self._update_status()

    def action_toggle_errors(self) -> None:
        self.errors_only = not self.errors_only
        if self.errors_only:
            self.commands_only = False
        self._render_step_at(self._cur_step_index)
        self._update_status()

    def action_orchestrator(self) -> None:
        if self.cur_run and self.cur_run.steps:
            self.query_one("#steps", ListView).index = 0  # orchestrator lane is first

    def action_toggle_live(self) -> None:
        self.follow_live = not self.follow_live
        if self.follow_live:
            self._reload()
        self._update_status()

    def action_refresh(self) -> None:
        self._reload()

    def action_search(self) -> None:
        inp = self.query_one("#search", Input)
        inp.add_class("visible")
        inp.can_focus = True
        inp.focus()

    def action_clear_search(self) -> None:
        inp = self.query_one("#search", Input)
        inp.remove_class("visible")
        inp.can_focus = False
        inp.value = ""
        if self.query:
            self.query = ""
            self._render_step_at(self._cur_step_index)
        self.query_one("#steps", ListView).focus()
        self._update_status()

    # ---- live polling ----
    def _poll(self) -> None:
        troot = self.gbs_dir / "transcripts"
        changed = False
        for r in self.runs:
            if model._session_mtime(troot / r.session_id) != self._mtimes.get(r.session_id):
                changed = True
                break
        if not changed and troot.is_dir():
            existing = {r.session_id for r in self.runs}
            for d in troot.iterdir():
                if d.is_dir() and d.name not in existing and any(d.glob("*.jsonl")):
                    changed = True
                    break
        if changed:
            self._reload()
