"""Prueba rapida en otras maquinas: aparece el menu y arrancan el primer y el
ultimo juego de la lista.

    python quicktest.py CART TAMANO_KB MAQUINA [patron_roms]
"""
import glob
import os
import sys

import realtest as rt
import multirom as mr
from PIL import Image


def main():
    cart, size, machine = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    pat = sys.argv[4] if len(sys.argv) > 4 else os.path.join(rt.HERE, "..", "roms", "*.zip")
    rt.set_timing(machine)
    games = [g for g in (mr.Game(f) for f in sorted(glob.glob(pat))) if not g.error]
    sel = []
    for g in games:
        risky = set()
        if None not in mr.allocate(sel + [g], cart, size, risky) and not risky:
            sel.append(g)
    img, rep = mr.build(sel, cart, size, "TEST")
    rom = os.path.join(rt.OUT, "q_%s_%s.rom" % (cart, machine))
    with open(rom, "wb") as f:
        f.write(img)
    romtype = mr.CARTS[cart]["romtype"]
    # menu
    mshot = os.path.join(rt.OUT, "q_%s_%s_menu.png" % (cart, machine))
    rt.openmsx(rom, romtype, machine, [], [(rt.MENU_KEYS + 1, mshot)])
    print("%s %s: %d juegos, menu %s" % (machine, cart, len(sel), "OK" if os.path.exists(mshot) else "SIN CAPTURA"))
    tiles = [Image.open(mshot).convert("RGB").resize((160, 120))] if os.path.exists(mshot) else []
    for i in (0, len(sel) - 1):
        g = sel[i]
        a = os.path.join(rt.OUT, "q_%s_%s_%d_menu" % (cart, machine, i))
        b = os.path.join(rt.OUT, "%s_%s_nat" % (g.sha1[:10], machine))
        rt.run_menu(rom, romtype, machine, i, a)
        if not all(os.path.exists(p) for p in rt.shot_names(b)):
            rt.run_native(g, machine, b)
        sc, ink = rt.score(a, b), rt.score_ink(a, b)
        bad = sc > rt.THRESHOLD or ink > rt.INK_THRESHOLD
        print("  [%d] %-30s dif=%5.1f tinta=%4.2f %s %s" % (i, g.title[:30], sc, ink,
              "<<< REVISAR" if bad else "", "; ".join(rep[i][2]["errors"])))
        for p in (rt.shot_names(b)[-1], rt.shot_names(a)[-1]):
            if os.path.exists(p):
                tiles.append(rt.label(Image.open(p).convert("RGB").resize((160, 120)), g.title[:20]))
    m = Image.new("RGB", (165 * len(tiles), 120))
    for k, t in enumerate(tiles):
        m.paste(t, (k * 165, 0))
    m.save(os.path.join(rt.OUT, "q_%s_%s.png" % (cart, machine)))


if __name__ == "__main__":
    main()
