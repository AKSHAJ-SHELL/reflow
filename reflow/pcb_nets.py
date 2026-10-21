"""Read pad nets from a .kicad_pcb.  OWNER: AGENT (task V-14, DECISIONS V-1 d).

Contract
--------
    load_pcb_pad_nets(path) -> dict[(ref, pad_number), net_name]

The gerbers are made from this file, so the verifier compares it with the
circuit.json netlist (that comparison is V-13, HUMAN). This module only reads.

- One entry per (footprint reference, pad number). A pad with no net, or net
  0 / "", maps to "".
- Accepts both pad-net syntaxes: tscircuit's `(net 3 "SDA")` and KiCad 10's
  `(net "SDA")`, and both reference syntaxes: `(property "Reference" "U1")`
  (KiCad 8+) and `(fp_text reference "U1")` (older).
- Pads with an empty number (mounting holes) and footprints without pads
  (logos) are skipped.
- A pad number repeated on the same net (split exposed pads) is one entry.

Raises PcbNetsError for an unreadable or non-board file, a footprint with
pads but no reference, a duplicate reference, or one pad number on two nets.

Must never
----------
- edit the board, refill zones, or call kicad-cli or pcbnew,
- guess a net for a pad, or merge two references,
- decide whether the board matches the design.
"""
from __future__ import annotations

from pathlib import Path

from reflow.netlist import parse_sexpr


class PcbNetsError(ValueError):
    """The .kicad_pcb could not be read as a board with pad nets."""


def load_pcb_pad_nets(path) -> dict[tuple[str, str], str]:
    board = _read(Path(path))
    pads: dict[tuple[str, str], str] = {}
    seen_refs: set[str] = set()
    for footprint in _children(board, "footprint"):
        footprint_pads = [pad for pad in _children(footprint, "pad") if len(pad) > 1 and pad[1] != ""]
        if not footprint_pads:
            continue
        ref = _reference(footprint)
        if ref in seen_refs:
            raise PcbNetsError(f"duplicate footprint reference {ref}")
        seen_refs.add(ref)
        for pad in footprint_pads:
            key = (ref, pad[1])
            net = _pad_net(pad)
            if pads.setdefault(key, net) != net:
                raise PcbNetsError(f"{ref} pad {pad[1]} is on two nets: {pads[key]!r} and {net!r}")
    return dict(sorted(pads.items()))


def _read(path: Path) -> list:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PcbNetsError(f"{path}: {exc.strerror or exc}") from exc
    try:
        root = parse_sexpr(text)
    except IndexError as exc:
        raise PcbNetsError(f"{path}: unbalanced or empty s-expression") from exc
    if not isinstance(root, list) or not root or root[0] != "kicad_pcb":
        raise PcbNetsError(f"{path}: not a kicad_pcb file")
    return root


def _children(node: list, key: str) -> list[list]:
    return [item for item in node[1:] if isinstance(item, list) and item and item[0] == key]


def _reference(footprint: list) -> str:
    for prop in _children(footprint, "property"):
        if len(prop) > 2 and prop[1] == "Reference":
            return prop[2]
    for text in _children(footprint, "fp_text"):
        if len(text) > 2 and text[1] == "reference":
            return text[2]
    name = footprint[1] if len(footprint) > 1 and isinstance(footprint[1], str) else "?"
    raise PcbNetsError(f"footprint {name} has pads but no reference")


def _pad_net(pad: list) -> str:
    nets = _children(pad, "net")
    if not nets:
        return ""
    net = nets[0]
    name = net[-1] if len(net) > 1 else ""
    if len(net) == 2 and name.isdigit():
        return ""       # `(net 0)`: a number with no name is no net
    return name
