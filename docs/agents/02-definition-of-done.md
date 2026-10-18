# 02 · Definition of done

A task is done only when **all** are true:

- [ ] The task's acceptance test exists, failed before the change, and passes now.
- [ ] `pytest -q` is fully green (KiCad-backed tests run on a machine with KiCad 10; say so in PROGRESS.md if you couldn't run them).
- [ ] Every object crossing a stage boundary is a `reflow/contracts.py` type; any example JSON you produced parses with `from_dict`.
- [ ] No HUMAN-owned file changed (`git diff --stat` checked).
- [ ] No hardcoded model ids, API keys, absolute paths or prompts in code.
- [ ] New dependencies follow 08-dependencies (verified, licensed, pinned, recorded).
- [ ] The module's README "contract" section still matches the code.
- [ ] `TASKS.md` status updated; `PROGRESS.md` entry appended.
- [ ] For AGENT→HUMAN tasks: left as `doing` with "awaiting human review" in PROGRESS.md. Only the human marks it done.
