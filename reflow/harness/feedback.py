"""Violation and compile-error conversion. Policy from H-00 / D-3.

`to_feedback` builds a `RetryFeedback` contract object. `render_feedback`
fills the compact-text prompt into the text the model sees. The on-disk
object stays JSON; this module does not change that schema.

Must never
----------
- call a model, the compiler, learn mode, or the router
- copy the human-only explanation field onto a feedback object or into text
- read a KiCad file, or place a schematic/board body in the rendered text
- send more than the first compile error
"""
from __future__ import annotations

import re
from pathlib import Path

from reflow.contracts import (
    CompileResult,
    FeedbackViolation,
    RetryFeedback,
    VerifyReport,
)

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_RULE_BLOCK = re.compile(
    r"rule_id: \{rule_id\}\n"
    r"severity: \{severity\}\n"
    r"refs: \{refs\}\n"
    r"nets: \{nets\}\n"
    r"message: \{message\}\n"
    r"fix_hint: \{fix_hint\}\n"
)
_DRAFT_PREFIX = "<!-- draft:"


def to_feedback(
    source: VerifyReport | CompileResult,
    *,
    attempt: int,
    max_attempts: int,
    history: list[str],
) -> RetryFeedback:
    """Copy the fields the model is allowed to see.

    A verify report becomes `kind="verify"` and keeps every violation's
    rule, severity, message, fix hint, refs, and nets. A compile result
    becomes `kind="compile"` and keeps only the first `CompileError`.
    """
    prior = list(history)
    if isinstance(source, VerifyReport):
        violations = [
            FeedbackViolation(
                rule_id=item.rule_id,
                severity=item.severity,
                message=item.message,
                fix_hint=item.fix_hint,
                refs=list(item.refs),
                nets=list(item.nets),
            )
            for item in source.violations
        ]
        return RetryFeedback(
            kind="verify",
            attempt=attempt,
            max_attempts=max_attempts,
            history=prior,
            violations=violations,
            compile_errors=[],
        )
    if isinstance(source, CompileResult):
        return RetryFeedback(
            kind="compile",
            attempt=attempt,
            max_attempts=max_attempts,
            history=prior,
            violations=[],
            compile_errors=list(source.errors[:1]),
        )
    raise TypeError(f"expected VerifyReport or CompileResult, got {type(source).__name__}")


def render_feedback(feedback: RetryFeedback, tsx: str) -> str:
    """Fill the compact-text prompt. The rule block repeats once per violation."""
    template = load_prompt("{compile_line}")
    match = _RULE_BLOCK.search(template)
    if match is None:
        raise RuntimeError("compact-text template is missing the rule_id block")
    if feedback.kind == "compile" or not feedback.violations:
        rendered_rules = ""
    else:
        pieces = [
            fill(match.group(0), {
                "rule_id": item.rule_id,
                "severity": item.severity,
                "refs": ", ".join(item.refs),
                "nets": ", ".join(item.nets),
                "message": item.message,
                "fix_hint": item.fix_hint,
            })
            for item in feedback.violations
        ]
        rendered_rules = "".join(pieces)
    outer = template[:match.start()] + "{rule_block}" + template[match.end():]
    error = feedback.compile_errors[0] if feedback.compile_errors else None
    return fill(outer, {
        "attempt": str(feedback.attempt),
        "max_attempts": str(feedback.max_attempts),
        "history": "\n".join(feedback.history),
        "rule_block": rendered_rules,
        "compile_line": "" if error is None else str(error.line),
        "compile_message": "" if error is None else error.message,
        "tsx": tsx,
    })


def load_prompt(marker: str) -> str:
    """Read the prompts file that contains `marker`. The draft banner is dropped.

    Callers pass a placeholder that only one template uses. The draft
    filenames are not spelled here.
    """
    directory = Path(__file__).resolve().parents[2] / "prompts"
    matches = [
        path for path in sorted(directory.glob("*.md"))
        if path.name != "README.md" and marker in path.read_text(encoding="utf-8")
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one prompt containing {marker}, found {len(matches)}")
    path = matches[0]
    text = path.read_text(encoding="utf-8")
    if text.startswith(_DRAFT_PREFIX):
        newline = text.find("\n")
        text = text[newline + 1:] if newline != -1 else ""
        if text.startswith("\n"):
            text = text[1:]
    return text


def fill(template: str, values: dict[str, str]) -> str:
    """Replace `{name}` placeholders. Other braces are left as written."""
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in values:
            return values[key]
        return match.group(0)
    return _PLACEHOLDER.sub(replace, template)
