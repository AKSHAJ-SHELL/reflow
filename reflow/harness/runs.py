"""Run-folder I/O. OWNER: AGENT (task H-05).

Contract
--------
create_run(run_dir, run) -> RunStore
    Create ``run_dir`` (the ``runs/<id>/`` folder) and write ``run.json``.
    Refuses when that directory already contains anything.

Each RunStore method writes one artifact, then rewrites ``run.json``.
The caller passes contract objects, including the ``RunResult`` to store.
After a completed step, ``run.json`` parses with ``from_dict(RunResult, ...)``.

    write_spec(spec, run) -> spec.json
    write_plan(plan, run) -> plan.json
    write_parts(parts, run) -> parts.json
    write_prompt(attempt, text, run) -> attempts/NN/prompt.md
    write_response(attempt, text, run) -> attempts/NN/response.md
    write_tsx(attempt, code, run) -> attempts/NN/index.circuit.tsx
    write_compile(attempt, compile_try, result, run) -> attempts/NN/compile-N.json
    write_verify(attempt, report, run) -> attempts/NN/verify.json
    write_feedback(attempt, feedback, run) -> attempts/NN/feedback.json
    write_run(run) -> run.json

Every write is atomic: a temp file in the destination's directory, then
``os.replace``. A step that fails before replace leaves that new file absent.
Rewriting ``run.json`` the same way leaves the previous snapshot in place
when the replace does not happen.

Must never
----------
- continue a folder that already has files, or expose a resume command
- choose ``best_attempt`` or ``RunResult.status``
- build feedback from a violation; the caller passes both objects
- read an MPN or LCSC id out of prompt, response, or TSX text
- write outside ``run_dir``
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from reflow.contracts import (
    CompileResult,
    GeneratedCode,
    Plan,
    ResolvedParts,
    RetryFeedback,
    RunResult,
    Spec,
    VerifyReport,
    to_dict,
)


class RunExistsError(FileExistsError):
    """``run_dir`` already has files. This module does not continue it."""


class RunStore:
    """One ``runs/<id>/`` directory. Holds no policy, only files."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write_spec(self, spec: Spec, run: RunResult) -> None:
        _require(spec, Spec)
        self._commit("spec.json", _json_bytes(spec), run)

    def write_plan(self, plan: Plan, run: RunResult) -> None:
        _require(plan, Plan)
        self._commit("plan.json", _json_bytes(plan), run)

    def write_parts(self, parts: ResolvedParts, run: RunResult) -> None:
        _require(parts, ResolvedParts)
        self._commit("parts.json", _json_bytes(parts), run)

    def write_prompt(self, attempt: int, text: str, run: RunResult) -> None:
        self._commit(f"attempts/{_attempt_segment(attempt)}/prompt.md", _text_bytes(text), run)

    def write_response(self, attempt: int, text: str, run: RunResult) -> None:
        self._commit(f"attempts/{_attempt_segment(attempt)}/response.md", _text_bytes(text), run)

    def write_tsx(self, attempt: int, code: GeneratedCode, run: RunResult) -> None:
        _require(code, GeneratedCode)
        # The TSX is stored verbatim. Nothing here is parsed into a part id.
        self._commit(
            f"attempts/{_attempt_segment(attempt)}/index.circuit.tsx",
            _text_bytes(code.tsx),
            run,
        )

    def write_compile(
        self, attempt: int, compile_try: int, result: CompileResult, run: RunResult,
    ) -> None:
        _require(result, CompileResult)
        n = _positive_int(compile_try, "compile_try")
        self._commit(
            f"attempts/{_attempt_segment(attempt)}/compile-{n}.json",
            _json_bytes(result),
            run,
        )

    def write_verify(self, attempt: int, report: VerifyReport, run: RunResult) -> None:
        _require(report, VerifyReport)
        self._commit(f"attempts/{_attempt_segment(attempt)}/verify.json", _json_bytes(report), run)

    def write_feedback(self, attempt: int, feedback: RetryFeedback, run: RunResult) -> None:
        _require(feedback, RetryFeedback)
        self._commit(
            f"attempts/{_attempt_segment(attempt)}/feedback.json",
            _json_bytes(feedback),
            run,
        )

    def write_run(self, run: RunResult) -> None:
        """Rewrite run.json. The caller chooses status and best_attempt."""
        _require(run, RunResult)
        _atomic_write(self._destination("run.json"), _json_bytes(run))

    def _commit(self, relative: str, data: bytes, run: RunResult) -> None:
        _require(run, RunResult)
        _atomic_write(self._destination(relative), data)
        _atomic_write(self._destination("run.json"), _json_bytes(run))

    def _destination(self, relative: str) -> Path:
        parts = Path(relative).parts
        if not parts or any(part in ("", ".", "..") for part in parts):
            raise ValueError(f"refusing to write outside the run folder: {relative}")
        root = self.path.resolve()
        dest = (self.path / relative).resolve()
        if root not in dest.parents:
            raise ValueError(f"refusing to write outside the run folder: {dest}")
        return dest


def create_run(run_dir: Path, run: RunResult) -> RunStore:
    """Create ``run_dir`` and write the initial ``run.json``."""
    _require(run, RunResult)
    path = Path(run_dir)
    if path.exists():
        if not path.is_dir():
            raise RunExistsError(f"{path} exists and is not a directory")
        if any(path.iterdir()):
            raise RunExistsError(f"{path} already has files; refusing to continue it")
    path.mkdir(parents=True, exist_ok=True)
    store = RunStore(path)
    _atomic_write(store._destination("run.json"), _json_bytes(run))
    return store


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _json_bytes(obj: object) -> bytes:
    text = json.dumps(to_dict(obj), indent=2, ensure_ascii=False) + "\n"
    return text.encode("utf-8")


def _text_bytes(text: str) -> bytes:
    if type(text) is not str:
        raise TypeError(f"expected str, got {type(text).__name__}")
    return text.encode("utf-8")


def _require(obj: object, cls: type) -> None:
    if not isinstance(obj, cls):
        raise TypeError(f"expected {cls.__name__}, got {type(obj).__name__}")


def _attempt_segment(attempt: int) -> str:
    return f"{_positive_int(attempt, 'attempt'):02d}"


def _positive_int(value: int, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} must be a positive int, got {value!r}")
    return value
