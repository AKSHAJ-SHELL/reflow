# P-07: parts from a library the user downloads (SparkFun first)

Status: PROPOSED 2026-11-06 by the agent (Claude), at the human's request. Nothing here is built.
Questions A–E below are the human's to decide. Resolver ranking and validity are HUMAN code (P-02).
Any change to `CatalogPart` or `ResolvedPart` needs an accepted `DECISIONS.md` entry. Golden rule 5
holds throughout: the model never names a part. It describes one, and the resolver finds it in a
source the user chose.

## Why

Some users must build from one vendor's parts, not JLCPCB's catalog. A class can require SparkFun
resistors and capacitors, and a lab or company can have its own approved-parts library. In KiCad
they download the vendor's library and search it. reflow only searches one source, the local
jlcparts snapshot (D-6a), so every passive on a reflow board is a JLC part. The INA226 demo run
(2026-11-06) showed this: "vanilla" passives, no way to ask for the user's library.

## What the user does

1. Downloads the library once, the way they would for KiCad. For SparkFun that's
   `sparkfun/SparkFun-KiCad-Libraries` (or the KiCad Plugin and Content Manager). reflow never
   downloads it.
2. Points reflow at it in `reflow.toml`:
   ```toml
   [parts]
   library = "~/kicad/SparkFun-KiCad-Libraries"  # a folder of .kicad_sym files
   use_library_for = ["resistor", "capacitor"]   # categories; everything else stays on JLC
   ```
3. Runs `reflow parts index`. It reads the library into a local index and prints how many
   resistors and capacitors it found, and which symbols it skipped and why.
4. Designs as usual. The plan step shows each passive with where it came from, for example
   `4.7k 0603 · SparkFun RES-xxxxx`. A request the library can't fill is Unresolved with the
   reason; it does **not** fall back to JLC silently (question C).

## What the SparkFun library actually contains (read 2026-11-06)

From the repository page itself:
- **License:** CC BY 4.0. Commercial use is allowed. Attribution means the README or BOM names the
  source.
- **Layout:** `symbols/` (.kicad_sym), `footprints/` (.pretty), `3dmodels/`.
- **Passives are one symbol per part, not a generic R/C.** Names encode the part: resistors
  `[resistance]_[size]_[wattage]_[tolerance]`, capacitors `[capacitance]_[size]_[voltage]_[tolerance]`.
- **Each part carries a SparkFun production ID (`PROD_ID`).** It's SparkFun's internal number. The page
  doesn't promise a manufacturer part number field.
- **No stock, no price, and no LCSC numbers.**

Still to check by reading the files, before anything is built: the exact field names, how many
passives have a manufacturer MPN, and whether every symbol names its footprint.

## Design (proposed)

- **A library index, AGENT code (`reflow/parts/library.py`).** It parses the `.kicad_sym` files the
  user points at, with the same symbol reader `reflow/schematic.py` and the pin-map code already use.
  Each symbol becomes a `CatalogPart`:
  - `source = "library:<name>"` and `category` from the symbol's name and keywords;
  - value and package parsed from the name, and checked against the symbol's own Value and Footprint
    fields, with the row skipped and reported if they disagree;
  - `mpn` = the symbol's manufacturer MPN field if it has one, else "".
  The index refuses to invent anything. A symbol it can't read is skipped and listed.
- **Searching.** `local_catalog.search` gains a sibling with the same signature. For each request, the
  harness asks the source that `use_library_for` names for that category.
- **The resolver** gets candidates as it does today. Its ranking and validity changes are questions A
  and B, and they are HUMAN.
- **Schematic.** A library part uses the library's own symbol (`<library>:<symbol>`) in place of
  `Device:R`/`Device:C`. Its footprint is the one the symbol names, and DRC runs on it like any other.
- **Export.** The BOM shows the library's ID and MPN, and an empty LCSC column for that row. The
  export report says "parts you source yourself: n" (question D).
- **Rule 5 check.** `foreign_part_numbers` already allows only resolved MPN/LCSC ids and named parts.
  A library part adds its library ID to the allowed set, and nothing else.

## Questions for the human

**A. Ranking without stock or price.** Today's order is JLC basic, then stock, then price. A library
has none of these.
- *Recommended:* among library candidates, prefer an exact package match, then the tightest tolerance
  that still meets the request, then the library's own order. Note: this is a new `_pick` for library
  rows (P-02, HUMAN).

**B. Stock and LCSC checks.** The resolver refuses a candidate with `stock == 0` or no LCSC id. Every
library row would fail both.
- *Recommended:* library rows skip both checks, and `ResolvedPart.source` says the part came from a
  library. This changes resolver validity (P-02, HUMAN), and arguably `ResolvedPart` itself:
  `lcsc = ""`, `stock = 0` and `basic = False` mean "doesn't apply", which needs a DECISIONS entry.
- *Alternative:* add `ResolvedPart.vendor_id`, and leave `lcsc` empty. Cleaner, but it's a contract
  change.

**C. When the library has no match.**
- *Recommended:* the request is Unresolved, with the closest library parts listed. Example:
  "no 4.7k 0402 in SparkFun; it has 4.7k 0603". The user changes the plan or the setting.
- *Alternative:* fall back to JLC, and mark the row. Rejected as the default, because a class that
  requires SparkFun parts would get a JLC part without anyone noticing.

**D. Fab export.** JLC assembly needs LCSC numbers.
- *Recommended:* export still works. Library rows are listed as "not assembled by JLC; source and
  place yourself", and `reflow export` prints that count. It never claims the board is fully
  assembled.
- *Alternative:* refuse assembly files when any part has no LCSC id.

**E. Scope of v1.**
- *Recommended:* resistors and capacitors only, from one library at a time. ICs already come from
  `named_parts`. Connectors, LEDs and more than one library can come later.

## Tasks this would create

| ID | Goal | Owner |
|---|---|---|
| P-07a | `reflow parts index`: read a downloaded KiCad library into `CatalogPart` rows; refuse rows whose name, value and footprint disagree | AGENT |
| P-07b | Search the library for the categories `[parts] use_library_for` names | AGENT |
| P-07c | Resolver: library ranking (A) and validity (B, C) | HUMAN |
| P-07d | Schematic and BOM use the library's symbol, footprint and ID; export report counts self-sourced parts (D) | AGENT |

Acceptance for the set: a fixture library with a few SparkFun-style resistors and capacitors. The
MCP9808 plan resolves its 4.7k and 100nF from the fixture library and its IC from `named_parts`. A
4.7k 0402 request is Unresolved, with the 0603 listed. No library file is ever downloaded by reflow,
and no test reads the network.

## What this doesn't do

- reflow doesn't download a library, or check that a SparkFun part is in stock at SparkFun.
- It doesn't make a SparkFun *breakout board* a part (a module on a header). That's a different
  feature.
- It doesn't vouch for the library's footprints. They go through DRC and KiCad ERC like any other.
