"""Model calls through the Claude Code CLI, on the user's own Claude Code login.  OWNER: AGENT (task M-04).

Contract
--------
    ClaudeCodeModel(model, timeout_s, *, executable=None).complete(system, prompt, *, max_tokens=None) -> Completion
    load_model(config) -> Model      # "claude-code" here; every other provider goes to reflow.llm.load_model

`REFLOW_PROVIDER=claude-code` runs each call as one `claude -p` (print mode),
so it uses the user's Claude Code subscription login instead of an API key:

    claude -p --output-format json --tools "" --no-session-persistence \
           --system-prompt <system> [--model <config model>]      # prompt on stdin

- **No tools:** `--tools ""` turns off every built-in tool, so the CLI can
  only answer. It can't read or write files or run commands.
- **Empty folder:** the working directory is a fresh, empty temporary folder,
  deleted afterwards, never the repo.
- **No session saved:** `--no-session-persistence`, so runs don't pile up in
  the user's history.
- **The prompt goes on stdin:** codegen prompts are long, and stdin keeps
  them off the command line.
- **No API key:** `ANTHROPIC_API_KEY` is removed from the CLI's environment,
  so a key left in the shell is never billed instead of the login.
- **The model:** `config["model"]` ("sonnet", "opus", or a full id). Empty
  means the CLI's default. Nothing here hardcodes a model.
- **max_tokens is ignored:** the CLI has no reply budget to set.

It lives outside reflow/llm.py, which stays stdlib-only HTTP with no
environment access and no model names (tests/test_llm.py). The other
providers are unchanged.

Must never
----------
- give the CLI a tool, run it in the repo, or save its session,
- retry, or keep conversation history between calls,
- turn reply text into a part number.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from reflow.llm import Completion, ModelError
from reflow.llm import load_model as _http_load_model

PROVIDER = "claude-code"


class ClaudeCodeModel:
    def __init__(self, model: str, timeout_s: float, *, executable: str | None = None) -> None:
        self.model, self.timeout_s = model or "", float(timeout_s)
        self.executable = executable

    def complete(self, system: str, prompt: str, *, max_tokens: int | None = None) -> Completion:
        exe = self.executable or shutil.which("claude")
        if not exe or not os.path.isfile(exe):
            raise ModelError("the claude CLI isn't installed or on PATH; install Claude Code and log in, "
                             "or use another REFLOW_PROVIDER")
        argv = [exe, "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
                "--system-prompt", system]
        if self.model:
            argv += ["--model", self.model]
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with tempfile.TemporaryDirectory(prefix="reflow-claude-code-") as folder:
            try:
                proc = subprocess.run(argv, input=prompt, capture_output=True, text=True, cwd=folder, env=env,
                                      timeout=self.timeout_s)
            except subprocess.TimeoutExpired as exc:
                raise ModelError(f"claude -p timed out after {self.timeout_s:g} s") from exc
        return parse_print_result(proc, self.model)


def parse_print_result(proc: subprocess.CompletedProcess, model: str) -> Completion:
    """The reply of one `claude -p --output-format json` call, or ModelError. Shared with reflow.tui.agent."""
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        tail = (proc.stderr or proc.stdout).strip()[-500:]
        raise ModelError(f"claude -p failed (exit {proc.returncode}): {tail or 'no output'}") from None
    if not isinstance(data, dict):
        raise ModelError("claude -p returned something other than a JSON object")
    if data.get("is_error") or data.get("subtype") not in (None, "success"):
        raise ModelError(f"claude -p: {str(data.get('result') or data.get('subtype') or 'error')[:500]}")
    text = data.get("result")
    if not isinstance(text, str) or not text.strip():
        raise ModelError("claude -p returned no text")
    usage = data.get("usage") or {}
    tokens_in = sum(int(usage.get(k) or 0) for k in
                    ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    used = next(iter(data.get("modelUsage") or {}), "") or model or "default"
    return Completion(text=text, model=f"{PROVIDER}/{used}", input_tokens=tokens_in,
                      output_tokens=int(usage.get("output_tokens") or 0))


def load_model(config: dict):
    if isinstance(config, dict) and config.get("provider") == PROVIDER:
        return ClaudeCodeModel(str(config.get("model") or ""), float(config.get("timeout_s") or 300))
    return _http_load_model(config)
