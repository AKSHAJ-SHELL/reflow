"""V-10: circuit.json -> Netlist (docs/04-contracts.md §5, DECISIONS V-1).

Inputs in tests/data/circuit_json/ were compiled with tsci 0.0.2768 from the
.tsx file of the same name. sensor_good is the full file; the others keep only
the source_* elements, which are all the loader reads. Expected nets below
are worked out by hand from the traces in each .tsx, not from the loader.
"""
import json
from pathlib import Path

import pytest

from reflow.circuit_netlist import CircuitJsonError, MergedNetsError, load_circuit_json
from reflow.rules import run_all

DATA = Path(__file__).resolve().parent / "data" / "circuit_json"

# sensor_good.tsx: U1 pinLabels pin1 SDA, pin2 SCL, pin3 A0, pin4 GND,
# pin5 A1, pin6 A2, pin7 ALERT, pin8 VDD; header J1, C1 decoupling, R1/R2 pull-ups.
SENSOR_GOOD_NETS = {
    "V3_3": {("J1", "1"), ("U1", "8"), ("C1", "1"), ("R1", "2"), ("R2", "2")},
    "GND": {("J1", "2"), ("U1", "4"), ("U1", "3"), ("U1", "5"), ("U1", "6"), ("C1", "2")},
    "SDA": {("J1", "3"), ("U1", "1"), ("R1", "1")},
    "SCL": {("J1", "4"), ("U1", "2"), ("R2", "1")},
    "unconnected-(U1-ALERT-Pad7)": {("U1", "7")},
}


def _members(nl) -> dict[str, set[tuple[str, str]]]:
    return {name: {(p.ref, p.pin) for p in pins} for name, pins in nl.nets.items()}


def _write(tmp_path: Path, elements) -> Path:
    path = tmp_path / "circuit.json"
    path.write_text(json.dumps(elements), encoding="utf-8")
    return path


def _component(cid: str, name: str, ftype: str = "simple_resistor") -> dict:
    return {"type": "source_component", "source_component_id": cid, "name": name, "ftype": ftype}


def _port(pid: str, cid: str, name: str, number: int, key: str | None = "k0") -> dict:
    port = {"type": "source_port", "source_port_id": pid, "source_component_id": cid,
            "name": name, "pin_number": number, "subcircuit_id": "s0"}
    if key is not None:
        port["subcircuit_connectivity_map_key"] = key
    return port


# ---------------------------------------------------------------------------
# connectivity from recorded boards
# ---------------------------------------------------------------------------

def test_sensor_good_nets_match_the_traces():
    nl = load_circuit_json(DATA / "sensor_good.circuit.json")
    assert _members(nl) == SENSOR_GOOD_NETS


def test_only_real_components_become_components():
    """Rails are nets, not parts (the .kicad_sch export turned them into V/GND parts)."""
    nl = load_circuit_json(DATA / "sensor_good.circuit.json")
    assert sorted(nl.components) == ["C1", "J1", "R1", "R2", "U1"]
    assert sorted(nl.components["U1"].pins) == [str(n) for n in range(1, 9)]


def test_each_pin_is_the_same_object_in_its_component_and_its_net():
    nl = load_circuit_json(DATA / "sensor_good.circuit.json")
    for name, pins in nl.nets.items():
        for pin in pins:
            assert nl.components[pin.ref].pins[pin.pin] is pin
            assert pin.net == name


def test_an_unnamed_net_is_named_after_its_first_pin():
    """sensor_series_cap.tsx wires U1.VDD to C1.pin2 with no net name."""
    nl = load_circuit_json(DATA / "sensor_series_cap.circuit.json")
    members = _members(nl)
    assert members["Net-(C1-pin2)"] == {("C1", "2"), ("U1", "8")}
    assert members["V3_3"] == {("J1", "1"), ("C1", "1"), ("R1", "2"), ("R2", "2")}
    assert nl.net_of("U1", "8") == "Net-(C1-pin2)"


def test_pin_names_are_the_raw_port_names_and_types_are_left_unknown():
    """The loader reports labels as written; pin kinds come only from a pin map (V-12)."""
    nl = load_circuit_json(DATA / "sensor_good.circuit.json")
    u1 = nl.components["U1"].pins
    assert [u1[str(n)].name for n in range(1, 9)] == ["SDA", "SCL", "A0", "GND", "A1", "A2", "ALERT", "VDD"]
    assert nl.components["R1"].pins["1"].name == "pin1"
    assert {p.pintype for pins in nl.nets.values() for p in pins} == {""}


def test_loading_is_deterministic():
    first = load_circuit_json(DATA / "sensor_good.circuit.json")
    second = load_circuit_json(DATA / "sensor_good.circuit.json")
    assert list(first.nets) == sorted(first.nets)
    assert [(n, [(p.ref, p.pin) for p in ps]) for n, ps in first.nets.items()] == \
           [(n, [(p.ref, p.pin) for p in ps]) for n, ps in second.nets.items()]


# ---------------------------------------------------------------------------
# the existing rules, run on circuit.json instead of the .kicad_sch export
# ---------------------------------------------------------------------------

def test_rules_find_nothing_on_the_good_sensor():
    nl = load_circuit_json(DATA / "sensor_good.circuit.json")
    assert run_all(nl) == []


def test_rules_find_both_missing_pullups():
    nl = load_circuit_json(DATA / "sensor_no_pullups.circuit.json")
    found = sorted((v.rule_id, tuple(v.nets)) for v in run_all(nl))
    assert found == [("i2c.missing_pullup", ("SCL",)), ("i2c.missing_pullup", ("SDA",))]


# ---------------------------------------------------------------------------
# strictness: malformed or ambiguous input raises
# ---------------------------------------------------------------------------

def test_shorted_named_nets_raise_and_name_both():
    """sensor_shorted_rails.tsx traces net.V3_3 to net.GND. Never pick one name silently."""
    with pytest.raises(MergedNetsError, match="GND.*V3_3|V3_3.*GND"):
        load_circuit_json(DATA / "sensor_shorted_rails.circuit.json")


def test_merged_nets_error_is_a_circuit_json_error():
    assert issubclass(MergedNetsError, CircuitJsonError)


@pytest.mark.parametrize("text", ["not json", '{"type": "source_port"}', "[1, 2]", '[{"name": "x"}]'])
def test_malformed_files_raise(tmp_path, text):
    path = tmp_path / "circuit.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(CircuitJsonError):
        load_circuit_json(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(CircuitJsonError):
        load_circuit_json(tmp_path / "nope.circuit.json")


@pytest.mark.parametrize("drop", ["source_port_id", "source_component_id", "name", "pin_number"])
def test_port_missing_a_required_key_raises(tmp_path, drop):
    port = _port("p1", "c1", "pin1", 1)
    del port[drop]
    with pytest.raises(CircuitJsonError, match=drop):
        load_circuit_json(_write(tmp_path, [_component("c1", "R1"), port]))


@pytest.mark.parametrize("drop", ["source_component_id", "name"])
def test_component_missing_a_required_key_raises(tmp_path, drop):
    comp = _component("c1", "R1")
    del comp[drop]
    with pytest.raises(CircuitJsonError, match=drop):
        load_circuit_json(_write(tmp_path, [comp]))


def test_port_on_an_unknown_component_raises(tmp_path):
    with pytest.raises(CircuitJsonError, match="c9"):
        load_circuit_json(_write(tmp_path, [_component("c1", "R1"), _port("p1", "c9", "pin1", 1)]))


def test_duplicate_reference_raises(tmp_path):
    elements = [_component("c1", "R1"), _component("c2", "R1")]
    with pytest.raises(CircuitJsonError, match="R1"):
        load_circuit_json(_write(tmp_path, elements))


def test_duplicate_pin_number_raises(tmp_path):
    elements = [_component("c1", "R1"), _port("p1", "c1", "pin1", 1), _port("p2", "c1", "pinA", 1)]
    with pytest.raises(CircuitJsonError, match="R1"):
        load_circuit_json(_write(tmp_path, elements))


def test_one_net_name_on_two_separate_nets_raises(tmp_path):
    elements = [
        _component("c1", "R1"), _port("p1", "c1", "pin1", 1, "k0"), _port("p2", "c1", "pin2", 2, "k1"),
        {"type": "source_net", "source_net_id": "n0", "name": "SDA", "subcircuit_connectivity_map_key": "k0"},
        {"type": "source_net", "source_net_id": "n1", "name": "SDA", "subcircuit_connectivity_map_key": "k1"},
    ]
    with pytest.raises(CircuitJsonError, match="SDA"):
        load_circuit_json(_write(tmp_path, elements))


def test_more_than_one_subcircuit_raises(tmp_path):
    second = _port("p2", "c1", "pin2", 2, "k1")
    second["subcircuit_id"] = "s1"
    elements = [_component("c1", "R1"), _port("p1", "c1", "pin1", 1), second]
    with pytest.raises(CircuitJsonError, match="subcircuit"):
        load_circuit_json(_write(tmp_path, elements))
