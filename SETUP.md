# reflow: setup (macOS, Apple Silicon)

Checked 2026-10-31 on macOS 26 (arm64). The README's Quickstart is the short version; this page lists every tool, what needs it, and the settings.

## Versions that work

| Tool | Version | Needed for |
|---|---|---|
| KiCad | 10.0.5 | everything: `reflow check` reads schematics with its `kicad-cli`; export runs DRC and ERC with it |
| Python | 3.11+ (tested on 3.12 and 3.14, via uv) | everything |
| Node | 26 (any recent LTS should do) | `reflow design`: installs tscircuit |
| Bun | 1.4 | `reflow design`: `tsci` runs on Bun |
| tscircuit (`tsci`) | 0.0.2768 | `reflow design`: compiles the AI's board code to circuit.json and `.kicad_pcb`, and routes it |
| Claude Code | 2.1 | optional: `REFLOW_PROVIDER=claude-code`, model calls on your Claude Code login instead of an API key |
| ngspice | 47 | optional: learn mode's simulations. Without it, reflow uses the ngspice library bundled with KiCad |

`reflow check` needs only KiCad and Python. It has no Python dependencies.

## 1. KiCad and Python

```bash
brew install --cask kicad
brew install uv
git clone https://github.com/AKSHAJ-SHELL/reflow && cd reflow
uv venv --python 3.14 .venv
source .venv/bin/activate
uv pip install -e .
reflow check fixtures/real_good            # expect: ✓ No issues found
```

reflow finds `kicad-cli` inside `/Applications/KiCad/KiCad.app`. If KiCad is somewhere else, set:

```bash
export KICAD_CLI=/path/to/kicad-cli
```

## 2. Designing boards

```bash
brew install node oven-sh/bun/bun
npm ci --prefix tools/tscircuit    # tscircuit 0.0.2768 with every dependency locked
export PATH="$PWD/tools/tscircuit/node_modules/.bin:$PATH"   # add to ~/.zshrc, or set TSCI to that tsci
tsci --version                     # 0.0.2768
reflow parts update                # JLCPCB parts snapshot from jlcparts, about 1.5 GB, into ~/.cache/reflow/jlcparts/
uv pip install -e '.[learn,tui]'   # learn mode's local web server (fastapi, uvicorn, fsrs), and the TUI (textual)
```

Why a lockfile: `npm i -g tscircuit@0.0.2768` pins tscircuit but not its dependencies. On 2026-10-31 a fresh install pulled a newer `circuit-json` and `tsci` failed to start (`Export named 'drawing_dimension_line' not found`). `tools/tscircuit/package-lock.json` was made from a working install, so `npm ci` gets exactly that tree.

The learn mode web app ships prebuilt in the package, so you don't need to build `web/`.

## 3. A model

Either your Claude Code login (no API key; install Claude Code and log in first):

```bash
export REFLOW_PROVIDER=claude-code
export REFLOW_MODEL=sonnet                   # or opus, or a full model id; empty uses Claude Code's default
```

Or an API:

```bash
export REFLOW_PROVIDER=anthropic             # or openai, or openai-compatible
export REFLOW_MODEL=<model id>
export REFLOW_BASE_URL=<url>                 # only for openai-compatible
export REFLOW_API_KEY=<your key>             # environment only; reflow refuses a key in reflow.toml
```

Keep the key out of your shell history: put these lines in a `.env` file (gitignored) and load it with `set -a; source .env; set +a`.

## Settings

`reflow.toml` (in the repo root) holds the loop's caps. A set environment variable overrides the file.

| Setting | Env | Default | What it does |
|---|---|---|---|
| `max_attempts` | `REFLOW_MAX_ATTEMPTS` | 3 | design attempts before reflow stops |
| `compile_cap` | `REFLOW_COMPILE_CAP` | 2 | compile retries inside one attempt |
| `provider`, `model`, `base_url` | `REFLOW_PROVIDER`, `REFLOW_MODEL`, `REFLOW_BASE_URL` | none | the model (above) |
| `timeout_s` | `REFLOW_TIMEOUT_S` | 60 | seconds per model call (300 for claude-code) |
| `max_tokens` | `REFLOW_MAX_TOKENS` | 4096 | per model reply; raise it for reasoning models |

Environment only:

| Env | What it does |
|---|---|
| `REFLOW_API_KEY` | API key for anthropic / openai / openai-compatible |
| `KICAD_CLI` | path to `kicad-cli` when it isn't in the KiCad app |
| `TSCI` | path to `tsci` when it isn't on PATH |
| `REFLOW_PARTS_DB` | where the parts snapshot lives (default `~/.cache/reflow/jlcparts/cache.sqlite3`) |
| `REFLOW_PARTS_URL`, `REFLOW_PARTS_TIMEOUT` | snapshot source and per-file download timeout (default 300 s) |
| `REFLOW_KICAD_SYMBOL_DIR` | KiCad symbol libraries for pin maps (default: the ones installed with KiCad) |
| `REFLOW_VAULT` | learn mode's vault (default `~/.reflow/vault`) |
| `REFLOW_NGSPICE`, `REFLOW_LIBNGSPICE` | the ngspice command or library for learn mode |

## Running the tests

```bash
uv pip install -e '.[test,learn,tui]'
pytest -q                          # about 7 minutes; needs KiCad and tsci
```

Every test should pass. `i2c.pullup_rail`, which `tests/test_i2c_pullup_rail.py` checks, is an agent-written draft awaiting the maintainer's review (DECISIONS O-1d).

## Contributors only: DSN/SES bridges and freerouting

reflow v1 routes with tscircuit's autorouter. The freerouting fallback (task X-02) isn't built; the scripts in `tools/bridges/` are for working on it. They need:

- Java 25+ (`brew install --cask temurin@25`) and `tools/freerouting.jar` (freerouting v2.4.1, built from source with `./gradlew executableJar`);
- KiCad's bundled Python, for `pcbnew`:
  ```bash
  export KICAD_PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
  $KICAD_PY -c "import pcbnew; print(pcbnew.Version())"     # 10.0.5
  ```

Run freerouting headless:

```bash
java -Djava.awt.headless=true -jar tools/freerouting.jar --gui.enabled=false -de board.dsn -do board.ses -mp 20
```

## Gotchas

- On Linux, a KiCad that has never opened its GUI has no global library tables, so ERC warns that every library is missing and `reflow export` refuses. Copy KiCad's defaults into place: `mkdir -p ~/.config/kicad/10.0 && cp /usr/share/kicad/template/{sym,fp}-lib-table ~/.config/kicad/10.0/` (CI does this).
- Copy the `.kicad_pro` next to any `.kicad_pcb`. Without it, DRC uses default rules and reports nonsense.
- Open a fixture through its `.kicad_pro`, not the `.kicad_sch`, or KiCad saves an `Untitled` project next to it.
- A wall of `Fontconfig warning` lines from kicad-cli is harmless Homebrew noise.
- `kicad-cli` has no DSN export; `tools/bridges/` uses `pcbnew.ExportSpecctraDSN` from `$KICAD_PY` (removed in KiCad 11+).
- Scripts using `pcbnew` should start with `import wx; app = wx.App(False)`, or `LoadBoard` can fail.
- Refill zones (`pcbnew.ZONE_FILLER`) after importing a routed SES, before running DRC.
- freerouting ignores unknown `--router.*` settings and still exits 0. Check its log.
