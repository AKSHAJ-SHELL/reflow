"""Catalog queries on the local jlcparts snapshot.  OWNER: AGENT (task P-05, DECISIONS D-6a).

Contract
--------
    search(request: PartRequest, *, db_path=None) -> list[CatalogPart]
    reflow_category(jlc_category, jlc_subcategory) -> str

Reads `cache.sqlite3` (installed by `reflow parts update`) read-only and
returns every in-stock row that fits the request, ordered by LCSC id. It does
not rank or pick: that is the resolver's job (P-02).

Queries, by what the request gives:

- `mpn` set (only ever a `Spec.named_parts` string, checked at the plan gate):
  every row whose MPN starts with it, case-insensitively, in any category.
  Matching a family name to one orderable part is the resolver's job (P-02b).
- resistor: JLC "Resistors" in the fixed-resistor subcategories, `value`
  compared as a number with the row's Resistance, `tolerance` at least as tight.
- capacitor: JLC "Capacitors", `value` compared with Capacitance, `voltage` as a
  minimum rating, `tolerance` at least as tight.
- connector: pin headers only, written as D-6a (a) says: `value` "RxC"
  (rows x pins per row) and `package` the pitch, e.g. "1x4" + "2.54mm".
  Right-angle headers (package marked 弯) are left out.
- anything else without an `mpn`: CatalogError, so nothing is guessed.

`package` must match the row's package (case-insensitive; a parenthetical
suffix is ignored) except for connectors, where it is the pitch.

Each CatalogPart carries `category` from `reflow_category` on the row's own
JLC category, so the resolver can reject a candidate of the wrong kind
(P-02b), plus the row's own `fetched_at`. Rows the snapshot leaves
uncategorised map to "other". Rows with no stock are never returned.

The database comes from `db_path`, else `reflow.parts.snapshot.default_db_path()`.

Must never
----------
- write to the database, or fetch anything,
- invent or complete a part number (an `mpn` is only matched as a prefix),
- return a row of a kind the query did not ask for.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from reflow.contracts import PartRequest
from reflow.parts.catalog import CatalogError, CatalogPart, parse_value
from reflow.parts.snapshot import FORMAT, default_db_path

SOURCE = "jlcparts"

_RESISTOR_SUBCATEGORIES = (
    "Chip Resistor - Surface Mount",
    "Through Hole Resistors",
    "High Precision & Low TCR SMD Resistors",
    "Metal Film Resistor (TH)",
    "Metal Oxide Resistors",
    "Carbon Film Resistors",
)
_PIN_HEADERS = ("Pin Headers",)
_HEADER = re.compile(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*")

_IC_CATEGORIES = {
    "Embedded Processors & Controllers", "Sensors", "Memory", "Clock/Timing", "Data Acquisition",
    "Interface", "Amplifiers/Comparators", "Logic", "Motor Driver ICs", "LED Drivers",
    "Magnetic Sensors", "Signal Isolation Devices", "Logic ICs",
    "Single Chip Microcomputer/Microcontroller", "ADC/DAC/Data Conversion",
    "Communication Interface Chip/UART/485/232", "Interface ICs", "Operational Amplifier/Comparator",
    "RTC/Clock Chip", "Nixie Tube Driver/LED Driver", "Amplifiers", "Driver ICs", "Analog ICs",
    "Embedded Peripheral ICs", "Data Converters", "Clock And Timing", "Communication Interface Chip",
}
_POWER_CATEGORIES = {"Power Management (PMIC)", "Power Management ICs", "Power Supply Chip", "Power Management"}
_SIMPLE_CATEGORIES = {
    "Capacitors": "capacitor",
    "Connectors": "connector",
    "Diodes": "diode",
    "Inductors, Coils, Chokes": "inductor",
    "Inductors/Coils/Transformers": "inductor",
    "Inductors & Chokes & Transformers": "inductor",
    "Transistors/Thyristors": "transistor",
    "Transistors": "transistor",
    "Triode/MOS Tube/Transistor": "transistor",
    "Crystals, Oscillators, Resonators": "crystal",
    "Crystals/Oscillators/Resonators": "crystal",
    "Crystal Oscillator/Oscillator/Resonator": "crystal",
    "Crystals": "crystal",
    "Resonators/Oscillators": "crystal",
    "Switches": "switch",
    "Key/Switch": "switch",
    "switches": "switch",
}
_COLUMNS = "lcsc, mfr, manufacturer, package, stock, library_type, price, attributes, category, subcategory, fetched_at"


def reflow_category(jlc_category: str, jlc_subcategory: str) -> str:
    """The reflow PART_CATEGORIES value for a JLC category; "other" when unsure."""
    if jlc_category == "Resistors":
        return "resistor" if jlc_subcategory in _RESISTOR_SUBCATEGORIES else "other"
    if jlc_category in _SIMPLE_CATEGORIES:
        return _SIMPLE_CATEGORIES[jlc_category]
    if jlc_category == "Optoelectronics":
        return "led" if "LED" in jlc_subcategory else "other"
    if jlc_category in _POWER_CATEGORIES:
        sub = jlc_subcategory.upper()
        return "regulator" if ("REGULATOR" in sub or "LDO" in sub or "DC-DC" in sub) else "ic"
    if jlc_category in _IC_CATEGORIES:
        return "ic"
    return "other"


def search(request: PartRequest, *, db_path=None) -> list[CatalogPart]:
    path = Path(db_path) if db_path is not None else default_db_path()
    with _open(path) as db:
        if request.mpn.strip():
            rows = _by_mpn(db, request)
        elif request.category == "resistor":
            rows = _passives(db, request, "Resistors", "Resistance", _RESISTOR_SUBCATEGORIES)
        elif request.category == "capacitor":
            rows = _passives(db, request, "Capacitors", "Capacitance", None)
        elif request.category == "connector":
            rows = _headers(db, request)
        else:
            raise CatalogError(
                f"no local catalog query for {request.category} parts yet ({request.id}); "
                "name the part number in the spec or pass --parts"
            )
    return [_candidate(row) for row in sorted(rows, key=lambda r: r["lcsc"])]


class _open:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise CatalogError(f"no parts database at {self.path}; run `reflow parts update`")
        try:
            self.db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            self.db.row_factory = sqlite3.Row
            row = self.db.execute("select value from meta where key = 'format'").fetchone()
        except sqlite3.Error as exc:
            raise CatalogError(f"{self.path} is not a jlcparts database: {exc}") from exc
        if row is None or row[0] != FORMAT:
            self.db.close()
            raise CatalogError(f"{self.path} is format {row[0] if row else 'unknown'!r}, expected {FORMAT}")
        return self.db

    def __exit__(self, *exc) -> None:
        self.db.close()


def _by_mpn(db: sqlite3.Connection, request: PartRequest) -> list[sqlite3.Row]:
    prefix = request.mpn.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = db.execute(
        f"select {_COLUMNS} from jlc_components where stock > 0 and mfr like ? escape '\\'",
        (prefix + "%",),
    ).fetchall()
    return [row for row in rows if _package_fits(request.package, row["package"])]


def _passives(db: sqlite3.Connection, request: PartRequest, jlc_category: str, attribute: str,
              subcategories: tuple[str, ...] | None) -> list[sqlite3.Row]:
    if not request.value.strip():
        raise CatalogError(f"{request.id}: a {request.category} request needs a value")
    wanted = parse_value(request.value)
    tolerance = _percent(request.tolerance) if request.tolerance.strip() else None
    voltage = _number(request.voltage, "V") if request.voltage.strip() else None
    sql = f"select {_COLUMNS} from jlc_components where category = ? and stock > 0"
    args: list = [jlc_category]
    if subcategories:
        sql += f" and subcategory in ({','.join('?' * len(subcategories))})"
        args.extend(subcategories)
    found = []
    for row in db.execute(sql, args):
        if not _package_fits(request.package, row["package"]):
            continue
        attrs = _attributes(row)
        if _value(attrs.get(attribute)) != wanted:
            continue
        if tolerance is not None:
            have = _percent(attrs.get("Tolerance", ""))
            if have is None or have > tolerance:
                continue
        if voltage is not None:
            rating = _number(attrs.get("Voltage Rating", ""), "V")
            if rating is None or rating < voltage:
                continue
        found.append(row)
    return found


def _headers(db: sqlite3.Connection, request: PartRequest) -> list[sqlite3.Row]:
    shape = _HEADER.fullmatch(request.value)
    pitch = _number(request.package, "MM")
    if shape is None or pitch is None:
        raise CatalogError(
            f"{request.id}: a header is written value '1x4' (rows x pins per row) and package '2.54mm' "
            f"(D-6a); got value {request.value!r}, package {request.package!r}"
        )
    rows, per_row = int(shape.group(1)), int(shape.group(2))
    found = []
    for row in db.execute(
        f"select {_COLUMNS} from jlc_components where category = 'Connectors' and stock > 0 "
        f"and subcategory in ({','.join('?' * len(_PIN_HEADERS))})", _PIN_HEADERS,
    ):
        if "弯" in row["package"]:
            continue
        attrs = _attributes(row)
        if (_number(attrs.get("Pitch", ""), "MM") == pitch
                and _count(attrs.get("Number of Rows", "")) == rows
                and _count(attrs.get("Number of Pins", "")) == rows * per_row):
            found.append(row)
    return found


def _candidate(row: sqlite3.Row) -> CatalogPart:
    attrs = _attributes(row)
    return CatalogPart(
        lcsc=f"C{row['lcsc']}",
        mpn=row["mfr"],
        manufacturer=row["manufacturer"],
        package=row["package"],
        value=str(attrs.get("Resistance") or attrs.get("Capacitance") or ""),
        stock=int(row["stock"]),
        basic=row["library_type"] == "base",
        unit_price_usd=_first_price(row["price"]),
        source=SOURCE,
        category=reflow_category(row["category"], row["subcategory"]),
        fetched_at=datetime.fromtimestamp(int(row["fetched_at"]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


# ---------------------------------------------------------------------------
# parsing the snapshot's strings
# ---------------------------------------------------------------------------

def _attributes(row: sqlite3.Row) -> dict:
    try:
        data = json.loads(row["attributes"] or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _package_fits(wanted: str, got: str) -> bool:
    if not wanted.strip():
        return True
    return got.split("(", 1)[0].strip().casefold() == wanted.strip().casefold()


def _value(text) -> Decimal | None:
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        return parse_value(text)
    except (CatalogError, InvalidOperation):
        return None


def _number(text: str, unit: str) -> Decimal | None:
    cleaned = text.strip().upper().replace(" ", "")
    if cleaned.endswith(unit):
        cleaned = cleaned[: -len(unit)]
    try:
        return Decimal(cleaned) if cleaned else None
    except InvalidOperation:
        return None


def _percent(text: str) -> Decimal | None:
    return _number(text.replace("±", "").replace("+/-", ""), "%")


def _count(text: str) -> int | None:
    digits = text.strip().upper().removesuffix("P")
    return int(digits) if digits.isdigit() else None


def _first_price(text: str) -> float:
    """'1-999:0.0023,1000-2999:0.0018,…' -> 0.0023 (the smallest-quantity tier)."""
    first = (text or "").split(",", 1)[0]
    try:
        return float(first.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 0.0
