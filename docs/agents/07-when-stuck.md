# 07 · When stuck

**Three attempts, then stop.** An attempt = one hypothesis + one change + one test run.

After the third failed attempt:

1. Revert to the last green state (`git stash` or discard your changes).
2. Add to `PROGRESS.md` under **Blocked**:
   ```
   - YYYY-MM-DD · <task ID> · <one-line symptom>
     Tried: 1) ... 2) ... 3) ...
     Evidence: <command> → <exact error, ≤10 lines>
     Need from human: <the specific question or decision>
   ```
3. Set the task to `blocked` in `TASKS.md`. Stop. Don't start another task to "make progress."

Stop immediately (no attempts) if the fix requires: editing HUMAN-owned code, changing a contract, weakening a test, adding a dependency with an unclear license, or writing outside the repo.
