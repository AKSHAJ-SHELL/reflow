# 04 · Testing rules

1. **Every rule has a known-good and a known-bad fixture.** Bad fixtures plant **exactly one** bug and list exactly its rule ID in `expected.toml`. Good fixtures list `violations = []`.
2. **Never weaken a test.** No new `skip`, `xfail`, looser assertion, reduced fixture set or edited `expected.toml` to make something pass. If a test is wrong, write why in PROGRESS.md and leave it for the human.
3. **Fixtures and `expected.toml` are HUMAN-owned.** Agents never create, edit or delete them.
4. **Contract tests** (`tests/test_contracts.py`) must stay green. A failure there means a schema changed: that needs a DECISIONS.md entry, not a test edit.
5. **Failing test first** for every task (01-workflow).
6. **Fail on purpose** once for any new check: short-circuit it, confirm a test goes red, restore.
7. **No network in tests.** Use recorded responses (fixtures under `tests/data/`) for API clients and model adapters.
8. **Fakes over mocks for the harness:** a fake model that returns scripted TSX and a fake compiler that returns scripted `CompileResult`s.
9. Tests that need KiCad skip cleanly when `kicad-cli` is missing (see `tests/test_cli.py`); pure-Python tests never need it.
10. Real-board fixtures are the strongest evidence. Only the human removes one.
