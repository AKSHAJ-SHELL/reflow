# V-2b · Model-drafted rules are visible, marked and confirmed by a person

Status: **PROPOSED** 2026-10-22 by the agent (Claude), at the human's request. Amends V-2 and V-2a. Nothing binds until the human accepts it in `DECISIONS.md`. No code yet.

## Problem

V-2 says `rules.toml` is "written by the student from datasheets". In practice a student will read the datasheet and then ask a model to write the file. That's fine for typing, but not for trust:

- If the same kind of model writes both the board and the rules it's checked against, the verifier only confirms that the model agrees with itself. A misremembered pinout or decoupling value ends up in both, and the board passes.
- Today nothing in a `rules.toml` says who wrote a line, or whether a person checked it against the page it cites.

The human asked for a gate that makes the student go through the datasheet before a model writes rules for them. They also asked whether reflow can open a separate Claude Code session for that study.

## What this proposal is not

**No hidden instructions.** A buried instruction aimed at the student's model was considered and rejected:
- Coding assistants are trained to treat file contents as data and to tell the user about embedded instructions, so it would likely be reported as a prompt injection. For an open-source tool, that's a lasting reputation problem.
- It wouldn't be enforcement anyway. The student can delete it, switch models, or just say "yes, I read it".

Everything below is documented in the README. The only gate that actually holds is the one in reflow's own code (part C).

## Decision asked

### A. The datasheet-tutor skill writes rules only after the study (prompt text)

Move `docs/proposals/datasheet-tutor-SKILL.md` to `skills/datasheet-tutor/SKILL.md` and tighten its "Writing rules.toml" section:

1. **Study first.** Before writing any rule, walk the student through the sections that become rules: pin table, supply and decoupling, reset/boot, interface pull-ups, address straps, unused pins. After each one, the student says the fact back in one sentence. That sentence becomes the rule's `why`.
2. **Write only when asked.** The skill writes `rules.toml` only when the student asks for it.
   - If the student hasn't been through a section, the skill offers to walk it first.
   - If the student says they've already studied it themselves (any wording that means that), the skill writes those rules anyway. They're still marked as model-drafted, and the skill says so.
3. **Every rule it writes** gets `drafted_by = "model"`, a `source` with the page, and a `quote` holding the datasheet sentence the rule rests on.
   - No page means no rule.
   - It never fills in `confirmed_by`.
4. **It ends with the next step:** "run `reflow rules confirm` and check each line against its page."

The skill is prompt text: AGENT drafts it, HUMAN approves it, as for `prompts/*.md` (H-08).

### B. `reflow init [DIR]` sets up a student project (CLI)

Writes, and never overwrites (an existing file is reported and skipped):

| File | What it is |
|---|---|
| `.claude/skills/datasheet-tutor/SKILL.md` | a copy of the skill (part A), where Claude Code loads project skills |
| `AGENTS.md` | short, plain project instructions for any coding agent: rules.toml facts come from the datasheet; model-written rules carry `drafted_by = "model"` and a `quote`; never fill `confirmed_by`, only `reflow rules confirm` does; offer the datasheet-tutor walk-through before writing rules |
| `CLAUDE.md` | one line, `@AGENTS.md`, so Claude Code reads the same text |
| `rules.toml` | only with `--part REF=MPN[:Lib:Symbol]`: a skeleton built from the pin map (an outline, no model). One commented entry per pin that needs a decision: a cap for each power pin, pull-ups for I²C pins, a tie for each address pin, and open/connected for reset/boot/unused. `to`, `value`, `source` and `why` are left blank, so `reflow rules check` fails until a person fills them. |

These files work because they're meant to be read: Claude Code and other agents follow `CLAUDE.md` / `AGENTS.md` as the project's own instructions. The README names all of them.

### C. Model-drafted rules are marked and confirmed by a person (contract change + CLI)

**Contract (the only contract change):** `ProjectRule` gains three optional fields. The defaults keep every existing `rules.toml` parsing.

```toml
[[rule]]
on           = "U1.VDD"
need         = "cap"
to           = "GND"
value        = "100nF..1uF"
source       = "MCP9808 datasheet DS20005095B, 6.1 Layout Considerations, p.35"
why          = "Decoupling right at the pins keeps VDD steady when the chip draws current."
drafted_by   = "model"                        # "" (a person wrote it) or "model"
quote        = "A 0.1 µF bypass capacitor ..."  # the datasheet sentence; required when drafted_by = "model"
confirmed_by = ""                             # written only by `reflow rules confirm`: "name, 2026-10-22"
```

**`reflow rules confirm [RULES] [--ref U1]`:**
- Shows each rule that is drafted but unconfirmed: on/need/to/value, `source` and `quote`. It asks: confirm, edit (opens `$EDITOR` on that rule), or skip.
- Confirming writes `confirmed_by = "<name>, <date>"` and changes nothing else in the file.
- **It needs a person at a terminal:** it refuses when stdin isn't a TTY and has no `--yes` flag. A model running shell commands normally has no TTY, so it can't confirm rules quietly. This is a real barrier, not an absolute one (see Limits).

**What "unconfirmed" changes:**
- `reflow rules check`: lists unconfirmed rules as warnings, with the count.
- `reflow design`: still checks every rule, confirmed or not, and labels the run. run.json/report get `unconfirmed_rules: N`, and the summary line says "N rule(s) not confirmed against the datasheet". No result is described as checked against the datasheet while N > 0 (golden rule 6).
- `reflow eval`: a board with an unconfirmed rule is "unchecked" and left out of the go/no-go, the same as a draft `expected.toml`.
- A violation from an unconfirmed rule says so in its message, so the student knows the rule itself may be wrong.

### D. `reflow learn REF [--datasheet PATH]` opens a separate study session (optional)

Opens a new Claude Code session for studying one chip, separate from the session the student designs in:

- It runs, in the project folder, `claude --name "reflow learn U1 (MCP9808)" "<first message>"`. The first message asks for the datasheet-tutor walk-through of U1 (part, package, datasheet path), and says not to write `rules.toml` until the student asks. It never uses `-p`, because the point is the student talking.
- **Where it opens:** on macOS, in a new Terminal window. Elsewhere, or with `--print-command`, it prints the exact command to paste.
- **Without `claude`:** if `claude` isn't on PATH, it prints the same first message for any other assistant. The skill and `AGENTS.md` work there too.
- **What reflow reads back:** nothing from the session itself. It reads only the `rules.toml` the student saves, and the confirm step (C) stays the gate.

This complements learn mode (A-04, L-01..L-03); it doesn't replace it.

## Limits, said plainly

- A student can still remove `drafted_by` or edit `confirmed_by` by hand. Doing either is a deliberate act, like signing, and reflow can't tell it apart from the real thing. The goal is that the honest path is the easy one, not that cheating is impossible.
- The TTY check stops a model from confirming quietly in a normal agent shell. It doesn't stop a determined person.
- A separate session doesn't prove the student studied. It only makes studying the default path.
- Not yet verified before building: that Claude Code loads `.claude/skills/<name>/SKILL.md` from the project, and the exact way to open a new Terminal window from Python on macOS. Both get checked, with a test or a recorded manual run, in their tasks.

## Questions for the human

1. **Which rules need confirming?** (a) only `drafted_by = "model"` rules, or (b) every rule (`confirmed_by` required everywhere). Recommendation: (a) for students, with eval boards (E-02) required to have every rule confirmed.
2. **Name in `confirmed_by`:** git `user.name`, or typed at the prompt? Recommendation: typed, defaulting to git `user.name`.
3. **The TTY requirement on `reflow rules confirm`:** yes or no? Recommendation: yes.
4. **`reflow learn` opening a Terminal window** (macOS only), or always printing the command? Recommendation: open it on macOS, print elsewhere.
5. **Where the skill lives:** move it to `skills/datasheet-tutor/` as the source `reflow init` copies from? Recommendation: yes.

## Tasks after acceptance

| ID | Task | Owner |
|---|---|---|
| V-23 | Contract patch (`drafted_by`, `quote`, `confirmed_by` on `ProjectRule`); `reflow rules check` warnings; unconfirmed labels in design/eval | AGENT→HUMAN (contract) |
| V-24 | `reflow rules confirm` (TTY, edit, write-back that preserves the rest of the file) | AGENT |
| I-01 | `reflow init` (never overwrites; skeleton rules.toml from the pin map) | AGENT |
| H-08b | Tighten the datasheet-tutor skill and write the `AGENTS.md` text | AGENT→HUMAN (prompt text) |
| L-04 | `reflow learn` (claude session or printed command) | AGENT |
