"""Lanza un juego desde un MultiROM de 1 juego (o el original) y registra PC + capturas cada 2 s.

    python probe_game.py PATRON CART [maquina] [native]
"""
import os
import subprocess
import sys
import glob

sys.path.insert(0, '../app')
import multirom as mr  # noqa: E402
from run import OPENMSX  # noqa: E402

RT = {mr.KONAMI4: 'Konami', mr.KONAMI5: 'KonamiSCC', mr.ASCII8: 'ASCII8', mr.ASCII16: 'ASCII16',
      mr.GKONAMI: '8kB', mr.GENERIC16: '16kB'}

pat, cart = sys.argv[1], sys.argv[2]
mach = sys.argv[3] if len(sys.argv) > 3 else 'C-BIOS_MSX2'
native = len(sys.argv) > 4 and sys.argv[4] == 'native'
files = glob.glob('../roms2/*/' + pat) + glob.glob('../roms/' + pat)
g = mr.Game(files[0])
if os.environ.get('PROBE_AREA'):
    g.ram_area = os.environ['PROBE_AREA']
out = os.path.abspath('out/probe').replace(os.sep, '/')
os.makedirs(out, exist_ok=True)
for f in glob.glob(out + '/s*.png'):
    os.remove(f)
if native:
    rom = out + '/nat.rom'
    open(rom, 'wb').write(g.raw)
    rt = RT.get(g.mapper)
else:
    img, rep = mr.build([g], cart, 2048 if cart == 'k5' else 8192, 'T')
    print(rep[0][2])
    rom = out + '/mr.rom'
    open(rom, 'wb').write(img)
    rt = mr.CARTS[cart]['romtype']
tcl = ['set throttle off', 'set ::f [open {%s/pc.txt} w]' % out]
k0 = 6 if mach.startswith('C-BIOS') else 8
t0 = 2 if native else k0 + 0.3
if not native:
    tcl += ['after time %d {keymatrixdown 8 1}' % k0, 'after time %.1f {keymatrixup 8 1}' % (k0 + .2)]
for k in (14, 17, 20, 23):      # como realtest
    tcl += ['after time %.1f {keymatrixdown 8 1}' % (t0 + k), 'after time %.1f {keymatrixup 8 1}' % (t0 + k + .15)]
for t in range(4, 39, 3):  # capturas
    tcl.append('after time %.1f {set throttle on}' % (t - 0.4))
    tcl.append('after time %d {puts $::f "%d [format %%04X [reg pc]] sp=[format %%04X [reg sp]]"; '
               'screenshot {%s/s%02d.png}; set throttle off}' % (t, t, out, t))
tcl.append('after time 40 {close $::f; exit}')
open(out + '/p.tcl', 'w').write('\n'.join(tcl))
cmd = [OPENMSX, '-machine', mach, '-cart', rom, '-script', out + '/p.tcl']
if rt:
    cmd[5:5] = ['-romtype', rt]
subprocess.run(cmd, timeout=200)
print(open(out + '/pc.txt', errors='replace').read())
from PIL import Image  # noqa: E402
ims = [Image.open('%s/s%02d.png' % (out, t)).convert('RGB').resize((160, 120))
       for t in range(4, 39, 3) if os.path.exists('%s/s%02d.png' % (out, t))]
m = Image.new('RGB', (165 * 6, 125 * 2))
for i, im in enumerate(ims):
    m.paste(im, ((i % 6) * 165, (i // 6) * 125))
m.save(out + '/m.png')
