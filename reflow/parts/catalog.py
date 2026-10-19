"""Parts catalog client.  OWNER: AGENT (tasks P-01, P-03).

Contract
--------
    search(category, *, value="", package="", limit=20) -> list[CatalogPart]

Fetches candidates from the public jlcsearch JSON API
(https://jlcsearch.tscircuit.com). A repeat call with the same cache directory
reads `reflow.parts.cache` and does not open the network.

The live API parses the resistance query with a numeric conversion, so a suffix
in "4.7k" is dropped and the query becomes 4.7 ohms. This client converts an
engineering value to the base unit (ohms, farads) before sending it, then
drops rows whose returned value or package does not match.

It returns every matching in-stock row, in the API's order, up to `limit`.
It does not rank and it does not choose a winner. That is the resolver's
HUMAN-owned job (P-02).

Base URL, timeout, and cache directory come from the environment when the
caller does not pass them:

    REFLOW_CATALOG_BASE_URL   default https://jlcsearch.tscircuit.com
    REFLOW_CATALOG_TIMEOUT    default 20 seconds
    REFLOW_CATALOG_CACHE      default <temp>/reflow/catalog

Must never
----------
- invent or fill in an LCSC id or MPN the backend did not return,
- copy a part number out of model text (there is no mpn/lcsc argument),
- hide a network or parse failure as "no results" (raise CatalogError),
- rank candidates (basic, then stock, then price) — that is P-02,
- ship a shared API key.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

from reflow.contracts import PART_CATEGORIES
from reflow.parts import cache as catalog_cache

DEFAULT_BASE_URL = "https://jlcsearch.tscircuit.com"
_SOURCE = "jlcsearch"

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
_SCALES = (
    (Decimal("1e9"), "G"),
    (Decimal("1e6"), "M"),
    (Decimal("1e3"), "k"),
    (Decimal("1"), ""),
    (Decimal("1e-3"), "m"),
    (Decimal("1e-6"), "u"),
    (Decimal("1e-9"), "n"),
    (Decimal("1e-12"), "p"),
)
_UNIT_WORDS = ("ohms", "ohm", "farads", "farad", "Ω", "ω")
_EUROPEAN = re.compile(r"(\d+)([pnuµμmkKMGrR])(\d+)")
_NUMBER = re.compile(r"(\d+(?:\.\d+)?)([pnuµμmkKMG])?")
_OHM_MARK = re.compile(r"(\d+(?:\.\d+)?)[Rr]")


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


class Transport(Protocol):
    def get(self, url: str) -> bytes: ...


class UrlLibTransport:
    """HTTP GET. Network errors and HTTP error statuses raise CatalogError."""

    def __init__(self, timeout: float = 20) -> None:
        if timeout <= 0:
            raise CatalogError("timeout must be positive")
        self.timeout = timeout

    def get(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "reflow-catalog"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise CatalogError(f"jlcsearch HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise CatalogError(f"jlcsearch unreachable: {exc.reason}") from exc
        except TimeoutError as exc:
            raise CatalogError("jlcsearch timed out") from exc
        except OSError as exc:
            raise CatalogError(f"jlcsearch unreachable: {exc}") from exc


@dataclass(frozen=True)
class _Endpoint:
    path: str
    rows_key: str
    query_param: str | None
    numeric: bool
    value_field: str | None
    display_unit: str


# Paths checked against the live API. Other categories use the generic list.
_ENDPOINTS = {
    "resistor": _Endpoint("/resistors/list.json", "resistors", "resistance", True, "resistance", ""),
    "capacitor": _Endpoint("/capacitors/list.json", "capacitors", "capacitance", True, "capacitance_farads", "F"),
    "led": _Endpoint("/leds/list.json", "leds", None, False, None, ""),
    "diode": _Endpoint("/diodes/list.json", "diodes", None, False, None, ""),
    "regulator": _Endpoint("/voltage_regulators/list.json", "regulators", None, False, None, ""),
}
_FALLBACK = _Endpoint("/components/list.json", "components", "search", False, None, "")


def search(
    category: str,
    *,
    value: str = "",
    package: str = "",
    limit: int = 20,
    transport: Transport | None = None,
    cache_dir: str | Path | None = None,
    base_url: str | None = None,
) -> list[CatalogPart]:
    """Return in-stock candidates. Does not choose one of them.

    `cache_dir=None` uses ``REFLOW_CATALOG_CACHE`` or a directory under the
    system temp dir. Pass a path to isolate a run. Network and parse failures
    raise CatalogError and are not written to the cache.
    """
    name = _require_category(category)
    if not isinstance(value, str) or not isinstance(package, str):
        raise CatalogError("value and package must be strings")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise CatalogError("limit must be a positive integer")
    endpoint = _ENDPOINTS.get(name, _FALLBACK)
    wanted = _wanted_value(endpoint, value)
    url = _url(_base_url(base_url), endpoint, wanted, value.strip(), package.strip())
    payload = _fetch(
        url,
        transport if transport is not None else UrlLibTransport(_timeout()),
        _cache_dir(cache_dir),
        endpoint.rows_key,
    )
    rows = payload[endpoint.rows_key]
    parts: list[CatalogPart] = []
    for row in rows:
        part = _candidate(row, endpoint, wanted, package.strip())
        if part is None:
            continue
        parts.append(part)
        if len(parts) == limit:
            break
    return parts


def _require_category(category: object) -> str:
    if not isinstance(category, str) or not category.strip():
        raise CatalogError("category is required")
    name = category.strip().casefold()
    if name not in PART_CATEGORIES:
        raise CatalogError(f"unknown category {category!r}")
    return name


def _wanted_value(endpoint: _Endpoint, value: str) -> Decimal | None:
    text = value.strip()
    if not text or not endpoint.numeric:
        return None
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


def _url(base: str, endpoint: _Endpoint, wanted: Decimal | None, value: str, package: str) -> str:
    params: dict[str, str] = {}
    if package:
        params["package"] = package
    if wanted is not None and endpoint.query_param:
        params[endpoint.query_param] = _format_query_number(wanted)
    elif value and endpoint.query_param == "search":
        params["search"] = value
    query = urllib.parse.urlencode(params)
    root = base.rstrip("/") + endpoint.path
    if not query:
        return root
    return f"{root}?{query}"


def _format_query_number(number: Decimal) -> str:
    """Plain decimal the API's numeric parser accepts. No unit suffix."""
    integral = number.to_integral_value()
    if number == integral:
        return str(int(integral))
    text = format(number.normalize(), "f").rstrip("0").rstrip(".")
    if text and text not in {"0", "-0"}:
        return text
    return format(number.normalize(), "e")


def _fetch(url: str, transport: Transport, cache_dir: Path | None, rows_key: str) -> dict:
    if cache_dir is not None:
        cached = catalog_cache.load(cache_dir, url)
        if cached is not None:
            return _json_object(cached, rows_key)
    try:
        body = transport.get(url)
    except CatalogError:
        raise
    except OSError as exc:
        raise CatalogError(f"catalog request failed: {exc}") from exc
    if isinstance(body, str):
        raw = body.encode()
    elif isinstance(body, (bytes, bytearray)):
        raw = bytes(body)
    else:
        raise CatalogError("catalog transport returned non-bytes")
    payload = _json_object(raw, rows_key)
    if cache_dir is not None:
        catalog_cache.store(cache_dir, url, raw)
    return payload


def _json_object(body: bytes, rows_key: str) -> dict:
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CatalogError("jlcsearch returned non-JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get(rows_key), list):
        raise CatalogError(f"jlcsearch response missing {rows_key!r}")
    return data


def _candidate(row: object, endpoint: _Endpoint, wanted: Decimal | None, package: str) -> CatalogPart | None:
    if not isinstance(row, dict):
        return None
    if package and not _package_matches(package, row.get("package")):
        return None
    if wanted is not None and not _number_matches(wanted, row.get(endpoint.value_field)):
        return None
    if row.get("in_stock") is False:
        return None
    lcsc_id = _lcsc_id(row.get("lcsc"))
    stock = _stock(row.get("stock"))
    if lcsc_id is None or stock is None:
        return None
    maker_part = row.get("mfr")
    return CatalogPart(
        lcsc=lcsc_id,
        mpn=maker_part if isinstance(maker_part, str) else "",
        manufacturer=_manufacturer(row),
        package=row.get("package") if isinstance(row.get("package"), str) else package,
        value=_display_value(endpoint, row),
        stock=stock,
        basic=row.get("is_basic") is True,
        unit_price_usd=_price(row.get("price1")),
        source=_SOURCE,
    )


def _package_matches(wanted: str, got: object) -> bool:
    if not isinstance(got, str):
        return False
    return got.split("(", 1)[0].strip().casefold() == wanted.strip().casefold()


def _number_matches(wanted: Decimal, got: object) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    try:
        actual = Decimal(str(got))
    except InvalidOperation:
        return False
    if wanted == 0:
        return actual == 0
    span = max(abs(wanted), abs(actual), Decimal("1"))
    return abs(wanted - actual) <= Decimal("1e-6") * span


def _lcsc_id(raw: object) -> str | None:
    """Format the API's numeric id as C + digits. Do not invent one."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        digits = str(raw)
    elif isinstance(raw, float) and raw >= 0 and raw.is_integer():
        digits = str(int(raw))
    elif isinstance(raw, str):
        digits = raw.strip().upper()
        if digits.startswith("C"):
            digits = digits[1:]
    else:
        return None
    if not digits.isdigit():
        return None
    return "C" + digits


def _stock(raw: object) -> int | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if isinstance(raw, float) and not raw.is_integer():
        return None
    count = int(raw)
    if count <= 0:
        return None
    return count


def _price(raw: object) -> float:
    if isinstance(raw, bool) or raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return 0.0
    return 0.0


def _manufacturer(row: dict) -> str:
    for key in ("manufacturer", "mfr_name", "brand"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _display_value(endpoint: _Endpoint, row: dict) -> str:
    if endpoint.value_field is None:
        return ""
    raw = row.get(endpoint.value_field)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return ""
    try:
        number = Decimal(str(raw))
    except InvalidOperation:
        return ""
    return _format_engineering(number, endpoint.display_unit)


def _format_engineering(number: Decimal, unit: str) -> str:
    if number < 0:
        return ""
    if number == 0:
        return f"0{unit}"
    for scale, prefix in _SCALES:
        if number >= scale or prefix == "p":
            return f"{_trim(number / scale)}{prefix}{unit}"
    return ""


def _trim(number: Decimal) -> str:
    integral = number.to_integral_value()
    if abs(number - integral) <= Decimal("1e-9"):
        return str(int(integral))
    text = format(number.quantize(Decimal("0.000001")), "f")
    return text.rstrip("0").rstrip(".") or "0"


def _base_url(override: str | None) -> str:
    if override is not None:
        if not isinstance(override, str) or not override.strip():
            raise CatalogError("base_url must be a non-empty string")
        return override.strip()
    env = os.environ.get("REFLOW_CATALOG_BASE_URL", "").strip()
    return env or DEFAULT_BASE_URL


def _timeout() -> float:
    raw = os.environ.get("REFLOW_CATALOG_TIMEOUT", "20")
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise CatalogError(f"REFLOW_CATALOG_TIMEOUT is not a number: {raw!r}") from exc
    if timeout <= 0:
        raise CatalogError("REFLOW_CATALOG_TIMEOUT must be positive")
    return timeout


def _cache_dir(cache_dir: str | Path | None) -> Path:
    if cache_dir is not None:
        return Path(cache_dir)
    env = os.environ.get("REFLOW_CATALOG_CACHE", "").strip()
    if env:
        return Path(env)
    return Path(tempfile.gettempdir()) / "reflow" / "catalog"
