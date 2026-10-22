# evals/: go/no-go boards (E-02)

Each folder is one board the harness must design. The go/no-go (TASKS.md):
`reflow design` produces a verifier-clean compiled board within 3 attempts on
at least 3 of 5, with zero part numbers outside the resolver.

**All five are drafts** (DECISIONS O-1): the agent wrote them, and nothing
here counts until a person has checked every line of `expected.toml` against
the datasheets, then set `status = "checked"` and filled `checked_by`. Lines
marked `TO CHECK` haven't been verified by anyone; MCP9808's cite pages that
were read (DS20005095B).

| Folder | Named part | Tests |
|---|---|---|
| `mcp9808_breakout` | MCP9808 (MSOP-8) | the go/no-go board itself |
| `at24c02_eeprom` | AT24C02 (SOP-8) | exact part number among many listings; WP strap |
| `ams1117_regulator` | AMS1117-3.3 (SOT-223) | a regulator; input and output capacitors |
| `pcf8574_expander` | PCF8574T/3,518 | the exact orderable part (the family "PCF8574" also matches PCF8574A, a different chip) |
| `led_indicator` | KT-0603R LED | a named non-IC part; series resistor |

## Files

- `request.txt`: the user's sentence.
- `spec.json`: a confirmed `Spec` (strict contract). `named_parts` are strings that appear verbatim in the request.
- `plan.json`: a `Plan` (strict contract), hand-written, because request → spec → plan isn't automatic yet (H-06). Headers use D-6a's encoding (`value` "1x4", `package` "2.54mm"). ICs state their package, so the resolver doesn't have to ask.
- `expected.toml`: what a correct board must contain.
  - `status`, `checked_by`: draft until a person checks it.
  - `outcome = "board"`: passing means a verifier-clean compiled board.
  - `nets`: net names that must exist.
  - `parts`: how many parts of each category the board has.
  - `violations`: the rule ids the final board may still have (`[]` = clean).
  - `[[net]]`: `name`, and `includes`, the pins that must be on it. `ic.SDA` is the pin with that datasheet name on the one IC (`regulator.`, `led.` likewise); a bare `resistor`, `capacitor` or `connector` means a pin of any part of that kind. `source` says where the expectation comes from.
  - `[[open]]`: pins that must stay unconnected.

`tests/test_evals.py` checks the structure of every folder. It can't check that an expectation is electrically right; that's the person's check.

## Running them (E-01, not built yet)

Needs `REFLOW_API_KEY`, a `base_url` in `reflow.toml`, and `reflow parts update` run once. Pin binding (V-12) isn't built, so the decoupling rules don't run yet; results should say so.
