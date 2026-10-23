# A real run with a failed first draft, for learn mode (L-01, L-10)

Run folder from `reflow eval` 20261022T193720Z, board mcp9808_breakout, model
nvidia/nemotron-3.5-lightning:free, reduced to what learn mode reads:
spec/plan/parts/run.json, plus each attempt's verify.json and full circuit.json
(tsci 0.0.2768; the viewers need the schematic_* and pcb_* elements).

- Attempt 1 failed with 10 errors: 7 `pinout.mismatch` on U1 (the pinout is
  mirrored), 2 `decoupling.missing` on U1 (one on the real GND pin, a
  consequence of the wrong labels), and 1 `i2c.missing_pullup` with no refs.
- Attempt 2 passed verify. (It's the false pass noted in PROGRESS.md: SDA/SCL
  are unconnected, which no rule catches yet.)

`rules.toml` is a copy of evals/mcp9808_breakout/rules.toml, so the folder works wherever it's copied (spec.json says `"rules_file": "rules.toml"`).
