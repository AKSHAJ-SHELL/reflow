## 2026-10-07 — first routing round trip (esp32_minimal)
- Chain works: KiCad → DSN → freerouting v2.4.1 → SES → KiCad
- First run 238 violations = setup error (no .kicad_pro, zones not refilled). Fixed → 77 vs 75 baseline.
- freerouting reported 0 unrouted / 1 violation; KiCad found 7 unconnected, +10 starved_thermal.
- Decision: pipeline always refills zones + re-runs KiCad DRC after routing; never trust the router's self-report.