#!/usr/bin/env bash
# Copy a fixture to a new name, safely.
#   tools/new_fixture.sh sensor_good bad_floating_addr
# Copies only the KiCad project files (.kicad_sch/.kicad_pro/.kicad_pcb),
# renames them to the new name, and never overwrites an existing fixture.
# Skips .history, lock files, .kicad_prl, the old .net, and expected.toml
# (the new fixture needs its own label).
set -euo pipefail
cd "$(dirname "$0")/../fixtures"

src="${1:?usage: tools/new_fixture.sh <src> <dst>}"
dst="${2:?usage: tools/new_fixture.sh <src> <dst>}"

[ -d "$src" ] || { echo "no fixture named '$src' in fixtures/"; exit 1; }
[ -e "$dst" ] && { echo "fixtures/$dst already exists, refusing to overwrite"; exit 1; }

mkdir "$dst"
for ext in kicad_sch kicad_pro kicad_pcb; do
  [ -f "$src/$src.$ext" ] && cp "$src/$src.$ext" "$dst/$dst.$ext"
done
echo "created fixtures/$dst:"
ls "$dst"
echo "next: open fixtures/$dst/$dst.kicad_pro in KiCad, plant ONE bug, write expected.toml"
