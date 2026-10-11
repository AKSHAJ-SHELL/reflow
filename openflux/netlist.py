"""Load a KiCad netlist (kicadsexpr) into plain Python objects."""
import re
from dataclasses import dataclass, field
from pathlib import Path

_TOKEN = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+')



def parse_sexpr(text: str):
    stack = [[]]
    for tok in _TOKEN.findall(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        elif tok.startswith('"'):
            stack[-1].append(tok[1:-1].replace('\\"', '"'))
        else:
            stack[-1].append(tok)
    return stack[0][0]


def _child(node, key):
    for item in node[1:]:
        if isinstance(item, list) and item and item[0] == key:
            return item
    return None


def _children(node, key):
    return [i for i in node[1:] if isinstance(i, list) and i and i[0] == key]


def _val(node, key, default=""):
    c = _child(node, key)
    return c[1] if c and len(c) > 1 else default


@dataclass
class Pin:
    ref: str
    pin: str
    net: str
    pintype: str = ""
    function: str = ""

    @property
    def name(self) -> str:
        suffix = f"_{self.pin}"
        return self.function[: -len(suffix)] if self.function.endswith(suffix) else self.function


@dataclass
class Component:
    ref: str
    value: str
    footprint: str
    lib: str
    part: str
    pins: dict = field(default_factory=dict)

    @property
    def lib_id(self) -> str:
        return f"{self.lib}:{self.part}"

    @property
    def prefix(self) -> str:
        return re.match(r"[A-Za-z_#]*", self.ref).group(0)


@dataclass
class Netlist:
    components: dict
    nets: dict

    def pins_on(self, net: str) -> list:
        return self.nets.get(net, [])

    def net_of(self, ref: str, pin: str):
        comp = self.components.get(ref)
        if comp is None:
            return None
        p = comp.pins.get(pin)
        return p.net if p else None

    @staticmethod
    def is_unconnected(net: str) -> bool:
        return net.startswith("unconnected-")


def load_netlist(path) -> Netlist:
    root = parse_sexpr(Path(path).read_text())

    components = {}
    for comp in _children(_child(root, "components") or ["components"], "comp"):
        lib = _child(comp, "libsource") or ["libsource"]
        c = Component(
            ref=_val(comp, "ref"),
            value=_val(comp, "value"),
            footprint=_val(comp, "footprint"),
            lib=_val(lib, "lib"),
            part=_val(lib, "part"),
        )
        components[c.ref] = c

    nets = {}
    for net in _children(_child(root, "nets") or ["nets"], "net"):
        name = _val(net, "name")
        nets[name] = []
        for node in _children(net, "node"):
            p = Pin(
                ref=_val(node, "ref"),
                pin=_val(node, "pin"),
                net=name,
                pintype=_val(node, "pintype"),
                function=_val(node, "pinfunction"),
            )
            nets[name].append(p)
            if p.ref in components:
                components[p.ref].pins[p.pin] = p


    return Netlist(components=components, nets=nets)

