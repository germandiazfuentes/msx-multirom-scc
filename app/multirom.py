"""
MSX MultiROM builder - nucleo (sin interfaz grafica).

Genera una imagen para cartuchos Konami5 (RBSC Multimapper) o Yamanooto con
un menu de seleccion y varios juegos, convirtiendo los mappers ASCII8,
ASCII16, Konami4 y Konami5 al mapper del cartucho.

Uso por linea de comandos:
    python multirom.py --cart k5 --size 512 -o salida.rom juego1.rom juego2.rom
"""

import argparse
import gzip
import hashlib
import json
import os
import sys
import unicodedata
import zipfile

import z80

BANK = 0x2000  # 8KB

# Tipos de mapper de las ROMs individuales
PLAIN, KONAMI4, KONAMI5, ASCII8, ASCII16, GKONAMI, GENERIC16 = range(7)
MAPPER_NAMES = {
    PLAIN: "ROM (sin mapper)",
    KONAMI4: "Konami4",
    KONAMI5: "Konami5 (SCC)",
    ASCII8: "ASCII8",
    ASCII16: "ASCII16",
    GKONAMI: "Generico 8K",
    GENERIC16: "Generico 16K",
}
# Identificador que muestra el menu (ver mapper_names en menu.asm)
MENU_MAPPER_ID = {PLAIN: 0, KONAMI4: 1, KONAMI5: 2, ASCII8: 3, ASCII16: 4, GKONAMI: 1, GENERIC16: 4}

# Cartuchos de destino
CARTS = {
    "k5": {
        "name": "Konami5 / RBSC Multimapper",
        "type": 0,
        "sizes": [512, 2048],
        "romtype": "KonamiSCC",
    },
    "yama": {
        "name": "Yamanooto",
        "type": 1,
        "sizes": [512, 2048, 4096, 8192],
        "romtype": "Yamanooto",
    },
}

ENTRY_SIZE = 48
ENTRIES_PER_BANK = 170
NAME_LEN = 30

# Registros Yamanooto (CFGR)
Y_MDIS = 0x01
Y_K4 = 0x08

# Registros del mapper Konami5 de destino, por pagina de 8KB (4000h..A000h)
K5_REGS = [0x5000, 0x7000, 0x9000, 0xB000]

# Escrituras de cambio de banco de cada mapper: direccion -> pagina.
# Para ASCII16 la pagina es de 16KB (0 = 4000h, 1 = 8000h).
SOURCE_REGS = {
    KONAMI4: {0x6000: 1, 0x8000: 2, 0xA000: 3},
    GKONAMI: {0x4000: 0, 0x6000: 1, 0x8000: 2, 0xA000: 3},
    KONAMI5: {0x5000: 0, 0x7000: 1, 0x9000: 2, 0xB000: 3},
    ASCII8: {0x6000: 0, 0x6800: 1, 0x7000: 2, 0x7800: 3},
    ASCII16: {0x6000: 0, 0x7000: 1, 0x77FF: 1},
    GENERIC16: {0x4000: 0, 0x8000: 1},
}

# Rangos completos que decodifica cada mapper: (desde, hasta, pagina)
SOURCE_RANGES = {
    KONAMI4: [(0x6000, 0x7FFF, 1), (0x8000, 0x9FFF, 2), (0xA000, 0xBFFF, 3)],
    GKONAMI: [(0x4000, 0x5FFF, 0), (0x6000, 0x7FFF, 1), (0x8000, 0x9FFF, 2), (0xA000, 0xBFFF, 3)],
    KONAMI5: [(0x5000, 0x57FF, 0), (0x7000, 0x77FF, 1), (0x9000, 0x97FF, 2), (0xB000, 0xB7FF, 3)],
    ASCII8: [(0x6000, 0x67FF, 0), (0x6800, 0x6FFF, 1), (0x7000, 0x77FF, 2), (0x7800, 0x7FFF, 3)],
    ASCII16: [(0x6000, 0x67FF, 0), (0x7000, 0x77FF, 1)],
    GENERIC16: [(0x4000, 0x7FFF, 0), (0x8000, 0xBFFF, 1)],
}


# Instrucciones que suelen preparar A justo antes de LD (nn),A
_A_LOADERS_1 = {0x78, 0x79, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x7F, 0x3C, 0x3D, 0xF1, 0x0A, 0x1A, 0x87}


def _code_like(data, i):
    """Heuristica: la instruccion en i parece codigo (no datos ni texto)."""
    if i < 3 or i + 5 > len(data):
        return False
    window = data[i - 3:i + 5]
    if all(0x20 <= b < 0x7F for b in window):
        return False  # texto ASCII
    return (data[i - 2] == 0x3E or data[i - 3] in (0x3A, 0x32)
            or data[i - 1] in _A_LOADERS_1)


def mapper_regs(data, mapper):
    """Direcciones de registro que usa el juego: las canonicas mas otras del
    rango del mapper que aparezcan al menos 2 veces en un contexto que parece
    codigo (precedidas de LD A,n / LD A,(nn) / LD A,r...)."""
    regs = dict(SOURCE_REGS[mapper])
    counts = {}
    for i in range(len(data) - 2):
        if data[i] != 0x32:
            continue
        addr = data[i + 1] | (data[i + 2] << 8)
        if addr in regs:
            continue
        for lo, hi, page in SOURCE_RANGES[mapper]:
            if lo <= addr <= hi:
                if _code_like(data, i):
                    counts[addr] = counts.get(addr, 0) + 1
                break
    for addr, n in counts.items():
        if n >= 2:
            regs[addr] = next(p for lo, hi, p in SOURCE_RANGES[mapper] if lo <= addr <= hi)
    return regs


# Tipos de la base de datos de openMSX
DB_TYPES = {
    "Konami": KONAMI4,
    "KonamiSCC": KONAMI5,
    "ASCII8": ASCII8,
    "ASCII16": ASCII16,
    "GenericKonami": GKONAMI,
    "8kB": GKONAMI,
    "16kB": GENERIC16,
    "16kb": GENERIC16,
    "ASCII8SRAM2": ASCII8,
    "ASCII8SRAM8": ASCII8,
    "ASCII16SRAM2": ASCII16,
    "ASCII16SRAM8": ASCII16,
    "KoeiSRAM8": ASCII8,
    "KoeiSRAM32": ASCII8,
}
DB_PLAIN = {"Mirrored", "Normal", "page1", "page12", "page2",
            "page23", "page012", "page123", "page0123", "page01", "Mirrored4000",
            "Mirrored8000", "MirroredC000", "Mirrored0000", "Mirrored0000"}

APP_DIR = os.path.dirname(os.path.abspath(__file__))
MENU_BIN = os.path.join(APP_DIR, "msx", "menu.bin")
ROMDB = os.path.join(APP_DIR, "data", "romdb.tsv.gz")
# Resultados del analisis en openMSX (analyze.py), por SHA1
ANALYSIS_DIR = os.path.join(os.path.expanduser("~"), ".msx_multirom", "analisis")


ANALYSIS_VERSION = 2   # 2: distingue escrituras al cartucho y a la RAM


def load_analysis(sha1):
    try:
        with open(os.path.join(ANALYSIS_DIR, sha1 + ".json"), encoding="utf-8") as f:
            an = json.load(f)
    except (OSError, ValueError):
        return None
    return an if an.get("version") == ANALYSIS_VERSION else None

_db = None


def romdb():
    global _db
    if _db is None:
        _db = {}
        if os.path.exists(ROMDB):
            with gzip.open(ROMDB, "rt", encoding="utf-8") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) == 4:
                        _db[parts[0]] = (parts[1], parts[2], parts[3])
    return _db


class RomError(Exception):
    pass


def ascii_name(text):
    """Nombre en ASCII imprimible (el menu usa la fuente de la BIOS)."""
    text = unicodedata.normalize("NFKD", text)
    out = "".join(c for c in text if 32 <= ord(c) < 127)
    return out.strip()


def guess_mapper(data):
    """Heuristica de openMSX: cuenta escrituras LD (nnnn),A a registros tipicos."""
    score = {KONAMI4: 0, KONAMI5: 0, ASCII8: 0, ASCII16: 0}
    for i in range(len(data) - 2):
        if data[i] != 0x32:
            continue
        addr = data[i + 1] | (data[i + 2] << 8)
        if addr in (0x5000, 0x9000, 0xB000):
            score[KONAMI5] += 1
        elif addr in (0x4000, 0x8000, 0xA000):
            score[KONAMI4] += 1
        elif addr in (0x6800, 0x7800):
            score[ASCII8] += 1
        elif addr == 0x6000:
            score[KONAMI4] += 1
            score[ASCII8] += 1
            score[ASCII16] += 1
        elif addr == 0x7000:
            score[KONAMI5] += 1
            score[ASCII8] += 1
            score[ASCII16] += 1
        elif addr == 0x77FF:
            score[ASCII16] += 1
    if score[ASCII8]:
        score[ASCII8] -= 1
    best = max(score, key=lambda k: (score[k], -k))
    return best if score[best] else None


ROM_EXTS = (".rom", ".mx1", ".mx2", ".bin", ".ri")


def read_rom_file(path):
    """Lee una ROM; si es un .zip coge la ROM mas grande de dentro.
    Devuelve (datos, nombre_interno)."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            names = [i for i in z.infolist() if i.filename.lower().endswith(ROM_EXTS)]
            if not names:
                raise RomError("El zip no contiene ninguna ROM")
            info = max(names, key=lambda i: i.file_size)
            return z.read(info), os.path.basename(info.filename)
    with open(path, "rb") as f:
        return f.read(), None


class Game:
    """Una ROM individual preparada para meterse en el cartucho."""

    def __init__(self, path, data=None):
        self.path = path
        inner = None
        if data is None:
            data, inner = read_rom_file(path)
        self.raw = data
        if not self.raw:
            raise RomError("Fichero vacio")
        self.sha1 = hashlib.sha1(self.raw).hexdigest()
        self.warnings = []
        self.ram_area = None        # area de RAM para las rutinas (None = por defecto)
        self.stub_place = os.environ.get("MULTIROM_STUBS", "ram")  # "ram" (RAM y si no ROM) o "rom"
        self.analysis = load_analysis(self.sha1)
        self._abs_targets = None
        db = romdb().get(self.sha1)
        self.db_type = db[0] if db else None
        base = os.path.splitext(os.path.basename(inner or path))[0]
        self.title = ascii_name(db[2] if db else base)[:NAME_LEN] or "SIN NOMBRE"
        self.system = db[1] if db else ""
        if db and db[0] in DB_TYPES:
            self.mapper = DB_TYPES[db[0]]
            self.mapper_src = "base de datos"
            if "SRAM" in db[0]:
                self.warnings.append("El juego usa SRAM para grabar; no funcionara la grabacion")
        elif db and db[0] in DB_PLAIN:
            self.mapper = PLAIN
            self.mapper_src = "base de datos"
        elif db:
            self.mapper = None
            self.mapper_src = "base de datos"
            self.warnings.append("Mapper '%s' no soportado" % db[0])
        else:
            self.mapper_src = "deteccion"
            if len(self.raw) <= 0x8000:
                self.mapper = PLAIN
            else:
                self.mapper = guess_mapper(self.raw)
                if self.mapper is None or (len(self.raw) <= 0x10000 and self._plain_header()):
                    self.mapper = PLAIN
        self.prepare()

    def _plain_header(self):
        for off in (0, 0x4000, 0x8000):
            if self.raw[off:off + 2] == b"AB":
                init = self.raw[off + 2] | (self.raw[off + 3] << 8)
                if 0x4000 <= init < 0xC000:
                    return True
        return False

    @property
    def nbanks(self):
        return len(self.data) // BANK

    @property
    def size_kb(self):
        return len(self.data) // 1024

    def set_mapper(self, mapper):
        self.mapper = mapper
        self.mapper_src = "usuario"
        self.prepare()

    def prepare(self):
        """Normaliza la imagen: self.data (multiplo de 8KB), self.rel (valores
        iniciales relativos de los 4 registros) y self.page2 (cabecera en 8000h)."""
        self.error = None
        self.page2 = False
        self.prep_warnings = []
        try:
            if self.mapper is None:
                raise RomError("Mapper no soportado")
            if self.mapper == PLAIN:
                self._prepare_plain()
            else:
                self._prepare_mapped()
        except RomError as e:
            self.error = str(e)
            self.data = b""
            self.rel = [0, 0, 0, 0]

    def _prepare_mapped(self):
        data = self.raw
        if len(data) % BANK:
            data = data + b"\xFF" * (BANK - len(data) % BANK)
        n = len(data) // BANK
        if n > 256:
            raise RomError("Juego de mas de 2MB: los registros Konami5 solo llegan a 256 bancos")
        if n & (n - 1):
            self.prep_warnings.append("Tamano no potencia de 2")
        if data[0:2] != b"AB":
            self.prep_warnings.append("La ROM no empieza por la cabecera 'AB'")
        self.data = data
        if self.mapper in (KONAMI4, KONAMI5, GKONAMI, GENERIC16):
            self.rel = [0, 1, 2, 3]
        elif self.mapper == ASCII8:
            self.rel = [0, 0, 0, 0]
        else:
            self.rel = [0, 1, 0, 1]

    def _prepare_plain(self):
        raw = self.raw
        if len(raw) > 0x10000:
            raise RomError("ROM sin mapper de mas de 64KB")
        hdr = None
        for off in range(0, len(raw), 0x4000):
            if raw[off:off + 2] == b"AB":
                init = raw[off + 2] | (raw[off + 3] << 8)
                text = raw[off + 8] | (raw[off + 9] << 8)
                if init == 0 and text:
                    raise RomError("ROM de BASIC (no soportada)")
                if 0x4000 <= init < 0xC000:
                    hdr = (off, init & 0xC000)
                    break
        if hdr is None:
            raise RomError("No se encuentra la cabecera 'AB' con direccion de inicio")
        off, hdr_addr = hdr
        file_base = hdr_addr - off  # direccion Z80 del byte 0 del fichero
        # ROMs de 48/64KB se cargan a partir de 0000h
        if len(raw) > 0x8000 and file_base != 0:
            file_base = 0
        if len(raw) > 0x8000 or file_base < 0x4000 or file_base + len(raw) > 0xC000:
            # Comprobar que no hay nada util fuera de 4000h-BFFFh
            for addr in range(0, 0x10000, 0x4000):
                if 0x4000 <= addr < 0xC000:
                    continue
                o = addr - file_base
                if o < 0 or o >= len(raw):
                    continue
                chunk = raw[o:o + 0x4000]
                if chunk.count(chunk[0]) != len(chunk):
                    self.prep_warnings.append(
                        "Hay datos en %04Xh-%04Xh que el cartucho no puede mostrar" % (addr, addr + 0x3FFF))
        win = bytearray(b"\xFF" * 0x8000)
        covered = [False] * 4
        for p in range(4):
            o = 0x4000 + p * BANK - file_base
            if 0 <= o < len(raw):
                piece = raw[o:o + BANK]
                win[p * BANK:p * BANK + len(piece)] = piece
                covered[p] = True
        used = [p for p in range(4) if covered[p]]
        self.page2 = hdr_addr == 0x8000
        if used == [0] or used == [2] or used == [1] or used == [3]:
            # 8KB, espejada en las 4 paginas
            p = used[0]
            self.data = bytes(win[p * BANK:(p + 1) * BANK])
            self.rel = [0, 0, 0, 0]
        elif used == [0, 1] or used == [2, 3]:
            p = used[0]
            self.data = bytes(win[p * BANK:(p + 2) * BANK])
            self.rel = [0, 1, 0, 1]
        else:
            self.data = bytes(win)
            self.rel = [0, 1, 2, 3]

    def describe(self):
        if self.mapper is None:
            return "No soportado"
        return MAPPER_NAMES[self.mapper]


# ---------------------------------------------------------------------------
# Parcheo de mappers

def find_sites(data, regs):
    """Busca escrituras a registros de mapper.
    Devuelve [(offset, longitud, direccion, registro_origen)]: registro_origen es
    el opcode LD (HL),r (None para LD (nn),A)."""
    sites = []
    i = 0
    n = len(data)
    while i < n - 2:
        op = data[i]
        if op in (0x32, 0x21):
            addr = data[i + 1] | (data[i + 2] << 8)
            if addr in regs:
                if op == 0x32:
                    sites.append((i, 3, addr, None))
                    i += 3
                    continue
                if i + 3 < n and data[i + 3] in (0x70, 0x71, 0x72, 0x73, 0x77):
                    sites.append((i, 4, addr, data[i + 3]))
                    i += 4
                    continue
        i += 1
    return sites


REF_OPCODES = {0xC3, 0xCD, 0xC2, 0xCA, 0xD2, 0xDA, 0xE2, 0xEA, 0xF2, 0xFA,
               0xC4, 0xCC, 0xD4, 0xDC, 0xE4, 0xEC, 0xF4, 0xFC,
               0x21, 0x11, 0x01, 0x2A, 0x3A, 0x22}


def infer_page(bank_data, candidates, size):
    """Adivina en que direccion se ejecuta un banco contando referencias
    absolutas (CALL/JP/LD rr,nn) que apuntan dentro de cada pagina candidata."""
    counts = dict.fromkeys(candidates, 0)
    d = bank_data
    for i in range(len(d) - 2):
        if d[i] in REF_OPCODES:
            addr = d[i + 1] | (d[i + 2] << 8)
            for p in candidates:
                if p <= addr < p + size:
                    counts[p] += 1
    return max(candidates, key=lambda p: counts[p])


class FreeSpace:
    """Huecos libres (rellenos de FFh o 00h) dentro de un banco."""

    def __init__(self, data, start, size):
        self.data = data
        self.start = start
        self.size = size
        self.runs = []
        self.scan()

    def scan(self):
        d, s, e = self.data, self.start, self.start + self.size
        runs = []
        i = s
        while i < e:
            b = d[i]
            j = i
            while j < e and d[j] == b:
                j += 1
            trailing = j == e
            if b in (0xFF, 0x00) and (j - i >= 32 or (trailing and j - i >= 12)):
                runs.append([i, j, trailing, b])
            i = j
        # Primero el relleno final del banco, luego los huecos mas largos de FFh
        runs.sort(key=lambda r: (not r[2], r[3] != 0xFF, -(r[1] - r[0])))
        self.runs = runs

    def alloc(self, n):
        for r in self.runs:
            if r[2]:
                # relleno final: usar el final del hueco, dejando margen delante
                if r[1] - r[0] >= n + 2:
                    r[1] -= n
                    return r[1]
            elif r[1] - r[0] >= n + 8:
                pos = r[0] + 4
                r[0] = pos + n
                return pos
        return None


class _Asm:
    """Ensamblador minimo: bytes y saltos relativos a etiquetas."""

    def __init__(self):
        self.b = bytearray()
        self.labels = {}
        self.fix = []

    def emit(self, *bs):
        self.b += bytes(bs)

    def word(self, w):
        self.b += bytes([w & 0xFF, (w >> 8) & 0xFF])

    def jr(self, op, label):
        self.b += bytes([op, 0])
        self.fix.append((len(self.b) - 1, label))

    def label(self, name):
        self.labels[name] = len(self.b)

    def code(self):
        for pos, label in self.fix:
            e = self.labels[label] - (pos + 1)
            assert -128 <= e < 128
            self.b[pos] = e & 0xFF
        return bytes(self.b)


def w2_code(addr):
    """Rutina W2 en addr: escribe A en (HL) con el cartucho seleccionado en la
    pagina 2. Los juegos ASCII8/ASCII16 cambian los bancos de 8000h-BFFFh
    escribiendo en 6000h-7FFFh, que esta en la pagina 1; en Konami5 esos
    registros (9000h, B000h) estan en la pagina 2, que puede ser RAM en ese
    momento (por ejemplo durante el INIT). Como el registro original esta en
    la pagina 1, el cartucho esta seleccionado en ella: se copia su slot
    primario a la pagina 2 un momento, con las interrupciones cortadas.
    Conserva todos los registros (F cambia)."""
    a = _Asm()
    a.emit(0xC5, 0x47)                          # PUSH BC / LD B,A
    a.emit(0xED, 0x57)                          # LD A,I (P/V = IFF2)
    a.emit(0xEA)                                # JP PE,ok
    a.word(addr + 9)
    a.emit(0xED, 0x57)                          # otra vez (fallo del Z80 NMOS)
    a.emit(0xF5, 0xF3)                          # ok: PUSH AF / DI
    a.emit(0xDB, 0xA8, 0x4F)                    # IN A,(0A8h) / LD C,A
    a.emit(0xE6, 0x0C, 0x07, 0x07)              # AND 0Ch / RLCA / RLCA
    a.emit(0xA9, 0xE6, 0x30, 0xA9)              # XOR C / AND 30h / XOR C
    a.emit(0xD3, 0xA8)                          # OUT (0A8h),A
    a.emit(0x70)                                # LD (HL),B
    a.emit(0x79, 0xD3, 0xA8)                    # LD A,C / OUT (0A8h),A
    a.emit(0xF1)                                # POP AF
    nei = addr + len(a.b) + 4
    a.emit(0xE2)                                # JP PO,nei
    a.word(nei)
    a.emit(0xFB)                                # EI
    a.emit(0x78, 0xC1, 0xC9)                    # nei: LD A,B / POP BC / RET
    return a.code()


W2_LEN = len(w2_code(0))


def make_stub(out_regs, src, hl_value, mask, base, scc=False, w2=None):
    if w2 is not None:
        return _make_stub_w2(out_regs, src, hl_value, mask, base, w2)
    b = [0xF5]                                  # PUSH AF
    if src is not None and src != 0x77:
        b.append(0x78 + (src & 7))              # LD A,r
    if scc:
        # Si el juego escribe 3Fh (mod 40h) quiere activar el SCC: se escribe tal cual
        b += [0xF5, 0xE6, 0x3F, 0xFE, 0x3F]     # PUSH AF / AND 3Fh / CP 3Fh
        b += [0x20, 0x08]                       # JR NZ,normal
        b += [0xF1, 0x3E, 0x3F]                 # POP AF / LD A,3Fh
        b += [0x32, out_regs[0] & 0xFF, out_regs[0] >> 8]  # LD (reg),A
        b += [0xF1, 0xC9]                       # POP AF / RET
        b.append(0xF1)                          # normal: POP AF
    if mask != 0xFF:
        b += [0xE6, mask]                       # AND mask
    if len(out_regs) == 2:
        b.append(0x87)                          # ADD A,A
    if base & 0xFF:
        b += [0xC6, base & 0xFF]                # ADD A,base
    b += [0x32, out_regs[0] & 0xFF, out_regs[0] >> 8]      # LD (reg),A
    if len(out_regs) == 2:
        b += [0x3C, 0x32, out_regs[1] & 0xFF, out_regs[1] >> 8]  # INC A / LD (reg),A
    b.append(0xF1)                              # POP AF
    if hl_value is not None:
        b += [0x21, hl_value & 0xFF, hl_value >> 8]  # LD HL,nn
    b.append(0xC9)                              # RET
    return bytes(b)


def _make_stub_w2(out_regs, src, hl_value, mask, base, w2):
    b = [0xF5]                                  # PUSH AF
    if src is not None and src != 0x77:
        b.append(0x78 + (src & 7))              # LD A,r
    if mask != 0xFF:
        b += [0xE6, mask]                       # AND mask
    if len(out_regs) == 2:
        b.append(0x87)                          # ADD A,A
    if base & 0xFF:
        b += [0xC6, base & 0xFF]                # ADD A,base
    b.append(0xE5)                              # PUSH HL
    for k, reg in enumerate(out_regs):
        if k:
            b.append(0x3C)                      # INC A
        b += [0x21, reg & 0xFF, reg >> 8]       # LD HL,reg
        b += [0xCD, w2 & 0xFF, w2 >> 8]         # CALL W2
    b.append(0xE1)                              # POP HL
    b.append(0xF1)                              # POP AF
    if hl_value is not None:
        b += [0x21, hl_value & 0xFF, hl_value >> 8]  # LD HL,nn
    b.append(0xC9)                              # RET
    return bytes(b)


# Areas de RAM donde poner las rutinas cuando no caben en la ROM del juego.
# Son zonas del BASIC que los juegos en cartucho no suelen usar; ninguna es
# segura al 100%, por eso se puede elegir por juego.
RAM_AREAS = {
    "PARM1": (0xF6E8, 205),
    "HOOKS": (0xFE03, 175),
    "KBUF": (0xF41F, 318),
    "FNKSTR": (0xF87F, 160),
    "BUF": (0xF55E, 258),
    # Debajo de la RAM que reserva la disquetera; el menu baja HIMEM hasta
    # aqui para que el BASIC no la use (juegos que ejecutan BASIC)
    "HIMEM": (0xDE00 - 318, 318),
}
DEFAULT_RAM_AREA = "PARM1"
RAM_BLOCK_MAX = max(n for _, n in RAM_AREAS.values())
# Orden en que se prueban las areas cuando hay analisis (HOOKS la ultima: la
# BIOS llama a esos ganchos)
AUTO_AREA_ORDER = ["PARM1", "KBUF", "BUF", "FNKSTR", "HOOKS"]   # HIMEM solo si el juego usa el BASIC


def area_used(game, name):
    """Cuantas direcciones del area uso el juego durante el analisis (None = sin analisis)."""
    an = game.analysis
    if not an or not an.get("init") or name not in RAM_AREAS:
        return None
    s, n = RAM_AREAS[name]
    return sum(1 for a in an["ram_access"] if s <= a < s + n)


def _free_runs(name, used):
    s, n = RAM_AREAS[name]
    runs = []
    i = s
    while i < s + n:
        if i in used:
            i += 1
            continue
        j = i
        while j < s + n and j not in used:
            j += 1
        if j - i >= 16:
            runs.append((name, i, j - i))
        i = j
    return sorted(runs, key=lambda r: -r[2])


def uses_basic(game):
    """Cabecera con STATEMENT o DEVICE: el juego se apoya en el BASIC, que usa
    las areas PARM1, BUF, KBUF..."""
    d = game.data
    if game.page2 and len(d) >= 0x4000 and d[0x4000:0x4002] == b"AB":
        d = d[0x4000:]
    if d[0:2] != b"AB" or any(d[6:16]):
        return False            # cabecera con codigo o texto: no es una de estas
    statement = d[4] | (d[5] << 8)
    return 0x4000 <= statement < 0xC000


def ram_candidates(game):
    """Zonas de RAM a probar para las rutinas: [(nombre, inicio, tamano)].
    Con analisis se usan primero los tramos que el juego no toco y despues
    los que solo lee; nunca los que escribe."""
    if game.ram_area:
        return [(game.ram_area,) + RAM_AREAS[game.ram_area]]
    an = game.analysis
    basic = uses_basic(game)
    if not an or not an.get("init"):
        name = "HIMEM" if basic else DEFAULT_RAM_AREA
        return [(name,) + RAM_AREAS[name]]
    # RAM de usuario que el juego no toco (sin la zona del menu E000h-E1FFh)
    user = []
    for start, n in an.get("user_free") or []:
        for a, b in ((start, min(start + n, 0xE000)), (max(start, 0xE200), start + n)):
            if b - a >= 32:
                # en tramos grandes, en el centro: lejos de las variables del
                # BASIC (crecen hacia arriba) y de la pila y las cadenas (abajo)
                size = min(b - a, RAM_BLOCK_MAX)
                user.append(("USER", a + (b - a - size) // 2, size))
    user.sort(key=lambda r: -r[2])
    accessed = set(an["ram_access"])
    written = set(an.get("ram_write", an["ram_access"]))
    out = list(user) if basic else []   # el BASIC usa sus areas: mejor la RAM libre
    for name in AUTO_AREA_ORDER:
        out += _free_runs(name, accessed)
    if not basic:
        out += user
    for name in AUTO_AREA_ORDER:
        if name != "HOOKS":   # leer un gancho es llamarlo
            out += [r for r in _free_runs(name, written) if r not in out]
    return out


def gk_switches_page0(data):
    """Un juego 'generico 8K' que cambia la pagina 4000h no puede usar el modo K4."""
    return bool(find_sites(data, {0x4000: 0}))


def needs_patch(mapper, cart, data=None):
    if mapper in (None, PLAIN):
        return False
    if cart == "yama":
        if mapper == GKONAMI:
            return data is None or gk_switches_page0(data)
        return mapper in (ASCII8, ASCII16, GENERIC16)
    return True


def yama_k4(game):
    return game.mapper == KONAMI4 or (game.mapper == GKONAMI and not gk_switches_page0(game.data))


def _write_insn(d, off):
    """Instruccion de escritura en memoria en d[off].
    Devuelve (inicio, longitud, modo, escrituras) o None. modo: hl, bc, de, nn,
    ix (con prefijo y desplazamiento). escrituras: [(origen, desplazamiento)]
    donde origen es un registro (0-7, 7 = A) o ("n", valor)."""
    op = d[off]
    if off > 0 and d[off - 1] in (0xDD, 0xFD, 0xED) and op not in (0xDD, 0xFD, 0xED):
        # openMSX da la direccion del opcode, despues del prefijo
        if (d[off - 1] != 0xED and (0x70 <= op <= 0x77 and op != 0x76 or op == 0x36)) \
                or (d[off - 1] == 0xED and op in (0x43, 0x53, 0x63)):
            off -= 1
            op = d[off]
    if 0x70 <= op <= 0x77 and op != 0x76:
        return off, 1, ("hl",), [(op & 7, 0)]
    if op == 0x36:
        return off, 2, ("hl",), [(("n", d[off + 1]), 0)]
    if op in (0x02, 0x12):
        return off, 1, ("bc",) if op == 0x02 else ("de",), [(7, 0)]
    nn = d[off + 1] | (d[off + 2] << 8)
    if op == 0x32:
        return off, 3, ("nn", nn), [(7, 0)]
    if op == 0x22:
        return off, 3, ("nn", nn), [(5, 0), (4, 1)]
    if op == 0xED and d[off + 1] in (0x43, 0x53, 0x63):
        nn = d[off + 2] | (d[off + 3] << 8)
        r = (d[off + 1] - 0x43) >> 3          # 0 = BC, 2 = DE, 4 = HL
        return off, 4, ("nn", nn), [(r + 1, 0), (r, 1)]
    if op in (0xDD, 0xFD):
        op2 = d[off + 1]
        disp = d[off + 2]
        disp = disp - 256 if disp >= 128 else disp
        if 0x70 <= op2 <= 0x77 and op2 != 0x76:
            return off, 3, ("ix", op, disp), [(op2 & 7, 0)]
        if op2 == 0x36:
            return off, 4, ("ix", op, disp), [(("n", d[off + 3]), 0)]
    return None


class DynPatcher:
    """Parchea los cambios de banco que encontro el analisis en openMSX y no
    se ven mirando el codigo (direccion calculada, LD (HL),r lejos del LD HL...).

    La instruccion (y las siguientes hasta ocupar 3 bytes) se sustituye por un
    JP a una rutina en RAM que hace la escritura traducida con 'xw', ejecuta las
    instrucciones movidas y vuelve con JP. La pila no se toca."""

    def __init__(self, game, data, ram, ram_start, ram_size, mask, base,
                 static_writes, touched, report, last, get_w2=None):
        self.g = game
        self.d = data
        self.ram = ram
        self.ram_start = ram_start
        self.ram_size = ram_size
        self.mask = mask
        self.base = base
        self.static_writes = static_writes
        self.touched = touched
        self.report = report
        self.last = last
        self.xw = None
        self.get_w2 = get_w2
        self.sixteen = game.mapper in (ASCII16, GENERIC16)
        self.orig = bytes(data)

    def sites(self):
        an = self.g.analysis
        if not an:
            return []
        ranges = SOURCE_RANGES[self.g.mapper]
        out = []
        for st in an.get("sites", []):
            addrs = [int(k) << 11 for k in st["slices"]]
            # registros del mapper original, o escrituras que en el original
            # no hacian nada pero en Konami5 cambiarian de banco (xw las ignora)
            if (not any(lo <= a <= hi for a in addrs for lo, hi, _ in ranges)
                    and not any(is_k5_reg(a) for a in addrs)):
                continue
            if st["off"] in self.static_writes or st["off"] + 1 >= len(self.d):
                continue
            out.append(st)
        return out

    def put(self, code):
        if len(self.ram) + len(code) > self.ram_size:
            if not self.last:
                raise _RamFull()
            return None
        addr = self.ram_start + len(self.ram)
        self.ram += code
        self.report["ram"] += 1
        return addr

    def run(self):
        sites = self.sites()
        if not sites:
            return
        # escrituras por offset de inicio de la instruccion
        self.writes = {}
        found = []
        for st in sites:
            w = _write_insn(self.d, st["off"])
            found.append(w)
            if w:
                self.writes[w[0]] = w
        self.done = set()
        failed = []
        for st, w in zip(sites, found):
            why = self.patch_site(st, w)
            if why:
                failed.append("%06Xh (%04Xh): %s" % (st["off"], st["pc"], why))
        if failed:
            self.report["warnings"].append(
                "Escrituras al mapper vistas en el analisis sin parchear: " + "; ".join(failed[:4])
                + (" ..." if len(failed) > 4 else ""))

    # Rutina comun: escribe A en la direccion HL traduciendo el registro del
    # mapper original al Konami5. Conserva BC, DE, HL; cambia AF.
    # Sale con Z si no es un registro y quien llama debe hacer la escritura
    # normal (se hace fuera, con la pila como la tenia el juego: hay bucles
    # que borran la RAM pasando por la pila).
    def make_xw(self):
        tbl = bytearray(16)                     # registro K5 por tramo de 2KB de 4000h-BFFFh
        for lo, hi, page in SOURCE_RANGES[self.g.mapper]:
            reg = K5_REGS[page * 2 if self.sixteen else page] >> 8
            for k in range(16):
                if lo <= 0x4000 + k * 0x800 <= hi:
                    tbl[k] = reg
        tbl_addr = self.put(bytes(tbl))
        if tbl_addr is None:
            return None
        nunits = len(self.d) // (0x4000 if self.sixteen else BANK)
        scc = self.g.mapper == KONAMI5 and nunits < 64
        w2 = self.get_w2() if self.get_w2 else None
        a = _Asm()
        a.emit(0xE5, 0xC5, 0x47)                # PUSH HL / PUSH BC / LD B,A
        a.emit(0x7C, 0xD6, 0x40, 0xFE, 0x80)    # LD A,H / SUB 40h / CP 80h
        a.jr(0x30, "pass")                      # JR NC,pass
        a.emit(0x0F, 0x0F, 0x0F, 0xE6, 0x0F)    # RRCA x3 / AND 0Fh
        a.emit(0x21)                            # LD HL,tabla
        a.word(tbl_addr)
        a.emit(0x85, 0x6F, 0x8C, 0x95, 0x67)    # HL += A
        a.emit(0x7E, 0xB7)                      # LD A,(HL) / OR A
        a.jr(0x28, "pass")                      # no es un registro
        a.emit(0x67)                            # LD H,A (registro K5)
        if scc:
            # 3Fh (mod 40h) en 9000h activa el SCC: se escribe tal cual
            a.emit(0xFE, 0x90)
            a.jr(0x20, "norm")
            a.emit(0x78, 0xE6, 0x3F, 0xFE, 0x3F)
            a.jr(0x20, "norm")
            a.emit(0x77)
            a.jr(0x18, "done")
        a.label("norm")
        a.emit(0x78)                            # LD A,B
        if self.mask != 0xFF:
            a.emit(0xE6, self.mask)
        if self.sixteen:
            a.emit(0x87)                        # ADD A,A
        if self.base & 0xFF:
            a.emit(0xC6, self.base & 0xFF)
        if w2 is None:
            a.emit(0x77)                        # LD (HL),A
            if self.sixteen:
                a.emit(0x3C, 0x4F, 0x7C, 0xC6, 0x20, 0x67, 0x71)  # INC A / segundo registro
        else:
            a.emit(0xCD)                        # CALL W2 (escribe con la pagina 2 del cartucho)
            a.word(w2)
            if self.sixteen:
                a.emit(0x3C, 0x4F, 0x7C, 0xC6, 0x20, 0x67, 0x79, 0xCD)
                a.word(w2)
        a.label("done")
        a.emit(0xC1, 0xE1, 0xF6, 0x01, 0xC9)    # POP BC / POP HL / OR 1 (NZ) / RET
        a.label("pass")
        # No es un registro del mapper original: escritura normal (Z), salvo
        # que caiga en un registro del Konami5 (NZ: se ignora)
        a.emit(0xC1, 0xE1)                      # POP BC / POP HL
        a.emit(0x7C, 0xD6, 0x40, 0xFE, 0x80)
        a.jr(0x30, "raw")
        a.emit(0x7C, 0xE6, 0x18, 0xFE, 0x10)    # 5000h, 7000h, 9000h, B000h (2KB)
        a.jr(0x28, "skip")
        a.label("raw")
        a.emit(0xAF, 0xC9)                      # XOR A (Z) / RET
        a.label("skip")
        a.emit(0xF6, 0x01, 0xC9)                # OR 1 (NZ) / RET
        return self.put(a.code())

    def abs_targets(self):
        g = self.g
        if g._abs_targets is None:
            d = g.data
            # JP/CALL incondicionales; los condicionales salen mucho en tablas
            # de datos, asi que solo cuentan si un destino aparece 2 veces
            t, cond = set(), {}
            for op in (0xC3, 0xCD, 0xC2, 0xCA, 0xD2, 0xDA, 0xE2, 0xEA, 0xF2, 0xFA,
                       0xC4, 0xCC, 0xD4, 0xDC, 0xE4, 0xEC, 0xF4, 0xFC):
                i = d.find(bytes([op]))
                while 0 <= i < len(d) - 2:
                    tgt = d[i + 1] | (d[i + 2] << 8)
                    if op in (0xC3, 0xCD):
                        t.add(tgt)
                    else:
                        cond[tgt] = cond.get(tgt, 0) + 1
                    i = d.find(bytes([op]), i + 1)
            t |= {k for k, n in cond.items() if n >= 2}
            g._abs_targets = t
        return g._abs_targets

    def patch_site(self, st, w):
        d = self.d
        if w is None:
            return "instruccion no soportada (%02X %02X)" % (d[st["off"]], d[st["off"] + 1])
        start, wlen = w[0], w[1]
        if start in self.done:
            return None                         # ya va dentro del parche de otra escritura
        cpu = st["pc"] - (st["off"] - start)
        # Instrucciones que se mueven a la rutina para dejar sitio al JP
        seq = [(start, None, w)]
        pos, addr, terminal = start + wlen, cpu + wlen, False
        while pos - start < 3 and not terminal:
            if pos >= len(d) - 4:
                return "fin de la ROM"
            if pos in self.writes:
                ww = self.writes[pos]
                seq.append((pos, None, ww))
                pos += ww[1]
                addr += ww[1]
                continue
            ins = z80.decode(d, pos, addr)
            if ins.kind == z80.BAD:
                return "instruccion siguiente no reubicable"
            seq.append((pos, ins, None))
            pos += ins.length
            addr += ins.length
            terminal = ins.kind in (z80.JP, z80.RET, z80.TERM)
        if pos - start < 3:
            return "no hay sitio para el salto"
        if any(i in self.touched for i in range(start, pos)):
            return "se solapa con otro parche"
        unit = 0x4000 if self.sixteen else BANK
        if start // unit != (pos - 1) // unit:
            return "cruza un limite de banco"
        # Un salto al principio de una de las instrucciones movidas caeria en los NOP
        inner = {cpu + (p - start) for p, _, _ in seq[1:]}
        if inner:
            lo = max(0, start - 130)
            near = z80.branch_targets(d, lo, min(len(d), pos + 130), cpu - (start - lo))
            if inner & (self.abs_targets() | near):
                return "hay saltos al medio de las instrucciones"
        if self.xw is None:
            self.xw = self.make_xw()
            if self.xw is None:
                return "no cabe en RAM"

        a = _Asm()
        for p, ins, ww in seq:
            if ww:
                self.emit_write(a, ww)
                continue
            if ins.kind == z80.JP:
                a.emit(0xC3)
                a.word(ins.target)
            elif ins.kind == z80.JPCC:
                a.emit(0xC2 + 8 * ins.cc)
                a.word(ins.target)
            elif ins.kind == z80.DJNZ:
                a.emit(0x10, 0x02, 0x18, 0x03, 0xC3)
                a.word(ins.target)
            else:
                a.emit(*d[p:p + ins.length])
        if not terminal:
            a.emit(0xC3)
            a.word(addr)
        stub = self.put(a.code())
        if stub is None:
            return "no cabe en RAM"
        d[start:start + 3] = bytes([0xC3, stub & 0xFF, stub >> 8])
        d[start + 3:pos] = bytes(pos - start - 3)
        self.touched.update(range(start, pos))
        self.done.update(p for p, ins, ww in seq if ww)
        self.report["dyn"] += 1
        return None

    def emit_write(self, a, w):
        """Codigo que hace la escritura w traducida (conserva todos los registros)."""
        start, wlen, mode, writes = w
        kind = mode[0]
        n = len(a.labels)
        for k, (src, delta) in enumerate(writes):
            a.emit(0xF5)                        # PUSH AF
            if kind != "hl":
                a.emit(0xE5)                    # PUSH HL
            if isinstance(src, tuple):
                a.emit(0x3E, src[1])            # LD A,n
            elif src != 7:
                a.emit(0x78 + src)              # LD A,r
            if kind == "bc":
                a.emit(0x60, 0x69)
            elif kind == "de":
                a.emit(0x62, 0x6B)
            elif kind == "nn":
                a.emit(0x21)
                a.word(mode[1] + delta)
            elif kind == "ix":
                a.emit(mode[1], 0xE5, 0xE1, 0xD5, 0x11)  # PUSH IX / POP HL / PUSH DE / LD DE,d
                a.word(mode[2])
                a.emit(0x19, 0xD1)              # ADD HL,DE / POP DE
            a.emit(0xCD)
            a.word(self.xw)
            if kind != "hl":
                a.emit(0xE1)                    # POP HL (no cambia los flags)
            if len(writes) == 1:
                # Z: escritura normal con la instruccion original
                a.jr(0x28, "raw%d" % n)
                a.emit(0xF1)
                a.jr(0x18, "next%d" % n)
                a.label("raw%d" % n)
                a.emit(0xF1)
                a.emit(*bytes(self.orig[start:start + wlen]))
                a.label("next%d" % n)
            else:
                # LD (nn),rr: el valor sale de un registro que no es A
                a.jr(0x20, "skip%d_%d" % (n, k))
                a.emit(0x78 + src, 0x32)        # LD A,r / LD (nn),A
                a.word(mode[1] + delta)
                a.label("skip%d_%d" % (n, k))
                a.emit(0xF1)                    # POP AF


def is_k5_reg(addr):
    return 0x4000 <= addr < 0xC000 and (addr & 0x1800) == 0x1000


def _veto_ram_sites(game, sites, report):
    """Quita los 'cambios de banco' que el analisis vio escribir en RAM (juegos
    que se copian a la RAM de 4000h-BFFFh y tienen variables ahi). Si una
    direccion solo se vio escribir en RAM, se quitan todos sus sitios."""
    an = game.analysis
    if not an:
        return sites
    ram_w = set(an.get("ram_sites", []))
    map_w = {s["off"] for s in an.get("sites", [])}
    to_ram, to_map = set(), set()
    for off, ln, addr, src in sites:
        w = off + 3 if ln == 4 else off
        if w in ram_w:
            to_ram.add(addr)
        if w in map_w:
            to_map.add(addr)
    bad = to_ram - to_map
    # En las ROMs que arrancan el BASIC, con analisis, lo que no parece codigo
    # y nunca se vio ejecutar es probablemente un dato (p. ej. la imagen de
    # disco de Sonyc)
    if an.get("init") and uses_basic(game):
        data_like = [s for s in sites if (s[0] + 3 if s[1] == 4 else s[0]) not in map_w
                     and (s[0] + 3 if s[1] == 4 else s[0]) not in ram_w and not _code_like(game.data, s[0])]
        if data_like:
            report["warnings"].append("%d posible(s) cambio(s) de banco que parecen datos y no se vieron en el "
                                      "analisis: no se parchean" % len(data_like))
            sites = [s for s in sites if s not in data_like]
    # Juego con RAM en las paginas del cartucho: las direcciones no estandar
    # (deducidas mirando el codigo) solo se aceptan si se vieron cambiar de banco
    canon = SOURCE_REGS.get(game.mapper, {})
    seen_map = to_map
    bad |= {s[2] for s in sites if s[2] not in canon and s[2] not in seen_map}
    if not bad:
        return sites
    keep = [s for s in sites if s[2] not in bad]
    report["warnings"].append("El analisis vio que %s es RAM en este juego: %d escritura(s) no se parchean" % (
        ", ".join("%04Xh" % a for a in sorted(bad)), len(sites) - len(keep)))
    return keep


def _adjust(data, cands, d):
    """Cambia bytes de cands para que la suma baje d (d < 0: suba). Devuelve lo que falte."""
    for pos in cands:
        if not d:
            break
        b = data[pos]
        k = min(d, b) if d > 0 else -min(-d, 255 - b)
        data[pos] = b - k
        d -= k
    return d


def keep_checksums(orig, data, report):
    """Hay juegos que suman los bytes de su ROM para detectar cambios (Young
    Artist reinicia el MSX si la suma de 4000h-7FFFh no da 0). Para que los
    parches no se noten, en cada banco de 8KB se ajustan bytes libres (huecos
    de FFh/00h) hasta que la suma de sus bytes sea la original."""
    failed = []
    for start in range(0, len(data), BANK):
        d = sum(data[start:start + BANK]) - sum(orig[start:start + BANK])
        if d == 0:
            continue
        fs = FreeSpace(data, start, BANK)
        cands = []
        while len(cands) < 64:
            pos = fs.alloc(1)
            if pos is None:
                break
            cands.append(pos)
        # ultimo recurso: bytes reservados de la cabecera (0Ah-0Fh), que la BIOS no lee
        if data[start:start + 2] == b"AB":
            cands += [start + i for i in range(0x0A, 0x10) if data[start + i] == orig[start + i] == 0]
        down = sum(data[p] for p in cands)          # cuanto puede bajar la suma
        up = sum(255 - data[p] for p in cands)      # cuanto puede subir
        if -up <= d <= down:
            d = _adjust(data, cands, d)
        elif d % 256 <= down:
            # sin sitio para la suma exacta: al menos la suma modulo 256
            d = _adjust(data, cands, d % 256) + d - d % 256
            d = 0 if d % 256 == 0 else d
        elif 256 - d % 256 <= up:
            d = _adjust(data, cands, d % 256 - 256) + d - d % 256 + 256
            d = 0 if d % 256 == 0 else d
        if d:
            failed.append(start // BANK)
    if failed:
        report["warnings"].append("No se pudo mantener la suma de los bancos %s (falla si el juego "
                                  "comprueba su ROM)" % ", ".join(map(str, failed[:8])))


class _RamFull(Exception):
    pass


def patch_game(game, cart, base, ram_area=None):
    """Prepara el juego para colocarlo en el banco 'base'.
    Devuelve (datos, informe, bloque_ram) donde bloque_ram es None o
    (direccion_ram, bytes) con las rutinas que el menu copia a RAM."""
    if ram_area:
        cands = [(ram_area,) + RAM_AREAS[ram_area]]
    else:
        cands = ram_candidates(game)
    warn = None
    rom_first = False
    if not cands and uses_basic(game):
        # Juegos en BASIC: llenan la RAM con variables pero no la borran
        # entera como algunos juegos en codigo maquina; PARM1 suele aguantar
        warn = None
        cands = [(DEFAULT_RAM_AREA,) + RAM_AREAS[DEFAULT_RAM_AREA]]
    if not cands:
        # El juego escribe en todas las areas (borra la RAM...): rutinas en la ROM
        warn = "El juego escribe en todas las areas de RAM candidatas; las rutinas que no caben en la ROM van a %s" % DEFAULT_RAM_AREA
        cands = [(DEFAULT_RAM_AREA,) + RAM_AREAS[DEFAULT_RAM_AREA]]
        rom_first = True
    for k, area in enumerate(cands):
        try:
            data, report, ram = _patch_game(game, cart, base, area, k == len(cands) - 1, rom_first)
        except _RamFull:
            continue
        report["area"] = area[0]
        if warn and ram:
            report["errors"].append("Probablemente no funcione: hay rutinas en RAM y el juego "
                                    "escribe en todas las areas de RAM candidatas")
        elif warn:
            report["warnings"].append(warn)
        used = area_used(game, area[0])
        if ram and used and game.ram_area:
            report["warnings"].append("El analisis indica que el juego usa %d bytes del area %s" % (used, area[0]))
        return data, report, ram


def _patch_game(game, cart, base, area, last, rom_first=False):
    data = bytearray(game.data)
    report = {"sites": 0, "stubs": 0, "ram": 0, "dyn": 0, "warnings": [], "errors": []}
    m = game.mapper
    if not needs_patch(m, cart, data):
        return bytes(data), report, None
    yama = cart == "yama"

    regs = mapper_regs(data, m)
    sites = find_sites(data, regs)
    sites = _veto_ram_sites(game, sites, report)
    report["sites"] = len(sites)
    if not sites:
        report["warnings"].append("No se encontraron cambios de banco que parchear")

    sixteen = m in (ASCII16, GENERIC16)
    unit = 0x4000 if sixteen else BANK
    nunits = len(data) // unit
    # como openMSX: tamanos que no son potencia de 2 usan la mascara de la siguiente
    p2 = 1 << max(0, (nunits - 1).bit_length())
    mask = p2 - 1 if p2 <= 256 else 0xFF
    stub_base = 0 if yama else base
    pages_all = [0x4000, 0x8000] if sixteen else [0x4000, 0x6000, 0x8000, 0xA000]
    area_name, ram_start, ram_size = area
    ram = bytearray()
    touched = set()
    static_writes = set()
    for off, ln, addr, src in sites:
        touched.update(range(off, off + ln))
        static_writes.add(off + ln - 1 if ln == 4 else off)
    # Los registros de las paginas 8000h/A000h del Konami5 estan en la pagina 2;
    # en ASCII8/ASCII16 los originales estan en la pagina 1 (ver w2_code)
    use_w2 = m in (ASCII8, ASCII16)
    w2_ram = []

    def get_w2_ram(last_resort=True):
        if not w2_ram:
            if len(ram) + W2_LEN > ram_size:
                if last_resort and not last:
                    raise _RamFull()
                return None
            w2_ram.append(ram_start + len(ram))
            ram.extend(w2_code(ram_start + len(ram)))
            report["ram"] += 1
        return w2_ram[0]

    dyn = DynPatcher(game, data, ram, ram_start, ram_size, mask, stub_base,
                     static_writes, touched, report, last, get_w2_ram if use_w2 else None)

    if yama and m in (ASCII8, GKONAMI):
        # El hardware suma el offset: basta con cambiar la direccion del
        # registro, salvo los ASCII8 de 8000h/A000h (ver w2_code)
        rest = []
        for site in sites:
            off, ln, addr, src = site
            if m == ASCII8 and regs[addr] >= 2:
                rest.append(site)
                continue
            new = K5_REGS[regs[addr]]
            data[off + 1] = new & 0xFF
            data[off + 2] = new >> 8
        sites = rest

    ram_stubs = {}
    spaces = {}
    rom_stubs = {}
    page_cache = {}

    def space(u):
        if u not in spaces:
            spaces[u] = FreeSpace(data, u * unit, unit)
        return spaces[u]

    w2_rom = {}

    def get_w2_rom(u, page):
        k = (u, page)
        if k not in w2_rom:
            pos = space(u).alloc(W2_LEN)
            if pos is None:
                return None
            addr = page + (pos - u * unit)
            data[pos:pos + W2_LEN] = w2_code(addr)
            touched.update(range(pos, pos + W2_LEN))
            report["stubs"] += 1
            w2_rom[k] = addr
        return w2_rom[k]

    def ram_call(stub, last_resort):
        if stub not in ram_stubs:
            if len(ram) + len(stub) > ram_size:
                if last_resort:
                    if not last:
                        raise _RamFull()
                    report["errors"].append("No caben mas rutinas en el area de RAM %s" % area_name)
                return None
            ram_stubs[stub] = ram_start + len(ram)
            ram.extend(stub)
            report["ram"] += 1
        return ram_stubs[stub]

    def caller_page(u, cands):
        if m == KONAMI4 and u == 0:
            return 0x4000
        if u == 0 and 0x4000 in cands:
            return 0x4000
        key = (u, tuple(cands))
        if key not in page_cache:
            page_cache[key] = infer_page(data[u * unit:(u + 1) * unit], cands, unit)
        return page_cache[key]

    for off, ln, addr, src in sites:
        u = off // unit
        if (off + ln - 1) // unit != u:
            report["warnings"].append("Cambio de banco en %06Xh cruza un limite de banco: ignorado" % off)
            continue
        tpage = regs[addr]
        if sixteen:
            out_regs = [K5_REGS[tpage * 2], K5_REGS[tpage * 2 + 1]]
        else:
            out_regs = [K5_REGS[tpage]]
        target_addr = pages_all[tpage]
        hl_value = addr if src is not None else None
        scc = m == KONAMI5 and tpage == 2 and nunits < 64
        need_w2 = use_w2 and out_regs[0] >= 0x8000

        def stub_for(w2):
            return make_stub(out_regs, src, hl_value, mask, stub_base, scc, w2)

        call = None
        # 1) En RAM (comun para todo el juego): vale aunque el juego copie a RAM
        #    el codigo que cambia de banco
        if game.stub_place == "ram" and not rom_first:
            w2 = get_w2_ram(False) if need_w2 else None
            if w2 is not None or not need_w2:
                call = ram_call(stub_for(w2), False)
        # 2) En la ROM, dentro del mismo banco que hace la llamada
        if call is None:
            cands = [p for p in pages_all if p != target_addr]
            page = caller_page(u, cands)
            w2 = get_w2_rom(u, page) if need_w2 else None
            stub = stub_for(w2) if (w2 is not None or not need_w2) else None
            k = (u, stub)
            pos = rom_stubs.get(k)
            if pos is None and stub is not None:
                pos = space(u).alloc(len(stub))
                if pos is not None:
                    data[pos:pos + len(stub)] = stub
                    touched.update(range(pos, pos + len(stub)))
                    rom_stubs[k] = pos
                    report["stubs"] += 1
            if pos is not None:
                call = page + (pos - u * unit)
        # 3) En RAM como ultimo recurso
        if call is None:
            w2 = get_w2_ram(True) if need_w2 else None
            if w2 is not None or not need_w2:
                call = ram_call(stub_for(w2), True)
            else:
                report["errors"].append("No caben mas rutinas en el area de RAM %s" % area_name)
        if call is None:
            continue
        data[off:off + 3] = bytes([0xCD, call & 0xFF, call >> 8])
        if ln == 4:
            data[off + 3] = 0x00  # NOP
    dyn.run()
    if ram:
        report["warnings"].append("%d rutina(s) en RAM (%s, %04Xh-%04Xh)" % (
            report["ram"], area_name, ram_start, ram_start + len(ram) - 1))
    keep_checksums(game.data, data, report)
    return bytes(data), report, ((ram_start, bytes(ram)) if ram else None)


# ---------------------------------------------------------------------------
# Construccion de la imagen

def menu_layout(games, cart):
    """Bancos del menu: (bancos_tabla, bancos_rutinas, total)."""
    n = len(games)
    table = max(1, -(-n // ENTRIES_PER_BANK))
    patched = sum(1 for g in games if needs_patch(g.mapper, cart, g.data))
    per_bank = BANK // RAM_BLOCK_MAX
    stubs = -(-patched // per_bank)
    return table, stubs, 1 + table + stubs


def menu_banks(games, cart="k5"):
    return menu_layout(games, cart)[2]


RISKY_MSG = ("Colocado donde un banco 63 (mod 64) puede activar el SCC sin querer; "
             "si falla, deja mas espacio libre en el cartucho")


def allocate(games, cart, size_kb, risky=None):
    """Asigna a cada juego su banco base. Devuelve lista de bases (None = no cabe).
    Si se pasa un conjunto 'risky', se anaden los indices de los juegos que
    solo cupieron en una posicion donde pueden activar el SCC sin querer."""
    total = size_kb * 1024 // BANK
    first = menu_banks(games, cart)
    used = [False] * total
    for b in range(min(first, total)):
        used[b] = True
    k5 = cart == "k5"
    limit = min(total, 256) if k5 else total
    order = sorted(range(len(games)), key=lambda i: -games[i].nbanks)
    bases = [None] * len(games)

    def fits(b, n):
        return b + n <= limit and not any(used[b:b + n])

    def preferred(g, b):
        # El SCC se activa al poner un banco 3Fh (mod 40h) en 8000h-9FFFh.
        n = g.nbanks
        if n >= 64 or (g.mapper == KONAMI5 and not k5):
            # Misma alineacion que en su cartucho original: el banco 3Fh del
            # juego coincide con un banco 3Fh (mod 40h) del cartucho. En
            # Yamanooto el hardware real mira el valor escrito pero openMSX
            # 21.0 mira el banco final; asi funciona en los dos.
            return b % 64 == 0
        # evitar que un banco 63 mod 64 aparezca en 8000h (activaria el SCC)
        if g.mapper == PLAIN:
            idx = {g.rel[2]}
        else:
            idx = set(range(n))
        return all((b + i) % 64 != 63 for i in idx)

    for i in order:
        g = games[i]
        n = g.nbanks
        if n == 0:
            continue
        cand = [b for b in range(first, limit - n + 1) if fits(b, n)]
        good = [b for b in cand if preferred(g, b)]
        pick = (good or cand or [None])[0]
        if pick is not None and not good and risky is not None:
            risky.add(i)
        if pick is not None:
            bases[i] = pick
            for b in range(pick, pick + n):
                used[b] = True
    return bases


def center(text, width=32):
    text = ascii_name(text).upper()[:width]
    pad = (width - len(text)) // 2
    return (" " * pad + text).ljust(width)


def build(games, cart, size_kb, title="MSX MULTIROM", menu_bin=MENU_BIN):
    """Construye la imagen. Devuelve (bytes, informe)."""
    if cart not in CARTS:
        raise ValueError("Cartucho desconocido: %s" % cart)
    games = [g for g in games if not g.error]
    if not games:
        raise ValueError("No hay juegos validos")
    total = size_kb * 1024 // BANK
    image = bytearray(b"\xFF" * (total * BANK))
    menu = open(menu_bin, "rb").read()
    image[0:len(menu)] = menu
    table_banks, stub_banks, _ = menu_layout(games, cart)
    table_bank = 1
    stub_bank = 1 + table_banks
    stub_pos = 0

    risky = set()
    rep_of = {}
    bases = allocate(games, cart, size_kb, risky)
    report = []
    placed = []
    for gi, (g, b) in enumerate(zip(games, bases)):
        if b is None:
            report.append((g, None, {"errors": ["No cabe en el cartucho"], "warnings": [],
                                     "sites": 0, "stubs": 0, "ram": 0}))
            continue
        pdata, rep, ram = patch_game(g, cart, b)
        if gi in risky:
            rep["warnings"].insert(0, RISKY_MSG)
        image[b * BANK:b * BANK + len(pdata)] = pdata
        stub_ref = (0, 0, 0, 0)
        if ram:
            dst, block = ram
            if stub_pos + len(block) > BANK:
                stub_bank += 1
                stub_pos = 0
            off = stub_bank * BANK + stub_pos
            image[off:off + len(block)] = block
            stub_ref = (stub_bank, 0x6000 + stub_pos, len(block), dst)
            stub_pos += len(block)
        placed.append((g, b, stub_ref))
        report.append((g, b, rep))
        rep_of[id(g)] = rep

    # Tabla de juegos
    image[table_bank * BANK:(table_bank + table_banks) * BANK] = bytes(table_banks * BANK)
    for idx, (g, b, stub_ref) in enumerate(placed):
        e = bytearray(ENTRY_SIZE)
        name = ascii_name(g.title)[:NAME_LEN].ljust(NAME_LEN)
        e[0:NAME_LEN] = name.encode("ascii")
        e[30] = g.nbanks & 0xFF
        e[31] = g.nbanks >> 8
        cfgr = 0
        if cart == "k5":
            regs = [(b + r) & 0xFF for r in g.rel]
            offr = 0
        else:
            regs = list(g.rel)
            offr = b >> 2
            cfgr = (b & 3) << 4
            if yama_k4(g):
                cfgr |= Y_K4
            elif g.mapper == PLAIN:
                cfgr |= Y_MDIS
        e[32:36] = bytes(regs)
        e[36] = offr
        e[37] = cfgr
        e[38] = 1 if g.page2 else 0
        if stub_ref[2] and rep_of[id(g)].get("area") == "HIMEM":
            e[38] |= 2          # el menu baja HIMEM para reservar las rutinas
        e[39] = MENU_MAPPER_ID[g.mapper]
        sb, src, ln, dst = stub_ref
        e[40] = sb
        e[42:44] = src.to_bytes(2, "little")
        e[44:46] = ln.to_bytes(2, "little")
        e[46:48] = dst.to_bytes(2, "little")
        pos = (table_bank + idx // ENTRIES_PER_BANK) * BANK + (idx % ENTRIES_PER_BANK) * ENTRY_SIZE
        image[pos:pos + ENTRY_SIZE] = e
    # Configuracion del menu
    image[0x20] = CARTS[cart]["type"]
    image[0x21] = len(placed) & 0xFF
    image[0x22] = len(placed) >> 8
    image[0x23] = table_bank
    image[0x30:0x50] = center(title).encode("ascii")
    return bytes(image), report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generador de MultiROM MSX (Konami5 / Yamanooto)")
    ap.add_argument("--cart", choices=sorted(CARTS), default="k5")
    ap.add_argument("--size", type=int, default=512, help="Tamano en KB (512, 2048, 4096, 8192)")
    ap.add_argument("--title", default="MSX MULTIROM")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("roms", nargs="+", help="ROMs (opcionalmente fichero:MAPPER, ej. juego.rom:ASCII8)")
    args = ap.parse_args(argv)
    names = {"G16": GENERIC16, "PLAIN": PLAIN, "K4": KONAMI4, "KONAMI4": KONAMI4, "K5": KONAMI5, "KONAMI5": KONAMI5,
             "ASCII8": ASCII8, "A8": ASCII8, "ASCII16": ASCII16, "A16": ASCII16, "GK": GKONAMI}
    games = []
    for spec in args.roms:
        path, _, mt = spec.partition(":") if not os.path.exists(spec) else (spec, "", "")
        g = Game(path)
        if mt:
            g.set_mapper(names[mt.upper()])
        games.append(g)
        print("%-30s %-20s %5dKB %s%s" % (g.title, g.describe(), g.size_kb,
                                          g.error or "", "; ".join(g.warnings + g.prep_warnings)))
    image, report = build(games, args.cart, args.size, args.title)
    with open(args.output, "wb") as f:
        f.write(image)
    for g, b, rep in report:
        print("  %-30s banco %s  parches=%d rutinas ROM=%d RAM=%d %s" % (
            g.title, b, rep["sites"], rep["stubs"], rep["ram"], "; ".join(rep["errors"] + rep["warnings"])))
    print("Escrito %s (%d KB)" % (args.output, len(image) // 1024))


if __name__ == "__main__":
    sys.exit(main())
