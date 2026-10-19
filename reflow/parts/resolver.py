"""Resolver validity and ranking. Task P-02.

    resolve(requests, named_parts, candidates, *, fetched_at=None) -> ResolvedParts

The catalog client returns unsorted candidates. This function picks the winner.
Ranking, highest priority first:

    1. JLCPCB basic (``basic`` True before False)
    2. higher stock
    3. lower unit price

A tie keeps the order of that request's candidate list. There is no fourth key.

Package match follows the catalog client: case-insensitive, and a parenthetical
suffix on the candidate package is ignored ("0402" matches "0402 (1005 Metric)").

Must never
----------
- invent an LCSC id or MPN
- read an MPN or LCSC id out of TSX, notes, or other free text
- let ``PartRequest.mpn`` become the chosen id unless that string is in ``named_parts``
- call the catalog client, or sort its candidate lists in place
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from reflow.contracts import PART_CATEGORIES, PartRequest, ResolvedPart, ResolvedParts, Unresolved
from reflow.parts.catalog import CatalogPart


def resolve(
    requests: Sequence[PartRequest],
    named_parts: Sequence[str],
    candidates: Mapping[str, Sequence[CatalogPart]],
    *,
    fetched_at: str | None = None,
) -> ResolvedParts:
    """Pick one catalog part per request, or record why that request is unresolved.

    Every request is placed in exactly one of ``resolved`` or ``unresolved``,
    in request order. ``candidates`` is keyed by ``PartRequest.id``.
    """
    if isinstance(requests, (str, bytes)) or not isinstance(requests, Sequence):
        raise TypeError("requests must be a sequence of PartRequest")
    if isinstance(named_parts, (str, bytes)) or not isinstance(named_parts, Sequence):
        raise TypeError("named_parts must be a sequence of strings")
    if not isinstance(candidates, Mapping):
        raise TypeError("candidates must map a request id to catalog parts")

    stamp = _fetched_at(fetched_at)
    named = _named_set(named_parts)
    _require_unique_ids(requests)

    resolved: list[ResolvedPart] = []
    unresolved: list[Unresolved] = []
    for request in requests:
        outcome = _resolve_one(request, named, _pool(candidates, request.id), stamp)
        if isinstance(outcome, ResolvedPart):
            resolved.append(outcome)
        else:
            unresolved.append(outcome)
    return ResolvedParts(resolved=resolved, unresolved=unresolved)


def _resolve_one(
    request: PartRequest,
    named: set[str],
    pool: Sequence[CatalogPart],
    fetched_at: str,
) -> ResolvedPart | Unresolved:
    category = request.category.strip().casefold()
    if category not in PART_CATEGORIES:
        return Unresolved(request.id, f"unknown category {request.category!r}")

    mpn = request.mpn.strip()
    if mpn and mpn not in named:
        return Unresolved(request.id, f"{mpn} is not in the user's named parts")
    if category == "ic" and not mpn:
        return Unresolved(request.id, "IC mpn is not in the user's named parts")

    parts = list(pool)
    if mpn:
        parts = [part for part in parts if part.mpn.strip() == mpn]
        if not parts:
            return Unresolved(request.id, f"{mpn} was not in the catalog")

    package = request.package.strip()
    if package:
        matched = [part for part in parts if _package_matches(package, part.package)]
        if not matched:
            if not parts:
                return Unresolved(request.id, "no catalog candidates")
            return Unresolved(request.id, f"no catalog part matches package {package}")
        parts = matched
    elif not parts:
        return Unresolved(request.id, "no catalog candidates")

    instock = [part for part in parts if part.stock > 0]
    if not instock:
        return Unresolved(request.id, "no in-stock catalog part")
    identified = [part for part in instock if part.lcsc.strip()]
    if not identified:
        return Unresolved(request.id, "catalog candidate has no LCSC id")

    winner = _pick(identified)
    return ResolvedPart(
        request_id=request.id,
        lcsc=winner.lcsc,
        mpn=winner.mpn,
        manufacturer=winner.manufacturer,
        package=winner.package,
        value=winner.value,
        stock=winner.stock,
        basic=winner.basic,
        unit_price_usd=winner.unit_price_usd,
        source=winner.source,
        fetched_at=fetched_at,
    )


def _pick(parts: Sequence[CatalogPart]) -> CatalogPart:
    """JLCPCB basic, then higher stock, then lower price. Stable on ties."""
    return sorted(
        parts,
        key=lambda part: (not part.basic, -part.stock, part.unit_price_usd),
    )[0]


def _package_matches(wanted: str, got: object) -> bool:
    """Same comparison the catalog client uses when it filters a package query."""
    if not isinstance(got, str):
        return False
    return got.split("(", 1)[0].strip().casefold() == wanted.strip().casefold()


def _pool(candidates: Mapping[str, Sequence[CatalogPart]], request_id: str) -> Sequence[CatalogPart]:
    pool = candidates.get(request_id, ())
    if isinstance(pool, (str, bytes)) or not isinstance(pool, Sequence):
        raise TypeError(f"candidates for {request_id!r} must be a sequence of CatalogPart")
    for part in pool:
        if not isinstance(part, CatalogPart):
            raise TypeError(f"candidates for {request_id!r} must be CatalogPart values")
    return pool


def _named_set(named_parts: Sequence[str]) -> set[str]:
    names: set[str] = set()
    for item in named_parts:
        if not isinstance(item, str):
            raise TypeError("named_parts entries must be strings")
        text = item.strip()
        if text:
            names.add(text)
    return names


def _require_unique_ids(requests: Sequence[PartRequest]) -> None:
    seen: set[str] = set()
    for request in requests:
        if not isinstance(request, PartRequest):
            raise TypeError("requests must contain PartRequest values")
        if request.id in seen:
            raise ValueError(f"duplicate PartRequest id {request.id!r}")
        seen.add(request.id)


def _fetched_at(fetched_at: str | None) -> str:
    if fetched_at is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(fetched_at, str) and fetched_at.strip():
        return fetched_at
    raise ValueError("fetched_at must be a non-empty ISO-8601 UTC string")
