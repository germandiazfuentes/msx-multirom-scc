"""Genera las ROMs de prueba de mapper (128KB) con pasmo."""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PASMO = os.path.join(HERE, "..", "..", "pasmo.exe")

VARIANTS = {
    "konami4": dict(A16=0, REG_P1=0x6000, REG_P2=0x8000, REG_P3=0xA000, NB=16),
    "konami5": dict(A16=0, REG_P1=0x7000, REG_P2=0x9000, REG_P3=0xB000, NB=16),
    "ascii8": dict(A16=0, REG_P1=0x6800, REG_P2=0x7000, REG_P3=0x7800, NB=16),
    "ascii16": dict(A16=1, REG_P1=0x6000, REG_P2=0x7000, REG_P3=0, NB=8),
}

for name, v in VARIANTS.items():
    src = os.path.join(HERE, "_%s.asm" % name)
    with open(src, "w") as f:
        for k, val in v.items():
            f.write("%s equ %d\n" % (k, val))
        f.write('include "mtest.asm"\n')
    out = os.path.join(HERE, "_%s.bin" % name)
    subprocess.run([PASMO, src, out], check=True, cwd=HERE)
    code = open(out, "rb").read()
    rom = bytearray(b"\xFF" * 0x20000)
    rom[0:len(code)] = code
    unit = 0x4000 if v["A16"] else 0x2000
    for b in range(0x20000 // unit):
        rom[b * unit + 0x1F00] = ord("B")
        rom[b * unit + 0x1F01] = b
        if v["A16"]:
            rom[b * unit + 0x3F01] = b
    with open(os.path.join(HERE, "mtest_%s.rom" % name), "wb") as f:
        f.write(rom)
    os.remove(src)
    os.remove(out)
    print(name, "ok")
