"""reflow.parts.catalog after P-06: shared types and value parsing, no client.

The jlcsearch client and its cache were retired (DECISIONS D-6a). Parts come
from the local jlcparts snapshot (reflow.parts.local_catalog). What stays here
is what the resolver, the local catalog, the CLI and the evals import.
"""
import importlib
from decimal import Decimal
from pathlib import Path

import pytest

import reflow.parts.catalog as catalog
from reflow.parts.catalog import CatalogError, CatalogPart, parse_value

SOURCE = Path(catalog.__file__).read_text(encoding="utf-8")


@pytest.mark.parametrize("text, ohms_or_farads", [
    ("4.7k", Decimal("4700")), ("4k7", Decimal("4700")), ("4.7kΩ", Decimal("4700")), ("4.7 k", Decimal("4700")),
    ("10R", Decimal("10")), ("1M", Decimal("1000000")), ("100nF", Decimal("1E-7")), ("0.1uF", Decimal("1E-7")),
    ("1µF", Decimal("1E-6")), ("22pF", Decimal("2.2E-11")),
])
def test_parse_value_gives_base_units(text, ohms_or_farads):
    assert parse_value(text) == ohms_or_farads


@pytest.mark.parametrize("text", ["", "abc", "4.7.1k", "k"])
def test_parse_value_rejects_what_it_cannot_read(text):
    with pytest.raises(CatalogError):
        parse_value(text)


def test_catalog_part_defaults_say_nothing_was_stated():
    part = CatalogPart(lcsc="C1", mpn="X", manufacturer="m", package="0402", value="", stock=1,
                       basic=False, unit_price_usd=0.0, source="jlcparts")
    assert (part.category, part.fetched_at) == ("", "")


def test_the_jlcsearch_client_is_gone():
    assert not hasattr(catalog, "search")
    assert not hasattr(catalog, "UrlLibTransport")
    for marker in ("jlcsearch.tscircuit.com", "urllib", "REFLOW_CATALOG_"):
        assert marker not in SOURCE, marker


def test_the_jlcsearch_response_cache_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("reflow.parts.cache")
