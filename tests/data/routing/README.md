# Routing inputs (X-01, X-04)

`mcp9808_fixed.tsx`: the MCP9808 eval board as fixed in learn mode (the real AI draft of eval run
20261022T193720Z, attempt 1, relabelled to the datasheet pinout and wired; it verifies clean).

tscircuit's autorouter runs inside `tsci export`. It gives a decoupling cap's traces a 1 mm
maximum length (`DEFAULT_MAX_DECOUPLING_TRACE_LENGTH_MM` in @tscircuit/core), and skips routing
the whole board when automatic placement leaves the cap farther than that from the pin. As
written, this board doesn't route. With `maxDecouplingTraceLength="3mm"` on C1, every connection
routes and C1's trace to VDD is 2.89 mm. With 2 mm it still doesn't route (tsci 0.0.2768).

2026-10-27: the limit covers both of a decoupling cap's traces, including its ground side to the
nearest GND pad. With 3 mm, placement missed by about 0.5 mm on 3 of 5 eval boards
(run 20261028T004800Z: 3.46–3.56 mm), and routing was skipped. The codegen prompt now asks for 5 mm.

Hole-clearance inputs (2026-10-27), exported .kicad_pcb files from real eval runs (Sonnet 5.5):
- `at24c02_via_0198mm.kicad_pcb` (run 20261028T010434Z): a via 0.198 mm from the SCL track. Under
  JLCPCB's "Via hole to Track" 0.2 mm this is a real violation.
- `ams1117_via_0216mm.kicad_pcb` (same run, attempt 2): a via 0.216 mm from U1 pad 1. It passes
  JLCPCB's 0.2 mm via rule; KiCad's 0.25 mm default flagged it.
- `mcp9808_routed_headers.kicad_pcb` (run 20261028T004800Z): routed, with J1's plated through-holes
  next to tracks (closest 1.25 mm), used to show the PTH rule applies to PTH pads.

Board-size input (2026-10-27): `pcf8574_40x30.tsx` is the PCF8574 eval draft from run
20261028T010434Z (Sonnet 5.5, attempt 1), unchanged. The model drew a 40 x 30 mm board and set
pcbX/pcbY by hand; J1 sits 0.56 mm and J2 4.64 mm past the edge, and tscircuit skipped routing
for the placement errors. With `<board>` (no width or height) and no pcbX/pcbY, tscircuit places
the parts and sizes the board around them (23.28 x 21.875 mm, tsci 0.0.2768), every part sits
inside the edge, and all 12 nets route. Our DRC still finds 2 router vias under JLCPCB's 0.2 mm
via-to-track rule on that board. Keeping the model's placement with no size also fits, but its
decoupling traces come out 8.35 and 8.98 mm, over the 5 mm limit. So the codegen prompt asks for
no size (unless the spec gives one) and no hand placement.
