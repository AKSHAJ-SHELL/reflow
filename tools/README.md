# tools/

| File | Does |
|---|---|
| `new_fixture.sh <src> <dst>` | Copy a fixture's KiCad files to a new name; refuses to overwrite |
| `nets.py <file.net>` | Print `net  ref.pin, ...` compactly |
| `bridges/export_dsn.py`, `bridges/import_ses.py` | KiCad 10 SWIG `pcbnew` DSN export / SES import (run with `$KICAD_PY`) |
| `freerouting.jar` | Not committed (gitignored); built per SETUP.md |

**Must never:** modify fixtures in place; run freerouting in-process (GPL: subprocess only).
