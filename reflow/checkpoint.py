"""Spec checkpoint and plan provenance gate (H-06).

Contract
--------
- ``load_spec`` / ``load_plan`` parse JSON only through ``from_dict``.
- ``confirmed is False`` means nothing downstream runs.
- A non-empty ``PartRequest.mpn`` must be a string in ``Spec.named_parts``.
- An mpn outside that list fails the plan. This module does not rewrite it.

Must never
----------
- Call a model, re-prompt a planner, or run the design for-loop (H-03, HUMAN).
- Copy model text into an MPN or LCSC id. The only mpn values that pass
  this gate are ones already listed in ``Spec.named_parts`` (or ``""``).
- Claim a board was designed, verified, or routed.
"""
from __future__ import annotations

import json
from pathlib import Path

from reflow.contracts import Plan, Spec, from_dict


class CheckpointError(Exception):
    """A spec or plan that must not proceed. The CLI maps this to exit code 2."""


def load_spec(path: Path) -> Spec:
    """Read a Spec JSON file and parse it with ``from_dict(Spec, ...)``."""
    return from_dict(Spec, _read_json(path))


def load_plan(path: Path) -> Plan:
    """Read a Plan JSON file and parse it with ``from_dict(Plan, ...)``.

    This does not accept the plan. Call ``reject_foreign_mpn`` before using it.
    """
    return from_dict(Plan, _read_json(path))


def require_confirmed(spec: Spec) -> None:
    """Stop before any downstream step when the user has not confirmed."""
    if spec.confirmed is not True:
        raise CheckpointError("spec is not confirmed; nothing downstream runs")


def reject_foreign_mpn(plan: Plan, spec: Spec) -> None:
    """Fail when a plan names an MPN the user did not type.

    Empty ``mpn`` is allowed. A non-empty value must match ``Spec.named_parts``
    exactly. The plan and the spec are not modified, and no LCSC id is read
    or written.
    """
    allowed = set(spec.named_parts)
    bad = [
        f"{part.id}: mpn {part.mpn!r} is not in Spec.named_parts"
        for part in plan.parts
        if part.mpn and part.mpn not in allowed
    ]
    if bad:
        raise CheckpointError("plan rejected; " + "; ".join(bad))


def _read_json(path: Path) -> dict:
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckpointError(f"{file}: {exc.strerror or exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CheckpointError(f"{file}: invalid JSON ({exc.msg})") from exc
    return data
