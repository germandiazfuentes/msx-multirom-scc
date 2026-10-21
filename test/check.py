"""Ejecuta una ROM en openMSX y lee el resultado del test de mapper (C000h)."""
import os
import subprocess
import sys

from run import OPENMSX

HERE = os.path.dirname(os.path.abspath(__file__))
_n = [0]


def check(rom, romtype, machine="C-BIOS_MSX1", index=-1, t=13.0, shot=None, start=6.0):
    _n[0] += 1
    res = os.path.join(HERE, "out", "_res_%d_%d.txt" % (os.getpid(), _n[0]))
    lines = ["set throttle off"]
    tt = start
    if index >= 0:
        for _ in range(index):
            lines += ["after time %.2f {keymatrixdown 8 64}" % tt,
                      "after time %.2f {keymatrixup 8 64}" % (tt + .15)]
            tt += .4
        lines += ["after time %.2f {keymatrixdown 8 1}" % (tt + .3),
                  "after time %.2f {keymatrixup 8 1}" % (tt + .45)]
    lines.append("after time %.2f {set throttle on}" % (t - .3))
    act = 'set f [open {%s} w]; puts $f "[peek 0xc000] [peek 0xc001] [peek 0xc002]"; close $f' % res.replace("\\", "/")
    if shot:
        act += "; screenshot {%s}" % os.path.abspath(shot).replace("\\", "/")
    lines.append("after time %.2f {%s; exit}" % (t, act))
    tcl = res + ".tcl"
    with open(tcl, "w") as f:
        f.write("\n".join(lines) + "\n")
    cmd = [OPENMSX, "-machine", machine, "-cart", rom, "-script", tcl]
    if romtype:
        cmd[5:5] = ["-romtype", romtype]
    subprocess.run(cmd, timeout=180)
    os.remove(tcl)
    if not os.path.exists(res):
        return ["?"]
    r = open(res).read().split()
    os.remove(res)
    return r


if __name__ == "__main__":
    a = sys.argv[1:]
    print(*check(a[0], a[1], a[2] if len(a) > 2 else "C-BIOS_MSX1", int(a[3]) if len(a) > 3 else -1))
