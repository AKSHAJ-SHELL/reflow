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


def bus_supplies(nl, net):
    """Supply nets of the ICs on an I²C line: {net: [ic refs]}, from their power_in pins.

    Empty when no IC on the line has a typed power pin (an unbound board), so the
    pull-up rail check can't judge and stays quiet.
    """
    supplies = {}
    for p in nl.pins_on(net):
        ic = nl.components.get(p.ref)
        if ic is None or ic.prefix != "U":
            continue
        for pin in ic.pins.values():
            if pin.pintype == "power_in" and not is_ground(pin.net) and not nl.is_unconnected(pin.net):
                supplies.setdefault(pin.net, []).append(ic.ref)
    return supplies


def cap_bridges(nl, rail, supplies):
    """A capacitor sits between the rail and a chip's supply: decoupling.series reports that."""
    for p in nl.pins_on(rail):
        cap = nl.components.get(p.ref)
        if cap is not None and cap.prefix == "C" and other_pin_net(cap, p.pin) in supplies:
            return True
    return False


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

        # A pull-up only works to a rail that powers a chip on the bus (draft, agent-written
        # at the human's request 2026-10-31; the human reviews it line by line).
        supplies = bus_supplies(nl, net)
        stray = [(r, far) for r, far in pullups
                 if supplies and far not in supplies and not cap_bridges(nl, far, supplies)]
        if stray:
            refs = [r for r, _ in stray]
            rails = sorted({far for _, far in stray})
            powered = ", ".join(f"{s} ({'/'.join(sorted(set(ics)))})" for s, ics in sorted(supplies.items()))
            out.append(Violation(
                rule_id="i2c.pullup_rail",
                severity="error",
                message=f"I²C {kind} line ({net}) is pulled up to {', '.join(rails)}, "
                        f"which doesn't power any chip on the bus.",
                why="The pull-up sets the line's high level. If its rail isn't the chips' "
                    "supply, it may be unpowered, so the line never goes high, or at another "
                    "voltage than the chips expect.",
                fix_hint=f"Move the far end of {', '.join(refs)} from {', '.join(rails)} to the "
                         f"chips' supply: {powered}. Or power the chips from {', '.join(rails)}.",
                refs=refs + sorted({ic for ics in supplies.values() for ic in ics}),
                nets=[net] + rails,
            ))
    return out
