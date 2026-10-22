"""`reflow check` and the `reflow design` command.

`design` loads a confirmed Spec and an optional Plan, then runs the harness
loop with pieces built from config: the model from `reflow.toml` and
REFLOW_* env (`load_model`), `compile_board`, parts from `--parts` or from
the local parts snapshot (`reflow parts update`) + resolver, and the design verifier on circuit.json. The retry
policy lives in that loop, not here. Tests inject those pieces through
`main(...)` keywords instead.

Parts are resolved from a plan, so without `--plan` or `--parts` the command
only accepts the spec (the loop plans after it checks parts, H-03).

Pin binding (V-12, HUMAN) is not built: `PIN_BINDING` is None, the verifier
runs with an explicit pass-through, and every real run prints a warning that
the decoupling rules did not run.
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
from reflow.circuit_netlist import CircuitJsonError
from reflow.compile import TsciMissingError, TsciTimeoutError, compile_board
from reflow.config import ConfigError, load_config
from reflow.contracts import ContractError, ResolvedParts, from_dict
from reflow.harness.loop import run_design
from reflow.llm import ModelError, load_model
from reflow.parts.catalog import CatalogError
from reflow.parts.local_catalog import search as catalog_search
from reflow.parts.resolver import resolve
from reflow.parts.snapshot import SnapshotError, update_snapshot
from reflow.netlist import load_netlist
from reflow.rules import run_all

MAC_KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
SEVERITY_ORDER = {"error": 0, "warning": 1}

# V-12 (HUMAN) supplies bind(netlist, parts, spec) -> Netlist here.
PIN_BINDING = None
UNBOUND_WARNING = (
    "warning: pin binding (V-12) is not built yet, so IC pins are untyped and the "
    "decoupling rules did not run on this board"
)


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
    """Accept a confirmed spec, then run the design loop.

    With nothing injected, the pieces come from config (`_run_from_config`).
    `model`/`compiler`/`verifier`/`parts` are test seams; `codegen` is the
    checkpoint seam that only receives the spec and plan. This command does
    not invent a part number and does not contain a second copy of the retry
    policy.
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
                return 0
            if plan is None and not getattr(args, "parts", None):
                print(
                    "spec accepted; design loop not run: parts are resolved from a plan, "
                    "so pass --plan (or --parts). The H-03 loop plans only after it checks parts."
                )
                return 0
            return _run_from_config(args, spec, plan, run_dir)
        if compiler is None or verifier is None:
            raise InputError("reflow design needs a compiler and a verifier")
        resolved = parts if parts is not None else _load_parts(args)
        if resolved is None:
            raise InputError("resolved parts are required; refusing to invent a part number")
        return _execute(
            spec, plan, resolved,
            model=model, compiler=compiler, verifier=verifier,
            folder=_run_folder(spec, run_dir, args),
            max_attempts=max_attempts, compile_cap=compile_cap,
        )
    except _RUN_ERRORS as exc:
        print(f"reflow: {exc}", file=sys.stderr)
        return 2


_RUN_ERRORS = (
    InputError, CheckpointError, ContractError, ModelError, ConfigError, CatalogError,
    TsciMissingError, TsciTimeoutError, CircuitJsonError,
)


def _run_from_config(args, spec, plan, run_dir) -> int:
    """The shell path: every piece comes from config, the catalog, or this package."""
    from reflow.verifier import VerifierInputError, make_verifier

    config = load_config()
    model = load_model(config)
    resolved = _load_parts(args)
    if resolved is None:
        resolved = _resolve_from_catalog(plan, spec)
    bind = PIN_BINDING
    if bind is None:
        print(UNBOUND_WARNING, file=sys.stderr)
        bind = _unbound
    try:
        return _execute(
            spec, plan, resolved,
            model=model, compiler=compile_board, verifier=make_verifier(bind=bind),
            folder=_run_folder(spec, run_dir, args),
            max_attempts=config["max_attempts"], compile_cap=config["compile_cap"],
        )
    except VerifierInputError as exc:
        raise InputError(str(exc)) from exc


def _execute(spec, plan, resolved, *, model, compiler, verifier, folder, max_attempts, compile_cap) -> int:
    result = run_design(
        spec, plan, resolved,
        model=model, compiler=compiler, verifier=verifier, run_dir=folder,
        max_attempts=max_attempts, compile_cap=compile_cap,
    )
    if result.status == "aborted":
        raise InputError(getattr(result, "abort_reason", "") or "aborted")
    print(f"status={result.status} best_attempt={result.best_attempt} run_dir={result.run_dir}")
    return 0 if result.status == "passed" else 1


def _resolve_from_catalog(plan, spec) -> ResolvedParts:
    """One local-snapshot query per plan part (D-6a), then the resolver picks (or refuses) each."""
    candidates = {part.id: catalog_search(part) for part in plan.parts}
    return resolve(plan.parts, spec.named_parts, candidates)


def _unbound(netlist, parts, spec):
    """Stand-in until V-12: pins stay untyped (UNBOUND_WARNING is printed)."""
    return netlist


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
    parts = sub.add_parser("parts", help="manage the local parts database")
    parts_sub = parts.add_subparsers(dest="parts_command", required=True)
    update = parts_sub.add_parser(
        "update",
        help="download and install the jlcparts snapshot",
        description=(
            "Download the jlcparts parts database (about 216 MB, 1.5 GB installed), "
            "check it, and install it at --db, REFLOW_PARTS_DB, or "
            "~/.cache/reflow/jlcparts/cache.sqlite3. The old database is kept if anything fails."
        ),
    )
    update.add_argument("--db", metavar="PATH", help="where to install cache.sqlite3")
    update.add_argument("--url", metavar="URL", help="snapshot base URL (default: REFLOW_PARTS_URL or jlcparts)")
    update.set_defaults(func=cmd_parts_update)
    evaluate = sub.add_parser(
        "eval",
        help="run the eval boards and report the go/no-go numbers",
        description=(
            "Run every board in --evals through the design loop with the configured model, then "
            "report first-pass and after-retry pass rates, part numbers outside the resolver, "
            "expectation misses and tokens. Results go to --out as JSON."
        ),
    )
    evaluate.add_argument("--evals", metavar="DIR", default="evals", help="eval folders (default: evals)")
    evaluate.add_argument("--out", metavar="DIR", default="evals/results", help="where the results JSON goes")
    evaluate.add_argument("--runs", metavar="DIR", default="runs/evals", help="run folders for each board")
    evaluate.add_argument("--only", metavar="NAME", action="append", help="run only this board (repeatable)")
    evaluate.set_defaults(func=cmd_eval)
    rules = sub.add_parser("rules", help="work with a project's rules.toml")
    rules_sub = rules.add_subparsers(dest="rules_command", required=True)
    check_rules_cmd = rules_sub.add_parser(
        "check",
        help="check a rules.toml against its parts' pin maps",
        description=(
            "Parse a rules.toml strictly and report errors (bad fields, blank why/source, pins that "
            "aren't on the part) and warnings (power, ground, reset and boot pins no rule mentions). "
            "Say which part each reference is with --symbol REF=Library:Symbol (KiCad) or "
            "--mpn REF=MPN (vendor pin data). Exit 1 on errors, 2 if the input can't be used."
        ),
    )
    check_rules_cmd.add_argument("rules_file", metavar="RULES", help="path to rules.toml")
    check_rules_cmd.add_argument("--symbol", metavar="REF=LIB:SYMBOL", action="append", default=[],
                                 help="pin map for REF from a KiCad symbol (repeatable)")
    check_rules_cmd.add_argument("--mpn", metavar="REF=MPN", action="append", default=[],
                                 help="pin map for REF from vendor pin data (repeatable)")
    check_rules_cmd.set_defaults(func=cmd_rules_check)
    return parser


def cmd_rules_check(args) -> int:
    from reflow.parts.pinmap import PinMapError, from_kicad_symbol, import_pin_map
    from reflow.project_rules import RulesFileError, check_rules, load_rules

    try:
        pin_maps = {}
        for option, build in (("symbol", lambda v: from_kicad_symbol(v)),
                              ("mpn", lambda v: import_pin_map(v).pin_map)):
            for pair in getattr(args, option):
                ref, sep, value = pair.partition("=")
                if not sep or not ref.strip() or not value.strip():
                    raise InputError(f"--{option} takes REF=VALUE, got {pair!r}")
                pin_maps[ref.strip()] = build(value.strip())
        rules = load_rules(Path(args.rules_file))
    except (InputError, PinMapError, RulesFileError) as exc:
        print(f"reflow: {exc}", file=sys.stderr)
        return 2
    result = check_rules(rules, pin_maps)
    for error in result.errors:
        print(f"error: {error}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    print(f"{result.rules} rules, {len(result.errors)} errors, {len(result.warnings)} warnings")
    return 1 if result.errors else 0


def cmd_eval(args) -> int:
    from reflow.evals import run_evals

    try:
        config = load_config()
        model = load_model(config)
        if PIN_BINDING is None:
            print(UNBOUND_WARNING, file=sys.stderr)
        summary = run_evals(
            Path(args.evals),
            make_model=lambda name: model,
            compiler=compile_board,
            bind=PIN_BINDING,
            runs_dir=Path(args.runs),
            out_dir=Path(args.out),
            only=args.only,
            max_attempts=config["max_attempts"],
            compile_cap=config["compile_cap"],
        )
    except (ConfigError, ModelError, CatalogError, ContractError, OSError) as exc:
        print(f"reflow: {exc}", file=sys.stderr)
        return 2
    for board in summary["boards"]:
        detail = board["abort_reason"] or board["error"] or "; ".join(board["expectation_misses"])
        foreign = len(board["foreign_part_numbers"])
        print(f"{board['name']}: {board['status']} in {board['attempts']} attempt(s), "
              f"{'clean' if board['clean'] else 'not clean'}, {foreign} foreign part number(s)"
              + (f" ({detail})" if detail else ""))
    t = summary["totals"]
    print(f"{t['passed']}/{t['boards']} passed ({t['first_pass']} on the first attempt), {t['clean']} clean, "
          f"{t['foreign_part_numbers']} part number(s) outside the resolver, "
          f"{t['input_tokens']} in / {t['output_tokens']} out tokens")
    go = summary["go_no_go"]
    print(f"go/no-go: {go['decision']} ({go['reason']})")
    return 0


def cmd_parts_update(args) -> int:
    try:
        info = update_snapshot(
            Path(args.db) if args.db else None,
            base_url=args.url,
            on_part=lambda name: print(f"fetching {name}", file=sys.stderr),
        )
    except SnapshotError as exc:
        print(f"reflow: {exc}", file=sys.stderr)
        return 2
    print(f"installed {info.path}: {info.components} parts, rows fetched {info.oldest_row} to {info.newest_row}")
    return 0


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
