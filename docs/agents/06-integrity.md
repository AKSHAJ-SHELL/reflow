# 06 · Integrity

- **Never claim "AI-designed," "verified" or "routed" without the report.** Every board in an output folder or a public post has its `VerifyReport` and our own `kicad-cli` DRC result beside it.
- **Never hide a failed run.** Failed attempts, refused nets and unrouted nets appear in the report and the demo. If the model one-shots a board, say so; don't stage a failure.
- **Never trust a tool's report on its own output.** Re-run DRC after routing (refill zones first). freerouting has reported success on a board KiCad found 7 unconnected items on.
- **Never overstate a comparison.** KiCad ERC is not silent on the real AVBotz board (it reports `power_pin_not_driven`). Comparisons with any other tool use published prompts and outputs anyone can rerun.
- **No fabricated data.** Example JSON is labeled illustrative; part numbers in real outputs come only from the resolver or the user.
- **No public framing as "killing" any company.** reflow is an open-source alternative.
