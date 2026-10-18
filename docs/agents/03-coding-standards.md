# 03 · Coding standards

- **Python ≥ 3.11**, stdlib first. Type hints on public functions. Dataclasses for data.
- **Small modules, one job each.** A module's README states its contract and what it must never do.
- **Prompts are files** in `prompts/*.md`, loaded at runtime. No prompt text in `.py` files beyond a one-line format string.
- **Config is not code.** Model ids, API base URLs, timeouts, caps (`max_attempts`, `COMPILE_CAP`) come from `reflow.toml` or environment variables, with defaults in one place. Secrets only from env vars; never committed.
- **Subprocesses:** list-form args (no `shell=True`), explicit timeouts, capture stderr, check return code **and** that expected output files exist.
- **Errors:** tool/input problems raise a named exception and map to exit code 2 at the CLI. Never `except Exception: pass`.
- **Paths:** `pathlib.Path`; never write outside the run folder or a temp dir.
- **Output is deterministic** for the same inputs (sorted lists, stable IDs), so diffs and tests are meaningful.
- **GPL/AGPL tools** (freerouting, easyeda2kicad) are called as separate processes, never imported or vendored.
- Keep functions short enough that the human can read the file in one sitting and explain each function in a sentence.
