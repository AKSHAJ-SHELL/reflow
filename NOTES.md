## 2026-10-07 — first routing round trip (esp32_minimal)
- Chain works: KiCad → DSN → freerouting v2.4.1 → SES → KiCad
- First run 238 violations = setup error (no .kicad_pro, zones not refilled). Fixed → 77 vs 75 baseline.
- freerouting reported 0 unrouted / 1 violation; KiCad found 7 unconnected, +10 starved_thermal.
- Decision: pipeline always refills zones + re-runs KiCad DRC after routing; never trust the router's self-report.
## 2026-10-07 — atopile quickstart
- Builds fine on 0.15.9 (0.5s, .kicad_pcb produced)
- CLI prints: 0.15.8 is the last CLI release, maintenance mode only, replaced by hosted app (0.16+)
- Picking: [cached? / required login? — fill in after the 33k test]
- Leaning: switch substrate to tscircuit. Decide after tscircuit quickstart.

## 2026-10-07 — substrate: switched atopile → tscircuit
- atopile 0.15.x CLI is end-of-life (maintenance only, replaced by hosted app)
- tscircuit: builds with no account; exports kicad_sch + kicad_pcb + DSN + netlist
- KiCad ERC/DRC/netlist all run on tscircuit exports; netlist matches tscircuit's own
- Open: power-net split bug (#595) untested — no power nets in sample
- Keep atopile in venv only to build its examples as reference answers

## 2026-10-08 — How to spot a short (and why ERC won't)

**What a short is (netlist view):** two things meant to be on separate nets end up on the same net.
Can't be judged from the netlist alone — compare against the intended connections.

**How to check:**
1. Write the intended nets first (e.g. blinky: +5V = J1.1, R1.1 · mid = R1.2, D1.A · GND = D1.K, J1.2)
2. Export the netlist: `$KICAD_CLI sch export netlist --format kicadsexpr -o x.net x.kicad_sch`
3. Print it compactly: `python3 tools/nets.py x.net`
4. Compare line by line
5. In KiCad: click a wire + backtick (`) highlights the whole net

**Signs of a short:**
- Both pins of a 2-pin part (R, C, LED, 2-pin connector) on the same net
- A power name missing: placed +5V and GND but only one shows up (KiCad keeps one name when two power symbols merge)
- A net with far more pins than expected

**Why ERC misses it:** ERC checks pin *types* (passive, input, output, power_in…), not intent.
R/C/LED/connector pins are all `passive`, so on simple boards ERC has almost nothing to check.
A cap is passive in parallel *and* in series → ERC can't tell them apart.
> ERC reasons about pin types; my rules reason about what each part is for.

**Lesson from today:** misread the blinky schematic image as a +5V/GND short — the netlist showed it was correct.
Verify connectivity from the netlist, never from the picture (mine or an AI's).

**Rule ideas (Block C):**
- Two different power symbols must never resolve to the same net
- Both pins of a 2-terminal part must be connected, and to *different* nets

## 2026-10-10 — First rule: decoupling.series
- bad_series_cap: KiCad ERC → [N] violations, none about C1/U1.8
- reflow decoupling.series → caught, with fix hint
- sensor_good / blinky_good → no false positives
## 2026-10-17 — Real-board gate: club MCP9808 → Pi Pico board
- Cloned my original board (github.com/AKSHAJ-SHELL/mcp9808-breakout) into scratch/club
- `reflow check` on the board as committed (series cap already fixed): **no issues** → no false positives on a real 13-component board
- Fixtures added: `real_good` (real board, clean) + `real_series_cap` (same board, original September series-cap mistake put back)
- `reflow check fixtures/real_series_cap` → **decoupling.series** caught, with why + fix
- pytest: 33 passed (7 fixtures × 4 + 5 CLI tests)

**Correction to my launch claim:** on the real board, KiCad ERC is NOT silent.
- ERC: `[power_pin_not_driven] Input Power pin not driven by any Output Power pins` on U1 pin 8 (V_DD)
- That's the series cap showing up indirectly: V_DD sits alone on its own net behind C1
- ERC names the symptom, not the cause, and gives no fix. The common reaction is to drop a PWR_FLAG on the net, which silences ERC while the board stays dead (likely why the toy bad_series_cap fixture reports 0 errors)
- Launch wording: "ERC says 'power pin not driven'; reflow says C1 is in series with the chip's power and how to fix it." Never claim "ERC is silent" for the real board.

**Noise:** the Fontconfig warnings from kicad-cli are Homebrew fontconfig config noise, harmless. Hide with `2>/dev/null`.
