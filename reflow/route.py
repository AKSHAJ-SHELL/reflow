"""Router wrapper for simple 2-layer boards.  OWNER: AGENT (tasks X-01, X-02, X-04).

Contract
--------
    route(kicad_pcb: Path, workdir: Path, *, max_tries: int = 3) -> contracts.RouteResult

- Default router: tscircuit's built-in autorouter. Fallback: freerouting via the
  KiCad 10 SWIG pcbnew DSN/SES bridge (tools/bridges/), run as a subprocess (GPL).
- After every route: refill zones, then re-run `kicad-cli pcb drc` ourselves.
  RouteResult.drc always comes from OUR DRC run.
- Nets flagged by the high-speed scope rule are never autorouted (refused_nets).

Must never
----------
- report "routed" from the router's own log,
- autoroute a refused net,
- modify the schematic.
"""
from __future__ import annotations

from pathlib import Path

from reflow.contracts import RouteResult


def route(kicad_pcb: Path, workdir: Path, *, max_tries: int = 3) -> RouteResult:
    raise NotImplementedError("X-01: router wrapper not built yet")
