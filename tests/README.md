# tests/

| File | What | Needs KiCad |
|---|---|---|
| `conftest.py` | Finds every fixture, exports a fresh netlist per test | yes |
| `test_netlist.py` | Invariants + hand-checked nets + expected violations per fixture | yes |
| `test_cli.py` | `reflow check` exit codes and output | yes (skips if missing) |
| `test_contracts.py` | Frozen schemas, strict example parsing, stub honesty | no |
| `test_circuit_netlist.py` | `circuit.json` → `Netlist` on recorded boards (`data/circuit_json/`), the rules on that netlist, and malformed input | no |
| `test_pcb_nets.py` | `.kicad_pcb` pad nets: tscircuit export vs its `circuit.json`, the club KiCad board vs its schematic, syntax and error cases | club case only (skips if missing) |
| `test_pinmap.py` | Pin maps from ST pin data and KiCad symbols (`data/pinmaps/`, licences beside them): MCP9808 vs its datasheet, STM32F103C8 across sources, disagreement reporting | installed-library case only (skips if missing) |
| `test_verifier.py` | The design verifier on recorded `circuit.json` boards: report shape, required `bind`, refuses `.kicad_sch` | no |
| `test_integration.py` | Real tsci + kicad-cli + rules, and the design loop with a scripted model (inputs in `data/integration/`) | yes, and tsci (skips if missing) |
| `test_parts_integration.py` | Plan → catalog → resolver on recorded jlcsearch responses (`data/jlcsearch_plan/`) | no |

Run: `pytest -q`. **Never weaken a test** (docs/agents/04-testing-rules.md).
