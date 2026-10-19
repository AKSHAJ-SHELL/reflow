"""P-01 catalog client and P-03 on-disk cache.

The live test calls the public jlcsearch API once. A second search with the same
cache directory must not touch the network. Recorded responses cover parsing
and failure paths; they are not a stand-in for that live query.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

import pytest

from reflow.parts.catalog import CatalogError, CatalogPart, UrlLibTransport, search

LCSC_ID = re.compile(r"C\d+")


class _CountingUrlLib(UrlLibTransport):
    def __init__(self) -> None:
        super().__init__(timeout=20)
        self.calls = 0

    def get(self, url: str) -> bytes:
        self.calls += 1
        return super().get(url)


class _Scripted:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.urls: list[str] = []

    def get(self, url: str) -> bytes:
        self.urls.append(url)
        return self.body


def _resistor(**overrides: object) -> dict:
    row = {
        "lcsc": 105871,
        "mfr": "RC0402FR-074K7L",
        "package": "0402",
        "resistance": 4700,
        "stock": 10,
        "is_basic": False,
        "price1": 0.5,
    }
    row.update(overrides)
    return row


def test_resistor_4k7_0402_returns_instock_parts_then_uses_cache(tmp_path):
    """Live jlcsearch query. The second call must not open the network."""
    transport = _CountingUrlLib()
    kwargs = dict(
        value="4.7k",
        package="0402",
        limit=20,
        transport=transport,
        cache_dir=tmp_path,
    )
    parts = search("resistor", **kwargs)
    assert transport.calls == 1
    assert isinstance(parts, list)
    assert 1 < len(parts) <= 20
    assert len({part.lcsc for part in parts}) == len(parts)
    for part in parts:
        assert isinstance(part, CatalogPart)
        assert LCSC_ID.fullmatch(part.lcsc)
        assert part.stock > 0
        assert part.package.casefold() == "0402"
        assert part.value == "4.7k"
        assert part.source == "jlcsearch"
        assert isinstance(part.mpn, str) and part.mpn != ""
        assert isinstance(part.manufacturer, str)
        assert isinstance(part.basic, bool)
        assert isinstance(part.unit_price_usd, float)
    again = search("resistor", **kwargs)
    assert transport.calls == 1
    assert [part.lcsc for part in again] == [part.lcsc for part in parts]


def test_network_failure_raises_catalog_error(tmp_path):
    class Down:
        def get(self, url: str) -> bytes:
            raise OSError("network down")

    with pytest.raises(CatalogError):
        search(
            "resistor",
            value="4.7k",
            package="0402",
            transport=Down(),
            cache_dir=tmp_path,
        )


def test_network_failure_is_not_cached_as_no_results(tmp_path):
    class Down:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str) -> bytes:
            self.calls += 1
            raise OSError("network down")

    transport = Down()
    for _ in range(2):
        with pytest.raises(CatalogError):
            search(
                "resistor",
                value="4.7k",
                package="0402",
                transport=transport,
                cache_dir=tmp_path,
            )
    assert transport.calls == 2


def test_second_scripted_call_makes_no_network_call(tmp_path):
    transport = _Scripted(json.dumps({"resistors": [_resistor(lcsc=25900, mfr="0402WGF4701TCE", stock=100, is_basic=True, price1=0.0011)]}).encode())

    class Once(_Scripted):
        def get(self, url: str) -> bytes:
            if self.urls:
                raise AssertionError(f"second network call: {url}")
            return super().get(url)

    transport = Once(transport.body)
    kwargs = dict(value="4.7k", package="0402", transport=transport, cache_dir=tmp_path)
    first = search("resistor", **kwargs)
    second = search("resistor", **kwargs)
    assert len(transport.urls) == 1
    assert [part.lcsc for part in second] == [part.lcsc for part in first] == ["C25900"]


def test_4k7_is_queried_as_ohms_and_not_ranked(tmp_path):
    """4.7k must be sent as 4700 ohms. API order is kept; non-matches drop out."""
    body = json.dumps({
        "resistors": [
            _resistor(),
            _resistor(lcsc=25900, mfr="0402WGF4701TCE", stock=1_000_000, is_basic=True, price1=0.001),
            _resistor(lcsc=2909356, mfr="FRC0402F4R70TS", resistance=4.7, stock=999_999, is_basic=True, price1=0.0001),
            _resistor(lcsc=105870, mfr="RC0402JR-074K7L", package="0603", stock=50, is_basic=True, price1=0.01),
            _resistor(lcsc=25169, mfr="0402WGJ047JTCE", stock=0, is_basic=True, price1=0.01),
        ]
    }).encode()
    transport = _Scripted(body)
    parts = search("resistor", value="4.7k", package="0402", transport=transport, cache_dir=tmp_path)
    query = parse_qs(urlparse(transport.urls[0]).query)
    assert query["package"] == ["0402"]
    assert query["resistance"] == ["4700"]
    plain = _Scripted(body)
    search("resistor", value="4.7", package="0402", transport=plain, cache_dir=tmp_path / "ohms")
    assert parse_qs(urlparse(plain.urls[0]).query)["resistance"] == ["4.7"]
    assert [part.lcsc for part in parts] == ["C105871", "C25900"]
    assert parts[0].basic is False
    assert parts[1].basic is True
    assert parts[0].mpn == "RC0402FR-074K7L"
    assert parts[1].manufacturer == ""


def test_capacitor_value_is_sent_in_farads(tmp_path):
    body = json.dumps({
        "capacitors": [{
            "lcsc": 3715679,
            "mfr": "939113424610-T3N",
            "package": "0402",
            "capacitance_farads": 1e-7,
            "stock": 13,
            "is_basic": False,
            "price1": 1.5,
        }]
    }).encode()
    transport = _Scripted(body)
    parts = search("capacitor", value="100nF", package="0402", transport=transport, cache_dir=tmp_path)
    sent = float(parse_qs(urlparse(transport.urls[0]).query)["capacitance"][0])
    assert abs(sent - 1e-7) / 1e-7 < 1e-9
    assert parts[0].lcsc == "C3715679"
    assert parts[0].value == "100nF"


def test_part_number_text_is_not_looked_up(tmp_path):
    class Boom:
        def get(self, url: str) -> bytes:
            raise AssertionError(f"looked up a part number: {url}")

    with pytest.raises(CatalogError):
        search("resistor", value="C25900", package="0402", transport=Boom(), cache_dir=tmp_path)


def test_search_takes_no_part_number_argument():
    names = set(search.__code__.co_varnames)
    assert "mpn" not in names
    assert "lcsc" not in names


def test_bad_json_raises_and_is_not_cached(tmp_path):
    class Garbage:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str) -> bytes:
            self.calls += 1
            return b"<html>nope</html>"

    transport = Garbage()
    for _ in range(2):
        with pytest.raises(CatalogError):
            search("resistor", value="4.7k", package="0402", transport=transport, cache_dir=tmp_path)
    assert transport.calls == 2


def test_empty_catalog_is_an_empty_list(tmp_path):
    transport = _Scripted(b'{"resistors": []}')
    assert search("resistor", value="4.7k", package="0402", transport=transport, cache_dir=tmp_path) == []
