# 05 · Verifier rules

All rules are **HUMAN-owned**. Agents may read them, run them and write plumbing around them; agents never edit `reflow/rules/`.

## Interface

```python
# reflow/rules/<family>.py
def check(nl: Netlist, pcb=None) -> list[Violation]: ...
```

`reflow.rules.run_all(netlist, pcb=None)` imports every module in `reflow/rules/` that has `check` and concatenates the results. A rule that crashes takes the whole run down. That is intended: a silently skipped rule is worse than a loud crash.

Every rule follows the same shape:

1. Find the pins that matter (by `pintype` or `Pin.name`).
2. Look at what else is on that net (by component prefix).
3. Follow two-terminal parts to their other leg (`other_pin_net`).
4. Judge, then emit a `Violation` with `why` (for people) and `fix_hint` (for the model).

## Catalog

| Rule ID | Catches | Reads | Bad fixture | Status |
|---|---|---|---|---|
| `decoupling.series` | Cap in series with an IC supply pin: the chip never powers on | netlist | `bad_series_cap`, `real_series_cap` | built |
| `decoupling.missing` | IC power pin with no cap to ground | netlist | none yet | built, needs fixture |
| `i2c.missing_pullup` | SDA/SCL with no pull-up | netlist | `bad_no_pullups` | built |
| `i2c.duplicate_pullup` | More than one pull-up on a line (warning) | netlist | none yet | built, needs fixture |
| `address.floating` | I²C address pin (A0–A2, ADDR) left unconnected | netlist + pin names | `bad_floating_addr` | built |
| `parts.provenance` | A part number in the design that came from neither the resolver nor the user | netlist + `ResolvedParts` + `Spec` | `bad_hallucinated_mpn` (to make) | planned (R-03) |
| `scope.high_speed` | USB/DDR/Ethernet/RF nets present, so autorouting is refused | netlist net names | `bad_usb_route` (to make) | planned (R-04) |
| `led.no_limiter` | LED across a supply with no series resistor | netlist | `bad_led_no_resistor` (to make) | planned (R-01) |
| `two_terminal.open` / `.shorted` | R/C/L/LED with a dangling pin, or both pins on one net | netlist | to make | planned (R-02) |

`parts.provenance` needs context the current interface doesn't pass (resolved parts, spec). Extending `check()` / `run_all()` with an optional context argument is a HUMAN decision (task R-05); the change must keep every existing rule working unchanged.

## Good fixtures (false-positive guards)

`blinky_good`, `sensor_good`, `real_good` must stay at **zero violations** for every rule, forever.

## Adding a rule (process)

1. `tools/new_fixture.sh <good> <bad_name>`, plant **one** bug in KiCad, write `expected.toml`.
2. Run `pytest -q`: the new bad fixture must fail first.
3. Write the rule.
4. `pytest -q`: all green, every good fixture still clean.
5. Fail on purpose: `return []` at the top of `check()`, confirm red, remove.
6. Commit rule + fixture together.

## KiCad quirks the rules rely on

- Pin functions carry a pin-number suffix (`SDA_1`); use `Pin.name`.
- A no-connect-flagged pin's `pintype` gains `+no_connect` and its net is `unconnected-(...)`, same as a forgotten pin.
- Two power symbols on one net merge into a single name (how rail shorts show up).
- ERC reasons about pin types, not intent, so it can't tell a series cap from a parallel one. On real boards it may report a *symptom* (`power_pin_not_driven`); never claim it is silent without running it.
