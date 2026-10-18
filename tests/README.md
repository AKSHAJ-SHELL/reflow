# tests/

| File | What | Needs KiCad |
|---|---|---|
| `conftest.py` | Finds every fixture, exports a fresh netlist per test | yes |
| `test_netlist.py` | Invariants + hand-checked nets + expected violations per fixture | yes |
| `test_cli.py` | `reflow check` exit codes and output | yes (skips if missing) |
| `test_contracts.py` | Frozen schemas, strict example parsing, stub honesty | no |

Run: `pytest -q`. **Never weaken a test** (docs/agents/04-testing-rules.md).
