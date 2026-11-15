# T-2: a front door anyone can use, with a live view of the board being built

Status: PROPOSED 2026-11-14 by the agent (Claude), at the human's request after the recorded demo call. Nothing here is built. Questions A–F are the human's to decide. Changes to R-10 (HUMAN) and to the resolver (P-02, HUMAN) stay HUMAN. A contract change needs an accepted `DECISIONS.md` entry. Golden rule 5 holds throughout: the AI never picks a part number.

## Why

On the call (2026-11-14), the host asked for **visuals**: when you accept the plan, an animation of the schematic and PCB being built, ideally in 3D.

The human's own goal is bigger. Reflow should work for **people with no electronics experience**, not only for people who can read a datasheet:
- hobbyists first, on low-power boards;
- higher-power boards, the Hack Club ASIC work and high-bandwidth memory later, as the human learns them (README, "This project grows as I learn").

Today's TUI (T-01) asks a person for four things a beginner can't give:
1. an exact part number;
2. answers to design questions with no suggested answer;
3. a `rules.toml` written from the datasheet;
4. a reading of a KiCad schematic.

It also shows nothing visual until you open KiCad.

## What exists to build on

- **Learn mode** (`reflow learn`) is a local web app: FastAPI on 127.0.0.1, with React in `web/`. It already shows a run's board in tscircuit's schematic and PCB viewers (`web/src/BoardView.tsx`), and it runs ngspice simulations (L-12).
- **The design loop** writes `run.json` after every step, and each compile's `circuit.json` lands in `runs/<run>/attempts/NN/build/`. A page can follow a run as it happens without changing the loop (HUMAN core).
- **The parts catalog** groups parts by kind. For example, it has 369 accelerometers, 106 of them in stock, and 744 current-sense amplifiers, 264 in stock (local snapshot, checked 2026-11-14).
- **V-2b (accepted 2026-10-22)** already decided that model-drafted rules are allowed if they're visible, marked and confirmed by a person. Its contract patch (V-23) and the `reflow rules confirm` command (V-24) aren't built.
- **R-10 (HUMAN, todo):** until it's built, `rules.toml` guides the design but doesn't fail a board.

## The pieces

### 1. Live build view (T-02)
After **Accept** and **Run the design**, a browser tab opens beside the TUI and shows the run:
- **Each attempt in order:** a compile error, the verifier's violations drawn on the board, then the next attempt.
- **For each compiled attempt:** the schematic, the PCB, and a 3D view of the board.
- **A build-up animation of the compiled board:** parts placed, then traces. It's labelled as a replay of the finished attempt, because tscircuit's router doesn't report the order it routed in.
- **The final verdict and next steps:** passed or failed, then learn mode, sign-off and export.

**Honesty rule:** the page shows only what this run produced. No canned animation, no progress bar that isn't tied to a real step, and a failed attempt shown as failed. On a recorded demo this is also what makes it believable.

### 2. Parts from a description, chosen by the person (T-03)
A beginner types "an accelerometer" instead of a part number. Reflow searches the local catalog for that kind of part and shows a few real options. The person picks one, and it becomes a typed part, like the part numbers people type today. Each option shows:
- whether it's in stock;
- its package and whether a hand can solder it;
- whether KiCad has a symbol for it;
- a one-line plain description from the catalog.

**Only parts with a trusted pin map are offered** (a KiCad symbol or vendor pin data), because pin binding (V-12) fails anything else. That keeps the list short and every option usable.

**Where the model fits:** at most, it turns "accelerometer for a robot" into a catalog query (a category and a few filters). It never names a part, and the person always makes the choice.

### 3. Rules a beginner can confirm (T-04, which is V-2b in practice)
The helper drafts each rule from the uploaded datasheet with:
- the exact quote and page;
- one plain sentence on why: "the chip pulls this line low but can't pull it high, so a resistor has to".

The person accepts or rejects each rule, and every accepted rule records who confirmed it (V-23's `confirmed_by`). Nothing becomes a rule without that click.

### 4. Suggested answers to plan questions (T-05)
Each planner question comes with a suggested answer and one line of why, e.g. "0603: big enough to solder by hand." The person can accept it or type their own. Suggestions are design choices, never part numbers.

### 5. Later: the front door moves to the browser (T-06)
A terminal is itself a barrier for someone with no experience. Once pieces 1–4 work, the same flow could run in the learn-mode web app. The TUI would stay for people who like terminals.

## Questions for the human

**A. Do beginners get rules before R-10?**
- *Recommended:* no. Build R-10 first, so confirmed rules really fail a board. A beginner who sees "passed" while a rule they confirmed is broken gets false confidence, which reflow exists to prevent.

**B. Where do the visuals live?**
- *Recommended:* a browser tab next to the TUI, served by the learn-mode server. Terminals can't draw 3D. The alternative is moving the whole front door to the browser now (T-06), which is bigger and could come later.

**C. Which 3D viewer?**
- *Recommended:* tscircuit's `@tscircuit/3d-viewer` (0.0.651), which reads the same `circuit.json`. **Its license isn't stated in its npm metadata**, so read the repository's license file first (docs/agents/08-dependencies). The other two viewers are MIT.
- *Fallback:* a plain three.js render of the board outline, parts and traces.

**D. Part suggestions and golden rule 5.**
- *Recommended:* a `DECISIONS.md` entry saying a part the person picks from a catalog list counts as typed. The model may at most form the catalog query, and the list's order comes from the catalog (in stock, basic part, price), not from the model.

**E. Can a beginner accept every suggested answer with one click?**
- *Recommended:* no. One click per question, so each decision is still read.

**F. What does "beginner" still have to do before fab?**
- *Recommended:* learn mode's sign-off stays required before export, as today. The README and the UI say plainly that a person who can read the schematic should look at it before ordering.

## Tasks this would create

| ID | Goal | Owner | Needs |
|---|---|---|---|
| R-10 | The six `need` checks, so rules fail a board | HUMAN | — |
| T-02 | Live build view: attempts, schematic, PCB, 3D, verdict, from the real run folder | AGENT | B, C |
| T-03 | Parts from a description: catalog search by kind, only parts with a trusted pin map, the person picks | AGENT (resolver parts HUMAN) | D |
| T-04 | Helper-drafted rules with quote and page, each confirmed by the person (V-23, V-24) | AGENT→HUMAN (contract) | A, R-10 |
| T-05 | Suggested answers with a why for every plan question | AGENT (prompt AGENT→HUMAN) | E |
| T-06 | The front door in the browser | AGENT | T-02…T-05 |

**Suggested order:** R-10 → T-02 → T-03 → T-04 → T-05 → T-06.

T-02 can start before R-10, because it only shows what already happens.

## What this doesn't do

- It doesn't make an unreviewed board safe to order. The sign-off and the README's Risks stay.
- It doesn't widen what reflow can design: still simple, low-speed, 2-layer boards. Higher power, ASIC work and high-bandwidth memory need their own checks first, as the README's growth table says.
- It doesn't let the model choose parts or confirm rules.
