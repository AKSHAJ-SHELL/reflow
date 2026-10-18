# 01 · Current state (2026-10-17)

## Status

| Component | Status | Evidence |
|---|---|---|
| Netlist loader (`reflow/netlist.py`) | **working** | Parses `kicad-cli sch export netlist --format kicadsexpr`; exercised by every fixture test |
| Violation model (`reflow/violation.py`) | **working** | 7 fields, frozen by `tests/test_contracts.py` |
| Rule `decoupling.series` / `decoupling.missing` | **working** (`.missing` has no dedicated fixture) | `bad_series_cap`, `avbotz_series_cap` |
| Rule `i2c.missing_pullup` / `i2c.duplicate_pullup` | **working** (`.duplicate` has no dedicated fixture) | `bad_no_pullups` |
| Rule `address.floating` | **working** | `bad_floating_addr` |
| `reflow check` CLI | **working** | Human + `--json` output, exit codes 0/1/2; `tests/test_cli.py` |
| Fixtures | **working**: 7 | blinky_good, sensor_good, bad_series_cap, bad_no_pullups, bad_floating_addr, avbotz_good, avbotz_series_cap |
| Tests | **working**: 33 (needs kicad-cli) + 49 contract tests (pure Python) | `pytest -q` |
| Stage contracts (`reflow/contracts.py`) | **working** (schemas only) | Added 2026-10-17 |
| DSN/SES bridge (`tools/bridges/`) | **working, not integrated** | Round trip proven 2026-10-07; scripts only |
| tscircuit sample (`boards/blinky`) | **not working as a board** | Compiles, but J1 is unconnected and R1.pin1 floats; it was a smoke test |
| Planner (LLM) | **not built** | |
| Model adapters (`reflow/llm.py`) | **not built** (stub) | |
| Compiler wrapper (`reflow/compile.py`) | **not built** (stub) | |
| Part catalog client (`reflow/parts/catalog.py`) | **not built** (stub) | |
| Part resolver validity/ranking | **not built** (HUMAN, no stub) | |
| Harness loop, retry feedback, termination | **not built** (HUMAN, no stub) | |
| Learn mode + sign-off | **not built** | |
| Router wrapper (`reflow/route.py`) | **not built** (stub) | |
| Fab export (`reflow/export.py`) | **not built** (stub) | |
| README | **not written** (one line) | |

## Real-board result (2026-10-17)

- `reflow check` on the author's real AVBotz MCP9808 → Pi Pico board: **no issues** (no false positives on 13 components).
- Same board with the original September series-cap mistake restored: **`decoupling.series` caught**.
- KiCad ERC on that bad board reports `power_pin_not_driven` on U1 pin 8: the symptom, not the cause, and no fix. **Do not claim "ERC is silent" for the real board.** (ERC is silent on the toy `bad_series_cap` fixture.)

## Housekeeping debt (do first, ~5 min, HUMAN: task Z-01)

- The rename commit `4199dff` moved files but **the `openflux` → `reflow` import edits are uncommitted** (9 files).
- Stray untracked `openflux/netlist.py`: an old copy re-saved by the editor. Delete it.
- `pyproject.toml` has `name = "reflow"`; intended `reflow-pcb`.
- `scratch/` is in `.gitignore` but 14 files under it are still tracked (committed before the ignore). `git rm -r --cached scratch`.
- README is empty.
