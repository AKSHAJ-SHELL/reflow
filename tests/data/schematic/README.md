# Schematic inputs (O-04)

Real boards from `reflow eval --repeat 3` run 20261028T161716Z (Sonnet 5.5), run 1 of each eval:
the attempt's `circuit.json`, `board.kicad_pcb` and `board.kicad_pro` from its build folder, and a
copy of the eval's `rules.toml` (its `[[part]]` names each chip's KiCad symbol). Unchanged.

- `mcp9808/`, `pcf8574/`, `at24c02/`: attempt 1, verify clean. Our schematic of each has 0 KiCad ERC
  errors and 0 warnings, `reflow check` on it is clean, and its nets are circuit.json's and the PCB's.
- `pcf8574/tscircuit.kicad_sch`: tscircuit's own export of the same board. KiCad ERC finds 21 errors
  and 87 warnings (wire ends 0.06–0.09 mm short of pins, off the 1.27 mm grid; invented symbol
  libraries), J2 and P0–P7 are disconnected, and GND is split in two.
- `led/`: attempt 1. tscircuit's LED has the anode on pad 1; KiCad's LED symbol has the cathode on
  pin 1, so the schematic is refused (the KT-0603R cathode pad is a TO CHECK line in expected.toml).
  No rules.toml: the eval has none.
- `ams1117/`: attempt 3. The board's U1 has pin 4 (the tab); KiCad's AMS1117-3.3 has 3 pins (V-12).

kicad-cli writes `.kicad_prl` next to what it opens, so tests work on copies.
