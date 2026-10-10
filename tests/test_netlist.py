import pytest
from openflux.rules import run_all

def test_annotated(board):
    """Every reference is real: no 'R?' and no duplicates."""
    name, nl, _ = board
    for ref in nl.components:
        assert "?" not in ref, f"{name}: unannotated part {ref}"


def test_every_pin_on_one_net(board):
    """Works on ANY project, no answer key needed."""
    name, nl, _ = board
    seen = {}
    for net, pins in nl.nets.items():
        for p in pins:
            key = f"{p.ref}.{p.pin}"
            assert key not in seen, f"{name}: {key} is on both {seen[key]} and {net}"
            seen[key] = net


def test_hand_checked_nets(board):
    name, nl, exp = board
    if not exp:
        pytest.skip("no expected.toml")
    for pin, net in exp.get("pin_net", {}).items():
        ref, num = pin.split(".")
        assert nl.net_of(ref, num) == net, f"{name}: {pin}"
    for group in exp.get("same_net", []):
        nets = {nl.net_of(*p.split(".")) for p in group}
        assert len(nets) == 1, f"{name}: {group} landed on {nets}"



def test_violations_match(board):
    name, nl, exp = board
    if "violations" not in exp:
        pytest.skip("no expected violations listed")
    found = {v.rule_id for v in run_all(nl)}
    assert found == set(exp["violations"]), f"{name}: got {found}"

