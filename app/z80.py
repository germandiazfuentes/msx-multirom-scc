"""Decodificador minimo de instrucciones Z80: longitud y tipo.

Solo lo necesario para reubicar unas pocas instrucciones a una rutina en RAM
(ver multirom.patch_dynamic).
"""

# Tipos de instruccion
PLAIN = "plain"     # se puede copiar tal cual a otra direccion
JP = "jp"           # JP nn / JR e (destino en .target)
JPCC = "jpcc"       # JP cc,nn / JR cc,e (condicion en .cc: 0=NZ 1=Z 2=NC 3=C ... 7=M)
DJNZ = "djnz"
RET = "ret"
RETCC = "retcc"
CALL = "call"       # CALL nn
CALLCC = "callcc"
TERM = "term"       # JP (HL) / JP (IX): se copia y termina la secuencia
BAD = "bad"         # no se sabe reubicar

# La rutina en RAM se alcanza con JP y vuelve con JP, sin tocar la pila, asi
# que PUSH/POP/RST/CALL se pueden copiar tal cual; solo hay que recalcular
# los saltos relativos.

_LEN2 = {0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E, 0x36, 0x3E, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38,
         0xC6, 0xCE, 0xD6, 0xDE, 0xE6, 0xEE, 0xF6, 0xFE, 0xD3, 0xDB, 0xCB}
_LEN3 = {0x01, 0x11, 0x21, 0x31, 0x22, 0x2A, 0x32, 0x3A, 0xC3, 0xCD,
         0xC2, 0xCA, 0xD2, 0xDA, 0xE2, 0xEA, 0xF2, 0xFA,
         0xC4, 0xCC, 0xD4, 0xDC, 0xE4, 0xEC, 0xF4, 0xFC}
# Instrucciones que usan (HL) y con prefijo DD/FD pasan a (IX+d)
_HLMEM = {0x34, 0x35, 0x36, 0x46, 0x4E, 0x56, 0x5E, 0x66, 0x6E, 0x7E,
          0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x77,
          0x86, 0x8E, 0x96, 0x9E, 0xA6, 0xAE, 0xB6, 0xBE}
_ED_LEN4 = {0x43, 0x4B, 0x53, 0x5B, 0x63, 0x6B, 0x73, 0x7B}
_ED_RET = {0x45, 0x4D, 0x55, 0x5D, 0x65, 0x6D, 0x75, 0x7D}  # RETN / RETI


class Insn:
    def __init__(self, addr, length, kind, target=None, cc=None):
        self.addr = addr          # direccion Z80 de la instruccion
        self.length = length
        self.kind = kind
        self.target = target
        self.cc = cc

    def __repr__(self):
        return "<%04X len=%d %s>" % (self.addr, self.length, self.kind)


def decode(data, i, addr):
    """Decodifica la instruccion en data[i] que se ejecuta en la direccion addr."""
    op = data[i]
    if op in (0xDD, 0xFD):
        op2 = data[i + 1]
        if op2 == 0xCB:
            return Insn(addr, 4, PLAIN)
        if op2 in (0xDD, 0xFD, 0xED):
            return Insn(addr, 1, BAD)
        if op2 == 0xE9:
            return Insn(addr, 2, TERM)
        if op2 == 0x36:
            return Insn(addr, 4, PLAIN)
        if op2 in _HLMEM:
            return Insn(addr, 3, PLAIN)
        n = 1 + _plain_len(op2)
        ins = _classify(data, i + 1, addr + 1, op2)
        ins.addr, ins.length = addr, n
        return ins
    if op == 0xED:
        op2 = data[i + 1]
        n = 4 if op2 in _ED_LEN4 else 2
        return Insn(addr, n, RET if op2 in _ED_RET else PLAIN)
    return _classify(data, i, addr, op)


def _plain_len(op):
    if op in _LEN3:
        return 3
    if op in _LEN2:
        return 2
    return 1


def _classify(data, i, addr, op):
    n = _plain_len(op)
    if op == 0xE9:
        return Insn(addr, 1, TERM)
    if op == 0xC3:
        return Insn(addr, 3, JP, data[i + 1] | (data[i + 2] << 8))
    if op == 0x18 or op == 0x10 or op in (0x20, 0x28, 0x30, 0x38):
        e = data[i + 1]
        tgt = (addr + 2 + (e - 256 if e >= 128 else e)) & 0xFFFF
        if op == 0x18:
            return Insn(addr, 2, JP, tgt)
        if op == 0x10:
            return Insn(addr, 2, DJNZ, tgt)
        return Insn(addr, 2, JPCC, tgt, (op - 0x20) >> 3)
    if (op & 0xC7) == 0xC2:
        return Insn(addr, 3, JPCC, data[i + 1] | (data[i + 2] << 8), (op >> 3) & 7)
    if op == 0xCD:
        return Insn(addr, 3, CALL, data[i + 1] | (data[i + 2] << 8))
    if (op & 0xC7) == 0xC4:
        return Insn(addr, 3, CALLCC, data[i + 1] | (data[i + 2] << 8), (op >> 3) & 7)
    if op == 0xC9:
        return Insn(addr, 1, RET)
    if (op & 0xC7) == 0xC0:
        return Insn(addr, 1, RETCC, cc=(op >> 3) & 7)
    return Insn(addr, n, PLAIN)


def branch_targets(data, start, end, base_addr):
    """Direcciones a las que saltan los JP/CALL/JR que aparecen en data[start:end]
    (que se ejecuta en base_addr). Se mira byte a byte, sin seguir el flujo, asi
    que salen falsos positivos: sirve para descartar con prudencia."""
    out = set()
    for i in range(start, end - 1):
        op = data[i]
        if op in (0x18, 0x10, 0x20, 0x28, 0x30, 0x38):
            e = data[i + 1]
            out.add((base_addr + i - start + 2 + (e - 256 if e >= 128 else e)) & 0xFFFF)
        elif i < end - 2 and (op in (0xC3, 0xCD) or (op & 0xC7) in (0xC2, 0xC4)):
            out.add(data[i + 1] | (data[i + 2] << 8))
    return out
