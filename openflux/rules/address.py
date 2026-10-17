import re
from openflux.violation import Violation

ADDR_NAME = re.compile(r"A\d")          # also consider names containing ADDR / ADR

def is_address_pin(name: str) -> bool:

    n = name.upper()
    return bool(ADDR_NAME.fullmatch(n) or "ADDR" in n or "ADR" in n)
  # fullmatch A\d, or "ADDR"/"ADR" in name.upper()

def check(nl, pcb=None):
    out = []
    for ref, comp in nl.components.items():
        if comp.prefix != "U":
            continue
        names = {p.name.upper() for p in comp.pins.values()}
        # 1. skip parts that aren't I²C devices (no SDA/SCL pin)
        if not ("SDA" in names and "SCL" in names):
            continue
        
        # 2. for each address pin: is its net unconnected, or is it alone on the net?

        for pin in comp.pins.values():
            if not is_address_pin(pin.name):
                continue
            pins = nl.pins_on(pin.net)
            if nl.is_unconnected(pin.net) or len(pins) == 1:
                message = f"Address pin {pin.name} (pin {pin.pin}) of {ref} isn't connected to anything."
                why = ("An address pin is a digital input. Left floating, it drifts to an undefined "
                        "level, so the chip can answer at the wrong I²C address, change address "
                        "while running, or collide with another device on the bus.")
                fix_hint = f"Tie {ref} {pin.name} to GND or the supply. The level sets the address; check the datasheet's address table."
                out.append(Violation("address.floating", "error", message, why, fix_hint,
                                        refs=[ref], nets=[pin.net]))
        # 3. if so, append Violation("address.floating", "error", message, why, fix_hint,
        #                            refs=[ref], nets=[net])


    return out