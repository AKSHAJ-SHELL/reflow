# D-6a · Parts data from the jlcparts snapshot, not the jlcsearch API

Status: **ACCEPTED** 2026-10-21 by the human, with the recommended answers to sub-questions a–d (proposed by agent, Claude). Amends D-6 (accepted 2026-10-19: "jlcsearch JSON API plus a local cache"). Binding text: `DECISIONS.md`.

## Why

jlcsearch is broken upstream (REVIEW.md §9):
- every typed passive query returns `stock: null, in_stock: false`, even C25900;
- free-text search returns the same unrelated parts for any query.

That's why every I²C eval board aborts today, and why the resolver picks an LED for a header (C2).

## What was checked (2026-10-21, snapshot downloaded to a scratch folder, read-only)

| Question | Answer |
|---|---|
| Source | [yaqwsx/jlcparts](https://github.com/yaqwsx/jlcparts): MIT code, pushed 2026-10-21, 840 stars. Data: `yaqwsx.github.io/jlcparts/data/cache.zip` + `cache.z01`…`z04` |
| Size | 216 MB download → `cache.sqlite3`, 1.54 GB. CRC checked against the archive |
| Format | `meta.format = source-db-v2`; table `jlc_components`: 2,700,372 parts, each with `lcsc`, `mfr`, `package`, `category`, `subcategory`, `stock`, `library_type` (`base` = JLC basic, 350 parts), `preferred`, `price` (JSON), `attributes` (JSON), `datasheet`, `fetched_at` |
| Freshness | Each row has its own `fetched_at`: 2026-09-14 to 2026-10-21 in this snapshot. Stock can be up to about 5 weeks old |
| 4.7k 0402 resistor | C25900 `0402WGF4701TCE`, **16,063,321 in stock, basic**: the row jlcsearch reports as out of stock |
| 100 nF 0402 capacitor | C307331 / C1525, basic, about 23M in stock (via `attributes.Capacitance`) |
| MCP9808 | C129490 `MCP9808T-E/MS` MSOP-8 (716), C94847 `MCP9808-E/MS` MSOP-8 (586), C194710 `MCP9808T-E/MC` DFN-8 (255), category Sensors / Temperature Sensors |
| 1×4 2.54 mm header | Found through `subcategory = Pin Headers` and attributes `Pitch = 2.54mm`, `Number of Rows = 1`, `Number of Pins = 4P`; e.g. C492412. `package` is free text, often in Chinese ("插件" through-hole, "弯插" right-angle) |
| Speed | Each query above is a full scan in about 0.25 s; no index needed for v1 |
| Unpacking | macOS `unzip` and `zip -s 0` both fail on this split archive (CRC error, truncated join). Concatenating the parts and inflating the single entry in Python works and is CRC-checked |

## Decision asked

1. **Source.** The catalog reads a local jlcparts snapshot, `cache.sqlite3`, opened read-only. No network at design time, which also satisfies P-03's "second run makes no network calls".
2. **Where it lives.** Outside the repo, at `REFLOW_PARTS_DB`, defaulting to `~/.cache/reflow/jlcparts/cache.sqlite3`. reflow never redistributes the database: each user downloads it from jlcparts.
3. **How it gets there.** A new `reflow parts update` downloads the five parts, joins and inflates them with a CRC check, and records the snapshot date. It's the only command that touches the network for parts.
4. **Honest freshness.** `ResolvedPart.fetched_at` is the row's own `fetched_at`, not the run time. `stock` is the snapshot's stock. Reports say "stock as of <date>".
5. **Basic part** = `library_type == "base"`. Ranking stays basic > stock > price (P-02).
6. **jlcsearch is retired.** The jlcsearch client and its tests (`tests/test_catalog.py` live test, `tests/test_parts_integration.py` recordings) are replaced, not kept as a fallback. Removing tests needs your explicit OK when that commit comes.

## Sub-questions for you

| # | Question | Recommendation |
|---|---|---|
| a | How should a plan describe a connector? Free-text `notes` ("1x4 2.54 mm pin header") can't be matched safely | Use the existing fields for headers: `value = "1x4"`, `package = "2.54mm"`, plus a planner prompt line saying so (H-08). No contract change |
| b | A user types the family `MCP9808`; the catalog sells `MCP9808T-E/MS`, `MCP9808-E/MS`, `MCP9808T-E/MC` | Your resolver half of C2: prefix match, filtered by package. If more than one package is left, Unresolved with a question ("MSOP-8 or DFN-8?") |
| c | Is 1.5 GB of disk acceptable for a student laptop? | Yes for v1. A trimmed export (in-stock rows only, a few columns) is a later optimisation |
| d | Data terms | Unverified: jlcparts' README states no separate data licence. The data is scraped from JLCPCB's public catalogue. reflow doesn't redistribute it |

## Tasks this creates

| ID | Work | Owner |
|---|---|---|
| P-04 | `reflow parts update`: download, join, inflate, CRC check, record snapshot date | AGENT |
| P-05 | Catalog client on the local snapshot: category-aware queries (resistor and capacitor by attributes, IC by named MPN prefix, header by pitch/rows/pins), each candidate carries its `category` (C2 catalog half) | AGENT |
| P-02b | Resolver: reject a candidate whose category doesn't match the request, and family → orderable MPN matching (C2 resolver half) | HUMAN |
| P-06 | Retire the jlcsearch client and its tests | AGENT, after your OK |
