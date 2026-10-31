"""E-02: every eval folder is well-formed (evals/README.md).

Structure only: the contracts parse strictly, the named parts are the user's,
headers use D-6a's encoding, and expected.toml agrees with the plan. Whether
an expectation is electrically right is the human's check (status "checked").
"""
import json
import re
import tomllib
from collections import Counter
from pathlib import Path

import pytest

from reflow.checkpoint import reject_foreign_mpn
from reflow.contracts import PART_CATEGORIES, Plan, Spec, from_dict

EVALS = Path(__file__).resolve().parents[1] / "evals"
# Board folders have a spec.json; evals/results/ (written by `reflow eval`) is not a board.
BOARDS = sorted(p for p in EVALS.iterdir() if p.is_dir() and (p / "spec.json").is_file())
HEADER = re.compile(r"\d+x\d+")


def _load(folder: Path):
    spec = from_dict(Spec, json.loads((folder / "spec.json").read_text(encoding="utf-8")))
    plan = from_dict(Plan, json.loads((folder / "plan.json").read_text(encoding="utf-8")))
    expected = tomllib.loads((folder / "expected.toml").read_text(encoding="utf-8"))
    return spec, plan, expected


def test_there_are_at_least_five_boards():
    assert len(BOARDS) >= 5, [b.name for b in BOARDS]


@pytest.mark.parametrize("folder", BOARDS, ids=lambda p: p.name)
def test_spec_and_plan_are_strict_and_the_request_matches(folder):
    spec, plan, _ = _load(folder)
    assert (folder / "request.txt").read_text(encoding="utf-8").strip() == spec.request
    assert spec.confirmed is True
    for name in spec.named_parts:
        assert name in spec.request, f"named part {name!r} is not in the user's request"
    reject_foreign_mpn(plan, spec)


@pytest.mark.parametrize("folder", BOARDS, ids=lambda p: p.name)
def test_plan_parts_are_written_the_way_the_catalog_reads_them(folder):
    _, plan, _ = _load(folder)
    ids = [p.id for p in plan.parts]
    assert len(ids) == len(set(ids))
    in_blocks = [pid for block in plan.blocks for pid in block.part_ids]
    assert sorted(in_blocks) == sorted(ids), "each part id is in exactly one block"
    for part in plan.parts:
        assert part.category in PART_CATEGORIES
        if part.category == "connector":
            assert HEADER.fullmatch(part.value) and part.package.endswith("mm"), part.id
        elif part.mpn:
            assert part.package, f"{part.id}: a named part states its package so the resolver needn't ask"
        else:
            assert part.category in {"resistor", "capacitor"}, f"{part.id}: no local query for {part.category} without an mpn"
            assert part.value and part.package, part.id


@pytest.mark.parametrize("folder", BOARDS, ids=lambda p: p.name)
def test_expected_agrees_with_the_plan(folder):
    _, plan, expected = _load(folder)
    assert expected["status"] in {"draft", "checked"}
    if expected["status"] == "checked":
        assert expected["checked_by"].strip(), "a checked eval names who checked it"
    assert expected["outcome"] == "board"
    assert set(expected["nets"]) <= set(plan.nets)
    assert expected["parts"] == dict(Counter(p.category for p in plan.parts))
    assert isinstance(expected["violations"], list)
    kinds = {p.category for p in plan.parts}
    for net in expected.get("net", []):
        assert net["name"] in plan.nets, net["name"]
        assert net["source"].strip()
        for pin in net["includes"]:
            assert pin.split(".", 1)[0] in kinds, f"{net['name']}: {pin} names a kind of part the plan doesn't have"
    for item in expected.get("open", []):
        assert item["source"].strip()
        for pin in item["pins"]:
            assert pin.split(".", 1)[0] in kinds


# ---------------------------------------------------------------------------
# pin binding (V-12): every board with an IC names where its pin map comes from
# ---------------------------------------------------------------------------

def _rules(folder: Path):
    from reflow.project_rules import load_rules

    spec, _, _ = _load(folder)
    return load_rules(folder / spec.rules_file) if spec.rules_file else None


@pytest.mark.parametrize("folder", BOARDS, ids=lambda p: p.name)
def test_every_board_with_an_ic_names_its_pin_map(folder):
    spec, plan, _ = _load(folder)
    chips = [p for p in plan.parts if p.category in {"ic", "regulator"}]
    if not chips:
        return
    rules = _rules(folder)
    assert rules is not None, f"{folder.name}: rules_file is empty, so its IC can't be bound to a pin map"
    named = {(p.mpn) for p in rules.part}
    for chip in chips:
        assert chip.mpn in named, f"{folder.name}: no [[part]] for {chip.mpn}"
    for part in rules.part:
        assert part.ref.startswith("U") and part.symbol, part
        assert part.mpn in spec.named_parts, f"{part.mpn} is not a part the spec names"


@pytest.mark.skipif(__import__("reflow.cli", fromlist=["find_kicad_cli"]).find_kicad_cli() is None,
                    reason="kicad-cli not found (the installed KiCad symbol library is beside it)")
@pytest.mark.parametrize("folder", BOARDS, ids=lambda p: p.name)
def test_each_named_symbol_is_in_the_installed_kicad_library(folder, monkeypatch):
    from reflow.parts.pinmap import from_kicad_symbol

    monkeypatch.delenv("REFLOW_KICAD_SYMBOL_DIR", raising=False)
    rules = _rules(folder)
    _, _, expected = _load(folder)
    for part in (rules.part if rules else []):
        names = {p.name.upper() for p in from_kicad_symbol(part.symbol).pins}
        for net in expected.get("net", []) + expected.get("open", []):
            for pin in net.get("includes", net.get("pins", [])):
                kind, _, pin_name = pin.partition(".")
                if pin_name and kind in {"ic", "regulator"}:
                    assert pin_name.upper() in names, f"{folder.name}: expected.toml names {pin}, the symbol has {sorted(names)}"


@pytest.mark.skipif(__import__("reflow.cli", fromlist=["find_kicad_cli"]).find_kicad_cli() is None,
                    reason="kicad-cli not found (the installed KiCad symbol library is beside it)")
@pytest.mark.parametrize("folder", BOARDS, ids=lambda p: p.name)
def test_each_boards_codegen_rules_carry_its_pin_table(folder, monkeypatch):
    """The codegen prompt gets every [[part]]'s pinLabels, from the same symbol V-12 binds to."""
    import dataclasses

    from reflow.parts.pinmap import from_kicad_symbol
    from reflow.project_rules import rules_prompt_block

    monkeypatch.delenv("REFLOW_KICAD_SYMBOL_DIR", raising=False)
    spec, plan, _ = _load(folder)
    rules = _rules(folder)
    if rules is None:
        return
    lines = rules_prompt_block(dataclasses.replace(spec, rules_file=str(folder / spec.rules_file)), plan).splitlines()
    for part in rules.part:
        table = [line for line in lines if line.startswith(f"{part.ref} pinLabels, from the KiCad symbol {part.symbol}: ")]
        assert len(table) == 1, (folder.name, lines)
        for pin in from_kicad_symbol(part.symbol).pins:
            assert f'pin{pin.number}: "{pin.name}"' in table[0], (folder.name, pin)
