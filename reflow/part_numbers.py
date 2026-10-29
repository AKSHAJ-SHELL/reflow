"""Part numbers on a compiled board that came from outside the resolver.  OWNER: AGENT (E-01, O-01).

Contract
--------
    foreign_part_numbers(circuit_json, parts: ResolvedParts, spec: Spec) -> list[dict]

Every manufacturer or supplier part number in the board's circuit.json that is
neither a resolved part's MPN or LCSC id nor one of the spec's named parts
(golden rule 5). Each entry is {ref, field, value}. Matching ignores case and
surrounding spaces. Used by the eval runner's go/no-go and by fab export.
"""
from __future__ import annotations

import json
from pathlib import Path

from reflow.contracts import ResolvedParts, Spec


def foreign_part_numbers(circuit_json, parts: ResolvedParts, spec: Spec) -> list[dict]:
    allowed = {s.strip().casefold() for s in spec.named_parts}
    for part in parts.resolved:
        allowed |= {part.mpn.strip().casefold(), part.lcsc.strip().casefold()}
    found = []
    for element in json.loads(Path(circuit_json).read_text(encoding="utf-8")):
        if element.get("type") != "source_component":
            continue
        ref = element.get("name", "?")
        mpn = element.get("manufacturer_part_number")
        if isinstance(mpn, str) and mpn.strip() and mpn.strip().casefold() not in allowed:
            found.append({"ref": ref, "field": "manufacturer_part_number", "value": mpn})
        for supplier, ids in (element.get("supplier_part_numbers") or {}).items():
            for value in ids if isinstance(ids, list) else [ids]:
                if isinstance(value, str) and value.strip() and value.strip().casefold() not in allowed:
                    found.append({"ref": ref, "field": f"supplier_part_numbers.{supplier}", "value": value})
    return found
