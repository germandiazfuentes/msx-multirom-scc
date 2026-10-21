"""Ejecuta cada ROM sola y cuenta escrituras en areas de RAM del sistema candidatas."""
import concurrent.futures as cf
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import multirom as mr  # noqa: E402
from run import OPENMSX  # noqa: E402

AREAS = {"KBUF": (0xF41F, 0xF55C), "BUF": (0xF55E, 0xF65F),
         "FNKSTR": (0xF87F, 0xF91E), "PARM1": (0xF6E8, 0xF7B4), "HOOKS": (0xFE03, 0xFEB1)}
RT = {mr.KONAMI4: "Konami", mr.KONAMI5: "KonamiSCC", mr.ASCII8: "ASCII8", mr.ASCII16: "ASCII16",
      mr.GKONAMI: "8kB", mr.GENERIC16: "16kB", mr.PLAIN: None}


def one(f, secs=42):
    g = mr.Game(f)
    if g.error:
        return g.title, "error"
    rom = os.path.abspath("romx/%s.rom" % g.sha1[:10])
    with open(rom, "wb") as fh:
        fh.write(g.raw)
    res = rom + ".txt"
    tcl = ["set throttle off", "set ::hits {}"]
    wps = []
    for n, (lo, hi) in AREAS.items():
        wps.append("debug set_watchpoint write_mem {0x%x 0x%x} {} {dict incr ::hits %s}" % (lo, hi, n))
    init = g.data[2] | g.data[3] << 8
    if g.page2:
        init = g.data[2] | g.data[3] << 8
    tcl.append("set ::bp [debug set_bp 0x%x {} {debug remove_bp $::bp; %s}]" % (init, "; ".join(wps)))
    for t in range(8, secs - 2, 3):
        tcl += ["after time %d {keymatrixdown 8 1}" % t, "after time %.1f {keymatrixup 8 1}" % (t + .3)]
        tcl += ["after time %.1f {keymatrixdown 8 128}" % (t + 1), "after time %.1f {keymatrixup 8 128}" % (t + 1.5)]
    tcl.append("after time %d {set f [open {%s} w]; puts $f $::hits; close $f; exit}" % (secs, res.replace(os.sep, "/")))
    with open(rom + ".tcl", "w") as fh:
        fh.write("\n".join(tcl))
    cmd = [OPENMSX, "-machine", "C-BIOS_MSX2", "-cart", rom, "-script", rom + ".tcl"]
    if RT[g.mapper]:
        cmd[5:5] = ["-romtype", RT[g.mapper]]
    subprocess.run(cmd, timeout=300)
    out = open(res).read().strip() if os.path.exists(res) else "?"
    return g.title, out or "-"


if __name__ == "__main__":
    files = sys.argv[1:] or sorted(glob.glob("../roms/*.zip"))
    with cf.ThreadPoolExecutor(6) as ex:
        for t, r in ex.map(one, files):
            print("%-32s %s" % (t[:32], r))
