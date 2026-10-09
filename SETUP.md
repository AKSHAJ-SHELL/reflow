# OpenFlux — Setup (macOS, Apple Silicon)

Tested 2026-10-07 on macOS (arm64).

## Versions that work

| Tool | Version | Notes |
|---|---|---|
| KiCad | 10.0.5 | Bundled Python 3.9 provides `pcbnew` (needed for DSN/SES) |
| Java | Temurin 25.0.4.1 | freerouting 2.4 requires Java 25+ |
| Python | 3.14.6 (via uv) | atopile ≥0.15 requires exactly 3.14 |
| atopile | 0.15.9 | Pinned `<0.16` (0.16 moves to a hosted workspace). Part picking needs `ato auth login` |
| freerouting | v2.4.1 | Built from source, pinned to the release tag |
| ngspice | 47 | Not needed until simulation work |

## 1. System tools

```bash
brew install --cask kicad
brew install --cask temurin@25
brew install uv ngspice
java -version        # must report 25+
```

## 2. KiCad paths

KiCad does not add commands to your shell on macOS. Add these to `~/.zshrc`:

```bash
export KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
export KICAD_PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
```

Verify:

```bash
$KICAD_CLI version
$KICAD_PY -c "import pcbnew; print(pcbnew.Version(), hasattr(pcbnew,'ExportSpecctraDSN'), hasattr(pcbnew,'ImportSpecctraSES'))"
# expected: 10.0.5 True True
```

## 3. Python environment (from the repo root)

```bash
uv python install 3.14
uv venv --python 3.14 .venv
source .venv/bin/activate
uv pip install "atopile>=0.15.9,<0.16"
which ato            # must point into .venv, not ~/.local/bin
ato --version        # 0.15.9
```

`easyeda2kicad` comes with atopile, so don't install it separately.

## 4. freerouting

```bash
git clone https://github.com/freerouting/freerouting ~/projects/openflux/freerouting
cd ~/projects/openflux/freerouting
git checkout v2.4.1
./gradlew executableJar
cp build/libs/freerouting-current-executable.jar <repo>/tools/freerouting.jar
```

Always run it headless:

```bash
java -Djava.awt.headless=true -jar tools/freerouting.jar --gui.enabled=false \
  -de board.dsn -do board.ses -mp 20
```

## 5. Reference clones (read-only, outside the repo)

`~/projects/openflux/` holds `atopile/`, `tscircuit/` and `freerouting/` for reading source.

## Gotchas hit during setup

- `pip install atopile` on Python 3.12 silently installs **0.2.69** (from 2024). Use Python 3.14.
- A global `ato` from `uv tool install` shadows the venv one. Remove it with `uv tool uninstall atopile`.
- `kicad-cli` has no DSN export. Use `pcbnew.ExportSpecctraDSN` from `$KICAD_PY` (removed in KiCad 11+).
- Scripts using `pcbnew` should start with `import wx; app = wx.App(False)`, or `LoadBoard` can fail.
- Copy the `.kicad_pro` alongside any `.kicad_pcb`. Without it, DRC uses default rules and reports nonsense.
- Refill zones (`pcbnew.ZONE_FILLER`) after importing a routed SES, before running DRC.
- freerouting ignores unknown `--router.*` settings and still exits 0. Check its log.
