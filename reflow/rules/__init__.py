from importlib import import_module
from pathlib import Path
from pkgutil import iter_modules


def run_all(netlist, pcb=None):
    found = []
    for m in iter_modules([str(Path(__file__).parent)]):
        mod = import_module(f"{__name__}.{m.name}")
        if hasattr(mod, "check"):
            found.extend(mod.check(netlist, pcb))
    return found
