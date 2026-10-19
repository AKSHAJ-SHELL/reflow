# reflow/parts/: part resolver

**Does:** turns each `PartRequest` (a category like "4.7k resistor, 0402, 1%") into a real, in-stock `ResolvedPart`, or an `Unresolved` with a reason.

| Piece | Owner | Status |
|---|---|---|
| `catalog.py`: fetch candidates from the parts backend (D-6). Unsorted. | AGENT (P-01, P-03) | built |
| `resolver.py`: package match, named-part provenance, ranking | P-02 | built |

**Contract:** `resolve(requests, named_parts, candidates) -> ResolvedParts` (docs/04-contracts.md §2). `candidates` is keyed by `PartRequest.id`. Every request lands in exactly one of `resolved` / `unresolved`.

Ranking, highest priority first: JLCPCB basic, then higher stock, then lower price. A tie keeps catalog order. The catalog client does not rank.

**Must never:** invent, complete or "correct" a part number; accept an MPN from model output that isn't in `Spec.named_parts`; read an MPN or LCSC id out of TSX; hide a network failure as "no results"; ship a shared API key.
