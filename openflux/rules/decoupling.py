from openflux.violation import Violation

GROUND_NAMES = {"GND", "VSS", "AGND", "DGND", "GNDA", "GNDD", "PGND"}


def is_ground(net: str) -> bool:
    return net.upper().lstrip("/") in GROUND_NAMES


def other_pin_net(cap, pin_number):
    for num, p in cap.pins.items():
        if num != pin_number:
            return p.net
    return None


def check(nl, pcb=None):
    out = []
    for ic in nl.components.values():
        if ic.prefix != "U":
            continue
        for pin in ic.pins.values():
            # only power pins that aren't ground
            if pin.pintype != "power_in" or is_ground(pin.net):
                continue

            # sort every cap on this power net into two piles
            ground_caps, bridge_caps = [], []
            for p in nl.pins_on(pin.net):
                cap = nl.components.get(p.ref)
                if cap is None or cap.prefix != "C":
                    continue
                far = other_pin_net(cap, p.pin)
                if far is None:
                    continue
                if is_ground(far):
                    ground_caps.append(cap.ref)
                else:
                    bridge_caps.append((cap.ref, far))

            if ground_caps:
                continue  # properly decoupled

            where = f"{ic.ref}.{pin.pin}"
            if bridge_caps:
                cap_ref, far = bridge_caps[0]
                out.append(Violation(
                    rule_id="decoupling.series",
                    severity="error",
                    message=f"{cap_ref} sits in series between {far} and {where}; "
                            f"{ic.ref} only gets power through a capacitor, which blocks DC.",
                    fix_hint=f"Connect {where} directly to {far}, then rewire {cap_ref} "
                             f"so one pin is on {far} and the other is on GND.",
                    refs=[cap_ref, ic.ref],
                    nets=[pin.net, far],
                ))
            else:
                out.append(Violation(
                    rule_id="decoupling.missing",
                    severity="error",
                    message=f"{where} ({pin.net}) has no decoupling capacitor to ground.",
                    fix_hint=f"Add a 100nF capacitor with one pin on {pin.net} and the "
                             f"other on GND, placed right next to {ic.ref}.",
                    refs=[ic.ref],
                    nets=[pin.net],
                ))
    return out