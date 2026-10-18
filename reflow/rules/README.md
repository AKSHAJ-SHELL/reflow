# reflow/rules/: verifier rules (OWNER: HUMAN)

**Does:** one module per rule family; each exports `check(nl, pcb=None) -> list[Violation]`. `run_all()` in `__init__.py` discovers them.

**Contract:** input is a `reflow.netlist.Netlist` (plus optional `.kicad_pcb` later); output is a list of `reflow.violation.Violation`. Rule IDs are `family.check`. Every rule ships with a known-bad fixture that produces exactly its ID, and all good fixtures stay clean. Catalog: `docs/05-verifier-rules.md`.

**Must never:** be edited by an agent; swallow its own exceptions; depend on a rendered picture; emit a Violation without both `why` (for people) and `fix_hint` (for the model).
