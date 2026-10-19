"""`reflow check` and the `reflow design` command.

`design` loads a confirmed Spec and an optional Plan. When a model is
supplied it runs the harness loop. The retry policy lives in that loop,
not here. Without a model, the command only accepts the spec.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import asdict
from pathlib import Path

from reflow.checkpoint import (
    CheckpointError,
    load_plan,
    load_spec,
    reject_foreign_mpn,
    require_confirmed,
)
from reflow.contracts import ContractError, ResolvedParts, from_dict
from reflow.harness.loop import run_design
from reflow.llm import ModelError
from reflow.netlist import load_netlist
from reflow.rules import run_all

MAC_KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
SEVERITY_ORDER = {"error": 0, "warning": 1}


class InputError(Exception):
    """A tool or input problem; maps to exit code 2."""


def find_kicad_cli():
    for candidate in (os.environ.get("KICAD_CLI"), "kicad-cli", MAC_KICAD_CLI):
        if candidate and (found := shutil.which(candidate)):
            return found
    return None


def resolve_schematic(path: Path) -> Path:
    if not path.exists():
        raise InputError(f"{path}: no such file or directory")
    if path.is_dir():
        found = sorted(path.glob("*.kicad_sch"))
        if len(found) != 1:
            listing = "".join(f"\n  {p.name}" for p in found) or " none"
            raise InputError(f"{path}: expected exactly one top-level .kicad_sch, found:{listing}")
        return found[0]
    if path.suffix == ".kicad_pro":
        sch = path.with_suffix(".kicad_sch")
        if not sch.is_file():
            raise InputError(f"{path}: no matching schematic {sch.name}")
        return sch
    if path.suffix == ".kicad_sch":
        return path
    raise InputError(f"{path}: expected a .kicad_sch, .kicad_pro, or project directory")


def export_netlist(kicad_cli: str, sch: Path, out: Path) -> Path:
    cmd = [kicad_cli, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(sch)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as e:
        raise InputError(f"could not run kicad-cli: {e}") from e
    if proc.returncode != 0 or not out.exists():
        detail = (proc.stderr or proc.stdout).strip()
        raise InputError(f"kicad-cli netlist export failed (exit {proc.returncode})\n{detail}")
    return out


def sort_violations(violations):
    return sorted(violations, key=lambda v: (SEVERITY_ORDER.get(v.severity, 2), v.rule_id))


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


class Style:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, code, text):
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def red(self, t):
        return self._wrap("31", t)

    def yellow(self, t):
        return self._wrap("33", t)

    def green(self, t):
        return self._wrap("32", t)

    def dim(self, t):
        return self._wrap("2", t)


def render_human(sch: Path, netlist, violations, style: Style) -> str:
    width = max(shutil.get_terminal_size().columns, 40)
    out = [f"reflow check {sch.name}", f"{len(netlist.components)} components, {len(netlist.nets)} nets", ""]

    rule_w = max((len(v.rule_id) for v in violations), default=0) + 3
    for v in violations:
        if v.severity == "error":
            tag = style.red("✗ ERROR")
        else:
            tag = style.yellow("⚠ WARN ")
        targets = ", ".join(v.refs) if v.refs else ", ".join(v.nets)
        out.append(f"{tag}  {v.rule_id.ljust(rule_w)}{targets}".rstrip())
        out.extend(textwrap.wrap(v.message, width - 2, initial_indent="  ", subsequent_indent="  ") or [""])
        for label, text in (("why:", v.why), ("fix:", v.fix_hint)):
            if not text:
                continue
            lines = textwrap.wrap(text, width - 8)
            out.append(f"  {style.dim(label)}  {lines[0]}")
            out.extend(f"        {line}" for line in lines[1:])
        out.append("")

    errors = sum(v.severity == "error" for v in violations)
    warnings = len(violations) - errors
    if not violations:
        out.append(style.green("✓ No issues found"))
    else:
        summary = f"{_plural(errors, 'error')}, {_plural(warnings, 'warning')}"
        out.append(style.red(summary) if errors else style.yellow(summary))
    return "\n".join(out)


def render_json(sch: Path, netlist, violations) -> str:
    errors = sum(v.severity == "error" for v in violations)
    return json.dumps({
        "schematic": sch.name,
        "components": len(netlist.components),
        "nets": len(netlist.nets),
        "errors": errors,
        "warnings": len(violations) - errors,
        "violations": [asdict(v) for v in violations],
    }, indent=2)


def cmd_check(args) -> int:
    try:
        sch = resolve_schematic(Path(args.path))
        kicad_cli = find_kicad_cli()
        if kicad_cli is None:
            raise InputError("kicad-cli not found. Install KiCad 10 or set KICAD_CLI.")
        with tempfile.TemporaryDirectory(prefix="reflow-") as tmp:
            netlist = load_netlist(export_netlist(kicad_cli, sch, Path(tmp) / "board.net"))
    except InputError as e:
        print(f"reflow: {e}", file=sys.stderr)
        return 2

    violations = sort_violations(run_all(netlist))
    if args.json:
        print(render_json(sch, netlist, violations))
    else:
        color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        print(render_human(sch, netlist, violations, Style(color)))

    errors = sum(v.severity == "error" for v in violations)
    if errors or (args.strict and violations):
        return 1
    return 0


def cmd_design(
    args,
    codegen=None,
    *,
    model=None,
    compiler=None,
    verifier=None,
    parts=None,
    run_dir=None,
    max_attempts=3,
    compile_cap=2,
) -> int:
    """Accept a confirmed spec. Run the design loop when a model is supplied.

    `codegen` remains the checkpoint seam used when no model is injected.
    This command does not invent a part number and does not contain a second
    copy of the retry policy.
    """
    try:
        if not args.spec:
            raise InputError("reflow design needs --spec PATH to a confirmed Spec JSON")
        spec = load_spec(Path(args.spec))
        if args.request is not None and args.request != spec.request:
            raise InputError(f"request does not match Spec.request ({spec.request!r})")
        require_confirmed(spec)
        plan = None
        if args.plan:
            plan = load_plan(Path(args.plan))
            reject_foreign_mpn(plan, spec)
        if model is None:
            if codegen is not None:
                codegen(spec, plan)
        else:
            if compiler is None or verifier is None:
                raise InputError("reflow design needs a compiler and a verifier")
            resolved = parts if parts is not None else _load_parts(args)
            if resolved is None:
                raise InputError(
                    "resolved parts are required; refusing to invent a part number"
                )
            folder = _run_folder(spec, run_dir, args)
            result = run_design(
                spec,
                plan,
                resolved,
                model=model,
                compiler=compiler,
                verifier=verifier,
                run_dir=folder,
                max_attempts=max_attempts,
                compile_cap=compile_cap,
            )
            if result.status == "aborted":
                reason = getattr(result, "abort_reason", "") or "aborted"
                raise InputError(reason)
            print(
                f"status={result.status} best_attempt={result.best_attempt} "
                f"run_dir={result.run_dir}"
            )
            return 0 if result.status == "passed" else 1
    except (InputError, CheckpointError, ContractError, ModelError) as exc:
        print(f"reflow: {exc}", file=sys.stderr)
        return 2
    if model is None and codegen is None:
        print("spec accepted; design loop not run (H-03)")
    return 0


def _load_parts(args):
    path = getattr(args, "parts", None)
    if not path:
        return None
    file = Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputError(f"{file}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"{file}: invalid JSON ({exc.msg})") from exc
    return from_dict(ResolvedParts, data)


def _run_folder(spec, run_dir, args) -> Path:
    if run_dir is not None:
        return Path(run_dir)
    chosen = getattr(args, "run_dir", None)
    if chosen:
        return Path(chosen)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    slug = re.sub(r"[^a-z0-9]+", "-", spec.title.lower()).strip("-") or "board"
    return Path("runs") / f"{stamp}-{slug}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reflow", description="AI-assisted PCB verifier")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="check a KiCad schematic")
    check.add_argument("path", help=".kicad_sch, .kicad_pro, or project directory")
    check.add_argument("--json", action="store_true", help="print results as JSON")
    check.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    check.set_defaults(func=cmd_check)
    design = sub.add_parser(
        "design",
        help="accept a confirmed spec and optional plan",
        description=(
            "Load a confirmed Spec JSON and, when given, a Plan JSON. "
            "A non-empty part mpn must appear in Spec.named_parts. "
            "Runs the design loop when a model is supplied."
        ),
    )
    design.add_argument(
        "request",
        nargs="?",
        help="board request; must match Spec.request when both are given",
    )
    design.add_argument("--spec", metavar="PATH", help="path to a Spec JSON file")
    design.add_argument("--plan", metavar="PATH", help="path to a Plan JSON file")
    design.add_argument("--parts", metavar="PATH", help="path to a ResolvedParts JSON file")
    design.add_argument("--run-dir", metavar="PATH", help="run folder to create")
    return parser


def main(
    argv=None,
    *,
    codegen=None,
    model=None,
    compiler=None,
    verifier=None,
    parts=None,
    run_dir=None,
    max_attempts=3,
    compile_cap=2,
) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    if args.command == "design":
        return cmd_design(
            args,
            codegen=codegen,
            model=model,
            compiler=compiler,
            verifier=verifier,
            parts=parts,
            run_dir=run_dir,
            max_attempts=max_attempts,
            compile_cap=compile_cap,
        )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
