# PROGRESS (append-only)

Newest entry at the bottom. Never edit or delete old entries. Every session (human or agent) appends one.

Format:
```
## YYYY-MM-DD · <who> · <task IDs>
Did: ...
Tests: <command> → <result>
Next: ...
```

## Blocked

(Agents: add blockers here with date + task ID; the human clears them.)

- none

---

## 2026-10-07 → 2026-10-17 · human · (history, summarized from NOTES.md and git log)
Did: toolchain round trip (KiCad → DSN → freerouting → SES → KiCad); switched substrate atopile → tscircuit; netlist loader + generic fixture tests; rules decoupling.series, i2c.missing_pullup/duplicate_pullup, address.floating; `reflow check` CLI; real club board fixtures (clean + original series-cap bug); renamed reflow → reflow.
Tests: `pytest -q` → 33 passed (2026-10-17).
Next: finish rename (Z-01), launch post for `reflow check` (D-01), harness decisions (H-00).

## 2026-10-17 · agent (Claude) · C-01 + docs/scaffold
Did: added `reflow/contracts.py` (22 stage contracts, strict from_dict), `docs/examples/*.json`, `tests/test_contracts.py` (49 tests), stubs `reflow/{llm,compile,route,export}.py`, `reflow/parts/catalog.py`; docs 00–08; README; TASKS.md; AGENTS.md/CLAUDE.md; DECISIONS.md; docs/agents/01–09; module READMEs; `runs/` added to .gitignore. No HUMAN-owned code touched. Rename import edits left uncommitted for the human (Z-01).
Tests: `python3 -m pytest -q --noconftest tests/test_contracts.py` → 49 passed (Linux VM, Python 3.10). KiCad-backed tests not run here (no kicad-cli); run `pytest -q` on the Mac.
Next: human answers H-00 (Q3–Q6) and decisions D-1…D-6.

## 2026-10-19 · agent (integration) · M-02, M-01, K-01, K-02, P-01, P-03, H-08, H-05, H-06, H-07
Did: agent-owned plumbing landed on `shashi`. Config loader (`reflow.toml` / env, `max_attempts=3`, `compile_cap=2`, missing `REFLOW_API_KEY` raises `ConfigError`). Model adapter `complete(system, prompt) -> Completion` with `ModelError` on 401/500, no retry and no tools, plus `extract_code_fence` (`str | None`). `compile_board` via `tsci` (blinky ok, syntax error `ok=False`, missing `tsci` raises). Catalog client and cache for jlcsearch; the client does not rank or pick a winner. Prompt drafts in `prompts/planner.md`, `prompts/codegen.md`, `prompts/fix.md` (human approval still required before a loop loads them). Run-folder writer `reflow/harness/runs.py`. `reflow design` loads a confirmed Spec JSON, refuses `confirmed: false`, and rejects a Plan `mpn` outside `Spec.named_parts`. H-01, H-02, H-03, H-04, P-02, and L-01 were not written. The harness loop is not implemented.
Tests: validation `pytest -q` on `51129f7f3e31bf2a0af9ec5b7df1d212ecc03ffb` → 154 passed. Verdict PASS (`docs/harness-validation-report.md`, worker `bc-3b0eca06-da2e-525f-a07f-096a3c0830e5`). The same run also reported 4 failed and 28 errors in `tests/test_cli.py` and `tests/test_netlist.py`; those match `dde218a` (KiCad 10 fixtures, KiCad 7 CLI) and are not from this plumbing.
Next: human writes H-00 acceptances, the harness loop (H-01..H-04), resolver validity (P-02), and learn-mode selection (L-01). End-to-end `reflow design` stays parked until that loop exists.
