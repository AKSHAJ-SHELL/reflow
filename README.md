# reflow

**An open-source AI PCB designer that won't let you ship a board you don't understand.**

The hard part of AI-designed boards isn't generating them. It's catching the ones that look fine and are dead. reflow's core is a verifier: hand-written rules for real design mistakes, run on every board, with a plain-English *why* and *fix* for each. The AI designs, the verifier checks, and you sign off before any fab files are written.

> On the author's real robotics board, a decoupling cap sat in series with the sensor's power pin. KiCad's ERC reported `power_pin_not_driven`: the symptom, with no cause and no fix. `reflow check` says: *"C1 sits in series between +3.3V and U1.8… Connect U1.8 directly to +3.3V, then rewire C1 so one pin is on +3.3V and the other is on GND."*

## Status (2026-10-31)

| Component | Status |
|---|---|
| `reflow check`: verifier CLI for any KiCad schematic (human + JSON output, CI exit codes) | ✅ working |
| Rules: `decoupling.series`, `decoupling.missing`, `i2c.missing_pullup`, `i2c.duplicate_pullup`, `address.floating`, plus pin-map checks on AI boards (`pinout.*`) | ✅ working |
| `reflow design`: model → tscircuit code → compile → verify → fix loop (≤ 3 attempts) | ✅ working, from a spec and plan you confirm (`reflow tui` drafts them; see Limits) |
| Part resolver: real parts from a local JLCPCB catalog snapshot; the AI never picks part numbers | ✅ working |
| Routing check + fab outputs (`reflow export`): tscircuit's routing checked with KiCad DRC, then gerbers, drill, placement, BOM, and a KiCad schematic | ✅ working |
| Learn mode + sign-off (`reflow learn`): spot the AI's bug in a local web app before you can export | ✅ working |
| Run report (`reflow report`): every attempt, error, violation and the sign-off | ✅ working |
| Front door (`reflow tui`): request → datasheet → plan questions → your rules.toml → design → check → fix, with a Claude Code agent beside you | 🆕 new (11-06), not yet tried by a person on a new board |

Eval (2026-10-28, Sonnet via Claude Code, 5 boards × 3 runs): 12 of 15 runs gave a verifier-clean board on the first attempt, with 0 part numbers outside the resolver. The AMS1117 regulator failed all 3 runs on a pin-map question that's still open. The expected answers for these boards haven't been checked by a person yet, so treat this as a draft result. Details: [evals/README.md](evals/README.md).

## Quickstart: check a board (5 minutes, macOS)

```bash
brew install --cask kicad                       # KiCad 10
git clone https://github.com/AKSHAJ-SHELL/reflow && cd reflow
uv venv --python 3.14 .venv && source .venv/bin/activate
uv pip install -e .

reflow check fixtures/real_series_cap        # a real board with a real bug
reflow check fixtures/real_good              # the same board, fixed
reflow check path/to/your/board.kicad_sch      # yours
```

Exit codes: `0` clean · `1` errors (or warnings with `--strict`) · `2` tool/input problem. Add `--json` for CI. reflow finds `kicad-cli` in the KiCad app; set `KICAD_CLI` if yours is somewhere else. `reflow check` has no Python dependencies; plain `pip install -e .` on Python 3.11+ works too.

## Design a board

Extra one-time setup (every tool, version and setting: [SETUP.md](SETUP.md)):

```bash
brew install node oven-sh/bun/bun   # tsci runs on Bun
npm ci --prefix tools/tscircuit    # tsci, which compiles the AI's board code, at the locked version
export PATH="$PWD/tools/tscircuit/node_modules/.bin:$PATH"   # or set TSCI to that tsci
reflow parts update                # downloads the JLCPCB parts snapshot (about 1.5 GB)
uv pip install -e '.[learn,tui]'   # learn mode's local web server, and the terminal UI
```

Pick a model. With [Claude Code](https://claude.com/claude-code) installed and logged in, no API key is needed:

```bash
export REFLOW_PROVIDER=claude-code REFLOW_MODEL=sonnet
```

Or use an API: set `REFLOW_PROVIDER` to `anthropic`, `openai` or `openai-compatible`, `REFLOW_MODEL` to a model id, `REFLOW_BASE_URL` if needed, and put the key in `REFLOW_API_KEY` (never in `reflow.toml`).

**The easy way: the terminal UI.** Make a folder for your board and open reflow there:

```bash
mkdir -p ~/boards/accel && cd ~/boards/accel && reflow tui
```

It walks you through it, with an agent (Claude Code, on your login) on the right that you can ask anything:

1. Type what you want and the chip's exact part number (reflow never picks one for you).
2. Drag the chip's datasheet PDF into the window; it uploads at once. reflow makes a page-by-page text copy so the agent can search all of it and cite pages. The agent reads only that datasheet and files in this folder.
3. Draft the plan, answer its questions, accept it.
4. Write your verifier, `rules.toml`: one rule for each thing the datasheet asks for. reflow gives you a template and checks it. Ask the agent if a section confuses you.
5. Confirm, and the agent designs the board (up to 3 attempts).
6. Run `reflow check` on it. If it doesn't pass, open it in KiCad and in learn mode to see what went wrong, then type the fix and run it again.

Everything is saved in the folder (`spec.json`, `plan.json`, `rules.toml`, `runs/`), so you can close it and pick up later.

**By hand.** Then design, learn, sign off and export. The five boards in `evals/` each have a ready `spec.json` and `plan.json`:

```bash
reflow design --spec evals/mcp9808_breakout/spec.json --plan evals/mcp9808_breakout/plan.json --run-dir runs/mcp9808
reflow learn runs/mcp9808          # find the AI's bug, then sign off
reflow export runs/mcp9808         # DRC, then gerbers, drill, placement, BOM, schematic into runs/mcp9808/out
reflow report runs/mcp9808         # report.md: every attempt, what failed and why
```

`reflow export` refuses, and lists every reason, unless the board passed the verifier, every net is routed with 0 DRC errors and within its length limit, every part number came from the resolver, and you signed off. The routing comes from tscircuit's autorouter, and it sometimes routes a decoupling cap's trace longer than the plan allows. reflow then calls the routing partial and refuses; run `reflow design` again with a new `--run-dir`.

## How it works

```
spec + plan (you) ─▶ part resolver (catalog)
        ─▶ codegen (LLM → tscircuit) ─▶ compile (tsci → KiCad)
        ─▶ VERIFIER (rules) ──fail, ≤3 tries──▶ back to codegen
                │ pass
                ▼
        learn mode + sign-off (you) ─▶ route check + DRC ─▶ gerbers · BOM · schematic · report
```

Details: [docs/02-architecture.md](docs/02-architecture.md).

## Folder guide

| Path | What's there |
|---|---|
| `reflow/` | The package: CLI, compile, verifier, routing check, export, schematic, report |
| `reflow/rules/` | Verifier rules, one file per family (hand-written) |
| `reflow/harness/` | The design loop: attempts, feedback to the model, when to stop |
| `reflow/parts/` | Parts snapshot, catalog queries, resolver, KiCad pin maps |
| `reflow/learn/` | Learn mode's server; `web/` is its source |
| `prompts/` | The model prompts, as files |
| `evals/` | Five boards the design loop is measured on |
| `fixtures/` | KiCad boards with known answers (`expected.toml`); one planted bug per bad board |
| `tests/` | Tests for every stage |
| `docs/` | Design docs, read in order 00 → 08; `docs/examples/` has a JSON example for every contract |
| `tools/` | `new_fixture.sh`, `nets.py`, DSN/SES bridges |
| `TASKS.md` | Task board with owners |

## Contributing

- **Send a board that died.** Open an issue with the KiCad files and what went wrong; it becomes a fixture and maybe a rule.
- Rules and fixtures are hand-written and reviewed carefully; plumbing PRs (CLI, exporters, API clients) are welcome. See [AGENTS.md](AGENTS.md) for the rules every contributor (human or AI) follows.
- Every new rule needs a known-good and a known-bad fixture. Never weaken a test to make it pass.

## Limits 

**What it can design**
- **Simple, low-speed, 2-layer boards:** I²C sensors, EEPROMs, LEDs, a regulator, about 20 parts. Microcontrollers, USB, DDR, Ethernet and RF are out: there's no high-speed check.
- **The TUI is new.** `reflow tui` drafts the spec and plan from your request and you confirm them, but no one has yet used it start to finish on a new board.

**What the checks miss**
- **Few rules.** The verifier catches 5 kinds of schematic mistake, plus pin-map errors and one draft rule (`i2c.pullup_rail`, awaiting review). It's not a replacement for KiCad ERC/DRC; run both.
- **Your `rules.toml` guides the design but doesn't fail it yet.** The model is told every rule you write, but nothing checks the board against them (R-10). A board can say `passed` while ignoring one of your rules.
- **I²C checks find the bus by pin name.** A chip whose datasheet names its I²C pins differently (the LIS3DH's `SPC`/`SDI` instead of `SCL`/`SDA`) skips the pull-up and address checks without saying so.
- **No SPI checks.** SPI boards rely on your `rules.toml` and KiCad's ERC.
- **No current or analog layout checks.** reflow doesn't know which traces carry high current, so trace width isn't checked. Kelvin connections (a current-sense amplifier's inputs meeting the shunt at its pads) aren't checked either. Check them in KiCad.

**Where it runs**
- **The board code comes from tscircuit.** reflow draws its own KiCad schematic at export (0 ERC errors and warnings on the boards it can draw) and doesn't ship tscircuit's, which loses connections.
- **Routing is tscircuit's autorouter.** It sometimes routes a trace past its length limit, and then export refuses.
- **The model's code runs on your machine**, as tscircuit TSX, with your permissions. See [docs/REVIEWING.md](docs/REVIEWING.md#4-known-risks-in-the-code-today).
- KiCad 10, single-sheet schematics. Tested on macOS only.
- reflow is an independent open-source project, not affiliated with any commercial PCB tool.
