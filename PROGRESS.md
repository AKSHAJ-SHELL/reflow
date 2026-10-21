# PROGRESS (append-only)

Newest entry at the bottom. Never edit or delete old entries. Every session (human or agent) appends one.

Format:
```
## YYYY-MM-DD · <who> · <task IDs>
Did: ...
Tests: <command> → <result>
Next: ...
```

## Blocked

(Agents: add blockers here with date + task ID; the human clears them.)

- 2026-10-20 · verifier input (docs/04 §5) · tscircuit's `.kicad_sch` export has wrong connectivity (traced pins split across nets or `unconnected`, rails become fake `V`/`GND` components, all pins `passive`). The verifier gives both false positives and false negatives on I2C boards; `.kicad_pcb` and `circuit.json` are correct. Choosing a new verifier input is a contract change and HUMAN. Evidence: `tests/test_integration.py`, REVIEW.md §9.
- 2026-10-20 · P-02 (HUMAN) + P-01 · resolver picks a part of the wrong kind (I2C header → LED C2286) and a named IC is never searched by its MPN. Catalog query half is AGENT (P-01); the resolver category check is HUMAN. Evidence: `tests/test_parts_integration.py`.
- 2026-10-20 · D-6 / P-03 · jlcsearch stock data and free-text search are broken upstream. Proposed: jlcparts SQLite snapshot (~205 MB). Needs a DECISIONS.md amendment and the human's OK to download.

---

## 2026-10-07 → 2026-10-17 · human · (history, summarized from NOTES.md and git log)
Did: toolchain round trip (KiCad → DSN → freerouting → SES → KiCad); switched substrate atopile → tscircuit; netlist loader + generic fixture tests; rules decoupling.series, i2c.missing_pullup/duplicate_pullup, address.floating; `reflow check` CLI; real AVBotz board fixtures (clean + original series-cap bug); renamed OpenFlux → reflow.
Tests: `pytest -q` → 33 passed (2026-10-17).
Next: finish rename (Z-01), launch post for `reflow check` (D-01), harness decisions (H-00).

## 2026-10-17 · agent (Claude) · C-01 + docs/scaffold
Did: added `reflow/contracts.py` (22 stage contracts, strict from_dict), `docs/examples/*.json`, `tests/test_contracts.py` (49 tests), stubs `reflow/{llm,compile,route,export}.py`, `reflow/parts/catalog.py`; docs 00–08; README; TASKS.md; AGENTS.md/CLAUDE.md; DECISIONS.md; docs/agents/01–09; module READMEs; `runs/` added to .gitignore. No HUMAN-owned code touched. Rename import edits left uncommitted for the human (Z-01).
Tests: `python3 -m pytest -q --noconftest tests/test_contracts.py` → 49 passed (Linux VM, Python 3.10). KiCad-backed tests not run here (no kicad-cli); run `pytest -q` on the Mac.
Next: human answers H-00 (Q3–Q6) and decisions D-1…D-6.

## 2026-10-19 · agent (integration) · M-02, M-01, K-01, K-02, P-01, P-03, H-08, H-05, H-06, H-07
Did: agent-owned plumbing landed on `shashi`. Config loader (`reflow.toml` / env, `max_attempts=3`, `compile_cap=2`, missing `REFLOW_API_KEY` raises `ConfigError`). Model adapter `complete(system, prompt) -> Completion` with `ModelError` on 401/500, no retry and no tools, plus `extract_code_fence` (`str | None`). `compile_board` via `tsci` (blinky ok, syntax error `ok=False`, missing `tsci` raises). Catalog client and cache for jlcsearch; the client does not rank or pick a winner. Prompt drafts in `prompts/planner.md`, `prompts/codegen.md`, `prompts/fix.md` (human approval still required before a loop loads them). Run-folder writer `reflow/harness/runs.py`. `reflow design` loads a confirmed Spec JSON, refuses `confirmed: false`, and rejects a Plan `mpn` outside `Spec.named_parts`. H-01, H-02, H-03, H-04, P-02, and L-01 were not written. The harness loop is not implemented.
Tests: validation `pytest -q` on `51129f7f3e31bf2a0af9ec5b7df1d212ecc03ffb` → 154 passed. Verdict PASS (`docs/harness-validation-report.md`, worker `bc-3b0eca06-da2e-525f-a07f-096a3c0830e5`). The same run also reported 4 failed and 28 errors in `tests/test_cli.py` and `tests/test_netlist.py`; those match `dde218a` (KiCad 10 fixtures, KiCad 7 CLI) and are not from this plumbing.
Next: human writes H-00 acceptances, the harness loop (H-01..H-04), resolver validity (P-02), and learn-mode selection (L-01). End-to-end `reflow design` stays parked until that loop exists.

## 2026-10-19 · agent · P-02
Did: added `reflow/parts/resolver.py`. `resolve(requests, named_parts, candidates)` returns `ResolvedParts`. Every request is in exactly one of `resolved` / `unresolved`. Package must match the request (same comparison as the catalog client, including a parenthetical suffix). Ranking is JLCPCB basic, then higher stock, then lower price; a tie keeps catalog order. The resolver does not call `catalog.search` and does not sort the candidate list in place. An IC whose mpn is not in `named_parts` is `Unresolved`. A named IC missing from the candidates is `Unresolved` with a reason that names the mpn and the catalog. An LCSC id is copied from the selected candidate only. Notes/TSX are not read. `DECISIONS.md` was not edited. Branch `shashi-resolver` was cut from `origin/shashi` `c7830a2` and is not merged.
Tests: `python3 -m pytest -q tests/test_resolver.py` → 20 passed. Short-circuiting `_pick` to the first candidate failed the three ranking tests; the sort was restored. `python3 -m pytest -q` → 171 passed, 7 skipped, 28 errors. Skips: 5 `kicad-cli` not found (`tests/test_cli.py`), 2 `tsci` not installed (`tests/test_compile.py`). Errors: 28 `FileNotFoundError: kicad-cli` in `tests/test_netlist.py` (pre-existing; KiCad is not installed here).
Next: the harness loop calls `resolve` with each request's `catalog.search` result. Do not merge this branch into `shashi` from here.

## 2026-10-19 · agent · H-00, H-01, H-02, H-03, H-04, H-07
Did: Marked D-1, D-2, D-3, D-6, and H-00 (Q3, Q4, Q5, Q6, COMPILE_CAP, status) ACCEPTED in DECISIONS.md, dated 2026-10-19, accepted by the human in chat. D-4, D-5, and P-1 stayed proposed. Implemented the design loop on `shashi-loop` (cut from `c7830a2`): compact feedback from the fix template, compile cap 2, best-attempt selection, and the abort rules. `reflow design` runs that loop when a model, compiler, and verifier are supplied. No live API key. Learn mode was not implemented. Did not merge `origin/shashi` at `5e561fb` (P-02 resolver) and did not edit resolver files.
Tests: `python3 -m pytest -q` → 171 passed, 7 skipped, 28 errors. The errors are `tests/test_netlist.py` setup (`kicad-cli` missing). The skips are `tests/test_cli.py` (no `kicad-cli`) and `tests/test_compile.py` (no `tsci`). `tests/test_harness.py` and `tests/test_design_cli.py` passed.
Next: bring P-02 onto this branch only when the human wants the resolver in the loop. D-4 (learn mode) stays open. Fresh check: `python3 -m pytest -q tests/test_harness.py tests/test_design_cli.py`.

## 2026-10-20 · agent (Claude) · review + integration tests (no task ID)
Did: reviewed `origin/shashi` (checked out as local `shashi`) into REVIEW.md. Added `tests/test_integration.py` (real tsci + kicad-cli + rules + design loop, scripted model), `tests/test_parts_integration.py` (plan → catalog → resolver on recorded jlcsearch responses in `tests/data/jlcsearch_plan/`), and TSX inputs in `tests/data/integration/`. Found that tscircuit's `.kicad_sch` export loses connectivity (see Blocked). Failing tests are left red; no skip/xfail added. Each passing new test was sabotaged in-process once and went red. No production code, HUMAN-owned file, fixture, or existing test changed.
Tests: `pytest -q` → 7 failed, 230 passed. Failures: 4 integration (schematic connectivity), 2 parts (resolver/catalog C2), 1 pre-existing live jlcsearch test (upstream data). KiCad 10 via `KICAD_CLI`, tsci 0.0.2768.
Next: the human picks the verifier input (circuit.json vs kicad_pcb) and the catalog source (jlcparts snapshot). Then AGENT work: verifier adapter, P-01 query fix, CLI wiring.

## 2026-10-20 · agent (Claude) · V-1 proposal (no task ID yet)
Did: drafted Decision V-1 (proposed, not accepted): verify `circuit.json` instead of tscircuit's `.kicad_sch`, with IC pins taken from HUMAN-verified part cards rather than TSX labels. Wrote `docs/proposals/V-1-circuit-json-ground-truth.md`, `V-1-contract.patch` (new `Citation`/`CardPin`/`PartCard`/`PIN_KINDS`, frozen-list + example updates, docs/02/04/06), `V-1-loop-HUMAN.patch` (one line in HUMAN-owned `loop.py`, for the human to apply), and `V-1-draft-card-MCP9808.toml` (draft, `verified_by` empty) from Microchip DS20005095B Table 3-1, cross-checked against EasyEDA C129490. Added the V-1 row to DECISIONS.md under Proposed. Did not apply either patch to the checkout. Found that the agent-written `tests/data/integration/sensor_*.tsx` uses a wrong MCP9808 pinout (A0 on pin 3; the datasheet says Alert), which is the failure mode V-1 targets.
Tests: both patches applied in a throwaway worktree → `tests/test_contracts.py` 51 passed; `pytest -q` 229 passed, 1 failed (pre-existing live jlcsearch). Example card corrupted twice (bad kind, unknown key) → contract tests red both times. Checkout unchanged: `pytest -q` → 7 failed, 230 passed (same as the previous entry).
Next: the human accepts or edits V-1, applies `V-1-loop-HUMAN.patch`, and verifies the MCP9808 card. Then AGENT: apply the contract patch in one commit, V-10, V-11, V-14, V-16.

## 2026-10-20 · agent (Claude) · V-2 proposal (no task ID yet)
Did: drafted Decision V-2 (proposed): generic rules (Python, maintainers) + a fixed set of requirement kinds (HUMAN rules) + per-chip requirements as data in signed part cards, with citation and verbatim quote. `docs/proposals/V-2-rule-framework.md`, plus a DECISIONS.md row. Confirmed ST's STM32_open_pin_data is BSD-3-Clause and types all 48 STM32F103C8 pins (9 Power, NRST Reset, BOOT0 Boot, 37 I/O). AN2586 capacitor values not verified; the doc's STM32 example marks them as placeholders. No code or contract changed.
Tests: none run (docs only). Checkout state unchanged from the previous entry.
Next: the human decides V-1, then V-2.

## 2026-10-20 · agent (Claude) · V-2 proposal, sources section
Did: added §10 to `docs/proposals/V-2-rule-framework.md`: seed sources (vendor pin data, KiCad libraries, EasyEDA as cross-check only, datasheets cited not redistributed), CC-BY-SA 4.0 proposal for `cards/`, and the contribution flow (card + good/bad board + `reflow card check` + two signatures). Checked the local KiCad 10 library: MCP9808 pins and types match DS20005095B but its Datasheet field points to 22203b; STM32F103C8 VSS pins 35/47 are `passive` while ST data says Power. Docs only.
Tests: none run.
Next: unchanged (human decides V-1, then V-2).

## 2026-10-20 · agent (Claude) · V-2 rewrite: project rules file
Did: replaced the V-2 draft with a shorter design: general rules ship with reflow; a project adds `rules.toml` (six `need` kinds, required `source` and `why`) written by the student from datasheets; reflow sends the rules to codegen as constraints and checks each at verify; a separate Claude skill (draft `docs/proposals/datasheet-tutor-SKILL.md`, not part of reflow) explains datasheets and writes the file on request. V-2 now amends V-1 (b): pin maps come from vendor data, then KiCad, then a hand card override. Added `docs/proposals/examples/rules.toml` (7 rules for the MCP9808 board, from DS20005095B). Updated the V-2 row in DECISIONS.md. Docs only.
Tests: example rules.toml parsed with tomllib; field check passed. No suite run (no code changed).
Next: the human decides V-1 and V-2.

## 2026-10-20 · agent (Claude) · V-1 contract change (commit b444ba2), V-2 contract draft
Did: the human accepted V-1 and V-2 in chat. Committed b444ba2 on `shashi`: V-1 and V-2 marked ACCEPTED in DECISIONS.md; `Citation`, `CardPin`, `PartCard`, `PIN_KINDS` in contracts.py, frozen in test_contracts.py, `docs/examples/part_card.json`; docs/02/04/06. docs/04 §2b/§5 and the contracts.py comment were reworded from the drafted patch to follow V-2's amendment of V-1 (b): pin maps come from vendor data, then KiCad, with a signed card as override. The applied `V-1-contract.patch` was dropped (the commit is the record). `loop.py` is untouched; `docs/proposals/V-1-loop-HUMAN.patch` still applies and is for the human. Drafted `docs/proposals/V-2-contract.patch` (not applied): `RULE_NEEDS`, `ProjectRule`, `ProjectRules`, `Spec.rules_file = ""`, frozen lists, `docs/examples/project_rules.json`, spec.json example, docs/04 §0/§0b. It also adds `rules_file` to the hand-listed round trip in `tests/test_design_cli.py`, because the patch otherwise breaks that test.
Tests: committed HEAD (clean worktree) → 1 failed (live jlcsearch), rest passed. HEAD + V-2 patch → contract + design CLI tests 70 passed; full suite 232 passed, 1 failed (live jlcsearch). V-2 example with an unknown `need` → contract tests red. Working tree with this session's uncommitted integration tests → 7 failed, 234 passed (known failures, REVIEW.md §9).
Next: the human approves V-2-contract.patch and applies V-1-loop-HUMAN.patch. Then AGENT: V-10 (circuit.json loader), pin-map importer, rules.toml parser and `reflow rules check`.

## 2026-10-20 · agent (Claude) · V-2 contract change (commit 6d47281)
Did: the human approved V-2-contract.patch in chat, including the `tests/test_design_cli.py` round-trip change. Committed 6d47281 on `shashi`: `RULE_NEEDS`, `ProjectRule`, `ProjectRules`, `Spec.rules_file = ""` in contracts.py; frozen lists and the example check in test_contracts.py; `docs/examples/project_rules.json`; `rules_file` in docs/examples/spec.json; docs/04 §0 row and §0b; `rules_file` in the hand-listed round trip in test_design_cli.py. DECISIONS.md V-2 row records the approval. The applied patch file was removed.
Tests: committed HEAD in a clean worktree → 232 passed, 1 failed (live jlcsearch). Working tree with this session's uncommitted integration tests → 7 failed, 237 passed (known, REVIEW.md §9). `V-1-loop-HUMAN.patch` still applies.
Next: the human applies `V-1-loop-HUMAN.patch`. AGENT: circuit.json loader (V-10), pin-map importer, rules.toml parser and `reflow rules check`. Still uncommitted: REVIEW.md, the integration tests and `tests/data/`, the `tests/README.md` rows, and PROGRESS.md.

## 2026-10-20 · agent (Claude) · V-10
Did: added `reflow/circuit_netlist.py`: `load_circuit_json(path) -> Netlist` from tscircuit's source_* elements, as in docs/04 §5. Nets are grouped by `subcircuit_connectivity_map_key`, named from `source_net`, else `Net-(<ref>-<pin>)` or `unconnected-(…)`. `pintype` is always "" (pin kinds come from the pin map, V-12), and `function` is the raw port name. Strict: a malformed file, missing key, duplicate ref or pin, unknown component, one net name on two nets, or more than one subcircuit raises `CircuitJsonError`. Two named nets on one key (net.V3_3 traced to net.GND) raise `MergedNetsError` rather than hiding the short. Added recorded inputs in `tests/data/circuit_json/` (tsci 0.0.2768; sensor_good full, three source_*-only trims, each beside its .tsx) and `tests/test_circuit_netlist.py` (26 tests). Clarified docs/04 §5 wording: a named net keeps its name even with one port, so a lone traced SDA still reaches the I²C rule. Added the V-1/V-2 tasks (V-10..V-22, R-07, R-10) to TASKS.md and README rows. No HUMAN-owned file changed.
Tests: `tests/test_circuit_netlist.py` failed first (module missing), then 26 passed. Sabotaged in-process three ways (pick one name for merged nets; ignore connectivity keys; set pin types) → red each time. `pytest -q` → 7 failed, 263 passed: the same 7 known failures (6 intentionally red integration tests + live jlcsearch), none new. KiCad 10 via `KICAD_CLI`, tsci 0.0.2768.
Next: how a short between named nets becomes a violation instead of an exception is a HUMAN decision (V-13). AGENT next: V-14 (`.kicad_pcb` pad-net reader) or V-11 (pin-map importer); V-16 wires the loader into the verifier.

## 2026-10-20 · agent (Claude) · V-14
Did: added `reflow/pcb_nets.py`: `load_pcb_pad_nets(path) -> {(ref, pad): net}` from a `.kicad_pcb`, using `reflow.netlist.parse_sexpr` (imported, not edited). It reads both pad-net syntaxes (tscircuit `(net 3 "SDA")`, KiCad 10 `(net "SDA")`) and both reference syntaxes (`property "Reference"`, older `fp_text reference`). A pad with no net is "". Mounting holes and pad-less footprints are skipped, and a split pad on one net is one entry. Unreadable or non-board files, pads with no reference, duplicate references, and one pad on two nets raise `PcbNetsError`. Known limit: after parsing, a pad net written as a bare number is read as "no net", so a net literally named "3" in KiCad 10 syntax would be misread (not seen in any recorded board). Added `tests/test_pcb_nets.py` (17 tests) and the two PCB exports from the same tsci run as the recorded circuit.json (`tests/data/circuit_json/*.kicad_pcb`). The comparison itself (`verify.pcb_mismatch`) is V-13, HUMAN.
Tests: failed first (module missing), then 17 passed, including the AVBotz KiCad 10 board vs its own schematic netlist via kicad-cli (fixture read only). Three in-process sabotages (read the net number instead of the name; drop the conflict check; drop the fp_text fallback) → red each time. `pytest -q` → 7 failed, 280 passed: the same 7 known failures, none new.
Next: V-11 (pin-map importer) or V-16 (verifier adapter wiring V-10 + V-14). V-12 and V-13 stay HUMAN.

## 2026-10-20 · agent (Claude) · V-11
Did: added `reflow/parts/pinmap.py`.
- `from_st_pin_data(mpn, st_dir)` reads ST STM32_open_pin_data `mcu/<RefName>.xml`. RefName patterns like `STM32F103C(8-B)Tx` match STM32F103C8T6 / CBT6, with an optional TR suffix.
- `from_kicad_symbol(lib_id, symbols_dir)` reads a KiCad symbol. It follows `extends`, collects every unit, folds identical copies, and raises on one pin number with two names.
- `compare_pin_maps` compares by `base_name`; `import_pin_map` returns the vendor map when there is one, checked against KiCad, with disagreements as text.
- Kinds use `contracts.CardPin`/`Citation`/`PIN_KINDS`. Power vs ground is decided by name (GND*, VSS*, AGND/DGND/PGND), and every kind taken from a name instead of the source's type is recorded in `notes`. Directories come from the arguments, else `REFLOW_ST_PIN_DATA` / `REFLOW_KICAD_SYMBOL_DIR`, else the library next to kicad-cli.
- Test data in `tests/data/pinmaps/`: ST `STM32F103C(8-B)Tx.xml` unmodified (BSD-3-Clause; LICENSE copied, commit 7d1f1514ed55), and four unmodified KiCad 10.0.5 symbols (CC-BY-SA-4.0 WITH KiCad-libraries-exception; notice in `kicad/LICENSE.md`). No new Python dependency (stdlib xml).
Found:
- KiCad's MCP9808_MSOP names and numbers match DS20005095B Table 3-1, but it types Alert as `output` (the datasheet says open-drain), and its Datasheet link is MCP9804's document 22203b. Both are reported as written.
- KiCad types STM32F103C8 VSS pins 35/47 `passive`. They're read as ground by name and noted.
- ST and KiCad agree on the STM32F103C8 once ST's alternate-function suffixes ("PC14-OSC32_IN") are ignored.
Not verified: ST's DS5319 datasheet could not be downloaded (st.com and mirrors blocked), so the STM32 expected pins come from ST's pin data, cross-checked against EasyEDA C8734 and KiCad (all three agree), not from the datasheet itself. The human should confirm against DS5319 Table 5.
Tests: `tests/test_pinmap.py` failed first (module missing), then 29 passed, including the installed KiCad 10 library found next to kicad-cli. Four in-process sabotages (no ground-by-name, compare returns nothing, only the first RefName alternative, ignore `extends`) → red each time. `pytest -q` → 7 failed, 309 passed: the same 7 known failures, none new.
Next: V-12 (bind ICs to pin maps, HUMAN) can use `import_pin_map` + `base_name`. PinMap/PinImport live in pinmap.py; promote them to contracts.py if V-12 needs them across a stage boundary (DECISIONS proposal). AGENT next: V-16 or V-21.
