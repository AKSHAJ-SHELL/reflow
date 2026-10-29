"""Fab output export.  OWNER: AGENT (tasks O-01, O-02).

Contract
--------
    export_fab(kicad_pcb, circuit_json, out_dir, *, verify: VerifyReport, route: RouteResult,
               parts: ResolvedParts, spec: Spec, run_dir) -> contracts.FabPackage
    ExportRefused(reasons: list[str])      # raised before anything is written

Writes into `out_dir` (which must be new or empty), from the routed
.kicad_pcb with kicad-cli:

- `gerbers/`: both copper layers, mask, paste, silkscreen and Edge.Cuts, plus
  KiCad's gerber job file;
- `board.drl`: one Excellon drill file in mm, plated and unplated holes together;
- `board-pos.csv`: KiCad's placement CSV in mm, both sides (Ref, Val, Package,
  PosX, PosY, Rot, Side). Not renamed or rotated for any assembler's format;
- `bom.csv`: Comment, Designator, Footprint, LCSC Part #, MPN, one row per
  identical part. Part numbers come from the board's circuit.json, and every one
  must be the resolver's or a spec named part. Comment is the part's value
  (4.7kΩ, 100nF), else its MPN. Footprint is the pos file's Package;
- `drc.json`: a copy of our KiCad DRC report;
- `report.json` and `report.md`: the run's report (reflow.report, O-02), with
  every attempt and this `RouteResult`, its report_path pointing at that copy.
  `FabPackage.design_md` is report.md; `report_html` stays "" (O-03).

Refuses (ExportRefused, listing every reason) unless:

- verify found 0 errors, and `verify` is the run's best attempt's verify.json;
- routing is "routed", with every net in copper, nothing over its length
  limit, and our DRC at 0 errors and 0 unconnected items;
- that DRC ran on this .kicad_pcb, its report file exists, and the board
  wasn't modified after it (by file time);
- no part number on the board came from outside the resolver.

Must never
----------
- export from a board whose DRC was not re-run after routing,
- drop the verification report from the package,
- put a part number in the BOM that the resolver or the spec didn't give.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from reflow.contracts import FabPackage, ResolvedParts, RouteResult, Spec, VerifyReport, to_dict
from reflow.part_numbers import foreign_part_numbers
from reflow.report import build_report, render_markdown

LAYERS = "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
BOM_COLUMNS = ["Comment", "Designator", "Footprint", "LCSC Part #", "MPN"]


class ExportRefused(Exception):
    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def export_fab(kicad_pcb, circuit_json, out_dir, *, verify: VerifyReport, route: RouteResult,
               parts: ResolvedParts, spec: Spec, run_dir) -> FabPackage:
    from reflow.cli import find_kicad_cli

    kicad_pcb, circuit_json, out_dir = Path(kicad_pcb), Path(circuit_json), Path(out_dir)
    reasons = refusals(kicad_pcb, circuit_json, verify=verify, route=route, parts=parts, spec=spec)
    if build_report(run_dir)["verify"] != to_dict(verify):
        reasons.append("the verify report isn't the run's best attempt's verify.json")
    if out_dir.exists() and any(out_dir.iterdir()):
        reasons.append(f"{out_dir} is not empty; export into a new folder")
    if reasons:
        raise ExportRefused(reasons)
    cli = find_kicad_cli()
    if cli is None:
        raise RuntimeError("kicad-cli not found, so the board can't be exported")

    out_dir.mkdir(parents=True, exist_ok=True)
    gerbers = out_dir / "gerbers"
    drill = out_dir / f"{kicad_pcb.stem}.drl"
    pos = out_dir / f"{kicad_pcb.stem}-pos.csv"
    _kicad(cli, "gerbers", "-o", f"{gerbers}/", "-l", LAYERS, kicad_pcb)
    _kicad(cli, "drill", "-o", f"{out_dir}/", "--format", "excellon", "-u", "mm", kicad_pcb)
    _kicad(cli, "pos", "-o", str(pos), "--format", "csv", "--units", "mm", "--side", "both", kicad_pcb)
    for made in (drill, pos):
        if not made.is_file():
            raise RuntimeError(f"kicad-cli wrote no {made.name}")

    bom = out_dir / "bom.csv"
    _write_bom(circuit_json, pos, bom)
    drc = out_dir / "drc.json"
    shutil.copyfile(route.drc.report_path, drc)
    packaged = replace(route, drc=replace(route.drc, report_path=str(drc)))
    report = build_report(run_dir, route=packaged)
    report_json, report_md = out_dir / "report.json", out_dir / "report.md"
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_md.write_text(render_markdown(report), encoding="utf-8")
    return FabPackage(gerbers_dir=str(gerbers), drill=str(drill), pos_csv=str(pos), bom_csv=str(bom),
                      design_md=str(report_md), report_json=str(report_json))


def refusals(kicad_pcb: Path, circuit_json: Path, *, verify: VerifyReport, route: RouteResult,
             parts: ResolvedParts, spec: Spec) -> list[str]:
    """Every reason this board may not go to a fab; [] when it may."""
    reasons = []
    if verify.errors:
        reasons.append(f"verify found {verify.errors} errors")
    if route.status != "routed":
        why = [f"routing is {route.status}"]
        if route.unrouted_nets:
            why.append("unrouted: " + ", ".join(route.unrouted_nets))
        if route.refused_nets:
            why.append("refused: " + ", ".join(route.refused_nets))
        why += [f"{t.net} {'–'.join(t.ports)} is {t.length_mm} mm (limit {t.limit_mm} mm)" for t in route.too_long]
        reasons.append("; ".join(why))
    if route.drc.errors:
        reasons.append(f"KiCad DRC found {route.drc.errors} DRC errors")
    if route.drc.unconnected:
        reasons.append(f"KiCad DRC found {route.drc.unconnected} unconnected items")
    if Path(route.kicad_pcb).resolve() != kicad_pcb.resolve():
        reasons.append(f"the DRC was run on a different board ({route.kicad_pcb})")
    report = Path(route.drc.report_path)
    if not report.is_file():
        reasons.append(f"the DRC report {report} is missing")
    elif kicad_pcb.is_file() and kicad_pcb.stat().st_mtime > report.stat().st_mtime:
        reasons.append(f"{kicad_pcb.name} changed after its DRC; route and check it again")
    for found in foreign_part_numbers(circuit_json, parts, spec):
        reasons.append(f"{found['ref']} has {found['field']} {found['value']}, which the resolver didn't give")
    return reasons


def _kicad(cli: str, kind: str, *args) -> None:
    proc = subprocess.run([cli, "pcb", "export", kind, *map(str, args)], capture_output=True, text=True,
                          timeout=300, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise RuntimeError(f"kicad-cli pcb export {kind} failed: {(proc.stderr or proc.stdout).strip()[-300:]}")


def _write_bom(circuit_json: Path, pos: Path, bom: Path) -> None:
    with open(pos, newline="", encoding="utf-8") as f:
        footprint = {row["Ref"]: row["Package"] for row in csv.DictReader(f)}
    rows: dict[tuple, list[str]] = {}
    for e in json.loads(circuit_json.read_text(encoding="utf-8")):
        if e.get("type") != "source_component":
            continue
        ref = e["name"]
        if ref not in footprint:
            raise RuntimeError(f"{ref} is in circuit.json but not on the board's placement file")
        mpn = e.get("manufacturer_part_number") or ""
        lcsc = ((e.get("supplier_part_numbers") or {}).get("jlcpcb") or [""])[0]
        value = next((v for k, v in e.items() if k.startswith("display_") and isinstance(v, str)), "")
        rows.setdefault((value or mpn, footprint[ref], lcsc, mpn), []).append(ref)
    lines = sorted(((sorted(refs, key=_ref_order), key) for key, refs in rows.items()), key=lambda r: _ref_order(r[0][0]))
    with open(bom, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(BOM_COLUMNS)
        for refs, (comment, package, lcsc, mpn) in lines:
            writer.writerow([comment, ",".join(refs), package, lcsc, mpn])


def _ref_order(ref: str) -> tuple[str, int]:
    match = re.fullmatch(r"([A-Za-z_]+)(\d+)", ref)
    return (match[1], int(match[2])) if match else (ref, 0)
