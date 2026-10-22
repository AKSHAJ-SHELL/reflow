# reflow/ (package)

| File | Does | Owner | Status |
|---|---|---|---|
| `netlist.py` | KiCad kicadsexpr netlist → `Netlist`/`Component`/`Pin` | HUMAN | working |
| `circuit_netlist.py` | tscircuit `circuit.json` → `Netlist` (the design verifier's input, V-1) | AGENT (V-10) | working |
| `pcb_nets.py` | `.kicad_pcb` → `{(ref, pad): net}` (what the gerbers are made from; V-1 d) | AGENT (V-14) | working |
| `verifier.py` | The design verifier: `circuit.json` → `VerifyReport`, with a required pin-binding step (V-12); `make_verifier` gives `run_design` its `verifier` | AGENT (V-16) | working; `.kicad_pcb` comparison waits on V-13 |
| `evals.py` | E-01 eval runner: runs `evals/` boards through the design loop and reports first-pass / after-retry pass rates, part numbers outside the resolver, expectation misses, tokens and the go/no-go (`reflow eval`) | AGENT (E-01) | working |
| `project_rules.py` | A project's `rules.toml` (V-2): strict parse to `ProjectRules`, field checks, pins against V-11 pin maps, warnings for uncovered power/ground/reset/boot pins (`reflow rules check`) | AGENT (V-21) | working |
| `pinbind.py` | V-12 pin binding: identify each IC by a resolved part number, relabel and type its pins from a trusted pin map by physical number, report `pinout.mismatch` / `.unidentified` / `.no_pin_map` | AGENT under O-1b (human review pending) | working |
| `violation.py` | The `Violation` dataclass every rule returns | HUMAN | working |
| `contracts.py` | Data types for every stage boundary + strict `from_dict` | AGENT (changes via DECISIONS.md) | working |
| `cli.py` | `reflow check`, and `reflow design` wired to config (model), `compile_board`, catalog + resolver, and the design verifier | AGENT | working; pin binding waits on V-12 |
| `llm.py` | One `complete(system, prompt)` interface over providers (anthropic, openai, openai-compatible); reply budget from config `max_tokens`; a cut-off reply raises | AGENT (M-01, M-03) | working |
| `compile.py` | tscircuit TSX → KiCad via `tsci` | AGENT | stub (K-01) |
| `route.py` | 2-layer routing + our own re-DRC | AGENT | stub (X-01) |
| `export.py` | Gerbers, drill, pos, BOM, report | AGENT | stub (O-01) |
| `rules/` | Verifier rules | HUMAN | 3 files, 5 rule IDs |
| `parts/` | Part catalog + resolver | catalog AGENT, resolver HUMAN | stub |
| `harness/` | The design loop | HUMAN core | not built |

**Contract:** data between stages is always a `contracts.py` type. **Never:** import GPL/AGPL code; read raw KiCad files into an LLM prompt.
