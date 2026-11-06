"""T-01: the TUI's agent, a multi-turn Claude Code session that may only read.

A fake `claude` records each call. The first message starts a session with a
fixed id; later ones resume it. The only tool is Read, the session runs in the
project folder, Read is allowed only inside it, and ANTHROPIC_API_KEY never reaches the CLI.
"""
import json
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from reflow.llm import ModelError
from reflow.tui.agent import ClaudeChat

RECORD = """
import json, os, sys
log = os.environ["FAKE_LOG"]
calls = json.load(open(log)) if os.path.exists(log) else []
calls.append({"argv": sys.argv[1:], "stdin": sys.stdin.read(), "cwd": os.getcwd(),
              "has_api_key": "ANTHROPIC_API_KEY" in os.environ})
json.dump(calls, open(log, "w"))
print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                  "result": "SDO/ADDR sets the address (p.18).", "usage": {}, "modelUsage": {}}))
"""
FAIL = """
import json
print(json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "boom"}))
"""


def _fake(tmp_path: Path, body: str) -> Path:
    exe = tmp_path / "bin" / "claude"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def test_the_chat_starts_a_session_then_resumes_it_with_read_only(tmp_path, monkeypatch):
    project = tmp_path / "board"
    project.mkdir()
    log = tmp_path / "log.json"
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-reach-the-cli")
    chat = ClaudeChat(project, system="You help a designer read a datasheet.", model="sonnet",
                      executable=str(_fake(tmp_path, RECORD)))
    assert chat.ask("What does SDO/ADDR do?") == "SDO/ADDR sets the address (p.18)."
    chat.ask("And CS?")
    first, second = json.loads(log.read_text())
    for call in (first, second):
        argv = call["argv"]
        assert argv[0] == "-p" and argv[argv.index("--output-format") + 1] == "json"
        assert argv[argv.index("--tools") + 1] == "Read"
        assert argv[argv.index("--allowedTools") + 1] == "Read(./**)"   # only files in the project folder
        assert argv[argv.index("--permission-mode") + 1] == "dontAsk"   # anything else is denied, not asked
        assert argv[argv.index("--model") + 1] == "sonnet"
        assert "--no-session-persistence" not in argv     # resuming needs the saved session
        assert Path(call["cwd"]).resolve() == project.resolve()
        assert not call["has_api_key"]
    assert first["argv"][first["argv"].index("--session-id") + 1] == chat.session_id
    assert "--resume" not in first["argv"]
    assert second["argv"][second["argv"].index("--resume") + 1] == chat.session_id
    assert first["stdin"] == "What does SDO/ADDR do?" and second["stdin"] == "And CS?"
    assert first["argv"][first["argv"].index("--system-prompt") + 1] == "You help a designer read a datasheet."


def test_a_saved_session_is_resumed_from_the_first_message(tmp_path, monkeypatch):
    log = tmp_path / "log.json"
    monkeypatch.setenv("FAKE_LOG", str(log))
    chat = ClaudeChat(tmp_path, system="s", session_id="0b0c5b9e-6f47-4b52-9d62-1f0a9c9b2a11", started=True,
                      executable=str(_fake(tmp_path, RECORD)))
    chat.ask("hello again")
    (call,) = json.loads(log.read_text())
    assert call["argv"][call["argv"].index("--resume") + 1] == "0b0c5b9e-6f47-4b52-9d62-1f0a9c9b2a11"


def test_an_error_from_claude_is_raised(tmp_path):
    chat = ClaudeChat(tmp_path, system="s", executable=str(_fake(tmp_path, FAIL)))
    with pytest.raises(ModelError, match="boom"):
        chat.ask("hi")
    assert not chat.started                       # a failed first call doesn't count as a started session


def test_no_claude_is_a_clear_error(tmp_path):
    with pytest.raises(ModelError, match="claude CLI"):
        ClaudeChat(tmp_path, system="s", executable=str(tmp_path / "missing")).ask("hi")


def test_each_prompt_is_found_by_its_own_placeholder():
    from reflow.harness.feedback import load_prompt

    for marker, heading in [("{request}", "# Planner"), ("{resolved_parts}", "# Codegen"),
                            ("{compile_line}", "# Fix"), ("{datasheet}", "# reflow TUI agent")]:
        assert heading in load_prompt(marker)     # raises if two prompts share a placeholder
