# 08 · Dependencies

Before adding any dependency (Python, npm, Java, system tool):

1. **Verify it's real and maintained.** Canonical URL, latest release date, open issues glance. Note "unverified" for anything you couldn't confirm.
2. **License check.** Permissive (MIT/BSD/Apache-2.0) may be imported. **GPL/AGPL only as a separate process**, never imported or vendored (freerouting is GPL-3.0; easyeda2kicad and AlphaCodium are AGPL-3.0).
3. **Need check.** Can stdlib or an existing dependency do it in < 50 lines? Then don't add it.
4. **Pin it.** Exact or compatible-range version in `pyproject.toml` / `package.json`; tool versions in `SETUP.md`.
5. **Record it** in PROGRESS.md (and DECISIONS.md if it changes the stack).

Pinned facts: KiCad **10.x** (SWIG `pcbnew` DSN/SES is slated for removal in 11), Java 25+ for freerouting 2.4, Python 3.14 venv (3.11+ required for `tomllib`). The verifier itself has **zero** Python runtime dependencies; keep it that way.
