# tests/

| File | What | Needs KiCad |
|---|---|---|
| `conftest.py` | Finds every fixture, exports a fresh netlist per test | yes |
| `test_netlist.py` | Invariants + hand-checked nets + expected violations per fixture | yes |
| `test_cli.py` | `reflow check` exit codes and output | yes (skips if missing) |
| `test_catalog.py` | `parse_value`, `CatalogPart` defaults, and that the jlcsearch client and cache are gone | no |
| `test_contracts.py` | Frozen schemas, strict example parsing, stub honesty | no |
| `test_circuit_netlist.py` | `circuit.json` → `Netlist` on recorded boards (`data/circuit_json/`), the rules on that netlist, and malformed input | no |
| `test_pcb_nets.py` | `.kicad_pcb` pad nets: tscircuit export vs its `circuit.json`, syntax and error cases | no |
| `test_pinmap.py` | Pin maps from ST pin data and KiCad symbols (`data/pinmaps/`, licences beside them): MCP9808 vs its datasheet, STM32F103C8 across sources, disagreement reporting | installed-library case only (skips if missing) |
| `test_verifier.py` | The design verifier on recorded `circuit.json` boards: report shape, required `bind`, refuses `.kicad_sch` | no |
| `test_design_wiring.py` | `reflow design` from config: scripted model, real tsci and verifier, fake catalog; config and catalog errors | tsci for the end-to-end cases (skips if missing) |
| `test_parts_snapshot.py` | `reflow parts update` on a six-part split-archive fixture (`data/snapshot/`) over file:// URLs: install, CRC and format checks, old database kept on failure | no |
| `test_local_catalog.py` | Local-snapshot queries on 27 real rows (`data/parts_db/`): values, tolerance, voltage, headers, MPN prefix, category mapping, the MCP9808 plan through the resolver | no |
| `test_evals.py` | Structure of every `evals/` board: strict spec and plan, named parts verbatim in the request, D-6a headers, expected.toml agrees with the plan | no |
| `test_eval_runner.py` | The eval runner with a scripted model, real tsci and verifier, and the parts fixture: pass rates, foreign part numbers, expectation misses, errors, go/no-go, results file, `reflow eval` | tsci (skips if missing); about 2 minutes |
| `test_project_rules.py` | `rules.toml` parsing and `reflow rules check`: required why/source, field errors, unknown pins, uncovered power/reset/boot pins | no |
| `test_rules_prompt.py` | Project rules rendered for the codegen/fix prompts (no why/source), `reflow design` resolving and checking `rules_file`, `[[part]]` pin maps in `reflow rules check`; one test is red until `docs/proposals/V-22-loop-HUMAN.patch` is applied | no |
| `test_pinbind.py` | V-12 pin binding on the first real board (`data/real_runs/`): its wrong MCP9808 pinout is reported pin by pin, the corrected board binds clean, bound power pins let decoupling run, unidentified / unmapped chips are errors | no |
| `test_integration.py` | Real tsci + kicad-cli + rules, and the design loop with a scripted model (inputs in `data/integration/`) | yes, and tsci (skips if missing) |

Run: `pytest -q`. **Never weaken a test** (docs/agents/04-testing-rules.md).
