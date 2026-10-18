# reflow/parts/: part resolver

**Does:** turns each `PartRequest` (a category like "4.7k resistor, 0402, 1%") into a real, in-stock `ResolvedPart`, or an `Unresolved` with a reason.

| Piece | Owner | Status |
|---|---|---|
| `catalog.py`: fetch candidates from the parts backend (D-6) | AGENT (P-01, P-03) | stub |
| Resolver validity + ranking (package matches, basic > stock > price, ICs only if user-named) | **HUMAN** (P-02) | not built, deliberately no stub |

**Contract:** `Plan.parts` + `Spec.named_parts` → `ResolvedParts` (docs/04-contracts.md §2). Every request lands in exactly one of `resolved` / `unresolved`.

**Must never:** invent, complete or "correct" a part number; accept an MPN from model output that isn't in `Spec.named_parts`; hide a network failure as "no results"; ship a shared API key.
