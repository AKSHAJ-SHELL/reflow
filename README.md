# reflow

**An early AI PCB design agent with a verifier that checks its work.**

You describe a small board. An AI drafts it. A verifier written by a person, not by the AI, checks the draft and explains every mistake in plain English. The AI never picks a part number.

> **This is an alpha.** It handles simple, low-speed boards, and it has real gaps. Read [Limits](#limits) and [Risks](#risks) before trusting anything it makes.

## This project grows as I learn

I'm learning electronics while I build this, and reflow only knows what I understand well enough to write a check for. The more I learn, the more the base of reflow will reflect it.

| Stage | What reflow can check | State |
|---|---|---|
| Low-speed boards: I²C sensors, EEPROMs, LEDs | connections, datasheet pin maps, decoupling and pull-ups | **built, and limited** |
| Power and analog: current limits, trace width, heat | | planned |
| High-speed and RF: impedance, return paths, length matching | | planned |
| FPGA boards: power sequencing, many rails, BGA | | planned |
| Chip design (Verilog) | whether the verifier-first idea carries over at all | an idea, not decided |

Anything marked planned doesn't exist yet. If you know more than I do, corrections are the most useful thing you can send.

## What works today

| Part | What it does | State |
|---|---|---|
| `reflow check` | Checks any KiCad schematic for 5 kinds of mistake | works |
| `reflow design` | Model → board code → compile → verify → fix, up to 3 attempts | works on simple boards |
| Part resolver | Finds real parts in a local copy of the JLCPCB catalog | works; some of it is awaiting my review |
| `reflow tui` | The guided way to design a board, step by step | new; one full run so far |
| `reflow learn` | Find the AI's bug in a local web app, run two circuit simulations, sign off | works; simulations awaiting my review |
| `reflow export` | Runs KiCad DRC, then writes gerbers, drill, placement and BOM | works; often refuses (see Limits) |
| `reflow report` | Writes up every attempt, error and sign-off | works |

**What has actually been tested:**
- **Eval, 2026-10-28:** 5 simple boards × 3 runs, on one model (Sonnet, through Claude Code). 12 of 15 runs gave a verifier-clean board on the first attempt, with 0 part numbers from outside the resolver. The AMS1117 regulator failed all 3. An AI agent drafted the boards' expected results and I checked them on 2026-10-31, after this run, so this run's file still says `undecided`. It's a progress check on simple boards I chose, not a benchmark. The results: [evals/results/20261028T161716Z.json](evals/results/20261028T161716Z.json).
- **One real run through the TUI, 2026-11-06:** an INA226 power monitor ([boards/opi-power-demo](boards/opi-power-demo)). It went from a prompt to a verifier-clean schematic on the first attempt, with 0 KiCad ERC violations, and an electrical mentor looked over the schematic informally. It hasn't been routed, exported or built, and its `rules.toml` wasn't enforced (see Limits).
- **No board designed by reflow has been fabricated and tested yet.**

## Try it: check a schematic (5 minutes, macOS)

You need [Homebrew](https://brew.sh). No AI or API key is involved in this part.

```bash
brew install --cask kicad
brew install uv
git clone https://github.com/AKSHAJ-SHELL/reflow
cd reflow
uv venv --python 3.14 .venv
source .venv/bin/activate
uv pip install -e .
```

Run it on a board with a planted bug, then on a good one:

```bash
reflow check fixtures/bad_series_cap
```

```bash
reflow check fixtures/sensor_good
```

The first one reports:

```
✗ ERROR  decoupling.series   C1, U1
  C1 sits in series between +3.3V and U1.8; U1 only gets power through a
  capacitor, which blocks DC.
  why:  A capacitor blocks DC, so the chip never gets steady power and won't
        turn on. Decoupling caps go in parallel, power to ground, to absorb fast
        current spikes at the chip.
  fix:  Connect U1.8 directly to +3.3V, then rewire C1 so one pin is on +3.3V
        and the other is on GND.
```

Then point it at your own board:

```bash
reflow check path/to/your/board.kicad_sch
```

## Design a board

**One-time setup.** Run these from the `reflow` folder (every tool and setting is in [SETUP.md](SETUP.md)):

```bash
brew install node oven-sh/bun/bun
npm ci --prefix tools/tscircuit
export PATH="$PWD/tools/tscircuit/node_modules/.bin:$PATH"
uv pip install -e '.[learn,tui]'
reflow parts update    # downloads the JLCPCB parts catalog, about 1.5 GB
```

The `export PATH` line lasts for one terminal session. Add it to `~/.zshrc`, with the full path, to keep it.

You also need [Claude Code](https://claude.com/claude-code), installed and logged in. reflow uses your login, so no API key is needed.

**Then make a folder for your board and open reflow there:**

```bash
mkdir -p ~/boards/my-board && cd ~/boards/my-board && reflow tui
```

The screen walks you through it, with an AI helper on the right you can ask anything:

1. **Say what you want,** and type the exact part number of the main chip. reflow never picks one for you.
2. **Drag in the chip's datasheet PDF.** The helper can then search it and cite pages.
3. **Draft the plan** and answer its questions. Press **Re-plan with my answers** until it's right, then **Accept plan**.
4. **Write your `rules.toml`:** one rule for each thing the datasheet asks for. reflow gives you a template and checks it. Ask the helper if a section confuses you.
5. **Run the design.** The AI gets up to 3 attempts.
6. **Run `reflow check`.** If it fails, open it in KiCad and learn mode, work out what went wrong, type the fix and run it again.

**← Back** (or Ctrl+B) goes back a step, and Ctrl+Q quits. Everything is saved in the folder, so you can close it and pick up later.

## All commands

| Command | What it does |
|---|---|
| `reflow check PATH` | Check a `.kicad_sch`, a `.kicad_pro` or a project folder. Add `--json` for JSON, or `--strict` to fail on warnings. |
| `reflow tui [FOLDER]` | Design a board step by step. Needs `[tui]` and Claude Code. |
| `reflow design --spec S --plan P --run-dir D` | Design without the TUI, from a spec and plan you wrote. |
| `reflow learn RUN` | Open a finished run in your browser: find the bug, simulate, sign off. Needs `[learn]`. |
| `reflow export RUN` | Run DRC and write fab files to `RUN/out`. |
| `reflow report RUN` | Write `report.md` and `report.json` for a run. |
| `reflow rules check FILE` | Check a `rules.toml` against its parts' pins. |
| `reflow parts update` | Download or refresh the JLCPCB parts catalog. |
| `reflow eval` | Run the eval boards. Add `--only NAME` for one, or `--repeat N`. |

`reflow check` exits `0` when clean, `1` on errors, and `2` for a tool or input problem. Add `--help` to any command for the details.

**Without the TUI**, each folder in `evals/` has a ready spec and plan:

```bash
reflow design --spec evals/mcp9808_breakout/spec.json --plan evals/mcp9808_breakout/plan.json --run-dir runs/mcp9808
```

```bash
reflow learn runs/mcp9808
```

```bash
reflow export runs/mcp9808
```

To use an API instead of Claude Code, see [SETUP.md](SETUP.md#3-a-model).

## Limits

**What it can design**
- **Simple, low-speed, 2-layer boards only:** I²C sensors, EEPROMs, LEDs, a regulator, about 20 parts.
- **Microcontrollers, USB, DDR, Ethernet and RF are out.** There's no high-speed check of any kind.
- **Regulators are shaky.** The AMS1117 failed every eval run on a pin-map question that's still open.

**What the checks miss**
- **"Passed" is a narrow claim.** It means the board compiled and has no violations of the few rules below. It doesn't mean the board works.
- **Only 5 kinds of schematic mistake are caught** (`decoupling.series`, `decoupling.missing`, `i2c.missing_pullup`, `i2c.duplicate_pullup`, `address.floating`), plus pin-map errors on AI boards and one draft rule (`i2c.pullup_rail`). It doesn't replace KiCad's ERC and DRC; run both.
- **Your `rules.toml` doesn't fail a board yet.** The AI is told your rules, but nothing checks the board against them. A board can say `passed` while breaking one (task R-10).
- **I²C checks find the bus by pin name.** A chip that names its pins differently, like the LIS3DH's `SPC`/`SDI`, skips those checks without telling you.
- **No SPI or UART checks.**
- **No current, heat or analog layout checks.** Trace width and Kelvin connections aren't checked. Check them in KiCad.
- **Only two simulations exist** (decoupling and I²C rise time). They use assumed values, shown next to each graph.

**Parts**
- **JLCPCB catalog only.** You can't use another vendor's library yet.
- **The catalog is a snapshot,** so stock and prices can be out of date.

**Routing and platform**
- **Routing is tscircuit's autorouter.** It sometimes breaks a length limit or can't finish, and then `reflow export` refuses. That's deliberate.
- **KiCad 10, single-sheet schematics.** The full flow has only been run on macOS.

## Risks

- **Don't order a board on reflow's word.** Review the schematic and layout yourself against the datasheets. A wrong board costs money and can damage whatever it's plugged into.
- **The AI's code runs on your computer** with your permissions. Its board code is compiled locally as tscircuit TSX, and it isn't sandboxed yet. If you use an API key, that code could reach it (task CI-06). Don't run reflow on a machine holding secrets you can't afford to lose. Details: [docs/REVIEWING.md](docs/REVIEWING.md#4-known-risks-in-the-code-today).
- **Your data goes to the model provider.** Your request, plan and answers, and the parts of your datasheet the helper reads, are sent to Claude or whichever API you set. Don't use it on confidential designs.
- **The local learn server has a known gap.** It only listens on your own machine, but it doesn't check the Host header yet, so a malicious website could try to reach it while it's running (task CI-07). Close it when you're done.
- **AI usage counts against your account.** Runs use your Claude Code plan or your API credits.
- **Some code hasn't had a full human review.** I hand-wrote the core rules and design loop, and AI agents wrote much of the plumbing. Items marked *awaiting human review* in [TASKS.md](TASKS.md) are agent-written and not yet signed off: the resolver's category logic, pin binding, the simulation testbenches and `i2c.pullup_rail`.
- **Expect breaking changes.** File formats and commands can change between versions.

## How it works

```
your request + datasheet ─▶ plan (you confirm) ─▶ part resolver (JLCPCB catalog)
        ─▶ AI writes board code ─▶ compile ─▶ VERIFIER ──fail, up to 3 tries──▶ back to the AI
                                                  │ pass
                                                  ▼
                 you review and sign off ─▶ route check + DRC ─▶ gerbers · BOM · schematic · report
```

More detail: [docs/02-architecture.md](docs/02-architecture.md).

## Folder guide

| Path | What's there |
|---|---|
| `reflow/` | The package: CLI, compile, verifier, routing check, export, TUI |
| `reflow/rules/` | The verifier's rules, one file per family |
| `reflow/harness/` | The design loop: attempts, feedback to the model, when to stop |
| `reflow/parts/` | Parts catalog, resolver, KiCad pin maps |
| `reflow/learn/` | Learn mode's server (`web/` is its source) |
| `prompts/` | The model prompts, as files |
| `boards/` | Sample board projects, including the INA226 demo |
| `evals/` | The boards the design loop is measured on |
| `fixtures/` | KiCad boards with known answers; one planted bug per bad board |
| `tests/` | Tests for every stage |
| `docs/` | Design docs, read in order 00 → 08 |
| `TASKS.md`, `PROGRESS.md` | What's planned, and a log of what happened, including failures |

## Contributing

- **Send a board that died.** Open an issue with the KiCad files and what went wrong. It could become a fixture and maybe a rule.
- **Tell me what's wrong.** Mistakes in the rules or in this README are the most useful reports.
- Plumbing PRs (CLI, exporters, API clients) are welcome. [AGENTS.md](AGENTS.md) has the rules every contributor, human or AI, follows. Never weaken a test to make it pass.

## License

**reflow doesn't have a license yet,** so for now no one else has permission to reuse the code. I plan to open-source it and will add a `LICENSE` file when I've chosen one.

reflow is an independent project, not affiliated with any commercial PCB tool.
