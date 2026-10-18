"""Fab output export.  OWNER: AGENT (tasks O-01, O-02).

Contract
--------
    export_fab(kicad_pcb: Path, kicad_sch: Path, out_dir: Path) -> contracts.FabPackage

- kicad-cli: gerbers, drill (excellon), pos (csv, mm), BOM; plus report.json.
- Refuses to export unless the latest verify + DRC results are attached to the run
  (integrity rule: never ship a board without its report).

Must never
----------
- export from a board whose DRC was not re-run after routing,
- drop the verification report from the package.
"""
from __future__ import annotations

from pathlib import Path

from reflow.contracts import FabPackage


def export_fab(kicad_pcb: Path, kicad_sch: Path, out_dir: Path) -> FabPackage:
    raise NotImplementedError("O-01: fab export not built yet")
