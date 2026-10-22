"""P-05: catalog queries on the local jlcparts snapshot (D-6a), the catalog half of C2.

tests/data/parts_db/cache.sqlite3 holds 27 real rows copied from the
2026-10-21 snapshot (see its README): the parts the MCP9808 eval board needs,
plus rows that must not match (wrong value, package, stock, kind, pitch).
"""
import dataclasses
import json
import sqlite3
from pathlib import Path

import pytest

from reflow.contracts import Plan, PartRequest, from_dict
from reflow.parts.catalog import CatalogError, CatalogPart
from reflow.parts.local_catalog import reflow_category, search
from reflow.parts.resolver import resolve

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "tests" / "data" / "parts_db" / "cache.sqlite3"


def _request(category, value="", package="", tolerance="", voltage="", mpn="", rid="p1") -> PartRequest:
    return PartRequest(id=rid, role="test", category=category, value=value, package=package,
                       tolerance=tolerance, voltage=voltage, mpn=mpn)


def _lcsc(parts: list[CatalogPart]) -> set[str]:
    return {p.lcsc for p in parts}


# ---------------------------------------------------------------------------
# passives by value
# ---------------------------------------------------------------------------

def test_resistor_by_value_and_package():
    found = search(_request("resistor", "4.7k", "0402"), db_path=DB)
    # not: C100658 (no stock), C23162 (0603), C93943 (47k), C22461632 (potentiometer), C25499 (network)
    assert _lcsc(found) == {"C25900", "C105871", "C105870"}
    assert {p.category for p in found} == {"resistor"}


def test_resistor_tolerance_must_be_as_tight_as_asked():
    found = search(_request("resistor", "4.7k", "0402", tolerance="1%"), db_path=DB)
    assert _lcsc(found) == {"C25900", "C105871"}          # C105870 is ±5%


def test_capacitor_by_value_package_and_voltage():
    assert _lcsc(search(_request("capacitor", "100nF", "0402"), db_path=DB)) == \
        {"C307331", "C1525", "C60474", "C22435938"}
    rated = search(_request("capacitor", "100nF", "0402", voltage="10V"), db_path=DB)
    assert _lcsc(rated) == {"C307331", "C1525", "C60474"}  # C22435938 is 6.3V


def test_value_spellings_are_compared_as_numbers():
    assert _lcsc(search(_request("capacitor", "0.1uF", "0402"), db_path=DB)) == \
        _lcsc(search(_request("capacitor", "100nF", "0402"), db_path=DB))
    assert _lcsc(search(_request("resistor", "4k7", "0402"), db_path=DB)) == {"C25900", "C105871", "C105870"}


def test_a_candidate_carries_what_the_resolver_needs():
    (part,) = [p for p in search(_request("resistor", "4.7k", "0402"), db_path=DB) if p.lcsc == "C25900"]
    assert part.mpn == "0402WGF4701TCE" and part.package == "0402"
    assert part.basic is True and part.stock > 0
    assert part.unit_price_usd == pytest.approx(0.0023)
    assert part.source == "jlcparts" and part.category == "resistor"
    assert part.fetched_at.endswith("Z") and part.fetched_at[:4] == "2026"


# ---------------------------------------------------------------------------
# headers (D-6a a: value "RxC", package = pitch)
# ---------------------------------------------------------------------------

def test_header_by_rows_pins_and_pitch():
    found = search(_request("connector", "1x4", "2.54mm"), db_path=DB)
    # not: C492412 (right angle), C541858 (2.0 mm), C492401 (1x2), C492421 (2x4)
    assert _lcsc(found) == {"C32713270", "C124378", "C41417361"}
    assert {p.category for p in found} == {"connector"}


def test_two_row_header():
    assert _lcsc(search(_request("connector", "2x4", "2.54 mm"), db_path=DB)) == {"C492421"}


def test_female_headers_are_not_pin_headers():
    assert search(_request("connector", "1x8", "2.54mm"), db_path=DB) == []   # only C27438, a female header


@pytest.mark.parametrize("value, package", [("", ""), ("4-pin", "2.54mm"), ("1x4", "")])
def test_header_without_the_d6a_encoding_raises(value, package):
    with pytest.raises(CatalogError, match="1x4"):
        search(_request("connector", value, package), db_path=DB)


# ---------------------------------------------------------------------------
# named parts by MPN
# ---------------------------------------------------------------------------

def test_named_ic_returns_every_orderable_variant():
    found = search(_request("ic", mpn="MCP9808"), db_path=DB)
    assert {p.mpn for p in found} == {"MCP9808-E/MS", "MCP9808T-E/MS", "MCP9808T-E/MC"}
    assert {p.category for p in found} == {"ic"}


def test_named_part_lookup_is_case_insensitive_and_takes_a_package():
    assert {p.mpn for p in search(_request("ic", mpn="mcp9808", package="MSOP-8"), db_path=DB)} == \
        {"MCP9808-E/MS", "MCP9808T-E/MS"}


def test_mpn_wildcards_are_literal():
    assert search(_request("ic", mpn="MCP98%"), db_path=DB) == []
    assert search(_request("ic", mpn="MCP9808_"), db_path=DB) == []


# ---------------------------------------------------------------------------
# categories
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("jlc, sub, expected", [
    ("Resistors", "Chip Resistor - Surface Mount", "resistor"),
    ("Resistors", "Potentiometers, Variable Resistors", "other"),
    ("Capacitors", "Multilayer Ceramic Capacitors MLCC - SMD/SMT", "capacitor"),
    ("Connectors", "Pin Headers", "connector"),
    ("Optoelectronics", "LED Indication - Discrete", "led"),
    ("Sensors", "Temperature Sensors", "ic"),
    ("Power Management (PMIC)", "Linear Voltage Regulators (LDO)", "regulator"),
    ("Power Management (PMIC)", "Battery Management", "ic"),
    ("Diodes", "Schottky Diodes", "diode"),
    ("Crystals, Oscillators, Resonators", "Crystals", "crystal"),
    ("", "", "other"),
])
def test_jlc_categories_map_to_reflow_categories(jlc, sub, expected):
    assert reflow_category(jlc, sub) == expected


def test_a_candidates_category_comes_from_the_row_not_the_request():
    (led,) = search(_request("ic", mpn="KT-0603R"), db_path=DB)
    assert led.category == "led"
    (uncategorised,) = search(_request("resistor", mpn="RCA02100KJLF"), db_path=DB)
    assert uncategorised.category == "other"            # the snapshot gives this row no category


# ---------------------------------------------------------------------------
# what isn't supported raises instead of guessing
# ---------------------------------------------------------------------------

def test_resistor_without_a_value_raises():
    with pytest.raises(CatalogError, match="value"):
        search(_request("resistor", "", "0402"), db_path=DB)


def test_category_with_no_local_query_raises():
    with pytest.raises(CatalogError, match="crystal"):
        search(_request("crystal", "16MHz", "3225"), db_path=DB)


def test_missing_database_says_how_to_get_one(tmp_path):
    with pytest.raises(CatalogError, match="reflow parts update"):
        search(_request("resistor", "4.7k", "0402"), db_path=tmp_path / "nope.sqlite3")


def test_database_in_another_format_raises(tmp_path):
    path = tmp_path / "cache.sqlite3"
    db = sqlite3.connect(path)
    db.execute("create table meta (key text, value text)")
    db.execute("insert into meta values ('format', 'something-else')")
    db.commit()
    db.close()
    with pytest.raises(CatalogError, match="source-db-v2"):
        search(_request("resistor", "4.7k", "0402"), db_path=path)


def test_database_path_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("REFLOW_PARTS_DB", str(DB))
    assert _lcsc(search(_request("resistor", "4.7k", "0402"))) == {"C25900", "C105871", "C105870"}


# ---------------------------------------------------------------------------
# the MCP9808 eval plan, through the real resolver
# ---------------------------------------------------------------------------

def test_mcp9808_plan_resolves_every_part():
    plan = from_dict(Plan, json.loads((ROOT / "docs" / "examples" / "plan.json").read_text(encoding="utf-8")))
    parts = [dataclasses.replace(p, value="1x4", package="2.54mm") if p.category == "connector"
             else dataclasses.replace(p, package="MSOP-8") if p.category == "ic" else p
             for p in plan.parts]
    candidates = {p.id: search(p, db_path=DB) for p in parts}
    result = resolve(parts, ["MCP9808"], candidates, fetched_at="2026-10-21T00:00:00Z")
    chosen = {r.request_id: r.lcsc for r in result.resolved}
    assert chosen["p2"] in {"C307331", "C1525"}                 # basic 100nF 0402 rated >= 10V
    assert chosen["p3"] == chosen["p4"] == "C25900"            # basic 4.7k 0402 1%
    assert chosen["p1"] == "C129490"                           # MCP9808T-E/MS, MSOP-8, most stock
    assert chosen["p5"] == "C32713270"                         # 1x4 2.54 mm, most stock
    assert result.unresolved == []
