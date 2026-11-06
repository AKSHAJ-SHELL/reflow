"""The TUI's agent: one multi-turn Claude Code session that may only read.  OWNER: AGENT (task T-01).

Contract
--------
    ClaudeChat(project_dir, *, system, model="", timeout_s=300, executable=None,
               session_id=None, started=False).ask(text) -> str

Each message is one `claude -p` call on the user's own Claude Code login:

    claude -p --output-format json --tools Read --allowedTools "Read(./**)" --permission-mode dontAsk \
           --system-prompt <system> (--session-id <id> | --resume <id>) [--model <model>]   # message on stdin

- **Read only, inside the project:** Read is the only tool, and it's allowed
  only under the project folder (`Read(./**)`); `dontAsk` denies anything
  else instead of asking. So the agent can read the datasheet and the
  project's files, but not other files, and can't write or run anything.
  (Checked by hand with claude 2.1.319: a Read of a file outside the folder
  came back as a permission denial.)
- **The project folder:** the CLI runs there, so "./datasheet.pdf" is the
  user's datasheet.
- **One conversation:** the first message starts a session with a fixed id
  (`--session-id`); every later one resumes it (`--resume`). The session is
  saved by Claude Code, so it shows in the user's Claude history for that
  folder. `started` says whether the first message went through; the TUI
  stores the id and `started`, so a restart continues the same chat.
- **No API key:** `ANTHROPIC_API_KEY` is removed from the CLI's environment,
  as reflow.claude_code does.

Must never
----------
- give the CLI a tool other than Read, or Read outside the project folder,
- turn reply text into a part number, a file, or a command.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

from reflow.claude_code import parse_print_result
from reflow.llm import ModelError


class ClaudeChat:
    def __init__(self, project_dir, *, system: str, model: str = "", timeout_s: float = 300,
                 executable: str | None = None, session_id: str | None = None, started: bool = False) -> None:
        self.project_dir = Path(project_dir)
        self.system, self.model, self.timeout_s = system, model or "", float(timeout_s)
        self.executable = executable
        self.session_id = session_id or str(uuid.uuid4())
        self.started = started

    def ask(self, text: str) -> str:
        exe = self.executable or shutil.which("claude")
        if not exe or not os.path.isfile(exe):
            raise ModelError("the claude CLI isn't installed or on PATH; install Claude Code and log in")
        argv = [exe, "-p", "--output-format", "json", "--tools", "Read", "--allowedTools", "Read(./**)",
                "--permission-mode", "dontAsk", "--system-prompt", self.system]
        argv += ["--resume", self.session_id] if self.started else ["--session-id", self.session_id]
        if self.model:
            argv += ["--model", self.model]
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        try:
            proc = subprocess.run(argv, input=text, capture_output=True, text=True, cwd=self.project_dir,
                                  env=env, timeout=self.timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise ModelError(f"claude -p timed out after {self.timeout_s:g} s") from exc
        reply = parse_print_result(proc, self.model).text
        self.started = True
        return reply
