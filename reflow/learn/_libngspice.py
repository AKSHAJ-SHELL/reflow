"""Run one ngspice deck on a shared libngspice (KiCad's) in a child process.  OWNER: AGENT (task L-12).

    python -m reflow.learn._libngspice LIB DECK OUT VECTOR

`reflow.learn.sim` runs this as a separate process when the ngspice command
isn't installed, so the shared library's global state, a hang or a crash
never reach the learn server, and the parent's timeout still applies.

It loads LIB with ctypes (the library is BSD-licensed ngspice; nothing is
vendored), feeds it the circuit lines of DECK (its `.control` block is left
out and the same steps are sent as commands: `run`, then the vector), and
writes "time value" rows to OUT, like ngspice's `wrdata`. Its first stdout
line is the library's own version banner ("ngspice-45.2 shared library").

`ngGet_Vec_Info` returns a pointer to one struct the library reuses on every
call, so each vector's data is copied out before the next lookup.

Exit status: 0 with OUT written, or 1 with the reason on stderr.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import CFUNCTYPE, POINTER, Structure, c_bool, c_char_p, c_double, c_int, c_short, c_void_p


class _VecInfo(Structure):
    _fields_ = [("v_name", c_char_p), ("v_type", c_int), ("v_flags", c_short),
                ("v_realdata", POINTER(c_double)), ("v_compdata", c_void_p), ("v_length", c_int)]


def _circuit(deck: str) -> list[str]:
    lines, skipping = [], False
    for line in deck.splitlines():
        low = line.strip().lower()
        if low.startswith(".control"):
            skipping = True
            continue
        if low.startswith(".endc"):
            skipping = False
            continue
        if not skipping and low != ".end":
            lines.append(line)
    return lines + [".end"]


def main(lib_path: str, deck_path: str, out_path: str, vector: str) -> int:
    messages: list[str] = []
    send = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
    on_exit = CFUNCTYPE(c_int, c_int, c_bool, c_bool, c_int, c_void_p)
    keep = (send(lambda s, i, p: (messages.append((s or b"").decode(errors="replace")), 0)[1]),
            send(lambda s, i, p: 0), on_exit(lambda *a: 0))
    try:
        ng = ctypes.CDLL(lib_path)
    except OSError as exc:
        print(f"can't load {lib_path}: {exc}", file=sys.stderr)
        return 1
    ng.ngGet_Vec_Info.restype = POINTER(_VecInfo)
    if ng.ngSpice_Init(keep[0], keep[1], keep[2], None, None, None, None) != 0:
        print("ngSpice_Init failed", file=sys.stderr)
        return 1
    banner = next((m.split("**", 1)[-1].strip() for m in messages if "ngspice-" in m), "ngspice (version unknown)")
    lines = _circuit(open(deck_path, encoding="utf-8").read())
    array = (c_char_p * (len(lines) + 1))(*[l.encode() for l in lines], None)
    if ng.ngSpice_Circ(array) != 0 or ng.ngSpice_Command(b"run") != 0:
        print("; ".join(m for m in messages if "error" in m.lower())[-500:] or "ngspice run failed", file=sys.stderr)
        return 1

    def copy(name: str) -> list[float]:
        found = ng.ngGet_Vec_Info(name.encode())
        if not found or not found.contents.v_realdata:
            raise KeyError(name)
        info = found.contents
        return [info.v_realdata[k] for k in range(info.v_length)]

    try:
        t = copy("time")
        v = copy(vector)
    except KeyError as exc:
        print(f"no vector {exc.args[0]} after the run", file=sys.stderr)
        return 1
    with open(out_path, "w", encoding="utf-8") as out:
        out.writelines(f" {a:.8e}  {b:.8e} \n" for a, b in zip(t, v))
    print(banner)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
