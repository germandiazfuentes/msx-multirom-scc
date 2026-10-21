"""Arnes de pruebas: arranca openMSX, pulsa teclas y captura la pantalla.

    python run.py ROM ROMTYPE MACHINE INDEX OUT.png [SEGUNDOS] [extra-keys]
INDEX = juego a elegir en el menu (-1 = no pulsar nada).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OPENMSX = os.path.join(HERE, "..", "tools", "openmsx", "openmsx.exe")

DOWN = (8, 0x40)
UP = (8, 0x20)
RIGHT = (8, 0x80)
LEFT = (8, 0x10)
SPACE = (8, 0x01)


def run(rom, romtype, machine, index, out, t=17.0, extra=(), start=6.0, tcl_extra=""):
    keys = []
    tt = start
    for _ in range(max(index, 0)):
        keys.append((tt, DOWN))
        tt += 0.4
    if index >= 0:
        keys.append((tt + 0.3, SPACE))
        tt += 0.3
    for dt, k in extra:
        keys.append((tt + dt, k))
    lines = ["set throttle off"]
    for kt, (row, mask) in keys:
        lines.append("after time %.2f {keymatrixdown %d %d}" % (kt, row, mask))
        lines.append("after time %.2f {keymatrixup %d %d}" % (kt + 0.15, row, mask))
    lines.append(tcl_extra)
    lines.append("after time %.2f {set throttle on}" % (t - 0.5))
    lines.append("after time %.2f {screenshot {%s}; exit}" % (t, os.path.abspath(out).replace("\\", "/")))
    script = os.path.join(HERE, "out", "_run_%d.tcl" % os.getpid())
    with open(script, "w") as f:
        f.write("\n".join(lines) + "\n")
    cmd = [OPENMSX, "-machine", machine, "-cart", rom, "-script", script]
    if romtype:
        cmd[5:5] = ["-romtype", romtype]
    subprocess.run(cmd, timeout=180)
    os.remove(script)


if __name__ == "__main__":
    a = sys.argv[1:]
    run(a[0], a[1], a[2], int(a[3]), a[4], float(a[5]) if len(a) > 5 else 14.0)
