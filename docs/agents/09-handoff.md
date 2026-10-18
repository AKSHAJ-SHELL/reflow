# 09 · Handoff

End every session with:

1. `pytest -q` result (and whether KiCad-backed tests ran).
2. `git status --short` clean of unintended files; nothing committed that wasn't part of the task.
3. `TASKS.md` statuses current.
4. A `PROGRESS.md` entry: **Did / Tests / Next**, including the exact next command a fresh session should run.
5. Anything the human must decide goes in `DECISIONS.md` (Proposed) or **Blocked**, not buried in chat.

A fresh agent with no chat history must be able to continue from `PROGRESS.md` + `TASKS.md` alone.
