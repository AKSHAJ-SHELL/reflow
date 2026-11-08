# fixtures/: boards with known answers (OWNER: HUMAN)

Each folder is a KiCad project (`<name>.kicad_sch/.kicad_pro/.kicad_pcb`) plus `expected.toml`:

```toml
violations = ["decoupling.series"]      # exact set of rule IDs; [] for good boards
pin_net  = { "U1.4" = "GND" }           # optional hand-checked nets
same_net = [["J1.2", "U1.1"]]           # optional
```

Good: `blinky_good`, `sensor_good`. Bad (one planted bug each): `bad_series_cap`, `bad_no_pullups`, `bad_floating_addr`.

**Make one:** `tools/new_fixture.sh <src> <dst>`, open via the `.kicad_pro`, plant one bug, write `expected.toml`.

**Must never:** be created, edited or deleted by an agent; contain more than one planted bug; be opened by double-clicking the `.kicad_sch` (creates "Untitled" files).
