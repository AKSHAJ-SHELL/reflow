"""P-02 resolver validity and ranking.

Candidates arrive unsorted. The resolver picks one winner per request:
JLCPCB basic, then higher stock, then lower price. It does not fetch, and it
does not invent an LCSC id or read an MPN out of TSX.
"""
from __future__ import annotations

import re

import pytest

from reflow.contracts import PartRequest, ResolvedPart, ResolvedParts, Unresolved
from reflow.parts.catalog import CatalogPart
from reflow.parts.resolver import resolve

FETCHED = "2026-10-19T00:00:00Z"
_LCSC = re.compile(r"C\d+")


def _part(**overrides: object) -> CatalogPart:
    fields: dict[str, object] = {
        "lcsc": "C1000",
        "mpn": "RC0402FR-074K7L",
        "manufacturer": "Yageo",
        "package": "0402",
        "value": "4.7k",
        "stock": 100,
        "basic": False,
        "unit_price_usd": 0.01,
        "source": "jlcsearch",
    }
    fields.update(overrides)
    return CatalogPart(**fields)  # type: ignore[arg-type]


def _resistor(request_id: str = "r1", **overrides: object) -> PartRequest:
    fields: dict[str, object] = {
        "id": request_id,
        "role": "pull-up",
        "category": "resistor",
        "value": "4.7k",
        "package": "0402",
    }
    fields.update(overrides)
    return PartRequest(**fields)  # type: ignore[arg-type]


def test_basic_beats_higher_stock_and_lower_price():
    """JLCPCB basic wins before stock and before price. Input is worst-first."""
    extended = _part(lcsc="C1", basic=False, stock=1_000_000, unit_price_usd=0.001)
    basic = _part(lcsc="C2", mpn="BASIC-4K7", basic=True, stock=10, unit_price_usd=0.50)
    order = [extended, basic]
    result = resolve([_resistor()], [], {"r1": order}, fetched_at=FETCHED)
    assert [part.lcsc for part in result.resolved] == ["C2"]
    assert result.unresolved == []
    assert result.resolved[0].basic is True
    assert order == [extended, basic]


def test_higher_stock_wins_when_basic_ties():
    low = _part(lcsc="C1", basic=True, stock=10, unit_price_usd=0.001)
    high = _part(lcsc="C2", mpn="HIGH-STOCK", basic=True, stock=500, unit_price_usd=0.90)
    result = resolve([_resistor()], [], {"r1": [low, high]}, fetched_at=FETCHED)
    assert result.resolved[0].lcsc == "C2"
    assert result.resolved[0].stock == 500


def test_lower_price_wins_when_basic_and_stock_tie():
    pricey = _part(lcsc="C1", basic=True, stock=100, unit_price_usd=0.20)
    cheap = _part(lcsc="C2", mpn="CHEAP-4K7", basic=True, stock=100, unit_price_usd=0.01)
    result = resolve([_resistor()], [], {"r1": [pricey, cheap]}, fetched_at=FETCHED)
    assert result.resolved[0].lcsc == "C2"
    assert result.resolved[0].unit_price_usd == 0.01


def test_equal_rank_keeps_catalog_order():
    """No fourth key. A tie stays in the order the catalog returned."""
    first = _part(lcsc="C1", basic=True, stock=100, unit_price_usd=0.01)
    second = _part(lcsc="C2", mpn="ALSO", basic=True, stock=100, unit_price_usd=0.01)
    result = resolve([_resistor()], [], {"r1": [first, second]}, fetched_at=FETCHED)
    assert result.resolved[0].lcsc == "C1"


def test_package_must_match_request():
    """A better-ranked part in another package is not the winner."""
    wrong = _part(lcsc="C9", package="0603", basic=True, stock=99_999, unit_price_usd=0.001)
    right = _part(lcsc="C2", package="0402", basic=False, stock=5, unit_price_usd=0.50)
    result = resolve([_resistor()], [], {"r1": [wrong, right]}, fetched_at=FETCHED)
    assert [part.lcsc for part in result.resolved] == ["C2"]
    assert result.resolved[0].package == "0402"


def test_package_match_allows_metric_suffix_and_case():
    metric = _part(lcsc="C2", package="0402 (1005 Metric)")
    sot = _part(lcsc="C3", package="SOT-23", value="", mpn="DIODE")
    resistor = _resistor()
    diode = PartRequest(id="d1", role="clamp", category="diode", package="sot-23")
    result = resolve(
        [resistor, diode],
        [],
        {"r1": [metric], "d1": [sot]},
        fetched_at=FETCHED,
    )
    assert [part.lcsc for part in result.resolved] == ["C2", "C3"]
    assert result.unresolved == []
    assert result.resolved[0].package == "0402 (1005 Metric)"


def test_blank_package_lets_ranking_choose():
    large = _part(lcsc="C1", package="0603", basic=False, stock=10, unit_price_usd=0.01)
    small = _part(lcsc="C2", package="0402", basic=True, stock=10, unit_price_usd=0.20)
    request = _resistor(package="")
    result = resolve([request], [], {"r1": [large, small]}, fetched_at=FETCHED)
    assert result.resolved[0].lcsc == "C2"


def test_ic_mpn_not_in_named_parts_is_unresolved():
    request = PartRequest(id="u1", role="sensor", category="ic", mpn="LM75", package="SOIC-8")
    offered = _part(lcsc="C123", mpn="LM75", package="SOIC-8", basic=True, stock=10_000, unit_price_usd=0.01)
    result = resolve([request], ["MCP9808"], {"u1": [offered]}, fetched_at=FETCHED)
    assert result.resolved == []
    assert result.unresolved[0].request_id == "u1"
    assert "LM75" in result.unresolved[0].reason
    assert result.unresolved[0].reason.strip()


def test_unnamed_ic_is_unresolved_even_when_named_parts_and_catalog_have_it():
    """The request MPN is what must be named. Notes are not a second channel."""
    notes = (
        'export default () => (\n'
        '  <chip name="U1" manufacturerPartNumber="MCP9808" '
        'supplierPartNumbers={{jlcpcb:["C12345"]}} />\n'
        ')'
    )
    request = PartRequest(id="u1", role="sensor", category="ic", mpn="", notes=notes)
    offered = _part(lcsc="C12345", mpn="MCP9808", package="MSOP-8", stock=50, unit_price_usd=0.80)
    result = resolve([request], ["MCP9808"], {"u1": [offered]}, fetched_at=FETCHED)
    assert result.resolved == []
    assert result.unresolved[0].request_id == "u1"
    assert "C12345" not in result.unresolved[0].reason
    assert not _LCSC.search(result.unresolved[0].reason)


def test_named_ic_missing_from_catalog_is_unresolved():
    request = PartRequest(id="u1", role="sensor", category="ic", mpn="MCP9808", package="MSOP-8")
    other = _part(
        lcsc="C1",
        mpn="LM75",
        package="MSOP-8",
        basic=True,
        stock=1_000_000,
        unit_price_usd=0.001,
    )
    result = resolve([request], ["MCP9808"], {"u1": [other]}, fetched_at=FETCHED)
    assert result.resolved == []
    reason = result.unresolved[0].reason
    assert result.unresolved[0].request_id == "u1"
    assert "MCP9808" in reason
    assert "catalog" in reason.casefold()
    assert reason.strip()


def test_named_ic_resolves_only_to_that_catalog_candidate():
    request = PartRequest(id="u1", role="sensor", category="ic", mpn="MCP9808", package="MSOP-8")
    other = _part(
        lcsc="C1",
        mpn="LM75",
        package="MSOP-8",
        basic=True,
        stock=1_000_000,
        unit_price_usd=0.001,
    )
    sensor = _part(
        lcsc="C42680",
        mpn="MCP9808",
        manufacturer="Microchip",
        package="MSOP-8",
        value="",
        basic=False,
        stock=20,
        unit_price_usd=1.50,
        source="jlcsearch",
    )
    result = resolve([request], ["MCP9808"], {"u1": [other, sensor]}, fetched_at=FETCHED)
    assert result.unresolved == []
    got = result.resolved[0]
    assert got == ResolvedPart(
        request_id="u1",
        lcsc="C42680",
        mpn="MCP9808",
        manufacturer="Microchip",
        package="MSOP-8",
        value="",
        stock=20,
        basic=False,
        unit_price_usd=1.50,
        source="jlcsearch",
        fetched_at=FETCHED,
    )


def test_model_mpn_outside_named_parts_does_not_become_the_id():
    request = _resistor(mpn="RC0402FR-074K7L")
    offered = _part(lcsc="C25900", mpn="RC0402FR-074K7L", basic=True, stock=8000)
    result = resolve([request], [], {"r1": [offered]}, fetched_at=FETCHED)
    assert result.resolved == []
    assert "RC0402FR-074K7L" in result.unresolved[0].reason
    assert "C25900" not in result.unresolved[0].reason


def test_named_passive_is_not_replaced_by_a_higher_ranked_part():
    request = _resistor(mpn="USER-PART")
    named = _part(lcsc="C1", mpn="USER-PART", basic=False, stock=1, unit_price_usd=1.0)
    better = _part(lcsc="C2", mpn="OTHER", basic=True, stock=99_999, unit_price_usd=0.001)
    result = resolve([request], ["USER-PART"], {"r1": [better, named]}, fetched_at=FETCHED)
    assert result.unresolved == []
    assert result.resolved[0].lcsc == "C1"
    assert result.resolved[0].mpn == "USER-PART"


def test_empty_catalog_does_not_invent_an_lcsc():
    result = resolve([_resistor()], [], {"r1": []}, fetched_at=FETCHED)
    assert result.resolved == []
    reason = result.unresolved[0].reason
    assert "catalog" in reason.casefold()
    assert not _LCSC.search(reason)


def test_blank_lcsc_is_not_filled_in():
    blank = _part(lcsc="  ", basic=True, stock=1000, unit_price_usd=0.001)
    result = resolve([_resistor()], [], {"r1": [blank]}, fetched_at=FETCHED)
    assert result.resolved == []
    assert not _LCSC.search(result.unresolved[0].reason)


def test_out_of_stock_candidate_is_unresolved():
    dead = _part(lcsc="C1", basic=True, stock=0, unit_price_usd=0.001)
    result = resolve([_resistor()], [], {"r1": [dead]}, fetched_at=FETCHED)
    assert result.resolved == []
    assert "stock" in result.unresolved[0].reason.casefold()


def test_every_request_lands_in_exactly_one_list_in_request_order():
    basic = _part(lcsc="C2", basic=True, stock=10, unit_price_usd=0.02)
    requests = [
        _resistor("b"),
        PartRequest(id="a", role="sensor", category="ic", mpn="MCP9808"),
        _resistor("c", package="0201"),
    ]
    result = resolve(
        requests,
        ["MCP9808"],
        {"b": [basic], "a": [], "c": [basic]},
        fetched_at=FETCHED,
    )
    assert isinstance(result, ResolvedParts)
    resolved_ids = [part.request_id for part in result.resolved]
    unresolved_ids = [part.request_id for part in result.unresolved]
    assert resolved_ids == ["b"]
    assert unresolved_ids == ["a", "c"]
    assert set(resolved_ids).isdisjoint(unresolved_ids)
    assert all(isinstance(part, ResolvedPart) for part in result.resolved)
    assert all(isinstance(part, Unresolved) for part in result.unresolved)
    assert "package" in result.unresolved[1].reason.casefold()
    assert "0201" in result.unresolved[1].reason


def test_missing_candidate_entry_is_unresolved():
    result = resolve([_resistor()], [], {}, fetched_at=FETCHED)
    assert result.resolved == []
    assert result.unresolved[0].request_id == "r1"
    assert "catalog" in result.unresolved[0].reason.casefold()


def test_duplicate_request_id_raises():
    with pytest.raises(ValueError, match="r1"):
        resolve([_resistor(), _resistor()], [], {"r1": []}, fetched_at=FETCHED)


def test_resolver_does_not_call_catalog_search(monkeypatch):
    """Ranking stays here. The catalog client stays an unsorted fetch."""

    def _boom(*_args, **_kwargs):
        raise AssertionError("resolver must not fetch or rank via catalog.search")

    monkeypatch.setattr("reflow.parts.catalog.search", _boom)
    monkeypatch.setattr("reflow.parts.resolver.search", _boom, raising=False)
    result = resolve([_resistor()], [], {"r1": [_part(basic=True)]}, fetched_at=FETCHED)
    assert result.resolved[0].lcsc == "C1000"


# ---------------------------------------------------------------------------
# P-02b (C2 resolver half, DECISIONS D-6a, O-1): category, family -> orderable
# MPN, connector pitch, and the row's own fetched_at.
# ---------------------------------------------------------------------------

def _ic(mpn: str = "MCP9808", package: str = "") -> PartRequest:
    return PartRequest(id="u1", role="sensor", category="ic", mpn=mpn, package=package)


def _orderable(lcsc: str, mpn: str, package: str, stock: int, **overrides: object) -> CatalogPart:
    fields: dict[str, object] = {"category": "ic", "source": "jlcparts"}
    fields.update(overrides)
    return _part(lcsc=lcsc, mpn=mpn, package=package, value="", stock=stock, **fields)


MCP9808_ROWS = [
    _orderable("C129490", "MCP9808T-E/MS", "MSOP-8", 716),
    _orderable("C94847", "MCP9808-E/MS", "MSOP-8", 586),
    _orderable("C194710", "MCP9808T-E/MC", "DFN-8-EP(2x3)", 255),
]


def test_a_candidate_of_another_kind_is_never_chosen():
    led = _part(lcsc="C2286", mpn="KT-0603R", package="0402", category="led", basic=True, stock=10**7)
    resistor = _part(lcsc="C25900", category="resistor", stock=10)
    result = resolve([_resistor()], [], {"r1": [led, resistor]}, fetched_at=FETCHED)
    assert [p.lcsc for p in result.resolved] == ["C25900"]


def test_only_other_kinds_is_unresolved_and_says_so():
    led = _part(lcsc="C2286", mpn="KT-0603R", category="led", stock=10**7)
    result = resolve([_resistor()], [], {"r1": [led]}, fetched_at=FETCHED)
    assert result.resolved == []
    reason = result.unresolved[0].reason
    assert "resistor" in reason and "led" in reason


def test_an_uncategorised_snapshot_row_is_rejected():
    """The snapshot leaves some rows without a category; local_catalog maps them to "other"."""
    row = _orderable("C55343413", "TMP102AQDRLRQ1-TUDI", "SOT-563", 2983, category="other")
    result = resolve([_ic("TMP102AQDRLRQ1-TUDI")], ["TMP102AQDRLRQ1-TUDI"], {"u1": [row]}, fetched_at=FETCHED)
    assert result.resolved == [] and "other" in result.unresolved[0].reason


def test_a_source_that_gives_no_category_is_not_filtered():
    """category "" means the source didn't say (the jlcsearch client); only a stated category is checked."""
    result = resolve([_resistor()], [], {"r1": [_part(lcsc="C7", category="")]}, fetched_at=FETCHED)
    assert [p.lcsc for p in result.resolved] == ["C7"]


def test_a_typed_family_with_two_packages_asks_which():
    result = resolve([_ic()], ["MCP9808"], {"u1": MCP9808_ROWS}, fetched_at=FETCHED)
    assert result.resolved == []
    reason = result.unresolved[0].reason
    assert "MSOP-8" in reason and "DFN-8-EP(2x3)" in reason
    assert "package" in reason.casefold()


def test_a_typed_family_with_its_package_resolves_to_an_orderable_part():
    result = resolve([_ic(package="MSOP-8")], ["MCP9808"], {"u1": MCP9808_ROWS}, fetched_at=FETCHED)
    assert result.unresolved == []
    got = result.resolved[0]
    assert (got.lcsc, got.mpn, got.package) == ("C129490", "MCP9808T-E/MS", "MSOP-8")


def test_family_matching_ignores_case():
    result = resolve([_ic("mcp9808", "MSOP-8")], ["mcp9808"], {"u1": MCP9808_ROWS}, fetched_at=FETCHED)
    assert [p.lcsc for p in result.resolved] == ["C129490"]


def test_an_exact_part_number_wins_over_longer_ones():
    rows = [
        _orderable("C6203", "AT24C02C-SSHM-T", "SOIC-8", 113_992),
        _orderable("C688857", "AT24C02", "SOP-8", 105_879),
    ]
    result = resolve([_ic("AT24C02")], ["AT24C02"], {"u1": rows}, fetched_at=FETCHED)
    assert [(p.lcsc, p.mpn) for p in result.resolved] == [("C688857", "AT24C02")]


def test_a_different_variant_behind_the_same_prefix_is_asked_about():
    """PCF8574 and PCF8574A are different chips (different I2C address) in the same package."""
    rows = [
        _orderable("C7605", "PCF8574T/3,518", "SOIC-16-300mil", 19_200),
        _orderable("C86832", "PCF8574AT/3,518", "SOIC-16-300mil", 4_890),
    ]
    result = resolve([_ic("PCF8574")], ["PCF8574"], {"u1": rows}, fetched_at=FETCHED)
    assert result.resolved == []
    reason = result.unresolved[0].reason
    assert "PCF8574T/3,518" in reason and "PCF8574AT/3,518" in reason


def test_a_typed_part_number_never_matches_a_shorter_one():
    rows = [_orderable("C1", "MCP980", "MSOP-8", 10**6)]
    result = resolve([_ic("MCP9808", "MSOP-8")], ["MCP9808"], {"u1": rows}, fetched_at=FETCHED)
    assert result.resolved == [] and "MCP9808" in result.unresolved[0].reason


def test_a_connector_package_is_its_pitch():
    """D-6a (a): a header request is value "1x4", package "2.54mm"; the row's package is free text."""
    request = PartRequest(id="j1", role="header", category="connector", value="1x4", package="2.54mm")
    header = _part(lcsc="C32713270", mpn="HX PZ2.54-1x4P ZZ", package="插件,P=2.54mm", value="",
                   category="connector", stock=135_024)
    result = resolve([request], [], {"j1": [header]}, fetched_at=FETCHED)
    assert [(p.lcsc, p.package) for p in result.resolved] == [("C32713270", "插件,P=2.54mm")]


def test_resolved_part_carries_the_rows_own_date():
    row = _part(lcsc="C25900", category="resistor", fetched_at="2026-10-02T08:00:00Z")
    result = resolve([_resistor()], [], {"r1": [row]}, fetched_at=FETCHED)
    assert result.resolved[0].fetched_at == "2026-10-02T08:00:00Z"
