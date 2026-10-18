# 08 · Runbook

macOS (Apple Silicon). Full tool versions and install steps: [`SETUP.md`](../SETUP.md).

## One-time

```bash
brew install --cask kicad          # 10.x; DSN/SES bridge needs 10, not 11
brew install --cask temurin@25     # freerouting
brew install uv oven-sh/bun/bun    # bun for tscircuit
npm i -g tscircuit                 # provides `tsci` (check: tsci --version)
export KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli   # in ~/.zshrc
uv venv --python 3.14 .venv && source .venv/bin/activate
uv pip install -e . pytest
```

## Everyday commands

| Task | Command |
|---|---|
| Check a board | `reflow check path/to/board.kicad_sch` (or a project folder / `.kicad_pro`) |
| JSON for scripts/CI | `reflow check board.kicad_sch --json` |
| All tests | `pytest -q` (expect 33 KiCad-backed + 49 contract tests) |
| Contract tests only (no KiCad) | `pytest -q tests/test_contracts.py` |
| New fixture from an existing one | `tools/new_fixture.sh sensor_good bad_<name>` |
| Open a fixture in KiCad | `open fixtures/<name>/<name>.kicad_pro` (always via the `.kicad_pro`) |
| Print a netlist compactly | `$KICAD_CLI sch export netlist --format kicadsexpr -o /tmp/x.net <sch> && python3 tools/nets.py /tmp/x.net` |
| ERC for comparison | `$KICAD_CLI sch erc <sch> -o /tmp/erc.rpt 2>/dev/null && cat /tmp/erc.rpt` |
| DSN export / SES import | `$KICAD_PY tools/bridges/export_dsn.py` / `import_ses.py` (KiCad's bundled Python) |
| Route headless | `java -Djava.awt.headless=true -jar tools/freerouting.jar --gui.enabled=false -de board.dsn -do board.ses -mp 20` |

## Exit codes (`reflow check`)

`0` no errors · `1` errors (or warnings with `--strict`) · `2` tool/input problem.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `kicad-cli not found` | Set `KICAD_CLI` (above) |
| Wall of `Fontconfig warning` lines | Homebrew fontconfig noise, harmless; add `2>/dev/null` |
| A fixture opens as "Untitled" | Opened the `.kicad_sch` directly. Quit without saving, delete `Untitled.*` in that folder, reopen via `.kicad_pro` |
| `pytest` ran 0 tests after pasting commands | zsh doesn't treat `#` as a comment when pasted; remove inline comments |
| DRC reports hundreds of violations | `.kicad_pro` missing next to the `.kicad_pcb`, or zones not refilled |
| freerouting "succeeds" but board is unrouted | Never trust its log; refill zones and run `kicad-cli pcb drc` |
| `LoadBoard` returns None in pcbnew scripts | Start with `import wx; app = wx.App(False)`; check the path exists |
| ImportError on `tomllib` | Python < 3.11; use the repo's 3.14 venv |
