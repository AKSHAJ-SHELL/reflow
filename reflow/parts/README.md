# reflow/parts/: part resolver

**Does:** turns each `PartRequest` (a category like "4.7k resistor, 0402, 1%") into a real, in-stock `ResolvedPart`, or an `Unresolved` with a reason.

| Piece | Owner | Status |
|---|---|---|
| `catalog.py`: fetch candidates from the parts backend (D-6). Unsorted. | AGENT (P-01, P-03) | built |
| `resolver.py`: package match, named-part provenance, ranking | P-02 | built |
| `local_catalog.py`: queries the local snapshot. Resistors and capacitors by value (as numbers), tolerance and voltage; pin headers by `value` "RxC" + `package` pitch (D-6a a); named parts by MPN prefix. Each candidate carries its reflow `category` and the row's `fetched_at`. Other categories without an MPN raise | AGENT (P-05) | built |
| `snapshot.py`: `reflow parts update` downloads the jlcparts database (D-6a), inflates it across its split parts with a CRC check, and installs it atomically at `REFLOW_PARTS_DB` (default `~/.cache/reflow/jlcparts/cache.sqlite3`) with `snapshot.json` | AGENT (P-04) | built |
| `pinmap.py`: an IC's pins (number, name, kind) from ST's STM32_open_pin_data, then the KiCad symbol library; reports where the two disagree | AGENT (V-11) | built |

**pinmap contract:** `import_pin_map(mpn, *, st_dir, kicad_lib_id, symbols_dir) -> PinImport{pin_map, checked_against, disagreements}`. The vendor map wins when there is one; disagreements are returned for a person to settle from the datasheet. Directories come from the arguments, else `REFLOW_ST_PIN_DATA` / `REFLOW_KICAD_SYMBOL_DIR`, else the library next to `kicad-cli`. **Never** reads a pin name or kind from the design, downloads anything, or silently corrects a source.

**Contract:** `resolve(requests, named_parts, candidates) -> ResolvedParts` (docs/04-contracts.md §2). `candidates` is keyed by `PartRequest.id`. Every request lands in exactly one of `resolved` / `unresolved`.

Ranking, highest priority first: JLCPCB basic, then higher stock, then lower price. A tie keeps catalog order. The catalog client does not rank.

**Must never:** invent, complete or "correct" a part number; accept an MPN from model output that isn't in `Spec.named_parts`; read an MPN or LCSC id out of TSX; hide a network failure as "no results"; ship a shared API key.
