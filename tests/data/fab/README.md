# Fab export inputs (O-01)

`pcf8574_run/`: a real run folder, the PCF8574 eval board from run 20261028T161716Z (Sonnet 5.5,
`--repeat 3`), run 1. It passed verify on attempt 1 with no violations, and every part number in
its circuit.json came from the resolver (`parts.json`) or the spec's named parts. tscircuit routed
all 12 nets, and our KiCad DRC under JLCPCB's 2-layer rules finds 0 errors and 0 unconnected
items (25 warnings, silkscreen and footprint-library ones).

Kept from the run: `run.json`, `spec.json`, `parts.json`, attempt 01's `verify.json` and
`index.circuit.tsx`, and from its `build/` the `circuit.json`, `board.kicad_pcb` and the
`board.kicad_pro` / `board.kicad_dru` that `compile_board` wrote. Left out: the
`.kicad_sch` (not used by the export) and the prompt and response. Paths in `run.json` and the
spec's `rules_file` were made relative to the repo; nothing else was changed.

kicad-cli writes `board.kicad_prl` next to any board it opens, so tests export from a copy.
