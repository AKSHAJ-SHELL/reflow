"""Run report: report.json and report.md.  OWNER: AGENT (task O-02).

Contract
--------
    build_report(run_dir, *, route: RouteResult | None = None) -> dict
    render_markdown(report: dict) -> str
    write_report(run_dir, out_dir=None, *, route=None) -> (report.json path, report.md path)
    ReportError                         # the run folder is incomplete or disagrees with itself

Reads a run folder (docs/02-architecture.md) and reports every attempt, the
failed ones included (golden rule 6):

    {run_id, title, request, status, best_attempt, tokens: {input, output},
     attempts: [{attempt, compiled, compile_tries: [{try, ok, errors: [CompileError]}],
                 verify: VerifyReport | null}],
     verify: the best attempt's VerifyReport | null,
     parts: ResolvedParts, route: RouteResult | null, signoff: SignOff | null,
     schematic: schematic/schematic.json (reflow.schematic, O-04) | null}

- `compile_tries` comes from attempts/NN/compile-N.json. A compiled attempt
  whose compile files were left out (reduced fixtures) has []; an attempt
  that didn't compile must have them, since they hold the only record of why.
- `verify` is attempts/NN/verify.json exactly as the verifier wrote it.
- `route` is the one passed in, else route/route.json when the run has one,
  else null, and the markdown then says the board wasn't routed or
  DRC-checked. Routing is never inferred from anything else.
- `signoff` is signoff.json when present.
- `schematic` is our KiCad schematic's check (ERC, `reflow check`, nets)
  from schematic/schematic.json, written by `reflow export`.

ReportError is raised, never papered over, when run.json names an attempt
whose folder is missing, a compiled attempt has no verify.json, an uncompiled
one has no compile record, the number of compile files differs from
run.json's compile_tries, or verify.json's errors, warnings or rule ids
differ from run.json's record of that attempt.

report.md is for people: the status, each attempt's compile errors and
violations (message, refs, fix hint), routing and DRC, parts and sign-off.

Must never
----------
- leave out a failed attempt or a violation,
- say a board is routed without a RouteResult (which carries our DRC),
- change anything in the run folder other than the two report files.
"""
from __future__ import annotations

import json
from pathlib import Path

from reflow.contracts import (
    CompileResult,
    ContractError,
    ResolvedParts,
    RouteResult,
    RunResult,
    SignOff,
    Spec,
    VerifyReport,
    from_dict,
    to_dict,
)

STATUS_WORDS = {
    "passed": "passed verify",
    "failed_verify": "failed verify",
    "failed_compile": "no attempt compiled",
    "aborted": "aborted",
}


class ReportError(Exception):
    pass


def build_report(run_dir, *, route: RouteResult | None = None) -> dict:
    run_dir = Path(run_dir)
    run = _read(RunResult, run_dir / "run.json")
    spec = _read(Spec, run_dir / "spec.json")
    parts = _read(ResolvedParts, run_dir / "parts.json")
    if route is None and (run_dir / "route" / "route.json").is_file():
        route = _read(RouteResult, run_dir / "route" / "route.json")
    signoff = _read(SignOff, run_dir / "signoff.json") if (run_dir / "signoff.json").is_file() else None
    schematic_json = run_dir / "schematic" / "schematic.json"
    schematic = json.loads(schematic_json.read_text(encoding="utf-8")) if schematic_json.is_file() else None

    attempts = [_attempt(run_dir, record) for record in run.attempts]
    best = next((a["verify"] for a in attempts if a["attempt"] == run.best_attempt), None)
    return {
        "run_id": run.run_id,
        "title": spec.title,
        "request": spec.request,
        "status": run.status,
        "best_attempt": run.best_attempt,
        "tokens": {"input": run.input_tokens, "output": run.output_tokens},
        "attempts": attempts,
        "verify": best,
        "parts": to_dict(parts),
        "route": to_dict(route) if route is not None else None,
        "signoff": to_dict(signoff) if signoff is not None else None,
        "schematic": schematic,
    }


def write_report(run_dir, out_dir=None, *, route: RouteResult | None = None) -> tuple[Path, Path]:
    report = build_report(run_dir, route=route)
    out = Path(out_dir) if out_dir is not None else Path(run_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path, md_path = out / "report.json", out / "report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def _attempt(run_dir: Path, record) -> dict:
    folder = run_dir / "attempts" / f"{record.attempt:02d}"
    if not folder.is_dir():
        raise ReportError(f"run.json lists attempt {record.attempt}, but {folder} is missing")
    files = sorted(folder.glob("compile-*.json"), key=lambda f: int(f.stem.split("-")[1]))
    tries = [{"try": n, "ok": c.ok, "errors": [to_dict(e) for e in c.errors]}
             for n, c in enumerate((_read(CompileResult, f) for f in files), start=1)]
    if files and len(files) != record.compile_tries:
        raise ReportError(f"attempt {record.attempt}: run.json says {record.compile_tries} compile tries, "
                          f"but {folder} has {len(files)} compile files")
    if not record.compiled:
        if not files:
            raise ReportError(f"attempt {record.attempt} didn't compile and {folder} has no compile-N.json")
        return {"attempt": record.attempt, "compiled": False, "compile_tries": tries, "verify": None}
    if not (folder / "verify.json").is_file():
        raise ReportError(f"attempt {record.attempt} compiled but {folder / 'verify.json'} is missing")
    verify = _read(VerifyReport, folder / "verify.json")
    said = (record.errors, record.warnings, list(record.rule_ids))
    found = (verify.errors, verify.warnings, [v.rule_id for v in verify.violations])
    if said != found:
        raise ReportError(f"attempt {record.attempt}: run.json records {said[0]} errors, {said[1]} warnings "
                          f"{said[2]}, but verify.json has {found[0]}, {found[1]} {found[2]}")
    return {"attempt": record.attempt, "compiled": True, "compile_tries": tries, "verify": to_dict(verify)}


def _read(cls, path: Path):
    try:
        return from_dict(cls, json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError as exc:
        raise ReportError(f"{path} is missing") from exc
    except (json.JSONDecodeError, ContractError) as exc:
        raise ReportError(f"{path}: {exc}") from exc


# --- markdown ----------------------------------------------------------------

def render_markdown(report: dict) -> str:
    lines = [f"# {report['title']}", ""]
    attempts = report["attempts"]
    status = STATUS_WORDS.get(report["status"], report["status"])
    best = f"best attempt {report['best_attempt']} of {len(attempts)}" if report["best_attempt"] else \
        f"{len(attempts)} attempts"
    lines.append(f"Run `{report['run_id']}`: **{status}**, {best}. "
                 f"Tokens: {report['tokens']['input']} in, {report['tokens']['output']} out.")
    if report["status"] == "passed":
        lines.append("")
        lines.append("Passed means the verifier's rules found no error. It doesn't check everything "
                     "(docs/05-verifier-rules.md).")
    lines += ["", f"> {report['request']}", "", "## Attempts", "",
              "| Attempt | Compiled | Compile tries | Errors | Warnings |", "|---|---|---|---|---|"]
    for a in attempts:
        v = a["verify"]
        tries = len(a["compile_tries"]) or "–"
        lines.append(f"| {a['attempt']} | {'yes' if a['compiled'] else 'no'} | {tries} | "
                     f"{v['errors'] if v else '–'} | {v['warnings'] if v else '–'} |")
    for a in attempts:
        lines += ["", f"### Attempt {a['attempt']}", ""]
        for t in a["compile_tries"]:
            if t["ok"]:
                lines.append(f"- Compile try {t['try']}: compiled.")
            for e in t["errors"]:
                at = f" ({e['file']}:{e['line']})" if e.get("line") else ""
                lines.append(f"- Compile try {t['try']} failed{at}: {e['message']}")
        v = a["verify"]
        if v is None:
            lines.append("- Not verified: it didn't compile.")
            continue
        lines.append(f"- Verify: {v['errors']} errors, {v['warnings']} warnings "
                     f"({v['components']} components, {v['nets']} nets).")
        for item in v["violations"]:
            refs = f" ({', '.join(item['refs'])})" if item["refs"] else ""
            lines.append(f"  - **{item['severity']}** `{item['rule_id']}`{refs}: {item['message']}")
            if item["fix_hint"]:
                lines.append(f"    Fix: {item['fix_hint']}")
    lines += ["", "## Routing and DRC", "", _route_line(report["route"])]
    lines += ["", "## Schematic", "", _schematic_line(report.get("schematic"))]
    lines += ["", "## Parts", "", "| Request | LCSC | MPN | Manufacturer | Package | Value |", "|---|---|---|---|---|---|"]
    for p in report["parts"]["resolved"]:
        lines.append("| " + " | ".join(_cell(p[k]) for k in ("request_id", "lcsc", "mpn", "manufacturer", "package", "value"))
                     + " |")
    for u in report["parts"]["unresolved"]:
        lines.append(f"\nUnresolved {u['request_id']}: {u['reason']}")
    lines += ["", "## Sign-off", "", _signoff_line(report["signoff"]), ""]
    return "\n".join(lines)


def _route_line(route: dict | None) -> str:
    if route is None:
        return "Not routed or DRC-checked. `reflow export RUN_DIR` routes the best attempt and checks it."
    words = {"routed": "routed", "partial": "partly routed", "refused": "refused", "failed": "not routed"}
    parts = [f"Routing ({route['router']}): {words.get(route['status'], route['status'])}, "
             f"{route['routed_nets']}/{route['total_nets']} nets in copper"]
    if route["unrouted_nets"]:
        parts.append("unrouted: " + ", ".join(route["unrouted_nets"]))
    if route["refused_nets"]:
        parts.append("refused: " + ", ".join(route["refused_nets"]))
    for t in route.get("too_long", []):
        parts.append(f"over length: {t['net']} {'–'.join(t['ports'])} {t['length_mm']} mm (limit {t['limit_mm']} mm)")
    drc = route["drc"]
    parts.append(f"KiCad DRC (JLCPCB 2-layer rules): {drc['errors']} errors, {drc['unconnected']} unconnected, "
                 f"{drc['warnings']} warnings. Report: {drc['report_path']}")
    return ". ".join(parts[:1]) + "".join(f" · {p}" for p in parts[1:])


def _schematic_line(schematic: dict | None) -> str:
    if schematic is None:
        return "No schematic checked yet. `reflow export RUN_DIR` draws one from circuit.json and checks it."
    if schematic["erc"] is None:
        return "Not drawn: " + "; ".join(schematic["problems"])
    erc, check, nets = schematic["erc"], schematic["check"], schematic["nets"]
    match = "nets match circuit.json and the PCB" if nets["circuit_json"] and nets["pcb"] else \
        "nets differ: " + "; ".join(nets["differences"][:3])
    line = (f"KiCad ERC: {erc['errors']} errors, {erc['warnings']} warnings · reflow check: {check['errors']} errors"
            f" · {match}. File: {schematic['path']}")
    for item in erc["items"][:5] + [v for v in check["violations"] if v.startswith("error")][:5]:
        line += f"\n- {item}"
    return line


def _signoff_line(signoff: dict | None) -> str:
    if signoff is None:
        return "Not signed off."
    head = f"Signed off: {'accepted' if signoff['accepted'] else 'not accepted'} at {signoff['at']}."
    if signoff["warnings_acknowledged"]:
        head += " Warnings acknowledged: " + ", ".join(signoff["warnings_acknowledged"]) + "."
    if signoff["overrides"]:
        head += " Overrides: " + ", ".join(signoff["overrides"]) + "."
    return head


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
