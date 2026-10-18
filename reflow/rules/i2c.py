from reflow.violation import Violation
from reflow.rules.decoupling import is_ground, other_pin_net


def find_i2c_nets(nl):
    """Return {net_name: "SDA" or "SCL"} for every I²C line an IC uses."""
    buses = {}
    for comp in nl.components.values():
        if comp.prefix != "U":
            continue
        for pin in comp.pins.values():
            func = pin.name.upper()
            for kind in ("SDA", "SCL"):
                if kind in func and not nl.is_unconnected(pin.net):
                    buses[pin.net] = kind
    return buses


def check(nl, pcb=None):
    out = []
    buses = find_i2c_nets(nl)

    for net, kind in buses.items():
        pullups = []
        for p in nl.pins_on(net):
            res = nl.components.get(p.ref)
            if res is None or res.prefix != "R":
                continue
            far = other_pin_net(res, p.pin)
            if far and not is_ground(far) and far not in buses and not nl.is_unconnected(far):
                pullups.append((res.ref, far))

        if not pullups:
            out.append(Violation(
                rule_id="i2c.missing_pullup",
                severity="error",
                message=f"I²C {kind} line ({net}) has no pull-up resistor.",
                why="I²C pins can only pull the line low. Without a resistor pulling it "
                    "high, the line never returns to 1 and nothing on the bus can talk.",
                fix_hint=f"Add a 4.7k resistor from {net} to the logic supply (e.g. +3.3V).",
                nets=[net],
            ))
        elif len(pullups) > 1:
            refs = [r for r, _ in pullups]
            out.append(Violation(
                rule_id="i2c.duplicate_pullup",
                severity="warning",
                message=f"I²C {kind} line ({net}) has {len(pullups)} pull-ups: {', '.join(refs)}.",
                why="Pull-ups in parallel combine into a smaller resistance, so every device "
                    "has to sink more current to pull the line low, which can exceed its limits.",
                fix_hint=f"Keep one pull-up on {net} and remove the others.",
                refs=refs,
                nets=[net],
            ))
    return out
