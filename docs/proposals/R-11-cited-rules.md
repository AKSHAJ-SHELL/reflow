# R-11: verifier rules from published sources ("book knowledge")

Status: PROPOSED 2026-10-29 by the agent. Rule code is HUMAN (`reflow/rules/`, docs/05). This file only
drafts candidates, each with its source, threshold, what it reads, the bad fixture to plant and what
it does to the boards we have. Nothing here is built.

## Why

The human asked for the verifier to carry "book knowledge", not just what one datasheet says. Two
kinds of knowledge fit the verifier, and they come in by different paths:

1. **General rules from a standard or a vendor's application note**: true for every board. Each
   becomes a rule in `reflow/rules/`, written by the human, cited in docs/05 (R-07).
2. **Per-part requirements from that part's datasheet** (decoupling value, an LDO's output capacitor,
   an LED's forward current): true for one part. These already have a path: `rules.toml` `[[rule]]`
   entries (V-21, R-10's `project.<need>` checks), drafted from the datasheet with a quote (V-2b) and
   confirmed by a person. They don't belong in a general rule.

Sources are cited by document, revision, section and table, not copied: the rule text is ours, and
docs/05 links the source.

Also already in place: KiCad's own ERC now runs on our schematic of every exported board (O-04), so
the textbook pin-type checks (a power input with nothing driving it, an output fighting an output,
an unconnected pin) are enforced at 0 errors and 0 warnings before export.

## Sources (read 2026-10-29 from the documents themselves)

- **[UM10204]** NXP, *I²C-bus specification and user manual*, UM10204 Rev. 7.0, 1 October 2021.
  §7.1 "Pull-up resistor sizing" (Equation 1: Rp(max) = tr / (0.8473 × Cb); Equation 2:
  Rp(min) = (VDD − VOL(max)) / IOL; Figures 41–42), Table 10 "Characteristics of the SDA and SCL
  I/O stages" (tr max 1000 ns Standard-mode, 300 ns Fast-mode; Cb max 400 pF; IOL 3 mA at
  VOL = 0.4 V for Standard- and Fast-mode; Ci max 10 pF per I/O pin).
  https://www.nxp.com/docs/en/user-guide/UM10204.pdf
- **[SCBA004]** Texas Instruments, *Implications of Slow or Floating CMOS Inputs*, SCBA004E,
  July 1994, revised July 2021. §1 "Characteristics of Slow or Floating CMOS Inputs" (an unused
  input left floating can oscillate or draw current through both input transistors), §3
  "Recommendations for Designing More-Reliable Systems", §5 "Pull-up or Pull-down Resistors".
  https://www.ti.com/lit/pdf/SCBA004

## Candidates

### 1. `i2c.pullup_too_strong`: error

- **Catches:** an SDA or SCL pull-up so small the bus devices can't pull the line low.
- **Rule:** Rp (the pull-ups on that line in parallel) < (VDD − 0.4 V) / 3 mA. [UM10204 §7.1 Eq. 2,
  Table 10: VOL(max) 0.4 V at IOL 3 mA, Standard- and Fast-mode]
- **Numbers:** 3.3 V → 967 Ω; 5 V → 1.53 kΩ (UM10204's own example at 5.5 V gives 1.7 kΩ).
- **Reads:** the pull-up's value and the rail it goes to, and that rail's voltage.
- **Decision for the human:** where VDD comes from. The netlist has a net name (`V3_3`, `+3V3`,
  `+5V`), not a voltage. Options: parse a small fixed set of names and fail loudly on any other;
  or take it from `Spec.power`; or a `[[rail]]` entry in rules.toml.
- **Bad fixture:** `sensor_good` with R1 changed 4k7 → 680R (on 3.3 V).
- **Boards today:** every board uses 4.7 kΩ: all pass.

### 2. `i2c.pullup_too_weak`: warning

- **Catches:** pull-ups so large the line can't rise within the mode's rise time.
- **Rule:** Rp > tr / (0.8473 × Cb). [UM10204 §7.1 Eq. 1, Table 10: tr max 1000 ns Standard-mode,
  300 ns Fast-mode]
- **Numbers:**

  | Cb | Standard-mode (100 kHz) | Fast-mode (400 kHz) |
  |---|---|---|
  | 50 pF | 23.6 kΩ | 7.08 kΩ |
  | 100 pF | 11.8 kΩ | 3.54 kΩ |
  | 400 pF (max) | 2.95 kΩ | 885 Ω |

- **Decisions for the human:** the bus speed (Standard unless the spec says 400 kHz?) and Cb, which
  the netlist can't give: the board's pins (Ci ≤ 10 pF each, Table 10) plus whatever the header
  connects to. **With Fast-mode and 100 pF, every eval board's 4.7 kΩ warns**; with Standard-mode
  they pass. This is the rule most likely to be "plausibly wrong" and is a warning, not an error.
- **Bad fixture:** `sensor_good` with R1 → 47k.

### 3. `input.floating`: warning

- **Catches:** an IC pin of kind `input` left unconnected (generalizes `address.floating` to every
  input pin).
- **Rule:** an `input` pin (from a trusted pin map, V-12, or a KiCad symbol's pin type) on an
  `unconnected-` net. [SCBA004 §1 for why; §3 and §5 for the fix: tie it through a pull-up or
  pull-down]
- **Reads:** pin kinds. On circuit.json pin kinds come only from the pin map (V-12); on a KiCad
  schematic from the symbol.
- **False positives:** inputs with an internal pull-up the datasheet says may float. Those need a
  per-part exception (rules.toml `need = "open"`, R-10), never a guess in the rule.
- **Bad fixture:** `sensor_good` with an address input's connection deleted is already
  `bad_floating_addr`; plant a second one on a non-address input (e.g. a WP pin) to show the
  general case. Suggest keeping `address.floating` as is and making this a separate rule ID.
- **Boards today:** good fixtures have no floating inputs; on our schematics of the eval boards every
  input (A0–A2, WP, SCL) is tied.

### 4. `i2c.speed_unstated`: warning (optional)

- **Catches:** a board whose pull-ups were never sized for a speed, because the spec doesn't say one.
- **Why:** rules 1–2 depend on the mode. A one-line spec field or rules.toml entry makes the
  assumption visible instead of buried in the rule.
- **This is a process rule, not physics; skip it if rule 2 assumes Standard-mode and says so.**

## Not proposed as general rules (they need the part's datasheet)

These come in through `rules.toml` per part (V-2b drafts, a person confirms), not `reflow/rules/`:

- decoupling value and count per power pin (e.g. 100 nF per VDD, as the part's datasheet says);
- an LDO's output capacitor and its ESR window (AMS1117's datasheet asks for one on the output;
  an ESR outside the window can make the LDO oscillate);
- an LED's current, (V − Vf) / R against If(max), from the LED's datasheet;
- an open-drain output (PCF8574's INT, MCP9808's Alert) that's used but has no pull-up: the KiCad
  symbol types MCP9808's Alert as `output`, not open-drain, so a general rule on pin types would
  miss it. The datasheet is the source.

## Questions for the human

1. Rules 1–2: where does a rail's voltage come from (fixed name table, `Spec.power`, or rules.toml)?
2. Rule 2: the default bus speed and Cb, or should the rule refuse to judge until the spec states them?
3. Rule 3: a new rule ID `input.floating`, or widen `address.floating`?
4. Which of 1–4 to build first. The agent can make the bad fixtures' circuit.json + schematic inputs
   in tests/data/ with the O-04 generator if that helps; `fixtures/` stays yours.

## When accepted

For each rule the human writes: the bad fixture (docs/05 process), a failing test, the rule, the
docs/05 catalog row with its source, and a check that `blinky_good`, `sensor_good`, `avbotz_good`
and the five eval boards stay as listed above.
