"""Prueba juegos reales: los mete en MultiROMs, los lanza desde el menu y compara
la pantalla con la del juego original ejecutado solo.

    python realtest.py CART TAMANO_KB [maquina] [filtro|-] [patron_roms] [etiqueta]

Se hacen varias capturas por juego; cada captura lanzada desde el menu se
compara con las capturas del original de instantes cercanos. 'dif' es la
diferencia media (0 = igual): los juegos con dif alta salen marcados.
"""
import concurrent.futures as cf
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
import multirom as mr  # noqa: E402
from run import OPENMSX  # noqa: E402
from PIL import Image, ImageChops, ImageDraw, ImageStat  # noqa: E402

RT = {mr.KONAMI4: "Konami", mr.KONAMI5: "KonamiSCC", mr.ASCII8: "ASCII8", mr.ASCII16: "ASCII16",
      mr.GKONAMI: "8kB", mr.GENERIC16: "16kB", mr.PLAIN: None}
OUT = os.path.join(HERE, "out", "real")
os.makedirs(OUT, exist_ok=True)

KEYS_T = [14, 17, 20, 23]          # pulsaciones de ESPACIO (s desde el arranque del juego)
SHOTS_T = [10, 13, 16, 19, 22, 25]  # capturas
NATIVE_BOOT = 2.0                   # el original arranca ~2 s despues de encender (C-BIOS)
MENU_KEYS = 6.0                     # el menu ya esta listo


def set_timing(machine):
    """Las BIOS reales tardan mas en arrancar (logo, disquetera...)."""
    global NATIVE_BOOT, MENU_KEYS
    if not machine.startswith("C-BIOS"):
        NATIVE_BOOT, MENU_KEYS = 5.0, 8.0
THRESHOLD = 18
INK_THRESHOLD = 0.6


def openmsx(rom, romtype, machine, keys, shots):
    lines = ["set throttle off"]
    for kt, row, mask in keys:
        lines += ["after time %.2f {keymatrixdown %d %d}" % (kt, row, mask),
                  "after time %.2f {keymatrixup %d %d}" % (kt + .15, row, mask)]
    for t, path in shots:
        lines.append("after time %.2f {set throttle on}" % (t - .4))
        lines.append("after time %.2f {screenshot {%s}; set throttle off}" % (t, path.replace("\\", "/")))
    lines.append("after time %.2f {exit}" % (shots[-1][0] + .2))
    tcl = shots[0][1] + ".tcl"
    with open(tcl, "w") as f:
        f.write("\n".join(lines) + "\n")
    cmd = [OPENMSX, "-machine", machine, "-cart", rom, "-script", tcl]
    if romtype:
        cmd[5:5] = ["-romtype", romtype]
    subprocess.run(cmd, timeout=300, capture_output=True)
    os.remove(tcl)


def shot_names(prefix):
    return [prefix + "_%02d.png" % t for t in SHOTS_T]


def run_menu(rom, romtype, machine, idx, prefix):
    keys = []
    t = MENU_KEYS
    for _ in range(idx):
        keys.append((t, 8, 0x40))
        t += 0.3
    t += 0.3
    keys.append((t, 8, 0x01))
    t0 = t + 0.1  # el juego arranca al soltar espacio
    for k in KEYS_T:
        keys.append((t0 + k, 8, 0x01))
    openmsx(rom, romtype, machine, keys, [(t0 + s, p) for s, p in zip(SHOTS_T, shot_names(prefix))])


def run_native(g, machine, prefix):
    rom = os.path.join(OUT, "native_%s.rom" % g.sha1[:10])
    with open(rom, "wb") as f:
        f.write(g.raw)
    keys = [(NATIVE_BOOT + k, 8, 0x01) for k in KEYS_T]
    openmsx(rom, RT[g.mapper], machine, keys,
            [(NATIVE_BOOT + s, p) for s, p in zip(SHOTS_T, shot_names(prefix))])


def small(p):
    try:
        return Image.open(p).convert("L").resize((64, 48))
    except OSError:
        return None


def diff(a, b):
    if a is None or b is None:
        return 255
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def ink_diff(a, b):
    """Para pantallas casi lisas (texto): parte de los pixeles 'con tinta'
    (distintos del color de fondo) que no coinciden. 0 = igual, 1 = distinto."""
    if a is None or b is None:
        return 1.0
    pa, pb = list(a.getdata()), list(b.getdata())
    bg = max(set(pa), key=pa.count)
    ink = [i for i in range(len(pa)) if abs(pa[i] - bg) > 30 or abs(pb[i] - bg) > 30]
    if len(ink) < 20:
        return 0.0
    return sum(1 for i in ink if abs(pa[i] - pb[i]) > 30) / len(ink)


def score_ink(menu_prefix, nat_prefix):
    m = [small(p) for p in shot_names(menu_prefix)]
    n = [small(p) for p in shot_names(nat_prefix)]
    vals = []
    for i, a in enumerate(m):
        vals.append(min(ink_diff(a, n[j]) for j in range(max(0, i - 1), min(len(n), i + 2))))
    return sum(vals) / len(vals)


def score(menu_prefix, nat_prefix):
    """Para cada captura desde el menu, la diferencia con la captura original
    mas parecida de instantes vecinos; devuelve la media."""
    m = [small(p) for p in shot_names(menu_prefix)]
    n = [small(p) for p in shot_names(nat_prefix)]
    vals = []
    for i, a in enumerate(m):
        vals.append(min(diff(a, n[j]) for j in range(max(0, i - 1), min(len(n), i + 2))))
    return sum(vals) / len(vals)


def label(img, text, col=(255, 255, 0)):
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, img.width, 14), fill=(0, 0, 0))
    d.text((3, 1), text, fill=col)
    return img


def main():
    cart = sys.argv[1]
    size = int(sys.argv[2])
    machine = sys.argv[3] if len(sys.argv) > 3 else "C-BIOS_MSX2"
    filt = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "-" else ""
    pat = sys.argv[5] if len(sys.argv) > 5 else os.path.join(HERE, "..", "roms", "*.zip")
    tag = sys.argv[6] if len(sys.argv) > 6 else "all"
    set_timing(machine)
    games = [mr.Game(f) for f in sorted(glob.glob(pat))]
    games = [g for g in games if not g.error and filt.lower() in g.title.lower()]
    # Repartir en varias imagenes si no caben (o si quedarian en un sitio con riesgo de SCC)
    groups, cur = [], []
    for g in games:
        if None in mr.allocate([g], cart, size):
            print("%-30s NO CABE" % g.title[:30])
            continue
        trial = cur + [g]
        risky = set()
        if None in mr.allocate(trial, cart, size, risky) or risky:
            if cur:
                groups.append(cur)
            cur = [g]
        else:
            cur = trial
    if cur:
        groups.append(cur)
    jobs = []
    for gi, grp in enumerate(groups):
        img, rep = mr.build(grp, cart, size, "TEST %d" % gi)
        rom = os.path.join(OUT, "%s_%s_%d.rom" % (cart, tag, gi))
        with open(rom, "wb") as f:
            f.write(img)
        for i, (g, b, r) in enumerate(rep):
            print("%-30s grupo %d banco %-4s parches=%-3d ROM=%-2d RAM=%-2d dyn=%-2d %s" % (
                g.title[:30], gi, b, r["sites"], r["stubs"], r["ram"], r.get("dyn", 0),
                "; ".join(r["errors"])))
            jobs.append((rom, i, g))
    romtype = mr.CARTS[cart]["romtype"]

    def work(job):
        rom, i, g = job
        a = os.path.join(OUT, "%s_%s_menu" % (cart, g.sha1[:10]))
        b = os.path.join(OUT, "%s_%s_nat" % (g.sha1[:10], machine))
        run_menu(rom, romtype, machine, i, a)
        if not all(os.path.exists(p) for p in shot_names(b)):
            run_native(g, machine, b)
        return g, a, b, score(a, b), score_ink(a, b)

    with cf.ThreadPoolExecutor(6) as ex:
        results = list(ex.map(work, jobs))
    # Montaje: original | menu (ultima captura); en rojo los dudosos
    tiles = []
    print()
    for g, a, b, sc, ink in results:
        bad = sc > THRESHOLD or ink > INK_THRESHOLD
        print("%-30s dif=%5.1f tinta=%4.2f %s" % (g.title[:30], sc, ink, "<<< REVISAR" if bad else ""))
        k = len(SHOTS_T) - 1
        pair = Image.new("RGB", (330, 125), (200, 0, 0) if bad else (60, 60, 60))
        for c, (p, lab) in enumerate(((shot_names(b)[k], "orig"), (shot_names(a)[k], cart))):
            if os.path.exists(p):
                im = Image.open(p).convert("RGB").resize((160, 120))
                pair.paste(label(im, "%s %s %.0f" % (lab, g.title[:14], sc)), (c * 165, 0))
        tiles.append(pair)
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    m = Image.new("RGB", (cols * 335, max(1, rows) * 130), (255, 0, 255))
    for i, t in enumerate(tiles):
        m.paste(t, ((i % cols) * 335, (i // cols) * 130))
    out = os.path.join(OUT, "montage_%s_%s_%s.png" % (cart, tag, machine))
    m.save(out)
    print(out)


if __name__ == "__main__":
    main()
