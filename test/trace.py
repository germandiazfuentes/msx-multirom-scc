"""Registra las escrituras de un juego en 4000h-BFFFh (PC -> direccion) en openMSX.

    python trace.py ROM ROMTYPE [segundos] [maquina]
"""
import os
import subprocess
import sys
from pathlib import Path

from run import OPENMSX

rom = Path(sys.argv[1]).resolve()
romtype = sys.argv[2]
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 20
machine = sys.argv[4] if len(sys.argv) > 4 else "C-BIOS_MSX2"
out = Path("out", rom.stem + "_writes.txt").resolve()
tcl = Path("out", rom.stem + "_trace.tcl")
tcl.write_text("""set throttle off
set ::w [dict create]
debug set_watchpoint write_mem {0x4000 0xBFFF} {} {
  dict incr ::w "[format %%04X [reg pc]] [format %%04X $::wp_last_address] [format %%02X $::wp_last_value]"
}
after time 6 {keymatrixdown 8 1}
after time 6.2 {keymatrixup 8 1}
after time 12 {keymatrixdown 8 1}
after time 12.2 {keymatrixup 8 1}
after time %s {set f [open {%s} w]; dict for {k v} $::w {puts $f "$k $v"}; close $f; exit}
""" % (secs, out.as_posix()))
cmd = [OPENMSX, "-machine", machine, "-cart", str(rom), "-script", str(tcl)]
if romtype != "-":
    cmd[5:5] = ["-romtype", romtype]
subprocess.run(cmd, timeout=600)
lines = out.read_text().splitlines()
# Agrupar por PC y direccion
agg = {}
for ln in lines:
    pc, addr, val, n = ln.split()
    k = (pc, addr)
    agg.setdefault(k, [0, set()])
    agg[k][0] += int(n)
    agg[k][1].add(val)
for (pc, addr), (n, vals) in sorted(agg.items(), key=lambda x: -x[1][0])[:40]:
    print("PC=%s escribe %s  x%-6d valores=%s" % (pc, addr, n, " ".join(sorted(vals))[:60]))
