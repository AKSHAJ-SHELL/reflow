# 07 · Learn mode

**Mandatory** in `reflow design`. Off in `reflow check` and CI. The point: the user can't ship a board they don't understand, without it feeling like homework.

## Principles

1. **Real bugs, not a quiz bank.** Every interaction comes from a violation this run actually produced (usually the AI's first failed attempt). `LearnInteraction.rule_id` must point at it.
2. **Think first, then see.** The user commits to an answer before the fix is revealed.
3. **Wrong answers teach, never block.** After answering, the user always sees the `why`. No retries-until-correct, no scores.
4. **Short.** 1–3 interactions per board in v1 (≈ 2 minutes, including the spec checkpoint and sign-off).
5. **Skip what's known.** v1: skip a concept already answered correctly earlier *in the same run*. Cross-run memory is v2 (vault).

## v1 interactions

| Kind | What the user does | Source | Status |
|---|---|---|---|
| `spot_bug` | Sees the AI's failed draft (parts list + the relevant nets). Names the culprit part and says why, before the fix is shown. Graded by matching refs, so free text is fine. | First failed attempt's violation | **v1 must** |
| `make_call` | Picks a key value (e.g. pull-up resistance) from 3 options; the verifier responds instantly | A rule with a tunable value | v1 if time (cut #3) |
| break-it (simulate) | Toggle a part off, watch it fail | ngspice via tscircuit | v2 |
| click-to-explore | Click any part to see why it's there | report/web UI | v2 |

If the AI's first attempt passes the verifier, there's no real bug to spot: show one key design decision instead (e.g. "why is there a 100nF cap next to U1?"), drawn from the plan, with the matching rule's `why`.

## Selection logic: HUMAN-owned (L-01)

Which violation becomes the interaction, what counts as a correct answer, and when to skip are "plausible wrong answer" logic, so the author writes them. Agents build the terminal screens (L-02) and the sign-off prompt (L-03).

## Sign-off (L-03)

Before any fab files: show remaining warnings and any overrides, then a single `y/n`. Recorded in `signoff.json` and copied into the report.

## Open (Decision D-4)

- (a) Spot-the-bug as multiple choice (pick the part from a list).
- (b) Spot-the-bug as free text, graded by ref matching.
- (c) Make-the-call first (value choice + instant re-verify), spot-the-bug second.
