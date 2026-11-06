"""One board project for the TUI: what the user typed, the datasheet, spec, plan, rules, runs.  OWNER: AGENT (task T-01).

Contract
--------
    Project(root)                                   # loads root/.reflow/tui.json if it's there
        .stage                                      # request | datasheet | plan | rules | design | check
        .start(request, part_numbers)               # the user's own words and part numbers
        .add_datasheet(pdf) -> Path                 # copied into root
        .draft_plan(model, answers=None) -> Draft   # planner prompt; answers are {question id: text}
        .accept_plan(draft)                         # writes spec.json + plan.json, unconfirmed
        .symbol_candidates(mpn) -> [lib_id]         # KiCad symbols whose name starts that part number
        .write_rules_template(symbol) -> Path       # rules.toml with [[part]] only; never overwrites
        .check_rules() -> RulesCheck
        .confirm()                                  # the user's yes; refused unless rules.toml checks clean
        .next_run_dir() -> Path / .design_command(run_dir) -> (argv, env) / .record_run(run_dir)
        .run_result(run_dir) -> RunResult | None / .check_run(run_dir) -> dict
        .add_fix(run_dir, text)                     # the user's fix, as a spec constraint for the next run

The flow, in the order the TUI shows it:

1. The user types the request and the exact part number(s). Those strings,
   and only those, become `Spec.named_parts` (AGENTS.md rule 5): whatever
   the planner puts in `named_parts` is replaced, and a plan part with any
   other `mpn` is refused (`reject_foreign_mpn`).
2. The datasheet must be a PDF (it starts with `%PDF`). It's copied into the
   project folder, where the agent (reflow.tui.agent, Read only) can read it.
3. The planner prompt (the one with the `{request}` placeholder) drafts the spec and plan. Its
   open questions go to the user; their answers go back to the planner and
   stay in `Spec.open_questions`. `Spec.request` stays the user's words.
4. rules.toml is the user's verifier. reflow writes only the `[[part]]` table
   (the typed part number and the KiCad symbol the user picked) and commented
   examples; it never overwrites the file. `check_rules` runs the same checks
   as `reflow rules check`, and a file with no `[[rule]]` is an error.
5. `confirm` is the only place `Spec.confirmed` becomes true, and only with a
   plan accepted and rules.toml at 0 errors.
6. A design is `reflow design --spec --plan --run-dir runs/NN-<title>` as a
   child process, on Claude Code unless REFLOW_PROVIDER is set.
7. A fix is the user's own sentence, added to `Spec.constraints` as
   "Designer's fix after <run>: ..." for the next run. The loop itself
   (reflow/harness/loop.py) is unchanged: each run starts fresh.

State lives in root/.reflow/tui.json, so closing and reopening the TUI
continues where the user was.

Must never
----------
- put a part number in the spec or plan that the user didn't type,
- write rules for the user, or overwrite their rules.toml,
- confirm the spec on its own, or run a design before the user confirms.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tomllib
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from reflow.checkpoint import CheckpointError, reject_foreign_mpn
from reflow.contracts import ContractError, OpenQuestion, Plan, RunResult, Spec, from_dict, to_dict
from reflow.harness.feedback import fill, load_prompt
from reflow.project_rules import RulesCheck, RulesFileError, check_rules, load_rules, pin_maps_from_parts

PLAN_SYSTEM = "Follow the user message. Reply with JSON only."
STAGES = ("request", "datasheet", "plan", "rules", "design", "check")
_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_TOP_SYMBOL = re.compile(r'^\t\(symbol "([^"]+)"', re.MULTILINE)


class ProjectError(ValueError):
    """The user's next step can't happen yet; the message says why."""


@dataclass
class State:
    request: str = ""
    part_numbers: list[str] = field(default_factory=list)
    datasheet: str = ""
    stage: str = "request"
    questions: list[dict] = field(default_factory=list)
    runs: list[str] = field(default_factory=list)
    fixes: list[dict] = field(default_factory=list)
    chat_session: str = ""
    chat_started: bool = False


@dataclass
class Draft:
    spec: Spec
    plan: Plan


class Project:
    def __init__(self, root) -> None:
        self.root = Path(root).resolve()
        self.state_path = self.root / ".reflow" / "tui.json"
        self.spec_path, self.plan_path = self.root / "spec.json", self.root / "plan.json"
        self.rules_path, self.runs_dir = self.root / "rules.toml", self.root / "runs"
        self.state = State()
        if self.state_path.is_file():
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.state = State(**{k: v for k, v in data.items() if k in State.__dataclass_fields__})

    @property
    def stage(self) -> str:
        return self.state.stage

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(asdict(self.state), indent=2) + "\n", encoding="utf-8")

    def _go(self, stage: str) -> None:
        self.state.stage = stage
        self.save()

    # --- 1. request and datasheet -------------------------------------------

    def start(self, request: str, part_numbers: list[str]) -> None:
        request = request.strip()
        typed = [p.strip() for p in part_numbers if p.strip()]
        if not request:
            raise ProjectError("type what you want to build")
        if not typed:
            raise ProjectError("type the exact part number of the main chip (reflow never picks one for you)")
        self.state.request, self.state.part_numbers = request, typed
        self._go("datasheet")

    def add_datasheet(self, pdf) -> Path:
        source = Path(str(pdf).strip().strip("'\"")).expanduser()
        if not source.is_file():
            raise ProjectError(f"{source} isn't a file")
        with source.open("rb") as f:
            if f.read(5) != b"%PDF-":
                raise ProjectError(f"{source.name} isn't a PDF")
        dest = self.root / source.name
        if source.resolve() != dest.resolve():
            shutil.copyfile(source, dest)
        self.state.datasheet = dest.name
        self._go("plan")
        return dest

    # --- 2. plan ----------------------------------------------------------------

    def draft_plan(self, model, answers: dict[str, str] | None = None) -> Draft:
        answered = [dict(q, answer=(answers or {}).get(q["id"], q.get("answer", "")).strip())
                    for q in self.state.questions]
        answered = [q for q in answered if q["answer"]]
        request = self.state.request
        if answered:
            request += "\n\nThe designer's answers to your open questions:\n" + "\n".join(
                f"- {q['question']} {q['answer']}" for q in answered)
        completion = model.complete(PLAN_SYSTEM, fill(load_prompt("{request}"), {"request": request}))
        spec, plan = _parse_draft(completion.text)
        known = {q["question"] for q in answered}
        merged = answered + [to_dict(q) for q in spec.open_questions if q.question not in known]
        questions = [OpenQuestion(id=f"q{n}", question=q["question"], answer=q.get("answer", ""))
                     for n, q in enumerate(merged, 1)]
        spec = replace(spec, request=self.state.request, named_parts=list(self.state.part_numbers),
                       open_questions=questions, confirmed=False, rules_file="rules.toml")
        try:
            reject_foreign_mpn(plan, spec)
        except CheckpointError as exc:
            raise ProjectError(str(exc)) from exc
        self.state.questions = [to_dict(q) for q in questions]
        self.save()
        return Draft(spec, plan)

    def accept_plan(self, draft: Draft) -> None:
        _write_json(self.spec_path, to_dict(replace(draft.spec, confirmed=False)))
        _write_json(self.plan_path, to_dict(draft.plan))
        self._go("rules")

    # --- 3. the user's rules --------------------------------------------------

    def symbol_candidates(self, mpn: str) -> list[str]:
        from reflow.parts.pinmap import PinMapError, _kicad_dir

        try:
            folder = _kicad_dir(None)
        except PinMapError:
            return []
        wanted, found = mpn.strip().upper(), []
        for lib in sorted(folder.glob("*.kicad_sym")):
            for name in _TOP_SYMBOL.findall(lib.read_text(encoding="utf-8", errors="replace")):
                stem = re.split(r"[_\-]", name)[0].upper()
                if len(stem) >= 4 and wanted.startswith(stem):
                    found.append((len(stem), f"{lib.stem}:{name}"))
        return [lib_id for _, lib_id in sorted(found, key=lambda item: (-item[0], item[1]))]

    def write_rules_template(self, symbol: str) -> Path:
        if self.rules_path.exists():
            raise ProjectError("rules.toml exists already; reflow never overwrites your rules")
        parts = []
        for n, mpn in enumerate(self.state.part_numbers, 1):
            parts += ["[[part]]", f'ref    = "U{n}"', f'mpn    = "{mpn}"']
            if n == 1 and symbol.strip():
                parts.append(f'symbol = "{symbol.strip()}"')
            parts.append("")
        text = "\n".join([
            "# rules.toml: your verifier for this board. You write the rules; reflow checks them.",
            "# One [[rule]] for each thing the datasheet asks for. `why` is your own sentence, `source` its page.",
            "# Stuck? Ask the agent in the TUI to walk you through the datasheet.",
            "",
            *parts,
            "# Example (remove the # signs to use it):",
            "# [[rule]]",
            '# on     = "U1.VDD"        # part reference + pin name from the datasheet\'s pin table',
            '# need   = "cap"           # cap | pullup | pulldown | tie | open | connected',
            '# to     = "GND"           # the net on the other side (cap, pullup, pulldown, tie)',
            '# value  = "100nF..1uF"    # optional: a value or range the datasheet gives',
            '# source = "<part> datasheet <revision>, <section>, p.<page>"',
            '# why    = "<your own one-sentence reason>"',
            "",
        ])
        self.rules_path.write_text(text, encoding="utf-8")
        return self.rules_path

    def check_rules(self) -> RulesCheck:
        if not self.rules_path.is_file():
            raise ProjectError("there's no rules.toml yet; create it from the template, then write your rules")
        try:
            data = tomllib.loads(self.rules_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            return RulesCheck(rules=0, errors=[f"rules.toml isn't valid TOML ({exc})"])
        if not data.get("rule"):
            return RulesCheck(rules=0, errors=["rules.toml has no [[rule]] yet. Write at least one: "
                                               "what does the datasheet ask for?"])
        try:
            rules = load_rules(self.rules_path)
        except RulesFileError as exc:
            return RulesCheck(rules=0, errors=[str(exc)])
        from reflow.parts.pinmap import PinMapError

        try:
            pin_maps, warnings = pin_maps_from_parts(rules)
        except PinMapError as exc:
            return RulesCheck(rules=len(rules.rule), errors=[f"pin map: {exc}"])
        result = check_rules(rules, pin_maps)
        result.warnings = warnings + result.warnings
        return result

    def confirm(self) -> None:
        if not self.spec_path.is_file() or not self.plan_path.is_file():
            raise ProjectError("accept a plan first")
        result = self.check_rules()
        if result.errors:
            raise ProjectError(f"rules.toml has {len(result.errors)} error(s); fix them first")
        spec = self._spec()
        _write_json(self.spec_path, to_dict(replace(spec, confirmed=True, rules_file="rules.toml")))
        self._go("design")

    # --- 4. design, check, fix ------------------------------------------------

    def next_run_dir(self) -> Path:
        title = self._spec().title if self.spec_path.is_file() else self.state.request
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "board"
        n = len(self.state.runs) + 1
        while (path := self.runs_dir / f"{n:02d}-{slug}").exists() or path.name in self.state.runs:
            n += 1
        return path

    def design_command(self, run_dir: Path) -> tuple[list[str], dict[str, str]]:
        argv = [sys.executable, "-m", "reflow", "design", "--spec", str(self.spec_path),
                "--plan", str(self.plan_path), "--run-dir", str(run_dir)]
        env = dict(os.environ)
        env.setdefault("REFLOW_PROVIDER", "claude-code")
        return argv, env

    def record_run(self, run_dir: Path) -> None:
        if Path(run_dir).name not in self.state.runs:
            self.state.runs.append(Path(run_dir).name)
        self._go("check")

    def run_result(self, run_dir: Path) -> RunResult | None:
        path = Path(run_dir) / "run.json"
        if not path.is_file():
            return None
        return from_dict(RunResult, json.loads(path.read_text(encoding="utf-8")))

    def check_run(self, run_dir: Path) -> dict:
        run = self.run_result(run_dir)
        if run is None or run.best_attempt == 0:
            raise ProjectError("no attempt compiled, so there's no board to check")
        from reflow.schematic import schematic_report

        return schematic_report(run_dir)

    def add_fix(self, run_dir: Path, text: str) -> None:
        text = " ".join(text.split())
        if not text:
            raise ProjectError("the fix is empty; say what the agent should change")
        name = Path(run_dir).name
        spec = self._spec()
        _write_json(self.spec_path, to_dict(replace(
            spec, constraints=[*spec.constraints, f"Designer's fix after {name}: {text}"])))
        self.state.fixes.append({"after": name, "text": text})
        self._go("design")

    def _spec(self) -> Spec:
        return from_dict(Spec, json.loads(self.spec_path.read_text(encoding="utf-8")))


def _parse_draft(text: str) -> tuple[Spec, Plan]:
    spec = plan = None
    problems = []
    for body in _FENCE.findall(text):
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        cls = Spec if "request" in data or "named_parts" in data else Plan
        try:
            obj = from_dict(cls, data)
        except ContractError as exc:
            problems.append(f"{cls.__name__}: {exc}")
            continue
        if cls is Spec and spec is None:
            spec = obj
        elif cls is Plan and plan is None:
            plan = obj
    if spec is None or plan is None:
        detail = "; ".join(problems) or "the reply had no spec and plan JSON"
        raise ProjectError(f"the planner's reply wasn't a valid spec and plan ({detail}); try again")
    return spec, plan


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
