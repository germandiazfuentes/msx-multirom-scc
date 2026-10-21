"""Analiza (sumando a lo que haya) todas las ROMs de un patron en una maquina."""
import glob, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import multirom as mr, analyze as an
from run import OPENMSX
pat, machine = sys.argv[1], sys.argv[2]
for f in sorted(glob.glob(pat)):
    g = mr.Game(f)
    if g.error or g.mapper == mr.PLAIN:
        continue
    r = an.run(g, os.path.abspath(OPENMSX), machine=machine, seconds=90)
    print("%-28s %s" % (g.title[:28], an.summary(r)))
