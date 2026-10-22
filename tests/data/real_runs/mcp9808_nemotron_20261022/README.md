# First real board, 2026-10-22

`reflow eval --only mcp9808_breakout` with the OpenRouter free model
`nvidia/nemotron-3.5-super-vl:free` (max_tokens 12000). It passed the verifier
on attempt 1, before pin binding existed, but its MCP9808 pinLabels are wrong:

| MSOP-8 pin | MCP9808 DS20005095B Table 3-1 | model's label | wired to |
|---|---|---|---|
| 3 | Alert | NC | nothing |
| 7 | A0 | VDD | V3_3 |
| 8 | VDD | A0 | GND |

Files: the model's `index.circuit.tsx`; `circuit.json` (its source_* elements,
compiled by tsci 0.0.2768); `parts.json` (the run's ResolvedParts from the
local jlcparts snapshot). Test input for V-12 (tests/test_pinbind.py).

`corrected.*` is the same board with the datasheet pinout (pin3 ALERT, pin7 A0,
pin8 VDD); `corrected_no_cap.*` also drops C1. Both compiled with tsci 0.0.2768.
