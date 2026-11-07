"""T-01: the TUI's screens, driven by Textual's test pilot with a fake agent, planner and design run.

Walks the whole front door: request and part number → datasheet upload → plan
(with a question answered) → the user's rules.toml, checked → confirm → a
design run → the check step. Nothing here calls Claude or tsci.
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.widgets import Button, ContentSwitcher, Input, RichLog  # noqa: E402

from reflow.tui.app import ReflowApp  # noqa: E402
from test_tui_project import FakePlanner  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ROOT / "tests" / "data" / "pinmaps" / "kicad"
RUN = json.loads((ROOT / "docs" / "examples" / "run_result.json").read_text())


class FakeChat:
    session_id, started = "0b0c5b9e-6f47-4b52-9d62-1f0a9c9b2a11", True

    def __init__(self):
        self.asked = []

    def ask(self, text):
        self.asked.append(text)
        return "[b]VDD[/b] needs 100 nF (p.35)."  # markup in a reply must show as plain text


def _fake_design(tmp_path: Path) -> Path:
    script = tmp_path / "fake_design.py"
    run = dict(RUN, status="failed_verify")
    script.write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "run_dir = Path(sys.argv[sys.argv.index('--run-dir') + 1])\n"
        "run_dir.mkdir(parents=True)\n"
        f"data = json.loads({json.dumps(json.dumps(run))})\n"
        "data['run_dir'] = str(run_dir); data['run_id'] = run_dir.name\n"
        "(run_dir / 'run.json').write_text(json.dumps(data))\n"
        "print('status=failed_verify')\nsys.exit(1)\n")
    return script


def test_the_whole_front_door(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(SYMBOLS))
    project = tmp_path / "board"
    project.mkdir()
    pdf = tmp_path / "MCP9808.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    chat, planner = FakeChat(), FakePlanner()
    app = ReflowApp(project, chat=chat, planner=planner)
    script = _fake_design(tmp_path)
    app.project.design_command = lambda run_dir: ([sys.executable, str(script), "--run-dir", str(run_dir)],
                                                  dict(**__import__("os").environ))

    async def walk():
        async with app.run_test(size=(160, 60)) as pilot:
            steps = app.query_one("#steps", ContentSwitcher)
            assert steps.current == "request"
            app.query_one("#request-text", Input).value = "MCP9808 temperature sensor breakout, I2C, 3.3V"
            app.query_one("#parts", Input).value = "MCP9808"
            await pilot.click("#start")
            assert steps.current == "datasheet"

            app.query_one("#datasheet-path", Input).value = f"'{pdf}'"     # a dragged path comes quoted
            await pilot.click("#upload")
            assert steps.current == "plan" and (project / "MCP9808.pdf").is_file()

            await pilot.click("#chat-input")
            app.query_one("#chat-input", Input).value = "What does VDD need?"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            assert chat.asked == ["What does VDD need?"]
            log = app.query_one("#chat-log", RichLog)
            assert any("[b]VDD[/b]" in line.text for line in log.lines)

            await pilot.click("#draft")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert not app.query_one("#accept", Button).disabled
            answer = app.query("#questions Input").first()
            answer.value = "0x18"
            await pilot.click("#replan")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "0x18" in planner.prompts[-1]
            await pilot.click("#accept")
            assert steps.current == "rules"
            assert app.query_one("#symbol", Input).value == "Sensor_Temperature:MCP9808_MSOP"

            await pilot.click("#confirm")                   # no rules yet: refused, still on rules
            assert steps.current == "rules"
            await pilot.click("#template")
            rules = project / "rules.toml"
            rules.write_text(rules.read_text() + '\n[[rule]]\non = "U1.VDD"\nneed = "cap"\nto = "GND"\n'
                             'source = "MCP9808 datasheet, 6.1, p.35"\nwhy = "spikes"\n')
            await pilot.click("#check-rules")
            await pilot.click("#confirm")
            assert steps.current == "design"
            assert json.loads((project / "spec.json").read_text())["confirmed"] is True

            await pilot.click("#run-design")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert steps.current == "check"
            assert app.project.state.runs == ["01-mcp9808-breakout"]

            app.query_one("#fix", Input).value = "Put C1 between V3_3 and GND."
            await pilot.click("#refix")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.project.state.runs == ["01-mcp9808-breakout", "02-mcp9808-breakout"]
            spec = json.loads((project / "spec.json").read_text())
            assert spec["constraints"][-1] == "Designer's fix after 01-mcp9808-breakout: Put C1 between V3_3 and GND."

    asyncio.run(walk())


def test_a_config_problem_is_a_message_not_a_crash(tmp_path, monkeypatch):
    from reflow.config import ConfigError

    project = tmp_path / "board"
    project.mkdir()
    app = ReflowApp(project, chat=FakeChat())

    def broken():
        raise ConfigError("REFLOW_API_KEY is not set")

    app._planner_model = broken
    app.project.start("MCP9808 breakout", ["MCP9808"])
    app.project.state.stage = "plan"

    async def walk():
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.click("#draft")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.is_running and app.query_one("#steps", ContentSwitcher).current == "plan"
            log = app.query_one("#chat-log", RichLog)
            assert any("REFLOW_API_KEY is not set" in line.text for line in log.lines)   # stays on screen

    asyncio.run(walk())


def test_back_returns_to_the_previous_step(tmp_path):
    project = tmp_path / "board"
    project.mkdir()
    app = ReflowApp(project, chat=FakeChat(), planner=FakePlanner())

    async def walk():
        async with app.run_test(size=(160, 60)) as pilot:
            steps = app.query_one("#steps", ContentSwitcher)
            assert not app.query_one("#back", Button).display        # nothing to go back to
            app.query_one("#request-text", Input).value = "INA226 power monitor"
            app.query_one("#parts", Input).value = "C49851, VSSOP-10"
            await pilot.click("#start")
            assert steps.current == "request"                        # a JLC number is refused
            app.query_one("#parts", Input).value = "MCP9808"
            await pilot.pause(0.3)                                   # Textual ignores a 2nd click within 0.2 s
            await pilot.click("#start")
            assert steps.current == "datasheet"
            await pilot.click("#back")
            assert steps.current == "request" and app.project.stage == "request"
            assert app.query_one("#parts", Input).value == "MCP9808"
            await pilot.press("ctrl+b")                              # already first: stays
            assert steps.current == "request"

    asyncio.run(walk())
