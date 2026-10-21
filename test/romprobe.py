"""Lanza el juego INDICE de una ROM ya generada, hace reset y mueve el cursor.

    python romprobe.py ROM ROMTYPE MAQUINA INDICE SALIDA.png
"""
import os, subprocess, sys
from run import OPENMSX
from PIL import Image

rom, rtype, mach, idx, png = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
out = os.path.abspath('out/romprobe').replace(os.sep, '/')
os.makedirs(out, exist_ok=True)
k0 = 6 if mach.startswith('C-BIOS') else 9
tcl = ['set throttle off']
def key(t, row, mask):
    tcl.extend(['after time %.2f {keymatrixdown %d %d}' % (t, row, mask),
                'after time %.2f {keymatrixup %d %d}' % (t + .15, row, mask)])
t = k0
for _ in range(idx):
    key(t, 8, 0x40); t += .3
key(t, 8, 1)
shots = [t + 3, t + 8]
key(t + 9, 8, 1)          # ESPACIO en el juego
shots.append(t + 12)
tr = t + 13
tcl.append('after time %.2f {reset}' % tr)
t2 = tr + k0
shots.append(t2 - .5)
for k in range(3):
    key(t2 + k * .4, 8, 0x40)
shots += [t2 + 2]
for i, s in enumerate(shots):
    tcl.append('after time %.2f {set throttle on}' % (s - .4))
    tcl.append('after time %.2f {screenshot {%s/s%d.png}; set throttle off}' % (s, out, i))
tcl.append('after time %.2f {exit}' % (shots[-1] + .3))
open(out + '/p.tcl', 'w').write('\n'.join(tcl))
for i in range(len(shots)):
    if os.path.exists('%s/s%d.png' % (out, i)):
        os.remove('%s/s%d.png' % (out, i))
subprocess.run([OPENMSX, '-machine', mach, '-cart', rom, '-romtype', rtype, '-script', out + '/p.tcl'], timeout=300)
m = Image.new('RGB', (165 * len(shots), 125))
for i in range(len(shots)):
    p = '%s/s%d.png' % (out, i)
    if os.path.exists(p):
        m.paste(Image.open(p).convert('RGB').resize((160, 120)), (i * 165, 0))
m.save(png)
