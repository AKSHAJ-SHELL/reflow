"""Sign-off gate before fab files.  OWNER: AGENT (task L-03).

Contract
--------
    remaining_warnings(run_dir) -> list[str]            # "rule_id: message", the best attempt's verify warnings
    prompt_signoff(run_dir, *, stdin=sys.stdin, out=print) -> SignOff   # writes signoff.json
    signoff_refusals(run_dir) -> list[str]              # [] when an accepted sign-off covers the warnings now
    SignOffError                                        # no terminal, or no answer

docs/07-learn-mode.md: before any fab files, show the remaining warnings and
any overrides, then a single y/n, recorded in signoff.json and copied into the
report. The learn UI (`reflow learn`) writes the same signoff.json; the
terminal prompt here is for `reflow export`.

- `prompt_signoff` asks only on a terminal (`stdin.isatty()`), never assumes
  a yes, and asks again until the answer is y/yes or n/no. Both answers are
  recorded; end of input records nothing. The terminal prompt takes no
  overrides (`overrides=[]`).
- `signoff_refusals`: refused when there is no signoff.json, when it was
  declined, or when its acknowledged warnings differ from the warnings now
  (the person signed off on something else).

Must never
----------
- write a sign-off nobody typed,
- let an export through on a declined or stale sign-off.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from reflow.contracts import ContractError, RunResult, SignOff, Spec, VerifyReport, from_dict, to_dict

YES, NO = {"y", "yes"}, {"n", "no"}


class SignOffError(Exception):
    pass


def remaining_warnings(run_dir) -> list[str]:
    run_dir = Path(run_dir)
    run = _read(RunResult, run_dir / "run.json")
    if not run.best_attempt:
        return []
    verify = run_dir / "attempts" / f"{run.best_attempt:02d}" / "verify.json"
    if not verify.is_file():
        return []
    return [f"{v.rule_id}: {v.message}" for v in _read(VerifyReport, verify).violations if v.severity == "warning"]


def prompt_signoff(run_dir, *, stdin=None, out=print) -> SignOff:
    run_dir = Path(run_dir)
    stdin = sys.stdin if stdin is None else stdin
    if not stdin.isatty():
        raise SignOffError("sign-off needs a person at a terminal; run this in one, or sign off in "
                           f"`reflow learn {run_dir}`")
    run = _read(RunResult, run_dir / "run.json")
    spec = _read(Spec, run_dir / "spec.json")
    warnings = remaining_warnings(run_dir)
    out(f"Sign-off: {spec.title} (run {run.run_id}, attempt {run.best_attempt})")
    out("Remaining warnings: " + ("none" if not warnings else ""))
    for warning in warnings:
        out(f"  - {warning}")
    out("Overrides: none")
    while True:
        out("Send this board to fab? [y/n] ")
        line = stdin.readline()
        if not line:
            raise SignOffError("no answer at sign-off; nothing recorded")
        answer = line.strip().lower()
        if answer in YES | NO:
            break
        out("Please answer y or n.")
    signed = SignOff(accepted=answer in YES, warnings_acknowledged=warnings, overrides=[],
                     at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    (run_dir / "signoff.json").write_text(json.dumps(to_dict(signed), indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    return signed


def signoff_refusals(run_dir) -> list[str]:
    run_dir = Path(run_dir)
    path = run_dir / "signoff.json"
    if not path.is_file():
        return [f"not signed off; answer the sign-off in `reflow export` at a terminal or in `reflow learn {run_dir}`"]
    signed = _read(SignOff, path)
    if not signed.accepted:
        return [f"sign-off was declined at {signed.at}"]
    if signed.warnings_acknowledged != remaining_warnings(run_dir):
        return [f"the warnings changed since the sign-off at {signed.at}; sign off again"]
    return []


def _read(cls, path: Path):
    try:
        return from_dict(cls, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        raise SignOffError(f"{path}: {exc}") from exc
