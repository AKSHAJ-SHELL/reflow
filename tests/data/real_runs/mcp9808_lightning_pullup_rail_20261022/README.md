# Verifier-clean board with its pull-ups on an unpowered rail, 2026-10-22

`reflow eval --only mcp9808_breakout` with `nvidia/nemotron-3.5-lightning:free`
(max_tokens 32000), run 20261022T192231Z, attempt 2. Attempt 1 mirrored the
MCP9808 pinout, and V-12 reported 7 `pinout.mismatch` errors. Attempt 2 fixed
every pin and the verifier found 0 errors, but the board doesn't work:

| net | pins |
|---|---|
| `Net-(C1-pin1)` | U1.8 (VDD), C1.1, J1.1 |
| `V3_3` | R1.2, R2.2 (nothing else) |
| `SDA` / `SCL` | U1.1 / U1.2, R1.1 / R2.1, J1.3 / J1.4 |

The pull-ups pull SDA and SCL up to `V3_3`, a rail that nothing powers. The chip
is powered from `Net-(C1-pin1)`. `i2c.missing_pullup` accepts any non-ground
net at the resistor's far end, so it passes.

Files: the model's `index.circuit.tsx`; `circuit.json` (its source_* elements,
compiled by tsci 0.0.2768); `parts.json` (the run's ResolvedParts from the
local jlcparts snapshot). Test input for tests/test_i2c_pullup_rail.py.
