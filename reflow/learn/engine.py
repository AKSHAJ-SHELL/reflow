"""What to teach from a run, and how to grade it.  Task L-01, written by the agent under O-1c; the human reviews it.

Contract
--------
    load_run(run_dir) -> RunView
    pick(run, *, skip=(), limit=3) -> Selection
    grade(pending, ref, why, *, tries, hinted) -> Graded
    concept_of(rule_id) -> str

`load_run` resolves a relative `Spec.rules_file` against the run folder.

Spot-the-bug only (DECISIONS D-4, L-2 phase 1). Interactions come from the
violations of the run's **first failed attempt** (the first compiled attempt
with verify errors), never from a question bank:

- one interaction per concept (`concept_of`), in the report's order, at most
  `limit`;
- **root cause first:** a part with a `pinout.mismatch` gets that interaction,
  and the attempt's other errors that point at the same part are left out as
  consequences of the wrong labels (a real run reported `decoupling.missing`
  on a GND pin the model had labelled SCL). Each one left out is named in
  `notes`;
- the right answer is the violation's refs; a violation with no refs (e.g.
  `i2c.missing_pullup`) is answered by any part on its nets in that attempt's
  circuit.json;
- a concept in `skip` (known, from the learner model) is left out and listed
  in `skipped`, so the UI can show it.

The prompt never names the part or the rule. The hint names the area to look
at, never the part.

Grading is by the part clicked (case and spaces ignored). The free-text why
is recorded and shown next to the right answer, not graded (L-2 interim
answer). Wrong answers teach, never block: a wrong first click returns the
hint and one more try; a wrong second click shows the answer and moves on.
Ratings for the learner model: right on the first try without the hint is
"good"; right with the hint or on the second try is "hard"; wrong twice is
"again".

Must never
----------
- invent an interaction that isn't a violation the run reported,
- show the answer, the rule or the part before the user commits,
- block the user or ask until they get it right.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from reflow.circuit_netlist import CircuitJsonError, load_circuit_json
from reflow.contracts import LearnInteraction, Plan, ResolvedParts, RunResult, Spec, VerifyReport, from_dict

_CONCEPTS = {
    "decoupling": "decoupling",
    "i2c": "i2c-pullup",
    "address": "address-strap",
    "pinout": "pinout",
    "led": "led-current-limit",
}
_HINTS = {
    "pinout": "Compare how the chip's pins are labelled in this draft with the pin table in its datasheet.",
    "decoupling": "Look at how each chip's supply pins connect to ground.",
    "i2c-pullup": "Follow the I²C data and clock lines: what pulls them high when nothing drives them low?",
    "address-strap": "Look at the chip's address pins: what are they connected to?",
    "led-current-limit": "Follow the current through the LED: what limits it?",
}
_PROMPT = ("The AI's first draft (attempt {attempt}) failed a check. Click the part that causes the problem, "
           "then say in one sentence what's wrong.")


@dataclass
class AttemptView:
    number: int
    compiled: bool
    verify: VerifyReport | None
    circuit_json: Path | None


@dataclass
class RunView:
    path: Path
    spec: Spec
    plan: Plan | None
    parts: ResolvedParts | None
    result: RunResult
    attempts: list[AttemptView]

    @property
    def best_attempt(self) -> int:
        return self.result.best_attempt


@dataclass
class Pending:
    id: str
    kind: str
    concept: str
    rule_id: str
    attempt: int
    prompt: str
    hint: str
    answer_refs: list[str]
    nets: list[str]
    message: str
    why: str
    fix_hint: str


@dataclass
class Selection:
    interactions: list[Pending]
    skipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class Graded:
    outcome: str                         # "correct" | "try_again" | "wrong"
    rating: str | None                   # "good" | "hard" | "again"; None while a try is left
    interaction: LearnInteraction | None  # set once the interaction is finished
    hint: str = ""
    answer_refs: list[str] = field(default_factory=list)
    why: str = ""
    fix_hint: str = ""
    message: str = ""


def concept_of(rule_id: str) -> str:
    family = rule_id.split(".", 1)[0]
    if family == "project":
        return "project-" + rule_id.split(".", 1)[1]
    return _CONCEPTS.get(family, family)


def load_run(run_dir) -> RunView:
    path = Path(run_dir)
    result = from_dict(RunResult, _json(path / "run.json"))
    attempts = []
    for record in result.attempts:
        folder = path / "attempts" / f"{record.attempt:02d}"
        verify = folder / "verify.json"
        circuit = folder / "build" / "circuit.json"
        attempts.append(AttemptView(
            number=record.attempt,
            compiled=record.compiled,
            verify=from_dict(VerifyReport, _json(verify)) if verify.is_file() else None,
            circuit_json=circuit if circuit.is_file() else None,
        ))
    spec = from_dict(Spec, _json(path / "spec.json"))
    if spec.rules_file.strip() and not Path(spec.rules_file).is_absolute():
        spec = replace(spec, rules_file=str((path / spec.rules_file).resolve()))
    return RunView(
        path=path,
        spec=spec,
        plan=from_dict(Plan, _json(path / "plan.json")) if (path / "plan.json").is_file() else None,
        parts=from_dict(ResolvedParts, _json(path / "parts.json")) if (path / "parts.json").is_file() else None,
        result=result,
        attempts=attempts,
    )


def pick(run: RunView, *, skip=(), limit: int = 3) -> Selection:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    failed = next((a for a in run.attempts if a.compiled and a.verify and a.verify.errors), None)
    if failed is None:
        if not any(a.compiled for a in run.attempts):
            return Selection([], reason="no attempt compiled, so there's no draft to look at")
        return Selection([], reason="the AI's first draft passed every check, so there's no bug to spot")

    errors = [v for v in failed.verify.violations if v.severity == "error"]
    nets = _parts_on_nets(failed.circuit_json)
    mislabelled = {ref for v in errors if v.rule_id.startswith("pinout.") for ref in v.refs}
    ordered = [v for v in errors if v.rule_id.startswith("pinout.")] + [v for v in errors if not v.rule_id.startswith("pinout.")]

    selection = Selection([])
    seen: set[str] = set()
    for index, violation in enumerate(ordered, 1):
        concept = concept_of(violation.rule_id)
        answer = sorted(set(violation.refs)) or sorted({r for net in violation.nets for r in nets.get(net, ())})
        if not answer:
            selection.notes.append(f"left out {violation.rule_id}: it names no part and its nets have none to click")
            continue
        if not violation.rule_id.startswith("pinout.") and set(answer) & mislabelled:
            parts = ", ".join(sorted(set(answer) & mislabelled))
            selection.notes.append(f"left out {violation.rule_id} on {parts}: a consequence of {parts}'s wrong pin labels")
            continue
        if concept in seen:
            continue
        seen.add(concept)
        if concept in skip:
            selection.skipped.append(concept)
            continue
        if len(selection.interactions) >= limit:
            continue
        selection.interactions.append(Pending(
            id=f"a{failed.number}-{index}",
            kind="spot_bug",
            concept=concept,
            rule_id=violation.rule_id,
            attempt=failed.number,
            prompt=_PROMPT.format(attempt=failed.number),
            hint=_HINTS.get(concept, "Look for what this kind of check looks for on the board."),
            answer_refs=answer,
            nets=list(violation.nets),
            message=violation.message,
            why=violation.why,
            fix_hint=violation.fix_hint,
        ))
    if not selection.interactions and not selection.reason:
        selection.reason = "nothing left to ask: every concept on this board is known, or had no part to click"
    return selection


def grade(pending: Pending, ref: str, why: str, *, tries: int, hinted: bool) -> Graded:
    clicked = ref.strip()
    right = clicked.upper() in {r.upper() for r in pending.answer_refs}
    reveal = dict(answer_refs=list(pending.answer_refs), why=pending.why, fix_hint=pending.fix_hint,
                  message=pending.message)
    if not right and tries < 2:
        return Graded("try_again", None, None, hint=pending.hint)
    rating = ("good" if tries == 1 and not hinted else "hard") if right else "again"
    answer = f"{clicked}: {why.strip()}" if why.strip() else clicked
    record = LearnInteraction(
        kind=pending.kind, concept=pending.concept, rule_id=pending.rule_id, prompt=pending.prompt,
        user_answer=answer, correct=right, explanation=pending.why,
    )
    return Graded("correct" if right else "wrong", rating, record, hint=pending.hint, **reveal)


def _parts_on_nets(circuit_json: Path | None) -> dict[str, set[str]]:
    if circuit_json is None:
        return {}
    try:
        netlist = load_circuit_json(circuit_json)
    except CircuitJsonError:
        return {}
    return {name: {pin.ref for pin in pins} for name, pins in netlist.nets.items()}


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
