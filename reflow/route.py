"""Router wrapper for simple 2-layer boards.  OWNER: AGENT (tasks X-01, X-02, X-04).

Contract
--------
    route_report(circuit_json, kicad_pcb, workdir) -> contracts.RouteResult
    route(kicad_pcb: Path, workdir: Path, *, max_tries: int = 3) -> contracts.RouteResult   # freerouting (X-02), not built

The default router is tscircuit's own autorouter, which runs inside
`tsci export` (`compile_board`). `route_report` reads what it did and checks
it with our own KiCad DRC:

- Nets: every net with two or more pins in circuit.json is a net to route.
  A `pcb_autorouting_error` means the router skipped the board, so every one of
  them is unrouted. Otherwise a net named in a `pcb_port_not_connected_error`
  or `pcb_trace_missing_error` is unrouted.
- DRC: `kicad-cli pcb drc --format json --severity-all` on the exported
  .kicad_pcb, always run here and never taken from the router. `unconnected`
  is KiCad's count of unconnected items.
- Trace length: a `pcb_trace_too_long_error` is tscircuit's own check of a
  trace with a length limit (a decoupling cap's `maxDecouplingTraceLength`).
  tscircuit still routes the board and KiCad's DRC doesn't check length, so
  route_report lists each one in `workdir/trace_length.json` (net, the two
  ports, length and limit in mm, rounded to 0.01) and counts it against
  "routed". The file is always written, `[]` when there are none.
- Status: "routed" only when every net is copper (none unrouted and KiCad finds
  nothing unconnected) **and** our DRC has no errors **and** no trace is over
  its length limit. "partial" when some nets are copper but nets are unrouted,
  DRC has errors, or a trace is too long. "failed" when none are routed.

DRC uses the rules in the board's `board.kicad_pro`, which `compile_board`
writes with JLCPCB's published 2-layer minimums (`reflow.fab_rules`; the
human chose JLCPCB on 2026-10-23). Without that file, KiCad's defaults apply
and flag tscircuit's 0.15 mm tracks. Every DRC error is reported, never hidden.

tscircuit gives a decoupling cap's traces a 1 mm maximum length by default,
and skips routing the whole board when placement can't meet it. The codegen
prompt asks for `maxDecouplingTraceLength="5mm"` on decoupling caps (the limit covers the
ground side too; 3 mm missed by ~0.5 mm on 3 of 5 eval boards)
(tests/data/routing/README.md).

tscircuit's vias are 0.3 mm on a 0.2 mm drill (a 0.05 mm ring), and its router
keeps about 0.1 mm of copper from a via to a track, so the hole can land under
JLCPCB's 0.2 mm via-hole-to-track. The prompt asks for
`<board minViaPadDiameter="0.4mm">`: with a 0.1 mm ring, 0.1 mm of copper
spacing puts the hole 0.2 mm from the track.

Must never
----------
- report "routed" from the router's own log, or without our DRC run,
- autoroute a refused net,
- modify the schematic.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from reflow.circuit_netlist import load_circuit_json
from reflow.contracts import DrcSummary, RouteResult

_NET_IN = re.compile(r"\bnet \[([^\]]+)\]|\bnet\.([A-Za-z0-9_]+)")
_TRACE_PORT = re.compile(r"\[([^\]]+)\]")


def route_report(circuit_json, kicad_pcb, workdir) -> RouteResult:
    elements = json.loads(Path(circuit_json).read_text(encoding="utf-8"))
    netlist = load_circuit_json(circuit_json)
    nets = sorted(name for name, pins in netlist.nets.items() if len(pins) >= 2)
    skipped = any(e["type"] == "pcb_autorouting_error" for e in elements)
    if skipped:
        unrouted = list(nets)
    else:
        unrouted = sorted({n for n in _nets_named(elements, netlist) if n in nets})
    drc = _drc(Path(kicad_pcb), Path(workdir))
    too_long = _too_long(elements)
    (Path(workdir) / "trace_length.json").write_text(json.dumps(too_long, indent=2) + "\n", encoding="utf-8")
    routed = len(nets) - len(unrouted)
    if routed == 0 and nets:
        status = "failed"
    elif unrouted or drc.unconnected or drc.errors or too_long:
        status = "partial"
    else:
        status = "routed"
    return RouteResult(status=status, router="tscircuit", tries=1, routed_nets=routed, total_nets=len(nets),
                       unrouted_nets=unrouted, refused_nets=[], drc=drc, kicad_pcb=str(kicad_pcb))


def route(kicad_pcb: Path, workdir: Path, *, max_tries: int = 3) -> RouteResult:
    raise NotImplementedError("X-02: freerouting fallback not built yet; tscircuit routes inside tsci export")


def _nets_named(elements: list[dict], netlist) -> set[str]:
    """Nets the router's errors say aren't connected by copper."""
    by_port = {f"{pin.ref}.{pin.function}": pin.net for pins in netlist.nets.values() for pin in pins}
    by_port.update({f"{pin.ref}.pin{pin.pin}": pin.net for pins in netlist.nets.values() for pin in pins})
    found: set[str] = set()
    for element in elements:
        if element["type"] not in ("pcb_port_not_connected_error", "pcb_trace_missing_error"):
            continue
        message = str(element.get("message", ""))
        for named, dotted in _NET_IN.findall(message):
            found.add(named or dotted)
        for port in _TRACE_PORT.findall(message):
            if port in by_port:
                found.add(by_port[port])
        for selector in re.findall(r"\.([A-Za-z]+\d+) > \.([A-Za-z0-9_+\-]+)", message):
            key = f"{selector[0]}.{selector[1]}"
            if key in by_port:
                found.add(by_port[key])
    return found


def _too_long(elements: list[dict]) -> list[dict]:
    """Each trace tscircuit says is over its length limit, by net and the ports it joins."""
    by_id = {}
    for e in elements:
        for kind in ("pcb_trace", "pcb_port", "source_port", "source_component", "source_net"):
            if e["type"] == kind:
                by_id[e[f"{kind}_id"]] = e
    found = []
    for e in elements:
        if e["type"] != "pcb_trace_too_long_error":
            continue
        ports = []
        for pcb_port in by_id[e["pcb_trace_id"]]["connectsTo"]:
            port = by_id[by_id[pcb_port]["source_port_id"]]
            ports.append(f"{by_id[port['source_component_id']]['name']}.{port['name']}")
        found.append({"net": by_id[e["source_net_id"]]["name"], "ports": sorted(ports),
                      "length_mm": round(float(e["actual_trace_length"]), 2),
                      "limit_mm": round(float(e["maximum_trace_length"]), 2)})
    return found


def _drc(kicad_pcb: Path, workdir: Path) -> DrcSummary:
    from reflow.cli import find_kicad_cli

    workdir.mkdir(parents=True, exist_ok=True)
    report = workdir / "drc.json"
    cli = find_kicad_cli()
    if cli is None:
        raise RuntimeError("kicad-cli not found, so the board can't be DRC-checked (and won't be called routed)")
    proc = subprocess.run([cli, "pcb", "drc", "--format", "json", "--severity-all", "-o", str(report), str(kicad_pcb)],
                          capture_output=True, text=True, timeout=300,
                          stdin=subprocess.DEVNULL)
    if not report.is_file():
        raise RuntimeError(f"kicad-cli pcb drc wrote no report: {(proc.stderr or proc.stdout).strip()[-300:]}")
    data = json.loads(report.read_text(encoding="utf-8"))
    violations = data.get("violations", [])
    return DrcSummary(
        errors=sum(v.get("severity") == "error" for v in violations),
        warnings=sum(v.get("severity") == "warning" for v in violations),
        unconnected=len(data.get("unconnected_items", [])),
        report_path=str(report),
    )
