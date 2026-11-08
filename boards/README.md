# boards/

Sample board projects.

- `opi-power-demo/`: an INA226 power monitor for an Orange Pi 5 Plus, made with `reflow tui` on 2026-11-06. Its `spec.json`, `plan.json` and `rules.toml` are here. The datasheet, the TUI's state and the run folder stay out of git. It reached a verifier-clean schematic; it hasn't been routed, exported or built, and its `rules.toml` wasn't enforced (R-10).

tscircuit sample projects. `blinky/` was a toolchain smoke test: it compiles and exports, but **J1 is not wired and R1.pin1 floats**, so it is not a valid board. Don't use it as a reference design or fixture.
