"""The design verifier: circuit.json -> VerifyReport.  OWNER: AGENT (task V-16, DECISIONS V-1).

Contract
--------
    verify_circuit_json(circuit_json, parts, spec, *, bind) -> contracts.VerifyReport
    make_verifier(*, bind) -> Callable[[str, ResolvedParts, Spec], VerifyReport]

`make_verifier` returns the callable `run_design` takes as `verifier`.

Steps, in order:
1. `load_circuit_json` (V-10) builds the Netlist from tscircuit's own
   connectivity. Pins are untyped and carry the design's labels.
2. `bind(netlist, parts, spec)` returns the Netlist the rules will see. This is
   where IC pins are relabelled and typed from trusted pin maps (V-12, HUMAN).
   It is required on purpose: without it no pin is typed power, so the
   decoupling rules cannot fire, and that must be a visible choice in the
   caller's code rather than a silent default here.
3. `run_all` on the bound Netlist; violations sorted as `reflow check` sorts them.

`VerifyReport.schematic` is the circuit.json file name. Field values match
`reflow check --json` for the same violations.

Not yet included: the `.kicad_pcb` comparison (V-1 d). `reflow.pcb_nets` reads
the pads (V-14); the rule that compares them is V-13 (HUMAN).

Raises VerifierInputError for a `.kicad_sch` path (tscircuit's schematic
export loses connectivity, V-1) or a `bind` that does not return a Netlist.
Errors from `load_circuit_json` propagate, including MergedNetsError for two
named nets wired together, which V-13 decides how to report.

Must never
----------
- verify tscircuit's .kicad_sch,
- type or rename pins itself, or skip `bind`,
- send anything to a model or read a part number from the design.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from reflow.circuit_netlist import load_circuit_json
from reflow.cli import sort_violations
from reflow.contracts import ResolvedParts, Spec, VerifyReport
from reflow.netlist import Netlist
from reflow.rules import run_all

Bind = Callable[[Netlist, ResolvedParts, Spec], Netlist]


class VerifierInputError(ValueError):
    """The verifier was given the wrong file, or `bind` misbehaved."""


def verify_circuit_json(circuit_json, parts: ResolvedParts, spec: Spec, *, bind: Bind) -> VerifyReport:
    path = Path(circuit_json)
    if path.suffix == ".kicad_sch":
        raise VerifierInputError(
            f"{path.name}: the design verifier reads circuit.json, never tscircuit's .kicad_sch "
            "(V-1). loop.py must pass compile_result.circuit_json (docs/proposals/V-1-loop-HUMAN.patch)."
        )
    netlist = bind(load_circuit_json(path), parts, spec)
    if not isinstance(netlist, Netlist):
        raise VerifierInputError(f"bind returned {type(netlist).__name__}, not a Netlist")
    violations = sort_violations(run_all(netlist))
    errors = sum(v.severity == "error" for v in violations)
    return VerifyReport(
        schematic=path.name,
        components=len(netlist.components),
        nets=len(netlist.nets),
        errors=errors,
        warnings=len(violations) - errors,
        violations=violations,
    )


def make_verifier(*, bind: Bind) -> Callable[[str, ResolvedParts, Spec], VerifyReport]:
    def verifier(circuit_json: str, parts: ResolvedParts, spec: Spec) -> VerifyReport:
        return verify_circuit_json(circuit_json, parts, spec, bind=bind)
    return verifier
