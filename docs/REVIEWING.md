# Reviewing changes to reflow

For the maintainer, reviewing a pull request alone (task CI-05). It covers how the code fits
together, where text can steer a model or an agent, what CI checks, and a checklist for each PR.

## 1. One-time GitHub settings

CI and `CODEOWNERS` only protect `main` with these turned on. They're repo settings, so the
maintainer sets them.

**Settings → Branches → add a rule (or ruleset) for `main`:**
- Require a pull request before merging.
- Require review from Code Owners.
- Dismiss stale approvals when new commits are pushed.
- Require status checks to pass: every `portable` job, `full` and `checks`.
- Block force pushes and deletion.

**Settings → Actions → General:**
- Fork pull request workflows: **Require approval for all outside collaborators**. No CI runs on
  a stranger's PR until you've read it and clicked Approve.
- Workflow permissions: **Read repository contents** (the default token is read-only).
- Leave "Allow GitHub Actions to create and approve pull requests" off.

**With one maintainer:** GitHub doesn't let you approve your own PR. Either let admins bypass
the rule for your own pushes, or work on a branch and merge your own PRs as admin once CI is
green. Outside PRs still need your review either way.

## 2. How the code fits together

The pipeline is in `docs/02-architecture.md` and the contracts between stages are in
`docs/04-contracts.md`. In short:

```
spec.json + plan.json (the user)
  → parts:    reflow/parts/        local JLCPCB snapshot → resolver picks real parts (the AI never picks one)
  → design:   reflow/harness/      the loop: prompt → model → code → compile → verify → feedback, ≤ 3 attempts
      model:    reflow/llm.py, reflow/claude_code.py, prompts/*.md
      code:     reflow/codefence.py   lifts the TSX out of the model's reply, unchanged
      compile:  reflow/compile.py     runs tsci on that TSX → circuit.json + .kicad_pcb
      verify:   reflow/verifier.py    circuit.json → netlist → reflow/rules/ + pin checks (pinbind.py)
  → learn:    reflow/learn/        local web app: spot the bug, sign off (signoff.py)
  → export:   reflow/export.py     route check (route.py) + DRC + our schematic (schematic.py) → fab files
  → report:   reflow/report.py
reflow check: KiCad schematic → reflow/netlist.py → reflow/rules/   (no model involved)
```

Who writes what (`docs/agents/05-hand-vs-agent-code.md`):

| Kind | Where | Review depth |
|---|---|---|
| What "correct" means | `reflow/rules/`, `reflow/harness/` core, `netlist.py`, `violation.py`, `contracts.py`, `fixtures/`, `expected.toml` | Line by line. An outside PR here needs a reason and a fixture that proves it. |
| What models and agents read | `prompts/`, `skills/`, `AGENTS.md`, `CLAUDE.md`, `docs/agents/` | Line by line, as if it were code (section 3). |
| What runs in CI | `.github/`, `tools/`, `pyproject.toml`, `tests/conftest.py` | Line by line. |
| Plumbing | the rest of `reflow/`, `web/` | Normal review; tests must cover it. |
| Tests | `tests/` | A test may never be loosened, skipped or deleted to make something pass (AGENTS.md rule 4). |

## 3. Where text can steer a model or an agent

A prompt injection is text that a model reads as instructions when it should be data. In reflow,
text reaches a model or a coding agent in these places:

| Text | Who reads it | What a bad PR could do |
|---|---|---|
| `prompts/*.md` | the design model, every run | tell it to write code that does something other than draw a board (see 4) |
| `AGENTS.md`, `CLAUDE.md`, `docs/agents/`, `skills/` | every contributor's coding agent (Claude Code, Codex, Cursor) when they open the repo | "also run this setup script", "don't mention this file", "fill in confirmed_by" |
| `evals/*/spec.json`, `request.txt`, `docs/examples/` | the model, through the spec | the same, hidden inside a board request |
| `rules.toml` quotes and `why` text, `tests/data/` | the model or the student's agent | the same, hidden inside a datasheet quote |
| part descriptions in the parts snapshot | the model, through resolved parts | the snapshot comes from jlcparts, not from a PR, but treat its text as untrusted |
| model replies | `codefence.py` → `compile.py` → tsci | the reply is code, and it runs (see 4) |

What to look for:
- **Instructions in data.** A spec, quote or test file that addresses a model ("you", "assistant",
  "ignore", "instead") is suspicious. Real datasheet text describes a chip.
- **Hidden text.** Invisible Unicode, HTML comments in Markdown (GitHub doesn't show them; a model
  reads them), very long lines, base64 blobs. `tools/check_injection.py` flags these.
- **Agent files asking for actions.** Any new line in `AGENTS.md`, `CLAUDE.md` or `skills/` that tells
  an agent to run a command, fetch a URL, edit files outside the task, push, or keep something from
  the user.
- **Remote images or links in agent files.** A model that renders `![](https://x/?q=...)` can leak
  data in the URL.
- **A model output turning into a part number, a path or a command.** AGENTS.md rule 5: a part
  number only comes from the resolver or `Spec.named_parts`.

## 4. Known risks in the code today

These are real and not fixed yet. Weigh any PR that touches these paths against them.

1. **The model's code runs on your machine.** `compile.py` writes the model's TSX unchanged and runs
   `tsci export` on it. `tsci` runs the file as JavaScript on Bun, with the user's permissions and
   the whole environment, including `REFLOW_API_KEY` if it's set. Anything that can steer the model
   (a spec, a quote, a prompt) can, in principle, make it write code that reads files or makes network
   requests. The same goes for learn mode's fix-it tools (`learn/fixit.py`), which recompile edited
   code. Nothing today restricts imports in the TSX or strips the environment for `tsci`.
2. **The learn server doesn't check the Host header.** It listens only on 127.0.0.1 and sends a
   strict Content-Security-Policy, but it doesn't reject requests whose `Host` isn't 127.0.0.1, which
   is the usual defence against DNS rebinding from a malicious web page. Not tested either way.

## 5. What CI checks, and what it doesn't

CI (`.github/workflows/ci.yml`) runs on every push to `main` and every PR:

| Job | What it does |
|---|---|
| `portable` | Ubuntu and macOS × Python 3.11 and 3.12, with no KiCad or tsci. Tests that need them skip. Not Windows yet (the tests fake tools with shebang scripts). |
| `full` | Ubuntu 24.04 with KiCad 10 and tsci 0.0.2768. Checks both are installed, so no test passes by skipping, then runs the whole suite and the built wheel from another folder. |
| `checks` | `tools/check_injection.py` (section 3) and `tools/check_links.py` (Markdown links resolve). |

The workflow itself is checked by `tests/test_ci_hygiene.py`:
- the token is read-only;
- no `pull_request_target`, `workflow_run` or secrets;
- actions are pinned to commit SHAs;
- no PR text is pasted into a shell command;
- every job has a timeout.

`tools/check_injection.py` scans the files git tracks. Before committing new files of your own, run it on them too:
`python tools/check_injection.py $(git ls-files -co --exclude-standard)`. (While writing it, an editing tool turned
`\u200b`-style escapes into the real invisible characters; the scanner caught it as soon as the files were added.)

`tests/test_codeowners.py` checks that `CODEOWNERS` lists every path in section 2's first three rows.

**CI can't tell you:**
- whether a rule is electrically right;
- whether a prompt change makes the model worse;
- whether new instructions in an agent file are malicious, when they're written plainly.

The checker only flags hidden text and known phrases. Plain-English instructions are your job.

**Model runs never happen in CI.** There are no API keys in CI. Run `reflow eval` locally before
merging a change to `prompts/`, the harness or the verifier, and compare with the last results in
`evals/results/`.

## 6. Checklist for each PR

1. **Who and why.** Is there an issue or a task ID? Does the diff do only that?
2. **CI is green**, including `full` (so no test skipped) and `checks`.
3. **Sensitive paths.** GitHub marks files you own; read every one of them line by line (section 2).
4. **Tests.** Every behaviour change has a test that failed before it. No test was loosened,
   skipped, marked xfail or deleted. No fixture or `expected.toml` changed without a datasheet page.
5. **Prompts and agent files** (section 3). Read them as instructions. Anything that tells a model or
   agent to act, rather than describing the task?
6. **Data files.** Specs, quotes, `tests/data/`: any text addressed to a model?
7. **Model output.** Does any new path let a model reply become a part number, a file path, a shell
   command or an import? Does anything new run code (`subprocess`, `eval`, `exec`, a new `tsci` call)?
8. **Dependencies.** A new package in `pyproject.toml` or `web/package.json`: is it needed, pinned
   exactly, licensed compatibly (`docs/agents/08-dependencies.md`)?
9. **Network.** Any new URL fetched at runtime? reflow fetches only the parts snapshot and the model
   provider.
10. **Docs.** README, SETUP and `docs/` still true? Is there a `PROGRESS.md` entry?

When in doubt, ask the contributor to explain, or check out the branch and run it in a throwaway
folder with no API key in the environment.
