"""Mosaico de capturas (original / k5 / yama) de varios juegos en una maquina.

    python grid.py MAQUINA SALIDA.png PATRON [PATRON...]
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import multirom as mr  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from realtest import SHOTS_T  # noqa: E402

mach, out = sys.argv[1], sys.argv[2]
rows = []
for pat in sys.argv[3:]:
    f = (glob.glob("../roms2/*/" + pat) + glob.glob("../roms/" + pat))[0]
    h = mr.Game(f).sha1[:10]
    for lab, pre in (("orig", "out/real/%s_%s_nat" % (h, mach)), ("k5", "out/real/k5_%s_menu" % h),
                     ("yama", "out/real/yama_%s_menu" % h)):
        ims = []
        for t in SHOTS_T:
            p = "%s_%02d.png" % (pre, t)
            ims.append(Image.open(p).convert("RGB").resize((128, 96)) if os.path.exists(p)
                       else Image.new("RGB", (128, 96), (255, 0, 255)))
        ImageDraw.Draw(ims[0]).text((2, 2), "%s %s" % (lab, pat[:14]), fill=(255, 255, 0))
        rows.append(ims)
m = Image.new("RGB", (len(SHOTS_T) * 130, len(rows) * 98))
for r, ims in enumerate(rows):
    for c, im in enumerate(ims):
        m.paste(im, (c * 130, r * 98))
m.save(out)
