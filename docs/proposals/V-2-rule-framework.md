# V-2 · Project rules: students write them from datasheets, reflow enforces them

Status: **ACCEPTED** 2026-10-20 by the human (proposed by agent, Claude). Builds on V-1 (verify `circuit.json`; pin facts never come from the AI's labels). Its contract change was approved and applied on 2026-10-20. Binding text: `DECISIONS.md`.

## The idea

1. **reflow ships general rules** (decoupling, pull-ups, floating pins, LED resistors, …) taken from standard schematic-review checklists. They run on every board.
2. **A project adds its own rules** in one plain file, `rules.toml`, next to the design. A student writes it while reading the datasheets for their parts. This covers the niche things the general rules can't know.
3. **reflow uses that file twice:**
   - **Design:** the rules go into the codegen prompt as constraints, so the AI tries to follow them.
   - **Verify:** every rule is checked deterministically against the compiled board. The AI's attempt is never trusted; a broken rule fails the board and goes back as a fix hint.
4. **Help is outside reflow.** A separate Claude skill (the *datasheet tutor*, now `skills/datasheet-tutor/SKILL.md`) explains datasheet sections. When the student asks, it writes `rules.toml` in this format. reflow doesn't call it and doesn't know it exists. It only reads the file.

## The file

One `[[rule]]` per thing the datasheet asks for. Six fields, four of them required.

```toml
[[rule]]
on     = "U1.VDD"                  # required: part.pin, by datasheet pin name or number
need   = "cap"                     # required: cap | pullup | pulldown | tie | open | connected
to     = "GND"                     # net the other side goes to (cap, pullup, pulldown, tie)
value  = "100nF..1uF"              # optional: one value or a range
source = "MCP9808 datasheet, 6.1, p.35"   # required: where you read it
why    = "Keeps VDD steady when the sensor draws current; ceramic, close to the pin."  # required: your own words
```

| `need` | Means | Checked as |
|---|---|---|
| `cap` | a capacitor from this pin to `to` | a C whose two pins are on this pin's net and `to`, value in range |
| `pullup` / `pulldown` | a resistor from this pin to a rail / to ground (`to` names it) | an R between this pin's net and `to`, value in range |
| `tie` | wire this pin directly to `to` | this pin's net is `to` |
| `open` | leave this pin unconnected | nothing else on its net |
| `connected` | this pin must not float | its net has at least one other pin |

That's the whole vocabulary for v1. A need it can't express is a request for a new `need` (a maintainer change with fixtures), not a free-text rule.

**Why `why` is required:** it's what learn mode shows the student later, it's never sent to the design model, and having to write it is the point where they understood the page.

## What reflow does with it

| Step | What happens |
|---|---|
| `reflow rules check rules.toml` | Strict parse. Every `on` names a pin that exists on that part's trusted pin map (V-1). Every rule has `source` and `why`. A **warning** (not an error) lists power, ground, reset and boot pins no rule mentions: "you haven't said anything about BOOT0". |
| Codegen and fix prompts | Rules rendered as one line each: `U1.VDD: cap to GND, 100nF..1uF`. No `why`, no `source`. |
| Verify | Each rule becomes a violation `project.<need>` when it fails, e.g. *"U1 pin 8 (VDD) has no 100nF–1µF capacitor to GND."* The fix hint is generated from the rule. `why` and `source` go to the report and learn mode only. |
| Learn mode (later) | Questions come from the student's own rules and the real violations on their board. |

## Where pin facts come from (amends V-1 b)

V-1 required a signed card for every IC. That's too heavy. Instead, pin numbers, names and types come from the first trusted source that has the part:
1. the vendor's machine-readable pin data (e.g. ST's STM32_open_pin_data, BSD-3);
2. the KiCad symbol library;
3. a hand-written card, as an override when 1–2 are wrong or missing.

No trusted pin map → verify error. The AI's `pinLabels` are still only compared against the map, never used.

## Who owns what

| Piece | Owner |
|---|---|
| General rules, and the six `need` checks | HUMAN (`reflow/rules/`, with good/bad fixtures) |
| `rules.toml` parser, `reflow rules check`, rendering into prompts | AGENT |
| The prompt text that carries the rules | AGENT drafts → HUMAN approves (H-08) |
| A project's `rules.toml` | the student (with or without the tutor) |
| The datasheet tutor skill | separate from reflow; lives in its own repo |

## Contract change (drafted after acceptance)

`ProjectRule{on, need, to, value, source, why}` and `RULE_NEEDS = {cap, pullup, pulldown, tie, open, connected}`. `Spec` gains `rules_file: str` (path, `""` for none) so the run folder records which rules the board was held to.

## Order of work

1. Accept V-1 and V-2.
2. HUMAN: the six `need` checks as rules, with fixtures. They're short; `cap` is `decoupling.missing` with a value range.
3. AGENT: parser + `reflow rules check`, the pin-map importer (vendor data, KiCad), and prompt rendering.
4. Try it on one real club board, with a student writing `rules.toml` from the datasheets.
5. Then learn mode.
