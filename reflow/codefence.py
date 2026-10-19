"""Lift one markdown code fence out of a model reply. OWNER: AGENT (M-01).

Contract
--------
extract_code_fence(text: str) -> str | None

Exactly one fenced block returns that block's body. No fence, or more than
one fence, returns None. The body is returned unchanged.

Must never
----------
- decide whether a run passed or failed,
- parse the body into a part number.
"""
from __future__ import annotations

import re

_FENCE = re.compile(
    r"^[ \t]*```[^\n]*\n(.*?)[ \t]*```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def extract_code_fence(text: str) -> str | None:
    bodies = _FENCE.findall(text)
    if len(bodies) != 1:
        return None
    return bodies[0]
