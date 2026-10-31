# L-2 · Learn mode: system design (v2)

Status: **ACCEPTED** 2026-10-22 by the human (design written by the human, @Akshaj; saved here by the agent). Binding text: `DECISIONS.md` rows L-2 and O-1c. This answers D-4 and D-5.

## Accepted with these choices (2026-10-22, human in chat)

- **Decisions:** the design below is accepted, which closes D-4 (spot-the-bug by click, plus make-the-call) and D-5 ((c) a local web app). The four new contracts (`SimRequest`, `SimResult`, `ConceptCard`, `VaultNote`) are approved. Each one is added in the phase that first uses it, frozen by `tests/test_contracts.py` like the others.
- **Ownership (O-1c):** the agent implements L-01 (selection, grading, skip logic) and the SPICE testbenches, each testbench with a hand-calculated expected value. The human reviews them line by line before they count. Golden rule 1 is unchanged for everything else.
- **Server:** FastAPI + uvicorn + fsrs as an optional extra, `pip install reflow-pcb[learn]`. `reflow check` and `reflow design` keep zero required dependencies.
- **Scope of the first push:** phases 1–2 (web shell, click spot-the-bug, sign-off, concept cards, skip logic, vault). The agent stops there for the human to look before simulation starts.
- **Interim answers to two open questions**, for the human to confirm or change:
  - free-text "why" is shown next to the right answer and not graded;
  - break-it runs only when the user asks.
- **Naming:** V-2b's study-session command (`reflow learn REF`, task L-04) becomes `reflow study REF`. That way `reflow learn RUN_DIR` opens this learn mode.

---

## Goal and principles

Learn mode makes sure nobody ships a reflow board they don't understand, in about two minutes per board, without it feeling like a quiz. v1 ships one terminal "spot the bug" step. v2, designed here, adds a local web UI where the user can look at their board, break it in simulation, and click any part to see why it's there. It has memory across boards, so known concepts are skipped.

1. **Real bugs from your own run, never a question bank.** Every interaction comes from a violation the AI actually made on this board, or a decision in its plan.
2. **Commit before you see.** The user answers or predicts first; the fix or the simulation result comes after.
3. **Wrong answers teach, never block.** The user always sees the why afterwards. No scores, no retry-until-correct.
4. **Short.** One to three interactions per board; the rest is optional exploration.
5. **Skip what's known.** A concept the user has recently shown they understand isn't asked again.
6. **Never lie about physics.** A simulation result is shown only if the simulator actually ran on this board's netlist; otherwise the UI says it can't simulate that.

## Architecture at a glance

The v1 harness doesn't change: it still writes the run folder. A new learn server on localhost reads that folder, asks the learn engine what to teach, runs simulations as separate ngspice processes, and writes notes to the vault. The browser talks only to that server.

## The four interactions

Each interaction is generated from this run's data (a violation, a plan decision, the netlist), never from a canned question. The first two are required; the last two are optional exploration.

| Interaction | What the user does | Built from | Required? | Version |
|---|---|---|---|---|
| Spot the bug | Sees the AI's failed draft in the schematic viewer and clicks the part that breaks it, then says why in a sentence. Graded by which part they clicked. | The first failed attempt's violation (refs, why) | Yes, if the AI made a mistake | v1 terminal, v2 click |
| Make the call | Picks a value (e.g. pull-up resistance: 470 Ω / 4.7 kΩ / 47 kΩ) and predicts what happens; the simulation answers | A rule with a tunable value + a simulation testbench | Yes if no bug to spot | v2 |
| Break it | Removes or changes a part ("delete C1") and watches the simulated waveform fail next to the working one | A per-concept SPICE testbench run on this board's parts | Optional | v2 |
| Click to explore | Clicks any part to see why it's there: the plan block it belongs to, the spec line it serves, the rule that checks it | Plan + spec + verifier rule catalog | Optional | v2 |

After each required interaction, the learner model records how it went (see "Learner model and memory vault"), so a concept the user clearly knows is skipped on the next board.

## UI: a local web app

`reflow design` starts a small server on localhost and opens a browser tab. The whole session happens there, and nothing leaves the user's machine except model calls. The terminal keeps working as a fallback.

| View | Shows | Built on |
|---|---|---|
| Spec | The draft spec and open questions to answer | Plain React form |
| Schematic | The board's schematic; click a part to select it (the main entry point for every interaction) | @tscircuit/schematic-viewer (has a component-click callback) |
| PCB | Placement and routing; the selected part is highlighted from outside | @tscircuit/pcb-viewer (canvas renderer, controller focus) |
| Learn panel | The current interaction: prompt, answer box, then the why and the fix | Plain React |
| Simulate | Two waveforms side by side: working board vs broken board | Plot library over ngspice results |
| BOM / assembly | Interactive BOM with part highlighting | InteractiveHtmlBom in an iframe |
| Vault | Graph of concepts, mistakes and past boards; click to open a note | react-force-graph-2d + link to Obsidian |
| Report + sign-off | Remaining warnings, overrides, final y/n | Plain React |

**Stack:** FastAPI + uvicorn on 127.0.0.1, server-sent events to push results to the page, POST requests for user actions. The front end is Vite + React, built once and shipped inside the Python package, so users don't need Node. Pin React to 19.1.0 if the 3D viewer is ever added (it pins that exact version).

## Simulation: break-it mode

Simulating the raw board won't show the bugs. Each concept needs a small hand-written testbench that adds the physics the board file doesn't contain: a circuit-json export has no trace parasitics, no IC load current and no open-drain drivers, so a series cap or a missing pull-up looks fine in a naive simulation.

How a break-it run works:

1. The verifier or the user picks a concept (e.g. decoupling) and a part on the board (C1 at U1).
2. reflow fills that concept's testbench template with the board's real values: supply voltage, cap value, resistor value, IC part.
3. It writes two SPICE decks, as designed and broken (C1 removed, or moved in series), and runs `ngspice -b` on each as a separate process.
4. It parses the output and sends both waveforms to the Simulate view, labelled with what was changed.

| Concept | Testbench adds | What the user sees |
|---|---|---|
| Decoupling | Supply trace resistance/inductance, a pulsed current draw at the IC | Supply at the chip sagging and ringing without the cap; flat with it |
| Series decoupling cap | Same, with the cap in series | No DC reaches the chip: supply at 0 V |
| I²C pull-ups | An open-drain switch, bus capacitance | Line never rising without a pull-up; rise time vs resistor value |
| LED current limit | LED model, supply | Current through the LED with and without the resistor |

**Limits.**
- Transient analysis only, a few concepts per release, and only where a testbench exists. Anything else says "can't simulate this yet" rather than guessing.
- tscircuit's own `<analogsimulation>` / `tsci simulate analog` is a candidate engine.
- An in-browser ngspice (eecircuit-engine) could make value sliders live later.
- Falstad's CircuitJS has the best animated visuals, but it's GPL and uses its own format, so it would only ever be an optional, separately served extra.

## Learner model and memory vault

One spaced-repetition card per concept decides what to ask. The vault is a plain folder of markdown notes the user can open in Obsidian. Both live on the user's machine at `~/.reflow/vault/`.

**Learner model.** Each concept (decoupling, I²C pull-ups, address straps, LED current limit, …) has an FSRS card, updated from what the user did, not from self-rating:

| What happened | Rating |
|---|---|
| Clicked the right part and gave the right reason, no hints | Good |
| Got there with the hint or on the second try | Hard |
| Picked the wrong part, or made the same mistake on their own board | Again |

Before a board, reflow checks each relevant concept's recall estimate; above about 0.9 it's skipped. Each skip is shown ("skipped: decoupling, you've got it"), so the user can choose to do it anyway.

**Vault layout** (Obsidian-compatible):

```
~/.reflow/vault/
  concepts/decoupling.md               why it matters, rule id, [[mistakes]] and [[boards]] that hit it; FSRS state in frontmatter
  mistakes/2026-11-02-series-cap.md    the AI's bad draft, what you answered, the fix
  boards/mcp9808-breakout.md           spec, parts, verify report, links to its concepts
```

`[[wikilinks]]` connect the three folders, so Obsidian's graph view (or Foam, or SilverBullet, which read the same files) shows how concepts, mistakes and boards relate. The web UI draws the same graph itself, and opens a note in Obsidian with `obsidian://open?path=…`. Logseq rewrites files in its own format, so it shouldn't edit the vault.

## Open-source building blocks

Almost every piece exists as permissively licensed open source; reflow writes the glue, the testbenches and the learning logic. Checked 2026-10-22; versions are from npm/PyPI.

| Component | Role in reflow | License | Latest seen | Verdict |
|---|---|---|---|---|
| @tscircuit/schematic-viewer | Schematic view; part-click events | MIT | 2.0.105 (Oct 13) | Use |
| @tscircuit/pcb-viewer | PCB view; highlight selected part | MIT | 1.11.433 (Oct 22) | Use |
| @tscircuit/runframe | Full tscircuit preview tab (no part-click event) | MIT | 0.0.3057 (Oct 22) | Optional |
| InteractiveHtmlBom | BOM / assembly tab | MIT | 2.12.0 (Sep 10) | Use |
| KiCanvas | View exported KiCad files | MIT | early alpha, no releases | Optional |
| ngspice | The simulator, run as a separate process | BSD-3 (per Wikipedia) | ngspice-47 (Aug 11) | Use |
| tscircuit analog simulation | `<analogsimulation>`, `tsci simulate analog`; transient only | MIT | CLI 0.1.2401 | Evaluate |
| eecircuit-engine | ngspice in WebAssembly, for live sliders | MIT | 1.8.0 (Sep 5) | Later |
| Falstad CircuitJS1 | Animated current-flow visuals | GPL-2.0+ | no releases | Optional, separate asset |
| PySpice / InSpice | Python ngspice bindings | GPL-3 | PySpice stale (2021) | Skip (license) |
| py-fsrs | Spaced-repetition scheduling per concept | MIT | 6.3.2 (Aug 9) | Use |
| pyBKT | Knowledge tracing (built for cohorts) | MIT | 1.4.3 (Aug 5) | Later, research only |
| Obsidian | Opening and browsing the vault | Proprietary, free | — | Optional |
| Foam, SilverBullet | Open-source vault readers | MIT | not verified | Optional |
| react-force-graph-2d | Vault graph inside the web UI | MIT | 1.29.2 (Sep 29) | Use |
| FastAPI + uvicorn | Local server, SSE push | MIT / BSD-3 | 0.159.1 (Oct 21) | Use |
| Vite + React | Front-end build | MIT | Vite 8.3.4, React 19.3.0 | Use |

**Gotchas:**
- The tscircuit packages are 0.0.x/1.x and release almost daily, so pin exact versions.
- The schematic viewer's right-click analysis fetches code from a CDN; disable it to keep everything local.
- GPL tools (CircuitJS, InSpice) stay out of the Python package.

Re-checked by the agent, 2026-10-22:
- FastAPI 0.161.1 (MIT), uvicorn 0.54.0 (BSD-3), fsrs 6.3.2 (MIT), httpx 0.28.1 (BSD-3, test client only).
- React 19.3.1, Vite 8.3.5, @vitejs/plugin-react 6.1.2, @tscircuit/pcb-viewer 1.11.433, react-force-graph-2d 1.29.2 (all MIT).
- @tscircuit/schematic-viewer 2.0.105: no license field on npm, but its GitHub LICENSE is MIT. It lists `tscircuit` and `typescript` as peer dependencies.

## How it wires together

The run folder stays the single source of truth: the harness writes it, the learn server reads it and adds learning records, and the browser only talks to the server. The UI never calls the model or the simulator directly.

Data that already exists from v1: spec.json, plan.json, parts.json, per-attempt verify.json (with each violation's refs and why), circuit.json from tscircuit, learn.json, signoff.json.

New contracts for v2 (added to `reflow/contracts.py`, frozen by tests like the others):

| Contract | Fields (short) |
|---|---|
| SimRequest | concept, target refs, variant (as_designed / broken), change (e.g. remove C1, R1=47k) |
| SimResult | concept, variant, signals [{name, unit, t[], v[]}], ngspice exit code, deck path, ran: bool |
| ConceptCard | concept, FSRS state, last reviewed, history of ratings |
| VaultNote | path, kind (concept / mistake / board), frontmatter, links |

Server endpoints:

| Endpoint | Does |
|---|---|
| GET /run | Spec, plan, parts, circuit-json and violations for the viewers |
| GET /learn/next | The next interaction the learn engine picked (or none) |
| POST /learn/answer | The user's click/answer; returns the why, updates the concept card |
| POST /sim | A SimRequest; result arrives later as an SSE event |
| GET /events | SSE stream: harness progress, sim.done, learn.next |
| POST /signoff | Final y/n + overrides; unlocks fab export |
| GET /vault/graph | Nodes and links parsed from the vault's wikilinks |

Order of events in one `reflow design` run:

1. The harness runs as today and writes the run folder.
2. The server starts and opens the browser.
3. The learn engine picks 1–3 interactions from the run and the concept cards.
4. The user answers in the schematic view (break-it and explore are optional).
5. Cards and vault notes update.
6. Sign-off.
7. Routing and fab export continue.

## Build order, risks and open questions

Originally planned to start after v1 ships (Nov 1) and after the AMC and MTFC crunch. Moved forward on 2026-10-22: the human wants learn mode in the Phil's Lab demo. Each phase is useful on its own.

1. Web shell + click-to-spot-the-bug: FastAPI server, schematic and PCB viewers, the v1 interaction moved from the terminal to a click.
2. Learner model + vault: concept cards, skip logic, notes written after each board.
3. Break-it for two concepts: decoupling and I²C pull-ups, each testbench checked against a hand calculation before it ships.
4. Click-to-explore + make-the-call: part explanations from the plan and spec; value choices answered by simulation.
5. Later: live sliders (in-browser ngspice), more concepts, optional animated visuals.

| Risk | Fallback |
|---|---|
| A testbench shows misleading physics | Every testbench has a known-good/known-bad test and a hand-calculated expected value; if a concept has no validated testbench, the UI says so |
| tscircuit viewers change weekly | Pin exact versions; wrap them in one component so a swap touches one file |
| Testers find it quiz-like and click through | Measure: share who name the right part before the reveal, time spent, skip requests; cut anything that feels like homework |
| Scope creep delays everything | Phases 1–2 are the v2 release; simulation ships when its first two testbenches are validated |

Open questions:

- Should break-it run on every board, or only when the user asks? (Interim: only when asked.)
- Is free-text "why" graded at all, or just shown alongside the right answer? (Interim: shown, not graded.)
- Should the vault be shareable (a team vault for a robotics club), or strictly personal?

## Sources

Pages opened 2026-10-22 (component links are in the building-blocks table): the tscircuit SPICE simulation guide (`<analogsimulation>`, `tsci simulate`), ngspice, eecircuit-engine, py-fsrs on PyPI, pyBKT, the Obsidian license, FastAPI.

Not verified:
- tscircuit simulation beyond transient analysis;
- eecircuit-engine's result format and bundled ngspice version;
- whether KiCanvas opens KiCad 10 files;
- ngspice's exact license mix;
- Foam and SilverBullet versions;
- whether InteractiveHtmlBom needs KiCad's Python to read boards.
