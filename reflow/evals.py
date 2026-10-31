"""Eval runner over evals/.  OWNER: AGENT (task E-01).

Contract
--------
    run_evals(evals_dir, *, make_model, compiler, bind=None, db_path=None,
              runs_dir, out_dir, only=None, max_attempts=3, compile_cap=2,
              repeats=1, model_retries=2, retry_wait_s=10.0, sleep=time.sleep) -> dict

For each eval folder (evals/README.md): resolve the plan's parts from the
local snapshot, run the design loop (`run_design`) with the design verifier,
then measure the best attempt's board:

- status, attempts, `first_pass` (passed on attempt 1), rule ids per attempt;
- `foreign_part_numbers`: every manufacturer or supplier part number in the
  board's circuit.json that came from neither the resolver nor the spec's
  named parts (the go/no-go's "zero part numbers outside the resolver");
- `expectation_misses`: what the board lacks against expected.toml, read on
  the board's own netlist. Kinds map to the reference prefixes codegen uses
  (ic/regulator U, resistor R, capacitor C, connector J, led/diode D); LED
  `anode`/`cathode` are tscircuit's pin 1 / pin 2. Until V-12 binds pin maps,
  IC pin names are the design's own labels;
- tokens in and out.

A board is `clean` when it passed, has no foreign part numbers and no
expectation misses.

`stage` says where a board stopped, in pipeline order:

- `parts`: an unresolved part aborted it before any model call, or the catalog failed;
- `model`: a model call still failed after its retries (not a design failure);
- `compile`: no attempt compiled;
- `pin_binding`: the best attempt's verify errors include a `pinout.*` error;
- `rules`: the best attempt failed verify on other rules;
- `part_numbers`: it passed with a part number from outside the resolver;
- `expectations`: it passed but misses expected.toml;
- `tool`: tsci, circuit.json or the verifier input failed;
- `none`: clean.

Model calls are retried: a ModelError (timeout, empty or cut-off reply,
provider error) is retried `model_retries` times, waiting `retry_wait_s` times
the retry number between tries. Each board records `model_retries` and the
errors it retried. The totals count `model_errors` apart from
`design_failures` (compile, pin_binding, rules, part_numbers, expectations).

`repeats` runs each board that many times, because a model's output varies
from run to run. `boards` has one entry per run (`repeat` 1..N; run folders
are `<runs>/<stamp>/<board>/run<N>` when N > 1), and `by_board` has each
board's runs, passes, clean runs, rates and stages. A board counts as clean
for the go/no-go when more than half of its runs were clean.

`go_no_go` follows TASKS.md: at least 3 clean boards out of 5, with no
foreign part numbers on any run, and it is "undecided" while any eval is
still a draft or there are fewer than five.

A model, catalog or compiler error is recorded on that board and the run
moves on. The summary is returned and written to `out_dir/<UTC stamp>.json`
with what the run used (model, pin binding, parts database and snapshot, git
commit, tsci version, repeats, and a SHA-256 of each prompts/*.md file plus
one `prompts_hash` over them, so runs on different prompts aren't compared
as if they were the same).

Pin binding: `make_bind(spec)` gives each board its binder (the CLI uses
`reflow.pinbind.binder_for_spec`, with the board's rules_file resolved next to
its spec). `bind` is one binder for every board. With neither, the verifier
gets a pass-through and the results say "none".

Must never
----------
- choose or invent a part number, or count a model-written one as resolved,
- report a board as clean without its verify report, or drop a failed board,
- call the go/no-go while any eval is a draft.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
import tomllib
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from reflow.circuit_netlist import CircuitJsonError, load_circuit_json, part_numbers
from reflow.compile import TsciMissingError, TsciTimeoutError, find_tsci
from reflow.contracts import Plan, ResolvedParts, Spec, from_dict
from reflow.harness.loop import run_design
from reflow.llm import ModelError
from reflow.part_numbers import foreign_part_numbers
from reflow.parts.catalog import CatalogError
from reflow.parts.local_catalog import search
from reflow.parts.resolver import resolve
from reflow.parts.snapshot import default_db_path
from reflow.verifier import VerifierInputError, make_verifier

NO_BINDING = "none (pins not bound to pin maps)"
_PREFIX = {
    "ic": "U", "regulator": "U", "resistor": "R", "capacitor": "C", "connector": "J",
    "led": "D", "diode": "D", "inductor": "L", "transistor": "Q", "crystal": "Y", "switch": "SW",
}
_LED_PINS = {"ANODE": "1", "CATHODE": "2"}
_ERRORS = (ModelError, CatalogError, TsciMissingError, TsciTimeoutError, CircuitJsonError, VerifierInputError)
_DESIGN_STAGES = ("compile", "pin_binding", "rules", "part_numbers", "expectations")
_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


class _Counting:
    """Wraps a model to note which model ids answered, and retries failed calls."""

    def __init__(self, model, retries: int = 0, wait_s: float = 0.0, sleep=time.sleep) -> None:
        self.model, self.ids = model, set()
        self.retries, self.wait_s, self.sleep = retries, wait_s, sleep
        self.retried: list[str] = []

    def complete(self, system, prompt, *, max_tokens=None):
        for retry in range(self.retries + 1):
            try:
                # None leaves the budget to the model (config max_tokens, M-03).
                completion = self.model.complete(system, prompt, max_tokens=max_tokens)
            except ModelError as exc:
                if retry == self.retries:
                    raise
                self.retried.append(f"ModelError: {exc}"[:300])
                self.sleep(self.wait_s * (retry + 1))
                continue
            self.ids.add(completion.model)
            return completion
        raise AssertionError("unreachable")


def run_evals(evals_dir, *, make_model: Callable[[str], object], compiler, bind=None, make_bind=None,
              db_path=None, runs_dir, out_dir, only: list[str] | None = None,
              max_attempts: int = 3, compile_cap: int = 2, repeats: int = 1,
              model_retries: int = 2, retry_wait_s: float = 10.0, sleep=time.sleep) -> dict:
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folders = sorted(p for p in Path(evals_dir).iterdir() if p.is_dir() and (p / "spec.json").is_file())
    if only:
        folders = [p for p in folders if p.name in only]
    model_ids: set[str] = set()
    boards = []
    for folder in folders:
        for repeat in range(1, repeats + 1):
            model = _Counting(make_model(folder.name), model_retries, retry_wait_s, sleep)
            run_dir = Path(runs_dir) / stamp / folder.name
            if repeats > 1:
                run_dir = run_dir / f"run{repeat}"
            board = _run_board(folder, model, compiler, bind, make_bind, db_path, run_dir, max_attempts, compile_cap)
            board.update(repeat=repeat, model_retries=len(model.retried), model_errors_retried=model.retried)
            boards.append(board)
            model_ids |= model.ids
    by_board = _by_board(boards)
    run_info = _run_info(stamp, model_ids, make_bind or bind, db_path)
    run_info.update(repeats=repeats, model_retries=model_retries)
    summary = {
        "run": run_info,
        "boards": boards,
        "by_board": by_board,
        "totals": _totals(boards),
    }
    summary["go_no_go"] = _go_no_go(boards, by_board)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{stamp}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def _run_board(folder: Path, model, compiler, bind, make_bind, db_path, run_dir: Path,
               max_attempts: int, compile_cap: int) -> dict:
    spec = from_dict(Spec, json.loads((folder / "spec.json").read_text(encoding="utf-8")))
    if spec.rules_file.strip() and not Path(spec.rules_file).is_absolute():
        spec = replace(spec, rules_file=str((folder / spec.rules_file).resolve()))
    plan = from_dict(Plan, json.loads((folder / "plan.json").read_text(encoding="utf-8")))
    expected = tomllib.loads((folder / "expected.toml").read_text(encoding="utf-8"))
    board = {
        "name": folder.name, "repeat": 1, "status": "", "stage": "", "attempts": 0, "best_attempt": 0,
        "first_pass": False, "model_retries": 0, "model_errors_retried": [],
        "rule_ids_by_attempt": [], "abort_reason": "", "error": "", "foreign_part_numbers": [],
        "expectations": expected.get("status", "draft"), "expectation_misses": [], "clean": False,
        "input_tokens": 0, "output_tokens": 0, "run_dir": str(run_dir),
    }
    try:
        bind = make_bind(spec) if make_bind is not None else (bind or _passthrough)
        verifier = make_verifier(bind=bind)
        parts = resolve(plan.parts, spec.named_parts,
                        {p.id: search(p, db_path=db_path) for p in plan.parts})
        result = run_design(spec, plan, parts, model=model, compiler=compiler, verifier=verifier,
                            run_dir=run_dir, max_attempts=max_attempts, compile_cap=compile_cap)
    except _ERRORS as exc:
        stage = "model" if isinstance(exc, ModelError) else "parts" if isinstance(exc, CatalogError) else "tool"
        board.update(status="error", stage=stage, error=f"{type(exc).__name__}: {exc}")
        return board
    board.update(
        status=result.status, attempts=len(result.attempts), best_attempt=result.best_attempt,
        first_pass=result.status == "passed" and len(result.attempts) == 1,
        rule_ids_by_attempt=[a.rule_ids for a in result.attempts],
        abort_reason=getattr(result, "abort_reason", "") if result.status == "aborted" else "",
        input_tokens=result.input_tokens, output_tokens=result.output_tokens,
    )
    if result.best_attempt:
        record = result.attempts[result.best_attempt - 1]
        circuit = Path(record.dir) / "build" / "circuit.json"
        try:
            board["foreign_part_numbers"] = _foreign(circuit, parts, spec)
            bound = bind(load_circuit_json(circuit), parts, spec, part_numbers(circuit))
            board["expectation_misses"] = _misses(getattr(bound, "netlist", bound), expected)
        except CircuitJsonError as exc:
            board["error"] = f"CircuitJsonError: {exc}"
    board["clean"] = (board["status"] == "passed" and not board["foreign_part_numbers"]
                      and not board["expectation_misses"] and not board["error"])
    board["stage"] = _stage(board, result)
    return board


def _stage(board: dict, result) -> str:
    if result.status == "aborted":
        return "parts"
    if result.status == "failed_compile":
        return "compile"
    if result.status == "failed_verify":
        record = result.attempts[result.best_attempt - 1]
        return "pin_binding" if any(r.startswith("pinout.") for r in _error_rule_ids(record)) else "rules"
    if board["error"]:
        return "tool"
    if board["foreign_part_numbers"]:
        return "part_numbers"
    if board["expectation_misses"]:
        return "expectations"
    return "none"


def _error_rule_ids(record) -> list[str]:
    """Error rule ids from the attempt's verify.json, else every rule id the attempt recorded."""
    report = Path(record.dir) / "verify.json"
    try:
        violations = json.loads(report.read_text(encoding="utf-8"))["violations"]
        return [v["rule_id"] for v in violations if v.get("severity") == "error"]
    except (OSError, ValueError, KeyError, TypeError):
        return list(record.rule_ids)


def _passthrough(netlist, parts, spec, part_numbers=None):
    return netlist


def _foreign(circuit: Path, parts: ResolvedParts, spec: Spec) -> list[dict]:
    return foreign_part_numbers(circuit, parts, spec)


def _misses(netlist, expected: dict) -> list[str]:
    misses = []
    for name in expected.get("nets", []):
        if name not in netlist.nets:
            misses.append(f"net {name} is missing")
    want: Counter = Counter()
    for kind, count in expected.get("parts", {}).items():
        want[_PREFIX.get(kind, kind.upper())] += count
    have = Counter(component.prefix for component in netlist.components.values())
    for prefix, count in sorted(want.items()):
        if have[prefix] != count:
            kinds = "/".join(k for k, p in _PREFIX.items() if p == prefix and k in expected["parts"])
            misses.append(f"parts: expected {count} {kinds} ({prefix}), board has {have[prefix]}")
    for net in expected.get("net", []):
        pins = netlist.nets.get(net["name"], [])
        for item in net.get("includes", []):
            if not any(_pin_is(netlist, pin, item) for pin in pins):
                misses.append(f"net {net['name']} should include {item}")
    for group in expected.get("open", []):
        for item in group.get("pins", []):
            matches = [pin for pins in netlist.nets.values() for pin in pins if _pin_is(netlist, pin, item)]
            if not matches:
                misses.append(f"{item} should stay unconnected, but the board has no such pin")
            elif any(not netlist.is_unconnected(p.net) and len(netlist.nets[p.net]) > 1 for p in matches):
                misses.append(f"{item} should stay unconnected")
    return misses


def _pin_is(netlist, pin, item: str) -> bool:
    kind, _, name = item.partition(".")
    prefix = _PREFIX.get(kind, kind.upper())
    if netlist.components[pin.ref].prefix != prefix:
        return False
    if not name:
        return True
    if prefix == "D" and name.upper() in _LED_PINS:
        return pin.pin == _LED_PINS[name.upper()]
    return pin.name.upper() == name.upper()


def _totals(boards: list[dict]) -> dict:
    count = len(boards)
    passed = sum(b["status"] == "passed" for b in boards)
    first = sum(b["first_pass"] for b in boards)
    stages = Counter(b["stage"] for b in boards)
    return {
        "model_errors": stages["model"],
        "design_failures": sum(stages[s] for s in _DESIGN_STAGES),
        "by_stage": dict(sorted(stages.items())),
        "model_retries": sum(b["model_retries"] for b in boards),
        "boards": count,
        "passed": passed,
        "first_pass": first,
        "aborted": sum(b["status"] == "aborted" for b in boards),
        "errors": sum(b["status"] == "error" for b in boards),
        "clean": sum(b["clean"] for b in boards),
        "pass_rate_first": first / count if count else 0.0,
        "pass_rate_after_retry": passed / count if count else 0.0,
        "foreign_part_numbers": sum(len(b["foreign_part_numbers"]) for b in boards),
        "input_tokens": sum(b["input_tokens"] for b in boards),
        "output_tokens": sum(b["output_tokens"] for b in boards),
    }


def _by_board(boards: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for board in boards:
        row = out.setdefault(board["name"], {"runs": 0, "passed": 0, "first_pass": 0, "clean": 0,
                                             "model_errors": 0, "stages": Counter()})
        row["runs"] += 1
        row["passed"] += board["status"] == "passed"
        row["first_pass"] += board["first_pass"]
        row["clean"] += board["clean"]
        row["model_errors"] += board["stage"] == "model"
        row["stages"][board["stage"]] += 1
    for row in out.values():
        row["pass_rate"] = row["passed"] / row["runs"]
        row["clean_rate"] = row["clean"] / row["runs"]
        row["clean_majority"] = row["clean"] * 2 > row["runs"]
        row["stages"] = dict(sorted(row["stages"].items()))
    return out


def _go_no_go(boards: list[dict], by_board: dict) -> dict:
    drafts = sorted({b["name"] for b in boards if b["expectations"] != "checked"})
    if drafts:
        return {"decision": "undecided", "reason": f"{len(drafts)} eval(s) still draft: {', '.join(drafts)}"}
    if len(by_board) < 5:
        return {"decision": "undecided", "reason": f"needs 5 checked evals, ran {len(by_board)}"}
    clean = sum(row["clean_majority"] for row in by_board.values())
    foreign = sum(len(b["foreign_part_numbers"]) for b in boards)
    infra = sum(b["stage"] == "model" for b in boards)
    note = f", {infra} run(s) lost to model errors" if infra else ""
    if clean >= 3 and foreign == 0:
        return {"decision": "go", "reason": f"{clean}/{len(by_board)} clean, no part numbers outside the resolver{note}"}
    return {"decision": "no-go",
            "reason": f"{clean}/{len(by_board)} clean, {foreign} part number(s) outside the resolver{note}"}


def _run_info(stamp: str, model_ids: set[str], bind, db_path) -> dict:
    db = Path(db_path) if db_path is not None else default_db_path()
    snapshot = db.parent / "snapshot.json"
    return {
        "started": stamp,
        "model": ", ".join(sorted(model_ids)),
        "pin_binding": NO_BINDING if bind is None else f"{bind.__module__}.{getattr(bind, '__qualname__', type(bind).__name__)}",
        "parts_db": str(db),
        "parts_snapshot": json.loads(snapshot.read_text(encoding="utf-8")) if snapshot.is_file() else None,
        "commit": _command(["git", "rev-parse", "--short", "HEAD"]),
        "uncommitted_changes": bool(_command(["git", "status", "--porcelain"])),
        "tsci": _command([find_tsci() or "tsci", "--version"]),
        **_prompt_hashes(),
    }


def _prompt_hashes() -> dict:
    files = sorted(p for p in _PROMPTS.glob("*.md") if p.name != "README.md")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    combined = hashlib.sha256("".join(f"{name}:{h}\n" for name, h in hashes.items()).encode()).hexdigest()
    return {"prompts": hashes, "prompts_hash": combined}


def _command(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                              cwd=Path(__file__).resolve().parents[1])
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""
