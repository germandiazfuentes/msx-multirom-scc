"""Analiza en openMSX todos los juegos de /roms (resultado en la cache)."""
import glob, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import multirom as mr, analyze as an
from run import OPENMSX
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 90
pat = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "roms", "*.zip")
machine = sys.argv[3] if len(sys.argv) > 3 else "C-BIOS_MSX2"
for f in sorted(glob.glob(pat)):
    g = mr.Game(f)
    if g.error or g.mapper == mr.PLAIN:
        continue
    an.forget(g.sha1)
    t = time.time()
    r = an.run(g, os.path.abspath(OPENMSX), machine=machine, seconds=secs)
    g.analysis = r
    d, rep, ram = mr.patch_game(g, "k5", 64)
    print("%-28s %-8s %4.1fs %s | dyn=%d %s" % (g.title[:28], mr.MAPPER_NAMES[g.mapper][:8], time.time() - t,
          an.summary(r), rep["dyn"], "; ".join(rep["errors"])))
