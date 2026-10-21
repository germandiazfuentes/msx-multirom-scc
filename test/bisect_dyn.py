"""Construye un K5 con un juego usando solo algunos sitios dinamicos y captura la pantalla."""
import sys, glob, os
sys.path.insert(0, '../app'); import multirom as mr
from run import run
pat, keep = sys.argv[1], sys.argv[2]
g = mr.Game(glob.glob('../roms/' + pat)[0])
sites = g.analysis['sites']
if keep != 'all':
    ks = {int(x, 16) for x in keep.split(',') if x}
    g.analysis = dict(g.analysis, sites=[s for s in sites if s['off'] in ks])
img, rep = mr.build([g], 'k5', 512, 'T')
print(rep[0][2])
open('out/bis.rom', 'wb').write(img)
run('out/bis.rom', 'KonamiSCC', 'C-BIOS_MSX2', 0, 'out/bis_%s.png' % keep.replace(',', '_')[:30], 24.0,
    extra=[(8, (8, 1)), (11, (8, 1)), (14, (8, 1))])
