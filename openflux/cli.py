"""`openflux check` — export a schematic's netlist with kicad-cli and run the rules."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import asdict
from pathlib import Path

from openflux.netlist import load_netlist
from openflux.rules import run_all

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
    out = [f"openflux check {sch.name}", f"{len(netlist.components)} components, {len(netlist.nets)} nets", ""]

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
        with tempfile.TemporaryDirectory(prefix="openflux-") as tmp:
            netlist = load_netlist(export_netlist(kicad_cli, sch, Path(tmp) / "board.net"))
    except InputError as e:
        print(f"openflux: {e}", file=sys.stderr)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openflux", description="AI-assisted PCB verifier")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="check a KiCad schematic")
    check.add_argument("path", help=".kicad_sch, .kicad_pro, or project directory")
    check.add_argument("--json", action="store_true", help="print results as JSON")
    check.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    check.set_defaults(func=cmd_check)
    return parser


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
