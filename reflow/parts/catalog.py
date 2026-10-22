"""Catalog types shared by the parts stage.  OWNER: AGENT (P-01, P-05, P-06).

Contract
--------
    CatalogPart                 one candidate row from a parts source
    CatalogError                a parts source is missing, unreadable, or can't answer
    parse_value(text) -> Decimal

Candidates come from the local jlcparts snapshot (`reflow.parts.local_catalog`,
DECISIONS D-6a). The jlcsearch HTTP client and its response cache were retired
in P-06. The resolver (`reflow.parts.resolver`) imports CatalogPart from here.

Must never
----------
- fetch anything, or rank or choose a candidate (that is P-02),
- invent or complete an LCSC id or MPN.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

_SI = {
    "p": Decimal("1e-12"),
    "n": Decimal("1e-9"),
    "u": Decimal("1e-6"),
    "µ": Decimal("1e-6"),
    "μ": Decimal("1e-6"),
    "m": Decimal("1e-3"),
    "k": Decimal("1000"),
    "K": Decimal("1000"),
    "M": Decimal("1000000"),
    "G": Decimal("1000000000"),
}
_UNIT_WORDS = ("ohms", "ohm", "farads", "farad", "Ω", "ω")
_EUROPEAN = re.compile(r"(\d+)([pnuµμmkKMGrR])(\d+)")
_NUMBER = re.compile(r"(\d+(?:\.\d+)?)([pnuµμmkKMG])?")
_OHM_MARK = re.compile(r"(\d+(?:\.\d+)?)[Rr]")


class CatalogError(RuntimeError):
    """A parts source is missing, unreadable, or can't answer this request."""


@dataclass
class CatalogPart:
    lcsc: str
    mpn: str
    manufacturer: str
    package: str
    value: str
    stock: int
    basic: bool
    unit_price_usd: float
    source: str
    category: str = ""      # the reflow category of this row; "" = the source didn't say
    fetched_at: str = ""    # when the source saw this row (ISO-8601 UTC); "" when unknown


def parse_value(text: str) -> Decimal:
    """Engineering value in base units: "4.7k" / "4k7" / "4.7kΩ" -> 4700, "100nF" -> 1E-7."""
    return _parse_value(text)


def _parse_value(text: str) -> Decimal:
    raw = text.strip().replace(" ", "")
    folded = raw.casefold()
    for suffix in _UNIT_WORDS:
        if folded.endswith(suffix.casefold()):
            raw = raw[: -len(suffix)]
            folded = raw.casefold()
            break
    if len(raw) > 1 and raw[-1] in "Ff":
        raw = raw[:-1]
    european = _EUROPEAN.fullmatch(raw)
    if european:
        number = Decimal(f"{european.group(1)}.{european.group(3)}")
        prefix = european.group(2)
        if prefix in "Rr":
            return number
        return number * _SI[prefix]
    plain = _NUMBER.fullmatch(raw)
    if plain:
        number = Decimal(plain.group(1))
        prefix = plain.group(2)
        if prefix is None:
            return number
        return number * _SI[prefix]
    marked = _OHM_MARK.fullmatch(raw)
    if marked:
        return Decimal(marked.group(1))
    raise CatalogError(f"cannot parse value {text!r}")
