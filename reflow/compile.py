"""Compiler wrapper: tscircuit TSX -> KiCad files.  OWNER: AGENT (tasks K-01, K-02).

Contract
--------
    compile_board(tsx: str, workdir: Path, *, timeout_s: int = 120) -> contracts.CompileResult

- Writes `tsx` to workdir/index.circuit.tsx and runs the tscircuit CLI (`tsci`)
  as a subprocess to export KiCad schematic + PCB (+ circuit-json).
- On failure returns ok=False with parsed CompileError entries and the last
  <= 40 lines of stderr. Never raises for a compile error; raises only if
  `tsci` itself is missing (exit code 2 territory, like `reflow check`).

Must never
----------
- edit or "repair" the model's code,
- write outside `workdir`,
- treat a non-zero exit as success, or a zero exit as proof the files exist.
"""
from __future__ import annotations

from pathlib import Path

from reflow.contracts import CompileResult


def compile_board(tsx: str, workdir: Path, *, timeout_s: int = 120) -> CompileResult:
    raise NotImplementedError("K-01: tsci compile wrapper not built yet")
