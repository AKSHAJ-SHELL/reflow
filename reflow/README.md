# reflow/ (package)

| File | Does | Owner | Status |
|---|---|---|---|
| `netlist.py` | KiCad kicadsexpr netlist → `Netlist`/`Component`/`Pin` | HUMAN | working |
| `circuit_netlist.py` | tscircuit `circuit.json` → `Netlist` (the design verifier's input, V-1) | AGENT (V-10) | working |
| `violation.py` | The `Violation` dataclass every rule returns | HUMAN | working |
| `contracts.py` | Data types for every stage boundary + strict `from_dict` | AGENT (changes via DECISIONS.md) | working |
| `cli.py` | `reflow check` (and later `reflow design`) | AGENT | `check` working |
| `llm.py` | One `complete(system, prompt)` interface over providers | AGENT | stub (M-01) |
| `compile.py` | tscircuit TSX → KiCad via `tsci` | AGENT | stub (K-01) |
| `route.py` | 2-layer routing + our own re-DRC | AGENT | stub (X-01) |
| `export.py` | Gerbers, drill, pos, BOM, report | AGENT | stub (O-01) |
| `rules/` | Verifier rules | HUMAN | 3 files, 5 rule IDs |
| `parts/` | Part catalog + resolver | catalog AGENT, resolver HUMAN | stub |
| `harness/` | The design loop | HUMAN core | not built |

**Contract:** data between stages is always a `contracts.py` type. **Never:** import GPL/AGPL code; read raw KiCad files into an LLM prompt.
