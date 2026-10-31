# Empty board that passed, 2026-10-22

`reflow eval --only mcp9808_breakout` with the OpenRouter free model
`nvidia/nemotron-3.5-lightning:free` (max_tokens 32000), run 20261022T190601Z.
The model wrote `supplierPartNumbers={["C…"]}`, a bare list. tscircuit wants
`supplierPartNumbers={{ jlcpcb: ["C…"] }}`, so it rejected all 5 components.
tsci still exited 0, writing 5 `source_failed_to_create_component_error` and
13 `source_trace_not_connected_error` into circuit.json, with no
source_component. `compile_board` reported ok, and the verifier saw 0
components, found 0 violations and passed the run.

Files: the model's `index.circuit.tsx`; `circuit.json` (its source_* elements,
compiled by tsci 0.0.2768); `parts.json` (the run's ResolvedParts from the
local jlcparts snapshot). Test input for tests/test_compile.py and
tests/test_verifier.py.
