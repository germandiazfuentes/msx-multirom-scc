"""Genera un MultiROM con varios juegos, lanza uno, hace reset y vuelve a mover el cursor.

    python multiprobe.py CART MAQUINA INDICE rom1 rom2 ...
"""
import os, subprocess, sys
sys.path.insert(0, '../app')
import multirom as mr
from run import OPENMSX
from PIL import Image

cart, mach, idx = sys.argv[1], sys.argv[2], int(sys.argv[3])
games = [mr.Game(f) for f in sys.argv[4:]]
img, rep = mr.build(games, cart, 2048 if cart == 'k5' else 8192, 'T')
for g, b, r in rep:
    print('%-25s banco=%s %s' % (g.title[:25], b, r.get('area')), r['errors'])
out = os.path.abspath('out/mprobe').replace(os.sep, '/')
os.makedirs(out, exist_ok=True)
for f in os.listdir(out):
    os.remove(os.path.join(out, f))
rom = out + '/mr.rom'
open(rom, 'wb').write(img)
k0 = float(os.environ.get('K0', 6 if mach.startswith('C-BIOS') else 8))
tcl = ['set throttle off']
t = k0
def key(t, row, mask):
    tcl.extend(['after time %.2f {keymatrixdown %d %d}' % (t, row, mask),
                'after time %.2f {keymatrixup %d %d}' % (t + .15, row, mask)])
for _ in range(idx):
    key(t, 8, 0x40); t += .3
key(t, 8, 1)
shots = [t + 4, t + 10]
tr = t + 12
tcl.append('after time %.2f {reset}' % tr)
t2 = tr + k0
for k in range(3):
    key(t2 + k * .4, 8, 0x40)
shots += [t2 - 1, t2 + 2]
for i, s in enumerate(shots):
    tcl.append('after time %.2f {set throttle on}' % (s - .4))
    tcl.append('after time %.2f {screenshot {%s/s%d.png}; set throttle off}' % (s, out, i))
tcl.append('after time %.2f {exit}' % (shots[-1] + .3))
open(out + '/p.tcl', 'w').write('\n'.join(tcl))
subprocess.run([OPENMSX, '-machine', mach, '-cart', rom] + ([] if os.environ.get('NOTYPE') else ['-romtype', mr.CARTS[cart]['romtype']]) + [
                '-script', out + '/p.tcl'], timeout=300)
m = Image.new('RGB', (165 * len(shots), 125))
for i in range(len(shots)):
    p = '%s/s%d.png' % (out, i)
    if os.path.exists(p):
        m.paste(Image.open(p).convert('RGB').resize((160, 120)), (i * 165, 0))
m.save(out + '/m.png')
