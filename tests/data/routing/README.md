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
