# R-11: verifier rules from published sources ("book knowledge")

Status: PROPOSED 2026-10-29 by the agent; Part B (the basic design-rules catalog) added 2026-10-31; Part C (rules from the student's own books, after launch) added 2026-10-31. Rule code is HUMAN (`reflow/rules/`, docs/05). This file only
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

## Part B: a basic design-rules catalog (added 2026-10-31)

The human asked (2026-10-31) for a basic set of design rules beyond ERC, true for almost every
board, for students and hobbyists to read and learn from. Candidates 1–4 above are the start; this
part adds the rest and sorts them all into tiers. Each one cites a free document that the agent read.

### Tiers

| Tier | Meaning | Today |
|---|---|---|
| ERC | Pin types and connections, KiCad's own check on our schematic | done (O-04, 0 errors and 0 warnings to export) |
| **error** | The board doesn't work, or works only by luck | `Violation.severity = "error"` |
| **warning** | Works, but outside what the source recommends | `"warning"` |
| **note** | Advice a beginner should see; leaving it out is a fair choice | **doesn't exist**, see Q5 |
| per-part | One part's datasheet (decoupling value, LDO output cap, LED current) | rules.toml (V-2b), not here |

### More sources (read 2026-10-31 from the documents themselves)

- **[SZZA009]** Texas Instruments, *PCB Design Guidelines for Reduced EMI*, SZZA009, November 1999.
  - §2.1.4 "Signal Return Grounds": on a two-layer board, gridding the ground is the closest thing
    to a ground plane, and "the most important thing to do (after floor planning)".
  - §2.2.3 "Gridding to Create Planes".
  - §2.2.4 "Bypassing and Ferrite Beads": make the bypass loop as small as possible in area and
    length; a 3:1 length-to-width rule for its traces.
  - §2.4.1: no unrelated component within 1 inch of a crystal.
  - https://www.ti.com/lit/pdf/szza009
- **[SLVA680]** Texas Instruments, *ESD Protection Layout Guide*, SLVA680A, February 2015, revised
  April 2022.
  - §1: ESD usually comes in through a user interface such as a cable connector.
  - §2.1: place the TVS "as near to the ESD Source as the PCB design rules allow", with no stub
    between it and the protected line.
  - https://www.ti.com/lit/pdf/slva680
- **[IPC-2221 via Digi-Key]** IPC-2221 itself is paid, so this is the free reproduction.
  - Digi-Key's PCB trace width calculator gives the IPC-2221 curve fit: I = k·ΔT^0.44·A^0.725,
    with A in mil² and k = 0.048 for external layers, 0.024 for internal.
  - It suggests 1 oz copper and a 10 °C rise.
  - https://www.digikey.com/en/resources/conversion-calculators/conversion-calculator-pcb-trace-width

Analog Devices' MT-101 (decoupling) and MT-031 (grounding) would be good sources too, but
analog.com refused the downloads on 2026-10-31, so nothing here cites them.

### The catalog

S = schematic (netlist from circuit.json), P = PCB (.kicad_pcb). "Boards" means the five eval
boards of run 20261028T161716Z.

| # | Rule ID | Tier | Level | Rule | Source | Boards |
|---|---|---|---|---|---|---|
| 1 | `i2c.pullup_too_strong` | error | S | Rp < (VDD − 0.4 V)/3 mA | UM10204 §7.1 Eq. 2 | all pass (4.7 kΩ) |
| 2 | `i2c.pullup_too_weak` | warning | S | Rp > tr/(0.8473·Cb) | UM10204 §7.1 Eq. 1 | depends on Q2 |
| 3 | `i2c.pullup_rail` | error | S | pull-up to a rail the bus devices aren't powered from | UM10204 §7.1 (Rp to VDD) | **drafted by the agent under O-1d (10-31), awaiting the human's review**; test `test_i2c_pullup_rail.py` |
| 4 | `input.floating` | warning | S | input pin unconnected | SCBA004 §1, §3, §5 | none floating |
| 5 | `led.no_limiter` | error | S | LED with no series resistor or current source | the LED's If(max); Ohm's law | already R-01 |
| 6 | `decoupling.far` | warning | P | bypass cap's path to its pin longer than *N* mm | SZZA009 §2.2.4 | not measured; threshold *N* is Q6 |
| 7 | `ground.no_pour` | warning on 2-layer | P | no ground zone or grid on a 2-layer board | SZZA009 §2.1.4, §2.2.3 | **all 5 fire**: no board has a zone (0 `(zone` in every .kicad_pcb) |
| 8 | `esd.unprotected_connector` | note | S + P | a connector's signal pin goes to an IC with no TVS between | SLVA680 §1, §2.1 | **all fire** (every board has a bare header) |
| 9 | `esd.tvs_far` | warning | P | a TVS that is present but far from its connector, or on a stub | SLVA680 §2.1 | none (no TVS) |
| 10 | `trace.too_narrow` | warning | P | trace narrower than IPC-2221 needs for its current at a 10 °C rise | IPC-2221 via Digi-Key | needs each net's current, Q7 |
| 11 | `crystal.crowded` | warning | P | an unrelated part within 25.4 mm of a crystal | SZZA009 §2.4.1 | no crystals |

Notes:

- **#7** fires on every board today because tscircuit's autorouter doesn't pour ground. If it
  is a warning, every board warns until codegen or the router adds a pour. That's honest, but it is
  noise until it's fixed, so the tier is Q8.
- **#8** is a note because a header on a bench board without ESD protection is a fair choice. It
  is exactly what a hobbyist doesn't know to think about.
- **#10** needs a current per net. The netlist has none. Options: `Spec.power`, rules.toml, or
  only power nets with an assumed current, stated in the message.
- **#11**: SZZA009 gives 1 inch with no derivation. It's a rule of thumb, which is why it is a
  warning.

### Considered and left out

- **SZZA009 §2.2.5:** a series resistor on every I/O pin, and 1000 pF on inputs. It is aimed at EMI
  in production microcontroller boards, the note itself says it isn't widely accepted, and it
  would fire everywhere.
- **A bulk capacitor at the power input:** a common rule, but the agent found no free source to
  cite yet.
- **Polarity marks on the silkscreen for LEDs, diodes and polarized caps:** a real assembly
  problem. The source would be the fab's assembly guide, which the agent hasn't read yet.

## Part C: rules from the student's own books (added 2026-10-31, after launch)

The human asked that students can bring their own textbooks (Horowitz & Hill, Ott, Montrose, a
course reader) and get rules from them, with no copyright problems. Parts A and B cite only free
vendor documents. Books are copyrighted, so this part is mostly about what reflow never stores,
sends or publishes.

The agent isn't a lawyer, and this is a design that keeps the copyright risk low, not legal advice.
The basis it relies on: copyright covers a book's wording, not the facts or design rules in it
(US: 17 U.S.C. §102(b)). A rule restated in our own words with a page reference is a citation; the
book's own sentences, figures and tables are not ours to copy.

### Copyright rules (the non-negotiables for this part)

1. **reflow never gets a book for the student.** It reads only a local file the student passes in.
   No downloading, no search for PDFs, no list of where to find them. A file it can't read (DRM,
   scanned images with no text layer) is refused with that reason; reflow never removes DRM or
   OCRs around it.
2. **The book never enters the repo or a shared file.** The PDF and the text extracted from it stay
   in a gitignored local folder (`.reflow/books/`, proposed). `reflow init` adds that folder to
   `.gitignore`. A test checks that `reflow init`'s `.gitignore` has it.
3. **What gets saved is ours.** A rule from a book keeps:
   - `source`: title, edition, author, section and page (a citation);
   - `why`: the student's or the model's own words, never pasted text.
   The book's sentence is used only to check the rule (below) and is **not** written to
   `rules.toml`. That differs from V-2b, where a datasheet rule keeps its `quote`; see Q10.
4. **Learn mode follows the same rule.** A concept card or vault note made from a book holds our
   own summary and the page reference, never the book's text, figures or tables.
5. **Only the pages needed go to the model.** The student names the chapter or page range. reflow
   sends those pages' text to the configured model provider to draft rules and nothing more, and
   says so before it does (see Q11).
6. **reflow ships no book-derived rules.** Parts A and B stay cited only to free documents.
   Rules from a book live in the student's own project.

### How it would work

1. `reflow rules from-book BOOK.pdf --pages 112-130 --cite "Ott, EMC Engineering, 2009"`.
   - It extracts the text of those pages locally.
   - It says which pages will go to the model, and asks before sending.
2. The model drafts candidate rules. For each one it must return a page number and the exact
   sentence the rule rests on.
3. **reflow checks every quote against the extracted text of that page.** If the sentence isn't
   on that page, the candidate is dropped and the run lists it with the reason. This is the
   loud-failure check: no page and sentence means no rule.
4. Each surviving candidate is sorted:
   - **It matches a built-in rule** (Part A or B, e.g. catalog #6, decoupling distance): reflow
     records the book as a second source for that rule in the student's project and shows the
     page when the rule fires. No new check.
   - **It's a per-pin requirement** that fits `rules.toml`'s `on`/`need`/`to`/`value` (a value
     range, a pull-up, a tie, a cap to ground): it becomes a `[[rule]]` with `drafted_by = "model"`
     and no `confirmed_by`, as V-2b already requires.
   - **Anything else** becomes a learn-mode note. It never fails a board.
5. The student goes through each one with `reflow rules confirm` (V-2b), with the page open,
   before it counts as confirmed. The book sentence is shown on screen for that check, read from
   the local copy, and then forgotten.

The honest limit: most textbook advice is general ("keep the loop small"), not per-pin. So most
of what a book gives is a second citation for a built-in rule, or a note. Few book rules become
new checks.

### What it touches

- A new CLI command (AGENT) and its prompt in `prompts/` (AGENT drafts, HUMAN approves, as H-08).
- The quote check (AGENT, with a failing test first: a quote not on its page is dropped).
- Sorting a candidate into "matches a built-in rule" is a judgment about rules, so the matching
  table is HUMAN (as docs/05).
- Possibly a contract change: a second `source` on a built-in rule's violation, or a
  `ProjectRule` field marking a book source (Q12).
- Learn mode: book notes as concept cards. Learn-mode selection (L-01) is HUMAN.

### Considered and left out

- **A shared library of rules from popular books.** It would be the most useful thing, and the
  riskiest: one file of many rules from one book, even in our words, starts to look like a
  summary of the book. Left out of v1; ask a lawyer before ever doing it.
- **Uploading the book to a reflow server.** reflow has no server for this, and the book should
  stay on the student's machine.

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

1. Candidates 1–2 (catalog #1–2): where does a rail's voltage come from (fixed name table, `Spec.power`, or rules.toml)?
2. Candidate 2 (catalog #2): the default bus speed and Cb, or should the rule refuse to judge until the spec states them?
3. Candidate 3 (catalog #4): a new rule ID `input.floating`, or widen `address.floating`?
4. Which to build first. The agent can make the bad fixtures' circuit.json + schematic inputs
   in tests/data/ with the O-04 generator if that helps; `fixtures/` stays yours.
5. A `note` severity: add it to `Violation` (a contract change; a note never fails a board or
   counts as a warning)? Or send notes only to learn mode as concept cards?
6. Catalog #6: the distance limit. codegen already asks for `maxDecouplingTraceLength="3mm"`; use the
   same 3 mm?
7. Catalog #10: where each net's current comes from.
8. Catalog #7: a warning now, even though every board fires until tscircuit pours ground, or a note
   until then?
9. Who writes catalog #6–11: the human (as now), or an O-1-style exception where the agent writes them
   and the human reviews every line?
10. Part C: for a book rule, keep no quote in `rules.toml` (the agent's recommendation), or keep a
    short one as V-2b does for datasheets? If no quote, `drafted_by = "model"` without `quote`
    must be allowed when the source is a book, which changes V-23's planned check.
11. Part C: sending book pages to the model provider. Ask every time (recommended), allow a
    setting in `reflow.toml`, or extract rules only from pages the student pastes in themselves?
12. Part C: how a book is recorded as a second source for a built-in rule. A field on the
    student's project (no contract change), or a second `source` on `Violation` (contract)?
13. Part C: when. The agent's recommendation is after v1, once Parts A and B are built.

## When accepted

For each rule the human writes: the bad fixture (docs/05 process), a failing test, the rule, the
docs/05 catalog row with its source, and a check that `blinky_good`, `sensor_good`
and the five eval boards stay as listed above.
