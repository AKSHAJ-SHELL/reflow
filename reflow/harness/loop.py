"""Design loop and termination. Policy is the accepted H-00 text.

Design attempts stop at `max_attempts` (default 3). Compile tries stop at
`compile_cap` (default 2) and do not increment the design attempt. A missing
code fence is a compile try. `best_attempt` is the compiled attempt with the
fewest errors, then the fewest warnings, then the latest number, or 0 when
nothing compiled.

The next codegen file is the best-so-far TSX only when the latest compiled
attempt has strictly more errors. Equal errors continue from the latest TSX.
Identical error rule ids and refs are logged and do not stop the run.

Must never
----------
- import an SDK, learn mode, the router, or a verifier rule
- read a KiCad file into a prompt
- let model text become a part number (the plan gate rejects a foreign mpn)
- invent a second stop rule beyond pass, compile cap, or abort
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from reflow.checkpoint import CheckpointError, reject_foreign_mpn
from reflow.codefence import extract_code_fence
from reflow.contracts import (
    AttemptRecord,
    CompileError,
    CompileResult,
    ContractError,
    GeneratedCode,
    Plan,
    ResolvedParts,
    RunResult,
    Spec,
    VerifyReport,
    from_dict,
)
from reflow.harness.feedback import fill, load_prompt, render_feedback, to_feedback
from reflow.harness.runs import RunStore, create_run
from reflow.llm import Model, ModelError

_CODEGEN_SYSTEM = "Follow the user message. Return one tsx code fence and no other fence."
_PLAN_SYSTEM = "Follow the user message. Reply with JSON only."
_PLAN_REPROMPT = (
    "The previous reply was not a valid Plan ({error}). "
    "Reply with one json fence that is only the Plan."
)
_FENCE_BODY = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


@dataclass
class _Board:
    attempt: int
    errors: int
    warnings: int
    tsx: str


def pick_best(attempts: list[AttemptRecord]) -> int:
    """1-based compiled attempt: fewest errors, then warnings, then latest."""
    compiled = [item for item in attempts if item.compiled]
    if not compiled:
        return 0
    winner = min(compiled, key=lambda item: (item.errors, item.warnings, -item.attempt))
    return winner.attempt


def run_design(
    spec: Spec,
    plan: Plan | None,
    parts: ResolvedParts,
    *,
    model: Model,
    compiler: Callable[[str, Path], CompileResult],
    verifier: Callable[[str, ResolvedParts, Spec], VerifyReport],
    run_dir: Path,
    max_attempts: int = 3,
    compile_cap: int = 2,
) -> RunResult:
    """Run one design folder. Callers pass caps from config; defaults match it."""
    folder = Path(run_dir)
    run = RunResult(
        run_id=folder.name,
        status="failed_compile",
        attempts=[],
        best_attempt=0,
        run_dir=str(folder),
    )
    store = create_run(folder, run)
    store.write_spec(spec, run)

    if spec.confirmed is not True:
        return _abort(store, run, "spec is not confirmed; nothing downstream runs")
    if parts.unresolved:
        store.write_parts(parts, run)
        reason = "; ".join(item.reason for item in parts.unresolved if item.reason)
        return _abort(store, run, reason or "unresolved parts")
    if plan is None:
        plan = _plan_from_model(model, spec, store, run)
        if plan is None:
            return _abort(store, run, "plan was not valid Plan JSON after one re-prompt")
    else:
        try:
            reject_foreign_mpn(plan, spec)
        except CheckpointError as exc:
            return _abort(store, run, str(exc))

    store.write_plan(plan, run)
    store.write_parts(parts, run)
    return _design_attempts(
        spec, plan, parts,
        model=model,
        compiler=compiler,
        verifier=verifier,
        store=store,
        run=run,
        max_attempts=max_attempts,
        compile_cap=compile_cap,
    )


def _abort(store: RunStore, run: RunResult, reason: str) -> RunResult:
    run.status = "aborted"
    run.best_attempt = 0
    run.abort_reason = reason
    store.write_run(run)
    return run


def _plan_from_model(model: Model, spec: Spec, store: RunStore, run: RunResult) -> Plan | None:
    base = fill(load_prompt("{request}"), {"request": spec.request})
    error = "not a Plan"
    for index in range(2):
        prompt = base if index == 0 else base + "\n" + _PLAN_REPROMPT.format(error=error)
        try:
            completion = model.complete(_PLAN_SYSTEM, prompt)
        except ModelError:
            run.status = "aborted"
            run.abort_reason = "model error during planning"
            store.write_run(run)
            raise
        run.input_tokens += completion.input_tokens
        run.output_tokens += completion.output_tokens
        try:
            return _parse_plan(completion.text, spec)
        except (ContractError, CheckpointError, ValueError) as exc:
            error = str(exc)
    return None


def _parse_plan(text: str, spec: Spec) -> Plan:
    found: list[dict] = []
    blobs = [text, *_FENCE_BODY.findall(text)]
    for blob in blobs:
        start = blob.find("{")
        end = blob.rfind("}")
        raws = [blob.strip()]
        if start != -1 and end > start:
            raws.append(blob[start:end + 1])
        for raw in raws:
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                found.append(data)
    if not found:
        raise ContractError("plan JSON was not a Plan")
    last = "plan JSON was not a Plan"
    for data in found:
        try:
            plan = from_dict(Plan, data)
        except ContractError as exc:
            last = str(exc)
            continue
        reject_foreign_mpn(plan, spec)
        return plan
    raise ContractError(last)


def _design_attempts(
    spec: Spec,
    plan: Plan,
    parts: ResolvedParts,
    *,
    model: Model,
    compiler: Callable[[str, Path], CompileResult],
    verifier: Callable[[str, ResolvedParts, Spec], VerifyReport],
    store: RunStore,
    run: RunResult,
    max_attempts: int,
    compile_cap: int,
) -> RunResult:
    records: list[AttemptRecord] = []
    boards: list[_Board] = []
    history: list[str] = []
    current_tsx = ""
    pending = None
    last_signature: tuple[frozenset[str], frozenset[str]] | None = None
    codegen = _codegen_text(spec, plan, parts)

    for attempt in range(1, max_attempts + 1):
        built = ""
        compile_result: CompileResult | None = None
        for compile_try in range(1, compile_cap + 1):
            use_fix = not (attempt == 1 and compile_try == 1)
            if use_fix:
                prompt = codegen + "\n\n" + render_feedback(pending, current_tsx)
            else:
                prompt = codegen
            store.write_prompt(attempt, prompt, run)
            try:
                completion = model.complete(_CODEGEN_SYSTEM, prompt)
            except ModelError:
                store.write_run(run)
                raise
            run.input_tokens += completion.input_tokens
            run.output_tokens += completion.output_tokens
            store.write_response(attempt, completion.text, run)

            tsx = extract_code_fence(completion.text)
            workdir = store.path / "attempts" / f"{attempt:02d}" / "build"
            if tsx is None:
                compile_result = CompileResult(
                    ok=False,
                    errors=[CompileError("model response contained no code fence")],
                    stderr_tail="",
                )
            else:
                built = tsx
                current_tsx = tsx
                store.write_tsx(attempt, GeneratedCode(
                    attempt=attempt,
                    compile_try=compile_try,
                    tsx=tsx,
                    model=completion.model,
                    input_tokens=completion.input_tokens,
                    output_tokens=completion.output_tokens,
                ), run)
                workdir.mkdir(parents=True, exist_ok=True)
                compile_result = compiler(tsx, workdir)
            store.write_compile(attempt, compile_try, compile_result, run)
            if compile_result.ok:
                break
            pending = to_feedback(
                compile_result,
                attempt=attempt,
                max_attempts=max_attempts,
                history=list(history),
            )
            store.write_feedback(attempt, pending, run)
        else:
            records.append(AttemptRecord(
                attempt=attempt,
                compile_tries=compile_try,
                compiled=False,
                errors=0,
                warnings=0,
                rule_ids=[],
                dir=f"{run.run_dir}/attempts/{attempt:02d}",
            ))
            run.attempts = list(records)
            run.best_attempt = pick_best(run.attempts)
            run.status = "failed_compile" if run.best_attempt == 0 else "failed_verify"
            store.write_run(run)
            return run

        assert compile_result is not None
        report = verifier(compile_result.kicad_sch, parts, spec)
        records.append(AttemptRecord(
            attempt=attempt,
            compile_tries=compile_try,
            compiled=True,
            errors=report.errors,
            warnings=report.warnings,
            rule_ids=[item.rule_id for item in report.violations],
            dir=f"{run.run_dir}/attempts/{attempt:02d}",
        ))
        run.attempts = list(records)
        run.best_attempt = pick_best(run.attempts)
        run.status = "passed" if report.errors == 0 else "failed_verify"
        store.write_verify(attempt, report, run)
        if report.errors == 0:
            store.write_run(run)
            return run

        previous = _best_board(boards)
        regressed = previous is not None and report.errors > previous.errors
        signature = _error_signature(report.violations)
        repeated = last_signature is not None and signature == last_signature
        history.append(_history_line(
            attempt, report.violations, regressed=regressed, repeated=repeated,
        ))
        boards.append(_Board(attempt, report.errors, report.warnings, built))
        if regressed and previous is not None:
            current_tsx = previous.tsx
        else:
            current_tsx = built
        last_signature = signature
        pending = to_feedback(
            report,
            attempt=attempt,
            max_attempts=max_attempts,
            history=list(history),
        )
        store.write_feedback(attempt, pending, run)

    store.write_run(run)
    return run


def _best_board(boards: list[_Board]) -> _Board | None:
    if not boards:
        return None
    return min(boards, key=lambda item: (item.errors, item.warnings, -item.attempt))


def _error_signature(violations: list) -> tuple[frozenset[str], frozenset[str]]:
    rules: list[str] = []
    refs: list[str] = []
    for item in violations:
        if item.severity != "error":
            continue
        rules.append(item.rule_id)
        refs.extend(item.refs)
    return frozenset(rules), frozenset(refs)


def _history_line(attempt: int, violations: list, *, regressed: bool, repeated: bool) -> str:
    bits: list[str] = []
    for item in violations:
        if item.severity != "error":
            continue
        refs = "/".join(item.refs)
        bits.append(f"{item.rule_id} {refs}".strip())
    body = ", ".join(bits) if bits else "verify failed"
    line = f"attempt {attempt}: {body}"
    if regressed:
        line += "; regressed"
    if repeated:
        line += "; same rule_ids and refs"
    return line


def _codegen_text(spec: Spec, plan: Plan, parts: ResolvedParts) -> str:
    return fill(load_prompt("{resolved_parts}"), {
        "spec": _render_spec(spec),
        "plan": _render_plan(plan),
        "resolved_parts": _render_parts(plan, parts),
    })


def _render_spec(spec: Spec) -> str:
    return "\n".join([
        f"request: {spec.request}",
        f"title: {spec.title}",
        f"power: {spec.power}",
        f"interfaces: {', '.join(spec.interfaces)}",
        f"constraints: {', '.join(spec.constraints)}",
        f"named_parts: {', '.join(spec.named_parts)}",
        f"confirmed: {'true' if spec.confirmed else 'false'}",
    ])


def _render_plan(plan: Plan) -> str:
    blocks = "; ".join(f"{block.name}: {block.purpose}" for block in plan.blocks)
    parts = [
        f"{part.id} {part.role} {part.category} {part.value} {part.package}"
        for part in plan.parts
    ]
    return "blocks: " + blocks + "\n" + "\n".join(parts) + "\nnets: " + ", ".join(plan.nets)


def _render_parts(plan: Plan, parts: ResolvedParts) -> str:
    roles = {part.id: part.role for part in plan.parts}
    lines = ["request_id\trole\tvalue\tpackage\tlcsc\tmpn"]
    for part in parts.resolved:
        lines.append("\t".join([
            part.request_id,
            roles.get(part.request_id, ""),
            part.value,
            part.package,
            part.lcsc,
            part.mpn,
        ]))
    return "\n".join(lines)
