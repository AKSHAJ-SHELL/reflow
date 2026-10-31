# X-04a: over-length traces in `RouteResult`, shown in learn mode

Status: ACCEPTED 2026-10-28 by the human (Q1 typed `too_long`, Q2 drop `trace_length.json`, Q3 one-line summary). Proposed the same day by the agent.

## Problem

tscircuit routes a board even when a trace is over its length limit (a decoupling cap's
`maxDecouplingTraceLength`). It records a `pcb_trace_too_long_error` in circuit.json, and KiCad's
DRC doesn't check length. Run 20261028T161716Z (Sonnet 5.5, all 5 evals × 3) had two such boards:

| Board | Net | Trace | Length | Limit |
|---|---|---|---|---|
| mcp9808, run 3 | V3_3 | C1.pin1 to J1.pin1 | 6.05 mm | 5 mm |
| pcf8574, run 2 | GND | C1.pin2 to U1.A0 | 14.01 mm | 5 mm |

Since ef2e5ef, `route_report` makes these boards "partial" and lists each trace in
`<workdir>/trace_length.json`. But `RouteResult` is frozen, so:

- the result says "partial" without saying why: no net is unrouted and DRC has 0 errors;
- the learn UI's routing line (`web/src/RouteLine.tsx`) gets only the `RouteResult`, so it shows
  "partly routed · 12/12 nets in copper · 0 errors" for those boards. That reads as a contradiction;
- anything later that reads a `RouteResult` (fab export O-01, eval results) would have to know to
  open a side file.

## Proposal

### (A) Contract

A new flat contract, and one new field with a default, so every existing `route_result.json`
still parses:

```python
@dataclass
class TraceLength:               # a trace over its length limit, from the router (X-04a)
    net: str                     # "GND"
    ports: list[str]             # the two ports it joins, sorted: ["C1.pin2", "U1.A0"]
    length_mm: float             # routed length, rounded to 0.01
    limit_mm: float              # the limit the board asked for, rounded to 0.01

@dataclass
class RouteResult:
    ...                          # unchanged fields
    too_long: list[TraceLength] = field(default_factory=list)
```

- `tests/test_contracts.py`: `TraceLength` and the new field are added to the frozen field
  lists; `docs/examples/route_result.json` gains a `too_long` entry.
- No `Optional` and no dict fields, so `from_dict` needs no changes (it already parses a list of
  dataclasses).
- The status rule is unchanged from ef2e5ef: any entry in `too_long` keeps the board from "routed".

### (B) `route_report`

Fills `too_long` from the same `pcb_trace_too_long_error` elements it reads today.
`trace_length.json` is then removed, so there's one source for the list (see Q2).

### (C) Learn UI

- `RouteLine` adds, when `too_long` isn't empty:
  "· over length: GND C1.pin2–U1.A0 14.01 mm (limit 5 mm)". It shows at most 3, then "…", the same
  way unrouted nets are shown.
- The same line still says "KiCad DRC (the board's default rules)". That has been wrong since
  10-23, because exported boards carry JLCPCB's rules. It becomes "KiCad DRC (JLCPCB 2-layer
  rules)".
- `api.ts` gains the `TraceLength` type. The server needs no change, because `/api/route` already
  returns `to_dict(result)`.
- Nothing is taught from it yet: learn mode's interactions (L-01) don't change.

## Not proposed

- **Making it a verify error, or feeding it to the fix loop:** that would be the harness core and
  feedback conversion, which are HUMAN. Routing stays a report.
- **Changing the length limit:** the prompt keeps asking for 5 mm.

## Questions for the human

1. **Field name:** `too_long` (proposed), or a more general `layout_errors: list[str]` that could
   hold other tscircuit `pcb_*` errors later? The typed list keeps the length and limit as numbers,
   and a generic string list would lose them.
2. **`trace_length.json`:** drop it once the field exists (proposed), or keep writing it too?
3. **UI:** is the one-line summary enough, or should an over-length trace also be highlighted on
   the PCB view?

## Tests (when accepted)

- Contract round trip, with the example file holding one `too_long` entry; an old
  `route_result.json` without the field still parses.
- `tests/test_route.py`: the two real boards in `tests/data/routing/` (`mcp9808_trace_6mm/`,
  `pcf8574_trace_14mm/`) give exactly their trace in `result.too_long` and status "partial". The
  board with the error removed gives `too_long == []` and "routed". These replace the checks of
  `trace_length.json`; the assertions stay as strict.
- `tests/test_learn_server.py`: `/api/route` on a run with an over-length trace returns it.
- UI build and a screenshot of the routing line on the PCF8574 board.
