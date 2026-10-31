"""M-04: model calls through the Claude Code CLI on the user's own login.

A fake `claude` executable records what it was given, so these tests check the
exact command: print mode, every tool off, no saved session, the prompt on
stdin, an empty temporary folder, and no ANTHROPIC_API_KEY in its environment
(so the call runs on the user's Claude Code login, not API credits).
"""
import json
import stat
import textwrap
from pathlib import Path

import pytest

from reflow.claude_code import ClaudeCodeModel, load_model
from reflow.llm import Completion, ModelError

ROOT = Path(__file__).resolve().parents[1]


def _fake(tmp_path: Path, body: str) -> Path:
    exe = tmp_path / "bin" / "claude"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text("#!/usr/bin/python3\n" + textwrap.dedent(body), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


RECORD = """
import json, os, sys
log = {"argv": sys.argv[1:], "stdin": sys.stdin.read(), "cwd": os.getcwd(),
       "cwd_entries": os.listdir("."), "has_api_key": "ANTHROPIC_API_KEY" in os.environ}
open(os.environ["FAKE_LOG"], "w").write(json.dumps(log))
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "```tsx\\nboard\\n```",
                  "usage": {"input_tokens": 1200, "cache_read_input_tokens": 300, "output_tokens": 450},
                  "modelUsage": {"claude-test-model": {}}}))
"""


def test_a_call_runs_print_mode_with_tools_off_on_stdin_in_an_empty_folder(tmp_path, monkeypatch):
    log = tmp_path / "log.json"
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-reach-the-cli")
    model = ClaudeCodeModel("sonnet", 60, executable=str(_fake(tmp_path, RECORD)))
    result = model.complete("You write tscircuit TSX.", "Design the board.")
    assert result == Completion(text="```tsx\nboard\n```", model="claude-code/claude-test-model",
                                input_tokens=1500, output_tokens=450)
    seen = json.loads(log.read_text())
    argv = seen["argv"]
    assert argv[0] == "-p"
    assert argv[argv.index("--tools") + 1] == ""
    assert "--no-session-persistence" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--system-prompt") + 1] == "You write tscircuit TSX."
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert "Design the board." not in argv            # the prompt goes on stdin, not the command line
    assert seen["stdin"] == "Design the board."
    assert seen["cwd_entries"] == [] and not Path(seen["cwd"]).resolve().is_relative_to(ROOT)
    assert not Path(seen["cwd"]).exists()             # the temporary folder is removed afterwards
    assert seen["has_api_key"] is False


def test_without_a_model_the_cli_default_is_used(tmp_path, monkeypatch):
    log = tmp_path / "log.json"
    monkeypatch.setenv("FAKE_LOG", str(log))
    ClaudeCodeModel("", 60, executable=str(_fake(tmp_path, RECORD))).complete("s", "p")
    assert "--model" not in json.loads(log.read_text())["argv"]


def test_an_error_reply_raises_with_its_message(tmp_path):
    exe = _fake(tmp_path, """
        import json, sys; sys.stdin.read()
        print(json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                          "result": "Claude usage limit reached"}))
    """)
    with pytest.raises(ModelError, match="usage limit"):
        ClaudeCodeModel("", 60, executable=str(exe)).complete("s", "p")


def test_a_failed_run_raises_with_stderr(tmp_path):
    exe = _fake(tmp_path, """
        import sys; sys.stdin.read(); sys.stderr.write("Invalid API key · Please run /login\\n"); sys.exit(1)
    """)
    with pytest.raises(ModelError, match="/login"):
        ClaudeCodeModel("", 60, executable=str(exe)).complete("s", "p")


def test_an_empty_reply_raises(tmp_path):
    exe = _fake(tmp_path, """
        import json, sys; sys.stdin.read()
        print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": ""}))
    """)
    with pytest.raises(ModelError, match="no text"):
        ClaudeCodeModel("", 60, executable=str(exe)).complete("s", "p")


def test_a_slow_cli_times_out(tmp_path):
    exe = _fake(tmp_path, "import time; time.sleep(5)\n")
    with pytest.raises(ModelError, match="timed out"):
        ClaudeCodeModel("", 0.5, executable=str(exe)).complete("s", "p")


def test_a_missing_cli_says_how_to_get_it(tmp_path):
    with pytest.raises(ModelError, match="Claude Code"):
        ClaudeCodeModel("", 60, executable=str(tmp_path / "nope")).complete("s", "p")


def test_load_model_picks_claude_code_and_leaves_other_providers_to_llm():
    from reflow import llm

    cc = load_model({"provider": "claude-code", "model": "opus", "api_key": "", "base_url": None, "timeout_s": 300,
                     "max_tokens": 4096})
    assert isinstance(cc, ClaudeCodeModel) and cc.model == "opus" and cc.timeout_s == 300
    http = load_model({"provider": "anthropic", "model": "m", "api_key": "k", "base_url": "https://x.invalid",
                       "timeout_s": 5, "max_tokens": 10})
    assert type(http) is type(llm.load_model({"provider": "anthropic", "model": "m", "api_key": "k",
                                               "base_url": "https://x.invalid", "timeout_s": 5, "max_tokens": 10}))


def test_the_cli_commands_use_this_loader():
    import reflow.cli as cli

    assert cli.load_model is load_model



def test_the_cli_loads_config_with_claude_code_keyless(monkeypatch, tmp_path):
    """`reflow eval` with REFLOW_PROVIDER=claude-code and no REFLOW_API_KEY gets past config."""
    import reflow.cli as cli
    import reflow.evals as evals_module

    for name in ("REFLOW_API_KEY", "REFLOW_MODEL", "REFLOW_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("REFLOW_PROVIDER", "claude-code")
    monkeypatch.chdir(ROOT)
    seen = {}

    def fake_run_evals(evals_dir, **kw):
        seen["model"] = kw["make_model"]("x")
        return {"boards": [], "by_board": {}, "go_no_go": {"decision": "undecided", "reason": "none"},
                "totals": {"boards": 0, "passed": 0, "first_pass": 0, "clean": 0, "foreign_part_numbers": 0,
                           "input_tokens": 0, "output_tokens": 0, "model_errors": 0, "design_failures": 0}}

    monkeypatch.setattr(evals_module, "run_evals", fake_run_evals)
    assert cli.main(["eval", "--evals", str(tmp_path)]) == 0
    assert isinstance(seen["model"], ClaudeCodeModel)
