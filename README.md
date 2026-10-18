# reflow

**An open-source AI PCB designer that won't let you ship a board you don't understand.**

The hard part of AI-designed boards isn't generating them. It's catching the ones that look fine and are dead. reflow's core is a verifier: hand-written rules for real design mistakes, run on every board, with a plain-English *why* and *fix* for each.

> On the author's real robotics board, a decoupling cap sat in series with the sensor's power pin. KiCad's ERC reported `power_pin_not_driven`: the symptom, with no cause and no fix. `reflow check` says: *"C1 sits in series between +3.3V and U1.8… Connect U1.8 directly to +3.3V, then rewire C1 so one pin is on +3.3V and the other is on GND."*

## Status (2026-10-17)

| Component | Status |
|---|---|
| `reflow check`: verifier CLI (human + JSON output, CI exit codes) | ✅ working |
| Rules: `decoupling.series`, `decoupling.missing`, `i2c.missing_pullup`, `i2c.duplicate_pullup`, `address.floating` | ✅ working |
| Test fixtures (incl. a real board, clean and with its original bug) | ✅ 7 boards, 82 tests |
| Stage contracts (schemas for every pipeline step) | ✅ working |
| `reflow design`: AI planner → parts → tscircuit codegen → verify → fix loop | 🚧 not built (in progress, target 2026-11-01) |
| Part resolver (real, in-stock parts; the AI never picks part numbers) | 🚧 not built |
| Interactive learn mode + sign-off | 🚧 not built |
| Simple 2-layer routing + fab outputs | 🚧 not built (toolchain round trip proven) |

## Quickstart (5 minutes, macOS)

```bash
brew install --cask kicad                       # KiCad 10
git clone https://github.com/AKSHAJ-SHELL/reflow && cd reflow
uv venv --python 3.14 .venv && source .venv/bin/activate
uv pip install -e . pytest
export KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli

reflow check fixtures/real_series_cap        # a real board with a real bug
reflow check fixtures/real_good              # the same board, fixed
reflow check path/to/your/board.kicad_sch      # yours
```

Exit codes: `0` clean · `1` errors · `2` tool/input problem. Add `--json` for CI.

## How it works

```
request ─▶ spec checkpoint (you) ─▶ planner (LLM) ─▶ part resolver (catalog)
        ─▶ codegen (LLM → tscircuit) ─▶ compile (tsci → KiCad)
        ─▶ VERIFIER (rules) ──fail, ≤3 tries──▶ back to codegen
                │ pass
                ▼
        learn mode + sign-off (you) ─▶ route + re-check DRC ─▶ gerbers · BOM · report
```

Today, only the verifier is built: `reflow check` runs it on any KiCad schematic. Details: [docs/02-architecture.md](docs/02-architecture.md).

## Folder guide

| Path | What's there |
|---|---|
| `reflow/` | The package: `netlist.py`, `violation.py`, `contracts.py`, `cli.py`, stubs for planned stages |
| `reflow/rules/` | Verifier rules, one file per family (hand-written) |
| `reflow/parts/`, `reflow/harness/` | Part resolver and harness (being built) |
| `fixtures/` | KiCad boards with known answers (`expected.toml`); one planted bug per bad board |
| `tests/` | Fixture tests, CLI tests, contract tests |
| `docs/` | Design docs, read in order 00 → 08; `docs/examples/` has a JSON example for every contract |
| `prompts/` | LLM prompts, as files (planned) |
| `tools/` | `new_fixture.sh`, `nets.py`, DSN/SES bridges |
| `TASKS.md` | Task board with owners |

## Contributing

- **Send a board that died.** Open an issue with the KiCad files and what went wrong; it becomes a fixture and maybe a rule.
- Rules and fixtures are hand-written and reviewed carefully; plumbing PRs (CLI, exporters, API clients) are welcome. See [AGENTS.md](AGENTS.md) for the rules every contributor (human or AI) follows.
- Every new rule needs a known-good and a known-bad fixture. Never weaken a test to make it pass.

## Limits (honest)

- Intent rules only: 5 checks today. Not a replacement for KiCad ERC/DRC; run both.
- KiCad 10. Single-sheet schematics.
- reflow is an independent open-source project, not affiliated with any commercial PCB tool.
