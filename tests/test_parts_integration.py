"""Integration: Plan.parts -> catalog.search -> resolve, on recorded jlcsearch data.

No network (docs/agents/04-testing-rules.md rule 7). The transport serves
responses recorded from jlcsearch on 2026-10-20 (first 20 rows each), keyed by
the exact URL the client builds. A URL with no recording fails the test, so a
change in what the client asks for is loud.

The recording is what jlcsearch really returned that day, including its
data problems (every 4.7k and 100nF 0402 row had stock null / in_stock false).
These tests assert the code's behaviour on that data, not the catalog's health.
"""
import json
from pathlib import Path

from reflow.contracts import Plan, from_dict
from reflow.parts.catalog import search
from reflow.parts.resolver import resolve

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data" / "jlcsearch_plan"
BASE = "https://jlcsearch.tscircuit.com"
RECORDED = {
    f"{BASE}/components/list.json": "components.json",
    f"{BASE}/capacitors/list.json?package=0402&capacitance=0.0000001": "capacitors_100n_0402.json",
    f"{BASE}/resistors/list.json?package=0402&resistance=4700": "resistors_4k7_0402.json",
}


class RecordedTransport:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str) -> bytes:
        self.urls.append(url)
        if url not in RECORDED:
            raise AssertionError(f"no recorded jlcsearch response for {url}")
        return (DATA / RECORDED[url]).read_bytes()


def _rows() -> dict[str, dict]:
    """Every recorded row by LCSC id, for checking what a winner actually is."""
    rows = {}
    for name in RECORDED.values():
        payload = json.loads((DATA / name).read_text(encoding="utf-8"))
        for items in payload.values():
            for row in items:
                rows[f"C{row['lcsc']}"] = row
    return rows


def _resolve_example_plan(tmp_path):
    plan = from_dict(Plan, json.loads((ROOT / "docs" / "examples" / "plan.json").read_text(encoding="utf-8")))
    spec = json.loads((ROOT / "docs" / "examples" / "spec.json").read_text(encoding="utf-8"))
    transport = RecordedTransport()
    candidates = {
        part.id: search(
            part.category, value=part.value, package=part.package,
            transport=transport, cache_dir=tmp_path / "cache",
        )
        for part in plan.parts
    }
    resolved = resolve(plan.parts, spec["named_parts"], candidates, fetched_at="2026-10-20T00:00:00Z")
    return plan, resolved, transport


def test_every_plan_part_lands_in_exactly_one_list(tmp_path):
    plan, resolved, _ = _resolve_example_plan(tmp_path)
    ids = [r.request_id for r in resolved.resolved] + [u.request_id for u in resolved.unresolved]
    assert sorted(ids) == sorted(part.id for part in plan.parts)


def test_out_of_stock_passives_are_unresolved_with_a_reason(tmp_path):
    """Recorded data has no in-stock 4.7k/100nF 0402 rows; nothing may be guessed."""
    _, resolved, _ = _resolve_example_plan(tmp_path)
    reasons = {u.request_id: u.reason for u in resolved.unresolved}
    for request_id in ("p2", "p3", "p4"):
        assert reasons.get(request_id) == "no catalog candidates", reasons


def test_named_ic_is_searched_by_its_part_number(tmp_path):
    """p1 is the user-named MCP9808. Its catalog query has to ask for MCP9808."""
    _, resolved, transport = _resolve_example_plan(tmp_path)
    assert any("MCP9808" in url for url in transport.urls), transport.urls
    assert [r.mpn for r in resolved.resolved if r.request_id == "p1"] == ["MCP9808"]


def test_connector_never_resolves_to_a_part_of_another_kind(tmp_path):
    """p5 is the I2C header. Picking an LED, diode, or resistor for it is wrong."""
    _, resolved, _ = _resolve_example_plan(tmp_path)
    rows = _rows()
    for part in resolved.resolved:
        if part.request_id != "p5":
            continue
        description = rows[part.lcsc]["description"]
        for wrong in ("LED", "Diode", "Resistor"):
            assert wrong not in description, f"p5 header resolved to {part.lcsc}: {description}"
