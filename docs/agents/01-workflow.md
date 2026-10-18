# 01 · Workflow

1. Read `PROGRESS.md` (last 3 entries + **Blocked**).
2. Pick **one** task from `TASKS.md` whose Owner is `AGENT` or `AGENT→HUMAN`, whose dependencies are `done`, and whose status is `todo`. Set it to `doing`.
3. Read the contract(s) it touches in `docs/04-contracts.md` and the stage doc.
4. **Write the failing test first**, from the task's acceptance test. Run it; see it fail for the right reason.
5. Implement the smallest thing that passes.
6. Run the full suite: `pytest -q`. All green, nothing skipped that wasn't skipped before.
7. Check `git status`/`git diff --stat`: only files your task should touch changed. If any HUMAN-owned file changed, revert it.
8. Mark the task `done` (or `blocked`), append to `PROGRESS.md`, hand off (09-handoff).

Never start a second task in the same session before the first is `done` or `blocked`.
