# A run with compile failures and a verify failure, for the run report (O-02)

Run folder from `reflow eval` 20261022T204747Z, board ams1117_regulator, model
nvidia/nemotron-3.5-lightning:free, reduced to what the report reads:
run.json, spec.json, parts.json, and each attempt's compile-N.json and verify.json.

- Attempt 1: compile try 1 failed (`Invalid footprint prop on chip "U1": "SOT-223"`), try 2
  compiled, and verify found 1 error: `pinout.mismatch` on U1 pin 4 (the tab; see V-12).
- Attempt 2: neither compile try compiled (try 1: "model response contained no code fence";
  try 2: the same SOT-223 footprint error), so it has no verify.json.
- Run status `failed_verify`, best attempt 1.

Absolute paths in run.json, spec.json and the compile files were made relative to the repo;
nothing else was changed. The prompts, responses, TSX and build folders are left out.
