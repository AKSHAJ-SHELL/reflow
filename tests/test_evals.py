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
