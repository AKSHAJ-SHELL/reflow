# AGENTS.md: operating manual for coding agents

You are working on **reflow**, an open-source AI PCB design agent. The verifier is done; the harness is being built. The author hand-writes everything that can be *plausibly wrong*; you build plumbing that fails *loudly*.

## Read order (every session)

1. `PROGRESS.md`: last 3 entries and anything under **Blocked**
2. `docs/00-overview.md`: assumptions and non-negotiables
3. `TASKS.md`: pick **one** task you own (Owner = AGENT or AGENT→HUMAN)
4. `docs/04-contracts.md` and the docs for your task's stage
5. `docs/agents/`: workflow and rules below

## Golden rules

1. **Never touch OWNER=HUMAN code:** `reflow/rules/`, `reflow/harness/` core (loop, termination, feedback conversion), resolver validity logic (P-02), learn-mode selection (L-01), `fixtures/`, `expected.toml` files, `reflow/netlist.py`, `reflow/violation.py`. Not even a typo fix. Write it in PROGRESS.md instead.
2. **One task ID at a time.** Failing test first. Done = the task's acceptance test passes and `pytest -q` is green.
3. **Contracts are law.** Data crossing a stage boundary is a type from `reflow/contracts.py`. Changing one needs a `DECISIONS.md` proposal the human accepts.
4. **Never weaken a test.** Not a skip, not a looser assert, not a deleted fixture.
5. **The AI never picks a part number.** No code path may let model output become an MPN/LCSC id unless it came from the resolver or `Spec.named_parts`.
6. **Never hide a failed run.** Never claim "AI-designed" or "routed" without the verify + DRC report.
7. **Prompts live in `prompts/*.md`, config in `reflow.toml`/env.** No hardcoded model ids, keys or paths.
8. **Stuck after 3 attempts → stop.** Write it under **Blocked** in `PROGRESS.md`.
9. **Log every session** in `PROGRESS.md` (append-only).

## Manual

| File | Topic |
|---|---|
| [docs/agents/01-workflow.md](docs/agents/01-workflow.md) | One task at a time, failing test first |
| [docs/agents/02-definition-of-done.md](docs/agents/02-definition-of-done.md) | When a task is actually done |
| [docs/agents/03-coding-standards.md](docs/agents/03-coding-standards.md) | Style, prompts as files, config |
| [docs/agents/04-testing-rules.md](docs/agents/04-testing-rules.md) | Fixtures, never weaken a test |
| [docs/agents/05-hand-vs-agent-code.md](docs/agents/05-hand-vs-agent-code.md) | Who writes what, and why |
| [docs/agents/06-integrity.md](docs/agents/06-integrity.md) | Honesty rules for outputs and claims |
| [docs/agents/07-when-stuck.md](docs/agents/07-when-stuck.md) | Stop rules |
| [docs/agents/08-dependencies.md](docs/agents/08-dependencies.md) | Verify, license, pin |
| [docs/agents/09-handoff.md](docs/agents/09-handoff.md) | End-of-session handoff |
