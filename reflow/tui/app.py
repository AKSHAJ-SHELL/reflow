"""The terminal UI: `reflow tui [PROJECT_DIR]`.  OWNER: AGENT (task T-01).

Contract
--------
    ReflowApp(project_dir, *, chat=None, planner=None).run()

Left: the current step. Right: the agent (reflow.tui.agent.ClaudeChat), which
the user can ask anything at any step: what a datasheet section means, how to
write a rule, why a run failed. Every step is reflow.tui.project.Project; this
module only shows it:

1. request + exact part number → 2. upload the datasheet → 3. draft the plan,
answer its questions, accept → 4. write rules.toml (template, editor, check)
and confirm → 5. design (`reflow design`, up to 3 attempts) → 6. `reflow
check` on the board's schematic. If it doesn't pass: open it in KiCad, open
learn mode (spot-the-bug, simulations), then type the fix and re-run.

`chat` and `planner` are test seams; by default both run on Claude Code.

Must never
----------
- render model text as markup, or run a command from it,
- confirm the spec or start a design without the user pressing the button.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rich.markdown import Markdown
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, ContentSwitcher, Footer, Header, Input, Label, RichLog, Static

from reflow.config import ConfigError
from reflow.harness.feedback import fill, load_prompt
from reflow.llm import ModelError
from reflow.tui.agent import ClaudeChat
from reflow.tui.project import Draft, Project, ProjectError, dropped_path

TITLES = {
    "request": "1 · What do you want to build?",
    "datasheet": "2 · Upload the datasheet",
    "plan": "3 · The plan",
    "rules": "4 · Your verifier: rules.toml",
    "design": "5 · Design",
    "check": "6 · Check the board",
}
GUIDE = {
    "request": "Tell me what you want to build, and type the exact part number of the main chip. "
               "I never pick a part number for you.",
    "datasheet": "Drag the chip's datasheet PDF into this window, or type its path and press Upload. "
                 "I'll make a text copy so the agent can search it, and I'll only use this datasheet.",
    "plan": "Press Draft the plan. Answer any questions I ask, then accept the plan. "
            "Ask me about the datasheet any time.",
    "rules": "Now write your verifier: rules.toml, one [[rule]] for each thing the datasheet asks for. "
             "Create it from the template, edit it, and check it. Ask me if you're stuck on a section.",
    "design": "Your spec is confirmed. Press Run the design: the agent gets up to 3 attempts.",
    "check": "Run reflow check on the board. If it fails, open it in KiCad and in learn mode to see "
             "what the agent got wrong, then tell me how to fix it.",
}

CSS = """
#main { width: 2fr; padding: 0 1; }
#chat { width: 1fr; border-left: solid $primary; padding: 0 1; }
#chat-log { height: 1fr; }
.title { text-style: bold; margin: 1 0; }
.hint { color: $text-muted; margin-bottom: 1; }
Input { margin-bottom: 1; }
Button { margin: 0 1 1 0; }
.row { height: auto; }
#steps, #steps > Vertical { height: auto; }  /* a step grows with its content, so #main can scroll to its buttons */
RichLog.box { height: 14; border: round $panel; }
"""


class ReflowApp(App):
    TITLE = "reflow"
    CSS = CSS
    BINDINGS = [("ctrl+q", "quit", "Quit"), ("ctrl+b", "back", "Back")]

    def __init__(self, project_dir, *, chat=None, planner=None) -> None:
        super().__init__()
        self.project = Project(project_dir)
        self.sub_title = str(self.project.root)
        self._chat, self._planner = chat, planner
        self.draft: Draft | None = None
        self.learn_proc: subprocess.Popen | None = None

    # --- layout -----------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with VerticalScroll(id="main"):
                with Horizontal(classes="row"):
                    yield Button("← Back", id="back", compact=True)
                    yield Label("", id="stage-title", classes="title")
                with ContentSwitcher(id="steps", initial=self.project.stage):
                    with Vertical(id="request"):
                        yield Input(placeholder="What do you want to build? e.g. ADXL343 accelerometer breakout, I2C, 3.3V",
                                    id="request-text")
                        yield Input(placeholder="Exact part number(s), comma-separated, e.g. ADXL343BCCZ-RL7", id="parts")
                        yield Button("Next", id="start", variant="primary")
                    with Vertical(id="datasheet"):
                        yield Static(GUIDE["datasheet"], classes="hint")
                        yield Input(placeholder="/path/to/datasheet.pdf", id="datasheet-path")
                        yield Button("Upload", id="upload", variant="primary")
                    with Vertical(id="plan"):
                        yield Static("", id="plan-summary")
                        yield Vertical(id="questions", classes="row")
                        with Horizontal(classes="row"):
                            yield Button("Draft the plan", id="draft", variant="primary")
                            yield Button("Re-plan with my answers", id="replan", disabled=True)
                            yield Button("Accept plan", id="accept", disabled=True, variant="success")
                    with Vertical(id="rules"):
                        yield Static("", id="rules-hint", classes="hint")
                        yield Input(placeholder="KiCad symbol for U1, e.g. Sensor_Motion:ADXL343", id="symbol")
                        with Horizontal(classes="row"):
                            yield Button("Create rules.toml", id="template")
                            yield Button("Open in editor", id="edit")
                            yield Button("Check my rules", id="check-rules", variant="primary")
                        yield RichLog(id="rules-log", classes="box", wrap=True, min_width=20)
                        yield Button("Confirm spec and design", id="confirm", variant="success")
                    with Vertical(id="design"):
                        yield Button("Run the design", id="run-design", variant="primary")
                        yield RichLog(id="design-log", classes="box", wrap=True, min_width=20)
                    with Vertical(id="check"):
                        yield Static("", id="run-summary")
                        with Horizontal(classes="row"):
                            yield Button("Run reflow check", id="check", variant="primary")
                            yield Button("Open in KiCad", id="kicad")
                            yield Button("Open learn mode", id="learn")
                            yield Button("Export", id="export")
                        yield RichLog(id="check-log", classes="box", wrap=True, min_width=20)
                        yield Input(placeholder="Tell the agent how to fix it", id="fix")
                        yield Button("Re-run with my fix", id="refix", variant="warning")
            with Vertical(id="chat"):
                yield Label("Agent (Claude Code, reads only)", classes="title")
                yield RichLog(id="chat-log", wrap=True, min_width=20)
                yield Input(placeholder="Ask the agent, e.g. what does SDO/ADDR do?", id="chat-input")
        yield Footer()

    def on_mount(self) -> None:
        self.show(self.project.stage)
        state = self.project.state
        if state.request:
            self.query_one("#request-text", Input).value = state.request
            self.query_one("#parts", Input).value = ", ".join(state.part_numbers)

    def show(self, stage: str) -> None:
        self.query_one("#steps", ContentSwitcher).current = stage
        self.query_one("#back", Button).display = stage != "request"
        first = self.query_one(f"#{stage}").query("Input, Button").first()
        self.call_after_refresh(first.focus)     # a hidden step's box must not keep the cursor
        self.query_one("#stage-title", Label).update(TITLES[stage])
        self.say("reflow", GUIDE[stage])
        if stage == "datasheet" and self.project.state.datasheet:
            self.say("reflow", f"You've uploaded {self.project.state.datasheet} already. Press Upload to keep it, "
                               "or drop a different PDF.")
        if stage == "rules":
            self._rules_hint()
        if stage == "check" and self.project.state.runs:
            self._run_summary()

    def say(self, who: str, text: str) -> None:
        style = {"reflow": "bold cyan", "you": "bold green", "agent": "bold magenta",
                 "problem": "bold red"}.get(who, "bold")
        log = self.query_one("#chat-log", RichLog)
        if who == "agent":
            # Markdown so **bold** and lists read well; never Rich markup, and links aren't made clickable.
            log.write(Text("agent:", style=style))
            log.write(Markdown(text, hyperlinks=False))
            return
        line = Text(f"{who}: ", style=style)
        line.append(text)                         # plain text: never markup
        log.write(line)

    def error(self, message: str) -> None:
        """A problem stays in the chat (a toast alone is gone in seconds)."""
        self.notify(message, severity="error", timeout=10)
        self.say("problem", message)

    def _log(self, widget_id: str, text: str, style: str = "") -> None:
        self.query_one(f"#{widget_id}", RichLog).write(Text(text, style=style))

    # --- buttons --------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handler = getattr(self, f"_on_{(event.button.id or '').replace('-', '_')}", None)
        if handler is not None:
            try:
                handler()
            except ProjectError as exc:
                self.error(str(exc))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "chat-input":
            self._ask(event.value)
            event.input.value = ""
        elif event.input.id == "datasheet-path":
            self.on_button_pressed(Button.Pressed(self.query_one("#upload", Button)))

    def _on_back(self) -> None:
        self.action_back()

    def action_back(self) -> None:
        if any(w.group == "design" and w.is_running for w in self.workers):
            self.notify("The design is still running; wait for it to finish.", severity="warning")
            return
        if self.project.stage == "request":
            return
        stage = self.project.back()
        if stage in ("rules", "plan", "datasheet", "request"):
            self.say("reflow", "Went back. The spec is unconfirmed again, so confirm it once more before the "
                               "next design." if stage == "rules" else "Went back.")
        self.show(stage)

    def _on_start(self) -> None:
        parts = self.query_one("#parts", Input).value.split(",")
        request = self.query_one("#request-text", Input).value
        problems = self.project.part_problems(parts)
        if problems:
            raise ProjectError("; ".join(problems))
        self.project.start(request, parts)        # also refuses an empty field or a JLC number
        self.show("datasheet")

    def _on_upload(self) -> None:
        if self.project.stage == "datasheet":
            self._upload(self.query_one("#datasheet-path", Input).value)

    def _upload(self, text: str) -> None:
        path = self.project.add_datasheet(text)
        copy = self.project.state.datasheet_text
        if copy:
            pages = (self.project.root / copy).read_text(encoding="utf-8").count("=== page ")
            note = f"Text copy: {copy} ({pages} pages), so the agent can search all of it and cite pages."
        else:
            note = "It has no text layer (a scan?), so the agent will read the PDF's pages directly."
        self.say("reflow", f"Got it: {path.name} ({path.stat().st_size // 1024} KB), copied into the project. {note}")
        self.query_one("#datasheet-path", Input).value = ""
        self.show("plan")

    def _dropped_pdf(self, text: str) -> bool:
        """A PDF dragged in at the datasheet step uploads at once; True when it did."""
        path = dropped_path(text) if self.project.stage == "datasheet" else None
        if path is None or path.suffix.lower() != ".pdf":
            return False
        try:
            self._upload(str(path))
        except ProjectError as exc:
            self.error(str(exc))
        return True

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in ("datasheet-path", "chat-input") and self._dropped_pdf(event.value):
            event.input.value = ""

    def on_paste(self, event) -> None:
        self._dropped_pdf(event.text)             # dropped with no box focused

    def _on_draft(self) -> None:
        self._plan(answers=None)

    def _on_replan(self) -> None:
        answers = {inp.name: inp.value for inp in self.query("#questions Input")}
        self._plan(answers=answers)

    def _on_accept(self) -> None:
        if self.draft is None:
            raise ProjectError("draft a plan first")
        self.project.accept_plan(self.draft)
        self.show("rules")

    def _on_template(self) -> None:
        path = self.project.write_rules_template(self.query_one("#symbol", Input).value)
        self._log("rules-log", f"Wrote {path.name}. Open it in your editor and write your rules.")

    def _on_edit(self) -> None:
        path = self.project.rules_path
        if not path.is_file():
            raise ProjectError("create rules.toml first")
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if editor:
            with self.suspend():
                subprocess.run([*editor.split(), str(path)])
        else:
            _open_file(path)
            self._log("rules-log", "Opened rules.toml in your text editor. Save it, then press Check my rules.")

    def _on_check_rules(self) -> None:
        result = self.project.check_rules()
        log = self.query_one("#rules-log", RichLog)
        log.clear()
        self._log("rules-log", f"{result.rules} rule(s): {len(result.errors)} error(s), "
                               f"{len(result.warnings)} warning(s)", "bold")
        for e in result.errors:
            self._log("rules-log", f"error: {e}", "red")
        for w in result.warnings:
            self._log("rules-log", f"warning: {w}", "yellow")
        if not result.errors:
            self._log("rules-log", "Your rules check clean. Confirm when you're ready.", "green")

    def _on_confirm(self) -> None:
        self.project.confirm()
        self.show("design")

    def _on_run_design(self) -> None:
        self._design()

    def _on_check(self) -> None:
        self._check()

    def _on_kicad(self) -> None:
        sch = self._current_run() / "schematic" / "board.kicad_sch"
        if not sch.is_file():
            raise ProjectError("run reflow check first: it writes the schematic")
        _open_file(sch)

    def _on_learn(self) -> None:
        run = self._current_run()
        if self.learn_proc is not None and self.learn_proc.poll() is None:
            self.learn_proc.terminate()
        self.learn_proc = subprocess.Popen([sys.executable, "-m", "reflow", "learn", str(run)],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.say("reflow", "Learn mode is opening in your browser: spot the bug, then run the simulations. "
                           "Come back and tell me how to fix it.")

    def _on_export(self) -> None:
        with self.suspend():
            subprocess.run([sys.executable, "-m", "reflow", "export", str(self._current_run())])
            input("\nPress Enter to go back to reflow.")

    def _on_refix(self) -> None:
        fix = self.query_one("#fix", Input)
        self.project.add_fix(self._current_run(), fix.value)
        self.say("you", f"Fix: {fix.value}")
        fix.value = ""
        self.show("design")
        self._design()

    # --- work that waits on Claude or tools -----------------------------------

    @work(thread=True, exclusive=True, group="plan")
    def _plan(self, answers) -> None:
        self.call_from_thread(self.say, "reflow", "Drafting the plan…")
        try:
            draft = self.project.draft_plan(self._planner_model(), answers=answers)
        except (ProjectError, ModelError, ConfigError) as exc:
            self.call_from_thread(self.error, str(exc))
            return
        self.call_from_thread(self._show_draft, draft)

    def _show_draft(self, draft: Draft) -> None:
        self.draft = draft
        spec, plan = draft.spec, draft.plan
        lines = [f"[b]{spec.title}[/b]  ·  power: {spec.power}",
                 "interfaces: " + "; ".join(spec.interfaces),
                 "constraints: " + "; ".join(spec.constraints),
                 "parts:"]
        lines = [Text.from_markup(lines[0])] + [Text(x) for x in lines[1:]]
        for p in plan.parts:
            lines.append(Text(f"  {p.id}  {p.category:<10} {p.role}  {p.value} {p.package} {p.mpn}".rstrip()))
        lines.append(Text("nets: " + ", ".join(plan.nets)))
        self.query_one("#plan-summary", Static).update(Text("\n").join(lines))
        box = self.query_one("#questions", Vertical)
        box.remove_children()
        open_ = [q for q in spec.open_questions if not q.answer]
        for q in spec.open_questions:
            box.mount(Label(Text(q.question)))
            box.mount(Input(value=q.answer, name=q.id, placeholder="your answer"))
        self.query_one("#replan", Button).disabled = not spec.open_questions
        self.query_one("#accept", Button).disabled = False
        self.say("reflow", f"Plan drafted: {len(plan.parts)} parts. "
                 + (f"{len(open_)} question(s) for you below." if open_ else "Accept it when it looks right."))

    @work(thread=True, exclusive=True, group="chat")
    def _ask(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.call_from_thread(self.say, "you", text)
        chat = self._chat_session()
        try:
            reply = chat.ask(text)
        except ModelError as exc:
            self.call_from_thread(self.say, "reflow", f"The agent couldn't answer: {exc}")
            return
        self.project.remember_chat(chat.session_id, chat.started)
        self.call_from_thread(self.say, "agent", reply)

    @work(thread=True, exclusive=True, group="design")
    def _design(self) -> None:
        run_dir = self.project.next_run_dir()
        argv, env = self.project.design_command(run_dir)
        log_path = self.project.root / ".reflow" / f"design-{run_dir.name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.call_from_thread(self._design_started, run_dir)
        seen = 0
        with log_path.open("w", encoding="utf-8") as out:
            proc = subprocess.Popen(argv, env=env, cwd=self.project.root, stdout=out, stderr=subprocess.STDOUT)
            while proc.poll() is None:
                time.sleep(1)
                seen = self._report_attempts(run_dir, seen)
        seen = self._report_attempts(run_dir, seen)
        tail = log_path.read_text(encoding="utf-8").strip().splitlines()[-6:]
        self.call_from_thread(self._design_done, run_dir, proc.returncode, tail)

    def _design_started(self, run_dir: Path) -> None:
        self.query_one("#run-design", Button).disabled = True
        self._log("design-log", f"Designing into {run_dir.relative_to(self.project.root)} (up to 3 attempts)…", "bold")

    def _report_attempts(self, run_dir: Path, seen: int) -> int:
        run = self.project.run_result(run_dir)
        if run is None:
            return seen
        for a in run.attempts[seen:]:
            if a.compiled:
                rules = ", ".join(sorted(set(a.rule_ids))) or "no violations"
                line = f"attempt {a.attempt}: compiled, {a.errors} error(s), {a.warnings} warning(s): {rules}"
            else:
                line = f"attempt {a.attempt}: didn't compile in {a.compile_tries} tries"
            self.call_from_thread(self._log, "design-log", line)
        return len(run.attempts)

    def _design_done(self, run_dir: Path, code: int, tail: list[str]) -> None:
        self.query_one("#run-design", Button).disabled = False
        for line in tail:
            self._log("design-log", line, "dim")
        run = self.project.run_result(run_dir)
        if run is None:
            self._log("design-log", f"reflow design stopped (exit {code}) before a run started. See the lines above.",
                      "red")
            return
        self.project.record_run(run_dir)
        verdict = {"passed": "passed every check", "failed_verify": "still fails a check",
                   "failed_compile": "never compiled", "aborted": "was aborted"}.get(run.status, run.status)
        self.say("reflow", f"The design {verdict} (best attempt {run.best_attempt}). Now run reflow check.")
        self.show("check")

    @work(thread=True, exclusive=True, group="check")
    def _check(self) -> None:
        run_dir = self._current_run()
        self.call_from_thread(self._log, "check-log", "Writing the schematic and running KiCad ERC + reflow check…",
                              "bold")
        try:
            result = self.project.check_run(run_dir)
        except (ProjectError, RuntimeError) as exc:
            self.call_from_thread(self._check_done, None, str(exc))
            return
        self.call_from_thread(self._check_done, result, "")

    def _check_done(self, result: dict | None, error: str) -> None:
        run = self.project.run_result(self._current_run())
        if result is None:
            self._log("check-log", error, "red")
            ok = False
        else:
            erc, check = result.get("erc"), result.get("check")
            if erc is not None:
                self._log("check-log", f"KiCad ERC: {erc['errors']} error(s), {erc['warnings']} warning(s)")
                for item in erc["items"][:20]:
                    self._log("check-log", f"  {item}", "yellow")
            if check is not None:
                self._log("check-log", f"reflow check: {check['errors']} error(s), {check['warnings']} warning(s)")
                for item in check["violations"]:
                    self._log("check-log", f"  {item}", "red" if item.startswith("error") else "yellow")
            for p in result.get("problems", []):
                self._log("check-log", f"problem: {p}", "red")
            ok = (run is not None and run.status == "passed" and erc is not None and check is not None
                  and erc["errors"] + erc["warnings"] == 0 and check["errors"] == 0 and not result.get("problems"))
        if ok:
            self.say("reflow", "The board passes: 0 ERC errors or warnings, 0 reflow check errors. "
                               "Press Export to route it, sign off and write the fab files.")
        else:
            self.say("reflow", "It doesn't pass yet. Open it in KiCad and in learn mode to find what the agent "
                               "got wrong (spot the bug, run the simulations), then type the fix below and re-run.")

    # --- helpers ----------------------------------------------------------------

    def _current_run(self) -> Path:
        if not self.project.state.runs:
            raise ProjectError("there's no run yet")
        return self.project.runs_dir / self.project.state.runs[-1]

    def _run_summary(self) -> None:
        run = self.project.run_result(self._current_run())
        text = "no run.json yet" if run is None else (
            f"{self.project.state.runs[-1]}: {run.status}, best attempt {run.best_attempt}, "
            f"{len(run.attempts)} attempt(s)")
        self.query_one("#run-summary", Static).update(Text(text))

    def _rules_hint(self) -> None:
        mpn = self.project.state.part_numbers[0]
        found = self.project.symbol_candidates(mpn)
        symbol = self.query_one("#symbol", Input)
        if found and not symbol.value:
            symbol.value = found[0]
        hint = (f"KiCad symbols that match {mpn}: {', '.join(found[:5])}. Check it's the right package."
                if found else f"No KiCad symbol matches {mpn}; type its library id (Library:Symbol).")
        self.query_one("#rules-hint", Static).update(Text(hint))

    def _chat_session(self) -> ClaudeChat:
        state = self.project.state
        system = fill(load_prompt("{datasheet}"), {
            "board_request": state.request,
            "datasheet": f"./{state.datasheet}" if state.datasheet else "(none uploaded yet)",
            "datasheet_text": f"./{state.datasheet_text}" if state.datasheet_text else "(none: read the PDF)",
            "part_numbers": ", ".join(state.part_numbers) or "(none yet)",
        })
        if self._chat is None:
            self._chat = ClaudeChat(self.project.root, system=system, model=os.environ.get("REFLOW_MODEL", ""),
                                    session_id=self.project.saved_chat()[0] or None,
                                    started=self.project.saved_chat()[1])
        self._chat.system = system                # current every message: the datasheet may arrive mid-chat
        return self._chat

    def _planner_model(self):
        if self._planner is None:
            from reflow.claude_code import load_model
            from reflow.config import load_config
            from reflow.providers import KEYLESS_PROVIDERS

            self._planner = load_model(load_config(keyless_providers=KEYLESS_PROVIDERS))
        return self._planner

    def on_unmount(self) -> None:
        if self.learn_proc is not None and self.learn_proc.poll() is None:
            self.learn_proc.terminate()


def _open_file(path: Path) -> None:
    opener = "open" if sys.platform == "darwin" else shutil.which("xdg-open")
    if not opener:
        raise ProjectError(f"open {path} yourself (no file opener found)")
    subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run(project_dir) -> int:
    os.environ.setdefault("REFLOW_PROVIDER", "claude-code")
    ReflowApp(project_dir).run()
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "."))
