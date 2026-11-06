# Think-with-me mode: system design

**Status:** draft for the human to accept, change or reject. Nothing here is built. Contract changes
it needs are listed in [§1.5](#15-contract-changes-need-a-decisionsmd-entry) and need a `DECISIONS.md` entry first.
**Written:** 2026-11-05, from the code on `shashi` (`b7bd1ae`).

**Answers this is built on** (the human, 2026-11-05):
- notes go in reflow's existing vault, `~/.reflow/vault` (`REFLOW_VAULT`);
- core Obsidian now, Dataview and Templater later, so notes must work with no community plugin;
- path wikilinks, as [reflow/learn/vault.py](../reflow/learn/vault.py) writes them now (`[[concepts/decoupling]]`);
- the vault is synced with git.

**Principle:** reflow helps the designer think; it doesn't think for them. When a check fails:
1. reflow explains why the rule fired;
2. it asks a question before showing a fix;
3. it applies nothing unless the user approves it;
4. it keeps the user's own reasoning in their vault.

---

## 0. What already exists (read before anything below)

Think-with-me overlaps learn mode heavily. It should reuse that code, not build a second copy.

| Exists | File | What think-with-me reuses |
|---|---|---|
| Rules and their human-written text | [reflow/rules/](../reflow/rules/) (HUMAN), [reflow/violation.py](../reflow/violation.py) (HUMAN) | `Violation.rule_id`, `message`, `why` (for people), `fix_hint` (for the model), `refs`, `nets`. **`why` is already hand-written physics**, the core of every explanation. |
| The design loop | [reflow/harness/loop.py](../reflow/harness/loop.py) (HUMAN) | Nothing at runtime. Its docstring says it must never import learn mode, and think-with-me is learn-mode-like. It reads what the loop writes: `attempts/NN/verify.json`. |
| The netlist | [reflow/netlist.py](../reflow/netlist.py) (HUMAN), [reflow/circuit_netlist.py](../reflow/circuit_netlist.py) | Which parts sit on a violation's nets, so a question can name them. |
| Spot-the-bug | [reflow/learn/engine.py](../reflow/learn/engine.py) (L-01, awaiting review) | Two of its rules: questions come only from real violations, and a `pinout.mismatch` is treated as the root cause of other errors on the same part. Also `concept_of(rule_id)`, and the rule that a wrong answer teaches but never blocks. |
| Fix-it tools | [reflow/learn/fixit.py](../reflow/learn/fixit.py) (L-14) | The only way an edit reaches a design: the user's edits change a *copy* of the TSX under `learn/fix/<n>/`, then the same verifier checks it. No model is involved. |
| The vault | [reflow/learn/vault.py](../reflow/learn/vault.py) (L-11) | `concepts/`, `mistakes/`, `boards/`; JSON-valued frontmatter; the `## My notes` section survives rewrites; the outside-vault write guard; `graph()`. |
| Citations | `contracts.Citation` (`doc`, `locator`, `url`); `ProjectRule.source` in `rules.toml`; `PinMap.source` in [reflow/parts/pinmap.py](../reflow/parts/pinmap.py) | Every datasheet reference think-with-me shows comes from one of these. |
| Book and datasheet citations for built-in rules | [docs/proposals/R-11-cited-rules.md](proposals/R-11-cited-rules.md) (proposal, Q1–Q13 open) | The format for citing a standard or book (title, section, page; no stored quotes). |

Two gaps shape the design:
- **Built-in rules cite nothing today.** `decoupling.series` has a good `why` but no datasheet or standard reference. R-11 proposes adding citations; it isn't decided.
- **`rules.toml` rules don't fire yet.** R-10 (`project.cap` …) is todo. Their `source` and `why` can still be *looked up* by part and pin, which is all think-with-me needs.

---

## 1. Architecture

### 1.1 Components

```
                       ┌──────────────────────────── read only ────────────────────────────┐
 run folder            │                                                                   │
 attempts/NN/verify.json ─┐                                                                │
                          ├─► [A] ViolationSource ─► [B] Grounder ─► [C] Session ─► [E] NoteWriter ─► vault
 reflow check --json  ────┘        (AGENT)            (HUMAN)       state machine    (AGENT)
                                                        ▲            (HUMAN gate)
                                    [R] Explanation     │                 │
                                        registry ───────┘                 ▼
                                        (HUMAN)                    [D] FixPath ─► learn/fix/<n>/ (copy) ─► same verifier
                                                                       (AGENT→HUMAN)
                                    [M] model (optional, off by default) ─► text labelled UNVERIFIED only
```

| | Component | Owner | Does | Must never |
|---|---|---|---|---|
| A | **ViolationSource** | AGENT | Turns a run folder (first failed attempt's `verify.json`, pinout root causes first, as `engine.pick` orders them) or `reflow check --json` output into a list of violations to work through, each with the board it came from | Invent a violation, or re-run a rule |
| R | **Explanation registry** | **HUMAN** | One hand-written entry per `rule_id`: failure mode, guiding question(s), the reveal answer, citations to standards or app notes, and a concept id | Be written or edited by a model or agent |
| B | **Grounder** | **HUMAN** | Builds one `Explanation` from three things: the `Violation`, its registry entry, and the per-part citations (a `rules.toml` `[[rule]]` on the same ref and pin, or the pin map's `Citation` for `pinout.*`). Labels every piece `verified`, `cited` or `unverified` (§3) | Take a citation from model text; change `Violation.why` |
| C | **Session state machine** | **HUMAN** | Per violation: explain → ask → wait for the user's reasoning or an explicit "show me" → reveal → propose fix → **approve or decline** → re-verify → done. Also the only place an approval is recorded | Reveal the answer before the user answers or asks; apply anything without an approval event |
| D | **FixPath** | AGENT→HUMAN | For a design run: `fixit.check_fix` on a copy, with edits the user built or approved. For `reflow check`: nothing is applied. reflow shows the fix and the user makes it in KiCad, then re-runs `reflow check` | Edit the user's `.kicad_sch`, the run's `attempts/`, or anything outside `learn/fix/` |
| E | **NoteWriter** | AGENT | Writes `reasoning/` and `sessions/` notes, and adds links to the `concepts/`, `boards/`, `rules/` and `sources/` notes (§2), through `Vault._write` | Rewrite the user's sections; write outside the vault; run git |
| M | **Model (optional)** | prompt HUMAN, plumbing AGENT | Off by default. If turned on, it may only reword the registry's question for this board, or answer a follow-up. Its text goes only into an *Unverified* block | Supply a citation, a fix, a part number (AGENTS.md rule 5), or the "why" |
| F | **Front end** | AGENT | Terminal first (`reflow think`), later a tab in the learn UI | Show the answer before the state machine allows it |

### 1.2 Data flow for one violation

```
Violation (rule_id, message, why, fix_hint, refs, nets)           from verify.json / check --json
  │
  ├─ registry[rule_id] ─────────► entry: failure_mode, question, answer, citations, concept
  ├─ rules.toml [[rule]] on ref.pin ─► per-part `source` + the student's own `why`   (if any)
  └─ pin map Citation ───────────► doc + locator                                   (pinout.* only)
  ▼
Explanation   segments: [ {text, label: verified|cited|unverified, from: "rules/decoupling.py"|"registry"|...} ]
  ▼
1. SHOW    message + why (verified) + citations (cited). No fix_hint, no answer yet.
2. ASK     registry question, e.g. "What does the chip see on VDD at DC, with C1 in series?"
3. WAIT    user types their reasoning  ──or──  explicitly asks "show me the answer"
             (both are recorded; neither blocks; an empty answer is allowed and recorded as empty)
4. REVEAL  registry answer + fix_hint (verified)
5. PROPOSE the fix: fix_hint in words; for a design run, the matching FixEdits as a preview
6. GATE    approve / decline / "I'll do it myself". Only `approve` lets FixPath run.
7. VERIFY  design run: check_fix → FixResult (same verifier). check mode: "re-run reflow check".
             outcome: resolved | still failing | not re-checked
8. NOTE    reasoning note (write-once) + links from concept/board/rule/source notes
```

### 1.3 Where it plugs into the harness

**Not inside the loop.** `loop.py` is HUMAN core, and its docstring forbids importing learn mode. The
loop also *is* the autonomous fixer: it sends `fix_hint` back to the model. Think-with-me works on what
the loop leaves behind, the same way `reflow learn RUN_DIR` does:

| Entry point | Reads | Writes |
|---|---|---|
| `reflow think RUN_DIR` | `run.json`, `attempts/NN/verify.json`, `circuit.json`, `spec.json` (for `rules_file`) | `RUN_DIR/think/session-<n>.json` (the session record), `RUN_DIR/learn/fix/<n>/` (only through FixPath), the vault |
| `reflow check --think SCHEMATIC` | the `VerifyReport` that `cmd_check` already builds | the vault only; never the schematic |
| learn UI tab (later) | as `reflow think` | as `reflow think` |

`reflow check --think` is the mode closest to the stated principle: the user designed the board, and
reflow helps them reason about their own mistake. The design-run mode works on the AI's draft, as learn
mode does. Whether to offer one or both is open (§7, D2). Pausing the loop for the human at each
failure would change `loop.py` and is listed as an option, not proposed (§7, D3).

### 1.4 What stays the same

- `reflow/rules/`, `violation.py`, `netlist.py` and `loop.py` don't change. The registry is keyed by
  `rule_id`, so no rule needs a new field.
- The verdict is still the verifier's. Think-with-me never marks a violation resolved; only a re-verify
  (`check_fix`, or a new `reflow check`) can.
- `reflow export`'s gates (verify, route, DRC, sign-off) don't change. A think-with-me session is not
  a sign-off.

### 1.5 Contract changes (need a DECISIONS.md entry)

| Change | Why |
|---|---|
| `VAULT_KINDS` gets `"reasoning"`, `"session"`, `"rule"`, `"source"` | New note folders (§2). `VAULT_KINDS` is a frozen contract set. |
| New `Explanation`: `rule_id`, `concept`, `segments: list[ExplanationSegment]`, `citations: list[Citation]`, `registry_hash` | Crosses Grounder → Session → NoteWriter |
| New `ExplanationSegment`: `text`, `label` (`verified` / `cited` / `unverified`), `origin` (a file path or `"model"`) | Grounding labels travel with the text |
| New `ThinkStep`: `rule_id`, `refs`, `nets`, `question`, `user_reasoning`, `asked_for_answer`, `answered_before_reveal`, `fix_status` (`none` / `proposed` / `approved` / `declined` / `self`), `outcome` (`resolved` / `failing` / `unchecked`), `fix_number` | The session record, written to `think/session-<n>.json` |
| New `ThinkSession`: `source` (`run` / `check`), `board`, `run_dir` or `schematic`, `verify_hash`, `steps`, `started`, `ended` | One per sitting |

---

## 2. Obsidian note schema

### 2.1 Folder layout

```
~/.reflow/vault/                      (REFLOW_VAULT; a git repo the user manages)
├── concepts/<concept>.md             EXISTING. Concept card. Gains a "## Reasoning" link list (see D9)
├── mistakes/<date>-<board>-<concept>.md   EXISTING (learn mode spot-the-bug)
├── boards/<board>.md                 EXISTING. Gains links to this board's sessions
├── reasoning/<date>-<board>-<rule>.md     NEW. One per violation worked through. WRITE-ONCE.
├── sessions/<date>-<board>-<n>.md         NEW. One per sitting: the list of reasoning notes, outcome counts
├── rules/<rule-id>.md                     NEW. Generated from the registry: what the rule checks, its
│                                          citations, the question. Rewritten when the registry changes.
└── sources/<doc-slug>.md                  NEW. One per cited document: the citation only, never its text
```

- **Names:** lower-case slugs, as `vault._slug` makes them. A rule id's dot becomes a hyphen
  (`decoupling.series` → `rules/decoupling-series.md`), so the id is never mistaken for a file extension.
  Dates are UTC `YYYY-MM-DD`. A collision gets `-2`, `-3` (as `write_mistake` does).
- **The concept ids** are the ones `engine.concept_of` already gives (`decoupling`, `i2c-pullup`,
  `address-strap`, `pinout`, `led-current-limit`), so learn mode and think-with-me share concept notes
  and their fsrs cards.

### 2.2 Frontmatter

Written the way `vault._write` writes today: one `key: <JSON value>` per line. JSON is valid YAML, so
core Obsidian shows the values as properties.

Rules for Dataview later:
- flat keys;
- snake_case;
- one type per key, across every note;
- lists are always lists, even with one item.

**`reasoning/` note:**

| Key | Type | Example | Notes |
|---|---|---|---|
| `kind` | text | `"reasoning"` | |
| `schema` | number | `1` | Bumped on any field change, so an old note is read correctly |
| `title` | text | `"mcp9808-breakout: C1 in series with U1 VDD"` | |
| `date` | text (ISO UTC) | `"2026-11-05T14:02:11Z"` | See D13 for Obsidian's date type |
| `board` | text | `"mcp9808-breakout"` | |
| `source` | text | `"run"` or `"check"` | |
| `run_dir` / `schematic` | text | `"runs/20261105-140000-mcp9808-breakout"` | The one that applies; the other is `""` |
| `attempt` | number | `1` | `0` for check mode |
| `rule_id` | text | `"decoupling.series"` | |
| `severity` | text | `"error"` | |
| `concept` | text | `"decoupling"` | |
| `refs` / `nets` | list | `["C1","U1"]` / `["V3_3","Net-(C1-Pad2)"]` | From the violation, unchanged |
| `grounding` | list | `["verified","cited"]` | Labels present in the note. If `"unverified"` is in the list, the note has model text |
| `citations` | list | `["sources/microchip-ds20005095b"]` | Links to `sources/` notes |
| `asked_for_answer` | checkbox | `false` | The user clicked "show me" before answering |
| `answered_before_reveal` | checkbox | `true` | |
| `fix_status` | text | `"approved"` | `none` / `proposed` / `approved` / `declined` / `self` |
| `outcome` | text | `"resolved"` | `resolved` / `failing` / `unchecked`, from the re-verify only |
| `registry_hash` | text | `"sha256:9f2c…"` | The registry entry this note was written from (staleness, §5.2) |
| `verify_hash` | text | `"sha256:41ab…"` | The `verify.json` or check report it came from |
| `reflow_version` | text | `"0.1.0"` | |

**`sessions/` note:**
- `kind`, `schema`, `title`, `date`, `board`, `source`, `run_dir` or `schematic`;
- `reasoning`: a list of links;
- counts: `answered`, `asked_for_answer`, `approved`, `resolved`.

**`rules/` note:**
- `kind`, `schema`, `rule_id`, `concept`;
- `citations` and `registry_hash`;
- `generated: true`, so the user knows reflow rewrites it.

**`sources/` note:**
- `kind`, `schema`, `doc`, `locator_examples`, `url`;
- `cited_by`: a list.

### 2.3 Body of a `reasoning/` note

```markdown
# mcp9808-breakout: C1 in series with U1 VDD

## What the check found
C1 sits in series between V3_3 and U1.8; U1 only gets power through a capacitor, which blocks DC.

## Why the rule fired
A capacitor blocks DC, so the chip never gets steady power and won't turn on. ...   ← Violation.why, verbatim
Failure mode: ...                                                                   ← registry, verified
Sources: [[sources/microchip-ds20005095b|MCP9808 datasheet]], 6.1 Layout Considerations, p.35   ← cited

## The question
What does U1 see on VDD at DC with C1 where it is?

## My reasoning
<the user's words, verbatim, never edited by reflow>

## The answer
<registry answer + fix_hint>  ·  or: "Not revealed."  ·  or: "Revealed on request before answering."

## The fix
Proposed: Connect U1.8 directly to V3_3, then rewire C1 ... · Status: approved · Re-verify: resolved (fix 2, 0 errors)

> [!warning] Unverified: model-generated
> <only if the model was used; otherwise this block is absent>

## My notes

Concept: [[concepts/decoupling]] · Rule: [[rules/decoupling-series]] · Board: [[boards/mcp9808-breakout]] · Session: [[sessions/2026-11-05-mcp9808-breakout-1]]
```

- **Callouts** (`> [!warning]`) are core Obsidian, so no plugin is needed for the *Unverified* block.
- **The user's sections** are `## My reasoning` and `## My notes`. reflow never rewrites them. A
  `reasoning/` note is write-once anyway (§2.5).

### 2.4 Linking conventions

- **Path links without `.md`**, as now: `[[concepts/decoupling]]`. An optional display alias
  (`[[concepts/i2c-pullup|I²C pull-ups]]`) keeps the path but reads like the brief's `[[I2C pull-ups]]`.
  `vault._LINK` already accepts `|alias`. Whether to write aliases is D11.
- **Every `reasoning/` note links up to:**
  - exactly one concept;
  - one rule;
  - one board;
  - one session;
  - its sources.
- **Concept, board, rule and source notes link down** in a list. Obsidian's backlinks show the same
  thing without writing a list; D9 weighs the git cost.
- **No link to a file that doesn't exist.** `graph()` already drops dangling targets. The NoteWriter
  creates the `rules/` and `sources/` notes before linking to them.

### 2.5 Git-friendly writing

The vault is a git repo, so every write should make a small, readable diff and avoid merge conflicts.
- **Write-once:**
  - `reasoning/` and `sessions/` notes are created and never rewritten;
  - a correction is a new note that links the old one.
- **Deterministic output:**
  - keys in a fixed order;
  - lists sorted, or in a stable order;
  - LF line endings and a trailing newline;
  - nothing time-dependent in a note that gets rewritten, except the field that changed.
- **No rewrite unless the content changes.** Rendering a note twice from the same input must produce
  identical bytes, so `git status` stays clean.
- **reflow never runs git.** It doesn't commit, pull or push. Where the user's reasoning goes is their
  choice; the docs say plainly that pushing the vault sends their notes to that remote.

---

## 3. Explanation grounding

Every sentence shown carries one of three labels, and each label says where the sentence came from.

| Label | Comes from | Who wrote it | Shown as |
|---|---|---|---|
| **verified** | `Violation.message` / `why` / `fix_hint` (from `reflow/rules/*.py`, or `reflow/pinbind.py` for `pinout.*`); registry `failure_mode`, `question`, `answer` | The human, reviewed line by line | Plain text |
| **cited** | registry `citations` (a standard, app note or book; R-11's format); `rules.toml` `source` for the same ref and pin; `PinMap.source` (`doc`, `locator`) | A person, pointing at a page | Text plus "Source: doc, locator". **Cited ≠ checked**: reflow doesn't read the page unless R-11's quote check exists and passed |
| **unverified** | the model, if turned on | A model | Only inside the *Unverified* callout, never in "Why the rule fired" or "The fix" |

The chain for one explanation, each link checkable by a test:

1. `Violation.rule_id` → **the rule that emitted it.** A test scans `reflow/rules/*.py` and
   `reflow/pinbind.py` for `rule_id` string literals (AST), so the set of ids is known without running anything.
2. `rule_id` → **its registry entry.** A coverage test: every id from step 1 has an entry, and every
   entry's id is in step 1. A new rule with no entry fails CI. A deleted rule leaves an orphan entry, which also fails.
3. Entry → **its citations.** Each one is a `Citation` (`doc`, `locator`, optional `url`). An entry with
   no citation shows "No source cited for this rule yet" instead of nothing, so a missing citation is visible.
4. Violation `refs` + `nets` → **per-part citations.**
   - a `rules.toml` `[[rule]]` whose `on` is one of the violation's refs, on a pin on one of its nets;
   - or, for `pinout.*`, the pin map the binder used.

   The student's own `why` from `rules.toml` is shown as "**You wrote:**", so it's clear it's their words.
5. **The text shown = the text stored.**
   - the "Why the rule fired" section equals `Violation.why` byte for byte, followed by the registry entry;
   - a test compares the rendered note against those sources.

**Registry file:** `reflow/think/explanations.toml` (HUMAN; add it to `CODEOWNERS` and to
REVIEWING.md §2's first row). One table per rule id:

```toml
[decoupling.series]
concept      = "decoupling"
failure_mode = "The chip's supply pin sees an open circuit at DC: it never powers on, or brown-outs ..."
question     = "What does {ic} see on {pin_net} at DC, with {cap} where it is?"
answer       = "Nothing: at DC a capacitor is an open circuit, so ..."
citations    = [{ doc = "...", locator = "..." }]
```

- **Placeholders** (`{ic}`, `{cap}`, `{pin_net}`) are filled only from the violation's `refs` and
  `nets`, by position, as the rule defines them. They're never filled from model text.
- **Copyright** (R-11 Part C): no datasheet or book text is stored in the registry, the vault or the
  session record. Only a citation and our own words.

---

## 4. Hand-code vs. offload

"HAND-CODE" is the HUMAN owner in AGENTS.md. "Offload" is AGENT (or AGENT→HUMAN where a reviewer must look).

| Piece | Owner | Why |
|---|---|---|
| Explanation registry content (failure modes, questions, answers, citations) | **HAND-CODE** | It *is* the explanation. A wrong sentence here teaches the wrong physics with a "verified" label. |
| `rule_id → entry` mapping and `rule_id → concept` (`engine.concept_of`) | **HAND-CODE** | Decides which explanation a violation gets. |
| Grounder: which source gets which label, placeholder filling, the "no citation" fallback | **HAND-CODE** | Decides what may be called verified. |
| Session state machine: the reveal gate and the approval gate | **HAND-CODE** | The two promises of the mode: no answer before the user thinks, no change without approval. |
| "Resolved" = the re-verify's `errors == 0` for that rule id and its refs | **HAND-CODE** | It's a verdict. |
| The think prompt, if the model is used (`prompts/think.md`) | **HAND-CODE** (H-08 style) | It steers what the model writes. |
| Registry coverage test, grounding byte-equality test, gate tests | AGENT→HUMAN | A test of correctness; the human reads it. |
| FixPath (calling `check_fix` with approved edits) | AGENT→HUMAN | Plumbing, but it touches the design copy. |
| Staleness hashes and `reflow vault audit` | AGENT→HUMAN | Plumbing; a wrong hash hides staleness. |
| ViolationSource (reading `verify.json`, `check --json`) | Offload | Plumbing over existing contracts. |
| Note rendering, frontmatter, slugs, folder layout, link lists | Offload | Boilerplate; tests pin it. |
| CLI flags (`reflow think`, `reflow check --think`, `--vault`), terminal prompts | Offload | Boilerplate. |
| Learn UI tab | Offload | Boilerplate over the same server state. |
| Dataview example queries and Templater templates (later) | Offload | Optional docs. |

---

## 5. Failure modes

### 5.1 Hallucinated explanations

**Risk:** a model explains a rule with wrong physics, an invented datasheet page, or a fix that adds a part.

**Mitigations:**
- **No model in v0.** Every explanation, question and answer comes from the rule text and the hand-written registry.
- **When a model is on:**
  - its text appears only in the *Unverified* callout;
  - it never fills "Why the rule fired", "The answer", "The fix" or a citation;
  - a test feeds a fake model text containing a page reference and a part number, and asserts neither
    reaches a verified or cited section, or `citations`.
- **AGENTS.md rule 5:** model text is never parsed into a part number or a `FixEdit`. `FixEdit`s come
  only from the user's own edits, or from the run's own later attempt shown as "the AI's fix" after the
  user tries (L-2a's existing rule).
- **No vault notes go back to the model.** Past notes contain earlier model text. Feeding them back
  would compound errors and opens a prompt-injection path. Add this to [REVIEWING.md](REVIEWING.md) §3.
- **The registry can be wrong too.** It's HUMAN-reviewed, has citations, and a "Report this
  explanation" path writes the user's objection to their note. It never silences the rule.

### 5.2 Stale notes

**Risk:** a note says "verified" about text that has since changed. Causes:
- a rule's `why` changed;
- a registry entry was corrected;
- `rules.toml` was edited;
- a datasheet revision changed;
- the board was re-run.

**Mitigations:**
- **Fingerprints in every note:**
  - `registry_hash` (the entry);
  - `verify_hash` (the report the note was written from);
  - `reflow_version`;
  - the hash of the `rules.toml` entry it cited.
- **`reflow vault audit`:**
  - recomputes each fingerprint from the current registry, rules and `rules.toml`;
  - lists the notes whose text no longer matches, with the reason ("decoupling.series explanation
    changed on 2026-11-20");
  - is read-only by default (D10).
- **`rules/` notes are regenerated** from the registry, so the current explanation is always one link
  away from an old note.
- **Write-once `reasoning/` notes:** an old note stays a true record of what was shown *then*, and is
  never silently rewritten.

### 5.3 Users who skip the question

**Risk:** the user always clicks "show me", so the mode becomes a fixer with extra steps.

**Mitigations:**
- **Never block.** Skipping is allowed and recorded honestly (`asked_for_answer: true`,
  `answered_before_reveal: false`). This is the same rule learn mode already follows.
- **Light friction:** the reveal is one explicit action ("Show me the answer"), never a timeout or a
  default. Typing anything, even "no idea", counts as an answer.
- **Make it visible:**
  - the session note and the end-of-session summary show "answered 1 of 4 before revealing";
  - the concept note lists skipped reasoning notes too, so the gap shows up in the graph.
- **The concept card is optional.** The skip may or may not count against the concept's fsrs card (D7).

### 5.4 Others worth designing for now

| Failure | Mitigation |
|---|---|
| A fix applied without approval | The state machine is the only caller of FixPath. Gate test: every path to `check_fix` goes through an `approve` event (and a test that a declined step never creates `learn/fix/<n>/`). |
| A fix applied to the wrong thing | FixPath only writes `learn/fix/<n>/` (fixit's guard). Check mode applies nothing. A test asserts the schematic's bytes are unchanged after `--think`. |
| Cascading violations (a wrong pinout makes three other rules fire) | Reuse `engine.pick`'s root-cause order: `pinout.*` first; consequences shown as "probably caused by U1's labels; re-check after fixing that". |
| The user's reasoning says the rule is wrong (a false positive) | An "I think this rule is wrong here" answer is recorded with the user's reason and linked to the rule note. The violation stays. A human reviews rule changes. |
| Git conflict on a rewritten note (concept, board, rule notes) | Write-once for the notes that matter; deterministic bytes; D9 (stop writing link lists and rely on backlinks). |
| The vault was edited by the user (frontmatter rewritten by Obsidian into YAML lists) | `vault._read_note` already reads YAML lists and plain strings; tests cover a note Obsidian rewrote. |
| Writing outside the vault | `Vault._write`'s `is_relative_to` guard, reused, plus a test with `../` in a board name. |

---

## 6. Build order (30-minute blocks)

Each block is one task with a failing test first, as AGENTS.md asks. HUMAN blocks are marked; an agent
does only the others, and stops at each HUMAN block. Some blocks will run over; it's better to split a
block than to merge two.

| # | Block | Owner | Test that fails first, then passes |
|---|---|---|---|
| 0 | DECISIONS entry for §1.5's contracts, and the answers to §7 that v0 needs (D1, D2, D5 at least) | HUMAN | none; human accepts |
| 1 | Contracts: `Explanation`, `ExplanationSegment`, `ThinkStep`, `ThinkSession`, new `VAULT_KINDS` | AGENT | `tests/test_contracts.py`: round-trip `to_dict`/`from_dict`; the frozen field lists |
| 2 | Registry loader + one entry (`decoupling.series`) | loader AGENT, entry HUMAN | Loader parses the entry; a missing key or unknown key raises; a placeholder not in the allowed set raises |
| 3 | Registry coverage test | AGENT→HUMAN | AST scan of `rule_id` literals in `reflow/rules/` + `reflow/pinbind.py` vs registry keys. **Fails** until block 4 |
| 4 | The remaining entries: `decoupling.missing`, `i2c.*`, `address.floating`, `pinout.*` | HUMAN | Block 3's test passes |
| 5 | Grounder | HUMAN | On `fixtures/bad_series_cap`: the "why" segment equals `Violation.why` byte for byte and is `verified`; a citation from `rules.toml` is `cited`; no segment is `unverified`; an entry with no citations yields the "No source cited" segment |
| 6 | Session state machine (pure functions, no I/O) | HUMAN | The answer isn't obtainable before `answer` or `ask_for_answer`; `apply` raises without `approve`; `declined` can't become `approved` without a new proposal; every transition is recorded |
| 7 | ViolationSource, check mode (`reflow check --json` → steps) | AGENT | `fixtures/bad_series_cap`, `bad_no_pullups`, `bad_floating_addr` each give exactly their rule's steps; `real_good` gives none |
| 8 | ViolationSource, run mode (first failed attempt, root cause first) | AGENT | A `tests/data/real_runs/` folder with a `pinout.mismatch` puts it first and marks the consequences |
| 9 | Reasoning-note renderer | AGENT | Golden file; re-render is byte-identical; frontmatter parses with `vault._read_note`; links are path links that exist after block 10 |
| 10 | Session, rule and source notes + concept/board links | AGENT | `Vault.graph()` has the new kinds and edges; a `../` board name is refused; a second run with the same input changes no bytes |
| 11 | `reflow check --think` terminal flow | AGENT | Scripted stdin: answer path and "show me" path; the schematic's bytes are unchanged; only the vault changed (tmp-dir diff) |
| 12 | `reflow think RUN_DIR` + FixPath | AGENT→HUMAN | No `learn/fix/<n>/` without approve; an approved correct fix → `outcome: resolved` from `check_fix`; a wrong one → `failing` |
| 13 | Fingerprints + `reflow vault audit` | AGENT→HUMAN | Edit a registry entry → that note is listed stale with the reason; untouched notes aren't |
| 14 | (optional, if D5 says so) model-reworded question behind a flag, `prompts/think.md` | prompt HUMAN, plumbing AGENT | Fake model returns a page reference and a part number: neither appears outside the *Unverified* callout or in `citations`/`FixEdit` |
| 15 | (later) learn UI tab | AGENT | The server never sends `answer` or `fix_hint` before the state machine allows it (API test, like `learn/answer`) |

Blocks 0, 2 (entry), 4, 5 and 6 are the human's, about 2.5 hours. v0 is blocks 0 to 11, all model-free.

---

## 7. Open decisions

Options with their tradeoffs. Not decided here.

**D1. Separate command, or part of learn mode?**
- (a) A separate `reflow think`. *Clear scope; doesn't touch L-01 code awaiting review. But two
  teaching flows on the same violations, which can confuse users.*
- (b) A new `LEARN_KINDS` kind, `"think"`, inside `reflow learn`. *One place to learn; reuses the
  server and UI. But it changes a frozen contract and L-01's code while it's under review.*
- (c) Both: one engine, two front ends. *Most flexible, most to test.*

**D2. Whose design?**
- (a) Check mode only: the user's own KiCad design. *Closest to "augment the designer"; no AI draft involved.*
- (b) Design runs only. *Fits the existing learn flow. But the user reasons about the AI's mistakes,
  not their own.*
- (c) Both. *Two ViolationSources; same everything else.*

**D3. Pause the design loop for the human?**
- (a) No: post-hoc only, as proposed. *No HUMAN core change.*
- (b) A loop option that stops after the first verify failure and hands over to think-with-me.
  *Truly human-in-the-loop design. But it changes `loop.py` (HUMAN) and the H-00 stop policy.*

**D4. Where citations for built-in rules live.**
- (a) In this registry. *Self-contained. But it could drift from R-11.*
- (b) In R-11's catalog, which the registry references. *One source of truth. But it waits on R-11's open questions.*
- (c) In the rule modules' docstrings. *Next to the code. But it means editing `reflow/rules/`, which the brief rules out.*

**D5. Model use.**
- (a) None. *Fully grounded; cheapest; can't adapt the question to an odd board.*
- (b) Reword the hand-written question for this board, unverified. *Small benefit, small risk.*
- (c) Answer follow-up "why?" questions, unverified. *Most helpful, most hallucination exposure; needs D-style eval.*

**D6. Grade the user's reasoning?**
- (a) No: recorded, shown next to the answer (L-2's interim answer for spot-the-bug's "why"). *Honest. No feedback on the reasoning.*
- (b) The user self-assesses ("I had it / partly / no"). *Cheap. Self-report, not evidence; L-11 rates only from what the user did.*
- (c) A model judges it, unverified. *Feedback. But a model grading physics is exactly what the mode distrusts.*

**D7. Does skipping the question affect the concept card?**
- (a) No review recorded. *Neutral. A skipped concept is never scheduled.*
- (b) Rated "again". *The concept is asked again sooner. But it punishes honesty about not knowing.*
- (c) Only answers before the reveal are reviewed. *Clean signal. Fewer reviews.*

**D8. Note granularity.**
- (a) One `reasoning/` note per violation, plus a session note (proposed). *Good backlinks and graph; more files.*
- (b) One session note holding every violation. *Fewer files. But the links say "this session", not "this mistake".*

**D9. Link lists in concept and board notes.**
- (a) Keep writing them, as vault.py does. *Visible without backlinks. But every session rewrites them,
  so they're the main source of git conflicts.*
- (b) Stop and rely on Obsidian's backlinks (core). *Write-once everywhere. But the list isn't visible
  in another Markdown reader, and `graph()` must read links from the child notes (it already does).*

**D10. Staleness.**
- (a) `reflow vault audit` reports and changes nothing. *Write-once holds. The user has to run it.*
- (b) The audit sets `stale: true` and a reason in the frontmatter. *Visible in Obsidian properties.
  But it rewrites write-once notes (one-line diffs).*
- (c) A generated `stale.md` index linking the stale notes. *One file changes; old notes stay untouched.*

**D11. Aliases in path links.**
- (a) Plain `[[concepts/i2c-pullup]]`. *Simplest.*
- (b) `[[concepts/i2c-pullup|I²C pull-ups]]`. *Reads like the brief. Slightly noisier source text.*

**D12. Git hygiene reflow could offer.**
- (a) Nothing; the vault is the user's repo. *Least surprise.*
- (b) `reflow vault init` writes a `.gitattributes` (`* text eol=lf`) and a `.gitignore` for Obsidian's
  `workspace.json`. *Fewer noisy diffs. But reflow writes into the user's repo config.*

**D13. Date properties.**
- (a) ISO UTC strings with `Z`, as vault.py writes now. *Consistent with existing notes. Obsidian may show them as text, not as a date property (not checked).*
- (b) `YYYY-MM-DDTHH:MM:SS` in local time. *Obsidian's date-time property type. Loses the zone.*
- (c) Both: `date` for Obsidian, `date_utc` for reflow. *Works either way; two fields.*

**D14. Field names for Dataview later.** Freeze §2.2's names now (schema 1), or wait until the
Dataview queries are written. *Freezing now avoids a migration; waiting avoids guessing what the queries need.*

---

## Unsure

- **Obsidian behaviour, not checked in Obsidian itself:**
  - whether core Obsidian shows JSON-valued frontmatter dates as a date property (D13);
  - whether a dot in a file name bothers it (avoided anyway with hyphens).
- **The AST scan for rule ids** (block 3) assumes ids are string literals at the `Violation(...)` call,
  which is true of every rule today (`address.py` passes it positionally). A rule that builds its id
  from a variable would need a registry entry the scan can't see.
- **The datasheet "section" for built-in rules** exists only once D4 is settled. Until then, most
  explanations show "No source cited for this rule yet". That's honest, but thin.
