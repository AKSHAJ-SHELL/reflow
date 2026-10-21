# V-1 · Verify `circuit.json` against human-verified ground truth

Status: **ACCEPTED** 2026-10-20 by the human (proposed by agent, Claude). Part (b) is **amended by V-2**: IC pin maps come from vendor pin data, then the KiCad symbol library, with a signed card only as an override. Where this text says "no verified card", read "no trusted pin map". Binding text: `DECISIONS.md`.

Files in this proposal:

| File | What | Who applies it |
|---|---|---|
| this file | the decision and the evidence | — |
| `V-1-contract.patch` | contract change: `contracts.py`, `tests/test_contracts.py` (frozen lists), `docs/04`, `docs/02`, `docs/06`, new `docs/examples/part_card.json` | agent, in **one commit**, after acceptance |
| `V-1-loop-HUMAN.patch` | one line in `reflow/harness/loop.py` (HUMAN-owned): pass `circuit_json` instead of `kicad_sch` to the verifier | **the human** |
| `V-1-draft-card-MCP9808.toml` | the first card, as a draft (`verified_by = ""`) | the human checks and signs it |

Both patches were applied together in a throwaway worktree: `tests/test_contracts.py` 51 passed, full `pytest -q` 229 passed plus 1 failed (the pre-existing live jlcsearch test). Breaking the example card (a bad pin kind, then an unknown field) turned the contract tests red both times.

---

## 1 · Problem

1. **The `.kicad_sch` that tscircuit exports has wrong connectivity** (REVIEW.md §9). It splits traced pins across nets, turns rails into fake components, and types every pin `passive`. The verifier both misses bugs and invents them.
2. **The verifier trusts the AI's pin labels.** Whichever file it reads, the rules learn which pin is "VDD" or "SDA" from `pinLabels` in the TSX the model wrote. If the label is wrong, the copper goes to the wrong physical pin, and a correctly labelled lie passes.

   This already happened in this repo: the `sensor_*.tsx` test inputs (written by an agent) put A0 on pin 3. The MCP9808 datasheet says pin 3 is Alert. Third-party pinouts found on the web also disagree with each other.
3. **Power pins are only known if the AI declares them** (`pinAttributes requiresPower`). If the declaration is missing, the decoupling rules have nothing to check and pass silently.
4. **No rule cites a source.** `docs/05-verifier-rules.md` has no datasheet or spec references.

## 2 · Decision asked

**V-1a · Input.** `reflow design` verifies `CompileResult.circuit_json`, the file `tsci` builds first, before the KiCad renders. It is never `.kicad_sch`. `reflow check` keeps reading KiCad schematics for hand-made boards. Both build the same `Netlist` type and run the same rules.

**V-1b · Ground truth for parts: human-verified part cards.** Each IC family and package gets one `PartCard`: every pin's number, datasheet name and kind, plus a `Citation` (document, table, page). Cards live in a new top-level `cards/` folder and are **HUMAN-owned like `fixtures/`**. A card with `verified_by = ""` is a draft, and the verifier refuses it.

**V-1c · Binding: the AI's labels are never trusted.** For each IC in `circuit.json`:

1. Take its LCSC id from `supplier_part_numbers.jlcpcb`. It must equal a `ResolvedParts` row, so it came from the resolver, not the model.
2. Look up the verified card for that LCSC id. No verified card → verify error `parts.no_card`.
3. Rename every pin by **physical pin number** from the card, and set `pintype` from the card's kind (`power`/`ground` → `power_in`).
4. A TSX label that differs from the card → verify error `pinout.mismatch`, whose message cites the card's source.

The rules then run on the card-labelled netlist, so the rules see the real chip.

**V-1d · Built = verified.** The `.kicad_pcb` pad nets (what the gerbers are made from) must equal the `circuit.json` connectivity. Any difference → verify error `verify.pcb_mismatch`.

**V-1e · Rules cite sources.** Every rule in `docs/05-verifier-rules.md` names the document it enforces. For example: pull-ups on SDA/SCL cite NXP UM10204 (I²C specification), plus the part's own datasheet (MCP9808 DS20005095B §3.1). Decoupling cites the datasheet's layout section (MCP9808 §6.1, p.35: 0.1–1 µF between VDD and GND, close to the pins). A rule without a citation isn't merged.

## 3 · Evidence

Prototype (scratchpad only, not in the repo). Real `tsci` compile → `circuit.json` → card binding → the unchanged rules in `reflow/rules/`:

| Board | Binding vs card | Rules |
|---|---|---|
| AI pinout (A0 on pin 3) | 4 × `pinout.mismatch`, e.g. "pin 3 labelled A0, Microchip DS20005095B Table 3-1, p.11 says ALERT" | `address.floating U1` (the real A0, pin 7, is wired to nothing) |
| Datasheet pinout | none | none (clean) |
| Datasheet pinout, no decoupling cap | none | `decoupling.missing U1`. Fires with **no** `pinAttributes` in the TSX, because power comes from the card. |
| Datasheet pinout, cap in series with VDD | none | `decoupling.series C1,U1` |
| LCSC id with no card | `parts.no_card U1` | — |

`circuit.json` alone, without cards, also fixed the I1 false positive and false negative (`i2c.missing_pullup` fires exactly when the pull-ups are absent).

Sources checked for the MCP9808 card:
- **Manufacturer datasheet** (Microchip DS20005095B, Table 3-1 p.11). MSOP-8: 1 SDA, 2 SCL, 3 Alert, 4 GND, 5 A2, 6 A1, 7 A0, 8 VDD.
- **EasyEDA symbol** for C129490 and C94847: same pin names. Every pin's electrical type is "unspecified", so it can't supply power pins.
- **Third-party web pinouts**: at least one disagrees with the datasheet. This is why the card is checked by a person against the manufacturer's document, and EasyEDA is used only as a cross-check while drafting.

## 4 · What changes in the contracts

`V-1-contract.patch`:

- **New types** in `contracts.py`: `Citation{doc, locator, url}`, `CardPin{number, name, kind}`, `PartCard{family, mpns, lcsc, package, pins, pin_source, verified_by, verified_on}`, and the enum `PIN_KINDS`. Added to `ALL_CONTRACTS`, frozen in `tests/test_contracts.py`, with a strict example `docs/examples/part_card.json`.
- **No existing field changes.** `VerifyReport.schematic` keeps its name. It now means "the file the netlist came from" (`board.kicad_sch` or `circuit.json`), so `reflow check --json` output is unchanged.
- **Docs:** §2b `PartCard` and the rewritten §5 in docs/04, plus the verifier row in docs/02 and the loop sketch in docs/06.
- **Not in the patch** (HUMAN-owned): `loop.py:276`, `verifier(compile_result.kicad_sch, …)` → `circuit_json`. See `V-1-loop-HUMAN.patch`.

Cards are written in TOML (easier for a person to edit and review) and parsed strictly with `from_dict(PartCard, tomllib.load(...))`.

## 5 · Ownership and tasks this creates

| Proposed ID | Work | Owner | Why that owner |
|---|---|---|---|
| V-10 | `circuit.json` → `Netlist` loader. Strict: a missing key or unknown element shape raises. Pinned tscircuit version. | AGENT | Mechanical; fails loudly |
| V-11 | Card loader: `cards/*.toml` → `PartCard`, refusing drafts | AGENT | Mechanical; strict parse |
| V-12 | Binding (V-1c): LCSC id → resolved row → card → relabel by pin number | **HUMAN** (agent may draft for review) | A wrong binding is a plausible wrong answer |
| V-13 | Rules `parts.no_card`, `pinout.mismatch`, `verify.pcb_mismatch` | **HUMAN** | Rules |
| V-14 | `.kicad_pcb` pad-net reader for V-1d | AGENT | Mechanical; the comparison is V-13 |
| V-15 | Cards for every IC in the 5 eval prompts (E-02) | agent drafts · **HUMAN** verifies and signs | Ground truth |
| V-16 | Verifier adapter `(circuit_json, ResolvedParts, Spec) → VerifyReport` wiring V-10..V-14 | AGENT | Plumbing |
| R-07 | Citations for every existing rule in docs/05 | **HUMAN** | Rules |

Card review checklist (per card, by a person): every pin number and name matches the manufacturer's pin table for **this package**; exposed pads are listed; `kind` is right for power/ground; `pin_source` names the document revision and page; `mpns` and `lcsc` are the same physical part.

## 6 · Open sub-questions for the human

1. **Passives and polarity.** Resistors and non-polarized caps need no card. LEDs, diodes, electrolytics and connectors do have pin meaning (anode/cathode, pin 1). Proposal: v1 cards cover ICs and polarized parts. Unpolarized two-terminal parts are exempt.
2. **Connectors.** A pin header has no datasheet pinout; its meaning comes from the Spec (`interfaces`, e.g. "3V3, GND, SDA, SCL"). Should the Spec's header order become ground truth for `J*` pins (checked like a card)? Recommended: yes, as a follow-up.
3. **`reflow check` on KiCad boards.** Should it also use cards when a symbol's MPN has one? Recommended: later. Hand-made KiCad symbols carry their own pin types today.
4. **Existing integration tests.** After acceptance, `tests/test_integration.py` switches to the new verifier, and the `sensor_*.tsx` inputs get the datasheet pinout. `test_schematic_export_keeps_the_traced_nets` stays as a record of the upstream tscircuit bug, or the human retires it (removing a test is the human's call).
