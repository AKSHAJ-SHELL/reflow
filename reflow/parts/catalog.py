"""Parts catalog client.  OWNER: AGENT (tasks P-01, P-03).

Contract
--------
    search(category: str, *, value: str = "", package: str = "", limit: int = 20) -> list[CatalogPart]

- Returns raw candidates from the configured backend (default candidate: tscircuit's
  jlcsearch JSON API; alternative: a local SQLite snapshot). See DECISIONS.md D-6.
- Pure data fetch. It does NOT choose a part; that is the resolver's HUMAN-owned job.

Must never
----------
- invent or "fill in" an LCSC/MPN that the backend didn't return,
- hide a network failure as "no results" (raise CatalogError),
- ship a shared API key.
"""
from __future__ import annotations

from dataclasses import dataclass


class CatalogError(RuntimeError):
    """The backend could not be reached or returned something unparseable."""


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


def search(category: str, *, value: str = "", package: str = "", limit: int = 20) -> list[CatalogPart]:
    raise NotImplementedError("P-01: catalog client not built yet")
