# Copyright (C) 2026 Germán Díaz / MSX Calamar
# SPDX-License-Identifier: GPL-2.0-or-later
"""Analisis dinamico de un juego en openMSX.

Ejecuta la ROM original (con su mapper) y registra:
  - cada instruccion que escribe en 4000h-BFFFh (direccion de la instruccion,
    banco en que estaba y zonas de 2KB a las que escribe). Asi se encuentran
    los cambios de banco que no se ven mirando el codigo (direccion calculada,
    Hydlide 3) o que se hacen desde RAM.
  - que direcciones de las areas de RAM candidatas (multirom.RAM_AREAS) lee o
    escribe el juego despues de arrancar, para elegir donde poner las rutinas.

El resultado se guarda por SHA1 en ~/.msx_multirom/analisis y se suma a los
analisis anteriores del mismo juego (automatico + jugando).
"""
import json
import os
import subprocess
import tempfile

import multirom as mr

CACHE_DIR = mr.ANALYSIS_DIR
ROMTYPES = {mr.KONAMI4: "Konami", mr.KONAMI5: "KonamiSCC", mr.ASCII8: "ASCII8",
            mr.ASCII16: "ASCII16", mr.GKONAMI: "8kB", mr.GENERIC16: "16kB", mr.PLAIN: None}
VERSION = mr.ANALYSIS_VERSION
CTX = 8          # bytes que se guardan antes de la instruccion
CTX_LEN = 24     # bytes de contexto en total

# Teclas que se pulsan en el modo automatico (fila, bit de la matriz):
# espacio, return, cursores, 1, F1 ... para pasar pantallas de titulo y menus
AUTO_KEYS = [(8, 0x01), (7, 0x80), (8, 0x01), (8, 0x40), (8, 0x01), (8, 0x80),
             (8, 0x01), (8, 0x20), (0, 0x02), (8, 0x10), (8, 0x01), (6, 0x20)]

TCL = r"""
catch {set save_settings_on_exit false}
set ::out [open {%(out)s} w]
fconfigure $::out -buffering line
set ::rb ""
foreach n [machine_info device] {
  if {[catch {set inf [machine_info device $n]}]} continue
  if {[dict exists $inf actualSHA1] && [dict get $inf actualSHA1] eq "%(sha1)s"} { set ::rb "$n romblocks" }
}
puts $::out "R $::rb"
set ::seen [dict create]
set ::acc [dict create]
set ::started 0
set ::cslot ""
proc ::mw {} {
  if {!$::started} return
  set pc [reg pc]
  if {$pc < 8} return
  set b -1
  if {$::rb ne "" && $pc >= 0x4000 && $pc < 0xC000 && [get_selected_slot [expr {$pc >> 14}]] eq $::cslot} {
    set b [debug read $::rb $pc]
  }
  set k "$pc $b"
  set s [expr {$::wp_last_address >> 11}]
  # S = escritura al cartucho, Q = a otra cosa (RAM en esa pagina)
  set t [expr {[get_selected_slot [expr {$::wp_last_address >> 14}]] eq $::cslot ? "S" : "Q"}]
  if {![dict exists $::seen $k]} {
    dict set ::seen $k [dict create]
    binary scan [debug read_block memory [expr {$pc - %(ctx)d}] %(ctxlen)d] H* hx
    puts $::out "W $pc $b $hx"
  }
  if {![dict exists $::seen $k $t$s]} {
    dict set ::seen $k $t$s 1
    puts $::out "$t $pc $b $s $::wp_last_value"
  }
}
proc ::ra {kind} {
  if {!$::started} return
  set a $::wp_last_address
  if {![dict exists $::acc $kind$a]} { dict set ::acc $kind$a 1; puts $::out "A $kind $a [reg pc]" }
}
debug set_watchpoint write_mem {0x4000 0xBFFF} {} ::mw
%(areas)s
# RAM de usuario (C000h hasta la pila): se rellena al arrancar el juego y al
# final se mira que bytes siguen igual (el juego no los escribio)
set ::filltop 0
proc ::fillram {} {
  if {%(fill)d < 0} return
  set top [expr {[reg sp] - 0x200}]
  set hm [peek16 0xFC4A]
  if {$hm < $top} { set top $hm }
  if {$top > 0xF380} { set top 0xF380 }
  if {$top <= 0xC000} return
  set ::filltop $top
  debug write_block memory 0xC000 [string repeat [binary format c %(fill)d] [expr {$top - 0xC000}]]
}
proc ::dumpram {} {
  if {$::filltop == 0} return
  binary scan [debug read_block memory 0xC000 [expr {$::filltop - 0xC000}]] H* hx
  puts $::out "M %(fill)d $hx"
}
proc ::tick {} { ::dumpram; after time 5 ::tick }
debug set_bp %(init)d {[debug read memory %(hdr)d] == 0x41 && [debug read memory %(hdr1)d] == 0x42} {
  if {!$::started} {
    set ::cslot [get_selected_slot %(hpage)d]; set ::started 1
    ::fillram
    puts $::out "I [machine_info time] $::cslot"
    %(tick)s
  }
}
after time 20 { if {!$::started} { set ::cslot [get_selected_slot 1]; set ::started 1; puts $::out "N" } }
set ::keys {%(keys)s}
proc ::press {i} {
  set k [lindex $::keys [expr {$i %% [llength $::keys]}]]
  keymatrixdown {*}$k
  after time 0.12 [list keymatrixup {*}$k]
  after time %(kdelay)s [list ::press [expr {$i + 1}]]
}
%(mode)s
"""


def cache_path(sha1):
    return os.path.join(CACHE_DIR, sha1 + ".json")


def load(sha1):
    return mr.load_analysis(sha1)


def save(sha1, result):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path(sha1), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)


def forget(sha1):
    try:
        os.remove(cache_path(sha1))
    except OSError:
        pass


def _header(raw):
    """(direccion de la cabecera, INIT) tal como se ve la ROM original."""
    for off in range(0, min(len(raw), 0x10000), 0x4000):
        if raw[off:off + 2] == b"AB":
            init = raw[off + 2] | (raw[off + 3] << 8)
            if 0x4000 <= init < 0xC000:
                return init & 0xC000, init
    return 0x4000, raw[2] | (raw[3] << 8)


def build_script(game, out, seconds, interactive, fill=-1):
    hdr, init = _header(game.raw)
    areas = []
    for start, size in mr.RAM_AREAS.values():
        rng = "{0x%04X 0x%04X}" % (start, start + size - 1)
        areas.append("debug set_watchpoint write_mem %s {} {::ra w}" % rng)
        areas.append("debug set_watchpoint read_mem %s {} {::ra r}" % rng)
    if interactive:
        mode = "after time 1 {}"
    else:
        mode = ("set throttle off\ncatch {set renderer none}\nafter time 5 {::press 0}\n"
                "after time %.1f {::dumpram; puts $::out E; close $::out; exit}" % seconds)
    return TCL % {
        "out": out.replace("\\", "/"), "sha1": game.sha1, "ctx": CTX, "ctxlen": CTX_LEN,
        "areas": "\n".join(areas), "init": init, "hdr": hdr, "hdr1": hdr + 1, "hpage": hdr >> 14,
        "keys": " ".join("{%d %d}" % k for k in AUTO_KEYS), "kdelay": "1.3",
        "mode": mode, "fill": fill, "tick": "after time 5 ::tick" if interactive else "",
    }


def run(game, openmsx, machine="C-BIOS_MSX2", seconds=90, interactive=False):
    """Analiza el juego. Devuelve el analisis (ya sumado al guardado).
    El modo automatico ejecuta el juego dos veces, con la RAM de usuario
    rellena de 00h y de FFh: un byte esta libre si acaba igual en las dos."""
    if game.mapper is None:
        raise mr.RomError("Mapper no soportado")
    if interactive:
        lines = _run_once(game, openmsx, machine, seconds, True, 0xFF)
    else:
        lines = _run_once(game, openmsx, machine, seconds, False, 0x00)
        lines += [ln for ln in _run_once(game, openmsx, machine, seconds, False, 0xFF)
                  if ln.startswith("M ")]
    result = parse(game, lines, machine, 0 if interactive else seconds)
    old = load(game.sha1)
    if old:
        result = merge(old, result)
    save(game.sha1, result)
    return result


def _run_once(game, openmsx, machine, seconds, interactive, fill):
    tmp = tempfile.mkdtemp(prefix="msxan_")
    rom = os.path.join(tmp, "juego.rom")
    out = os.path.join(tmp, "traza.txt")
    tcl = os.path.join(tmp, "analisis.tcl")
    with open(rom, "wb") as f:
        f.write(game.raw)
    with open(tcl, "w", encoding="utf-8") as f:
        f.write(build_script(game, out, seconds, interactive, fill))
    cmd = [openmsx, "-machine", machine, "-cart", rom]
    rt = ROMTYPES.get(game.mapper)
    if rt:
        cmd += ["-romtype", rt]
    cmd += ["-script", tcl]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(cmd, timeout=None if interactive else max(120, seconds * 3),
                   capture_output=True, creationflags=flags)
    if not os.path.exists(out):
        raise mr.RomError("openMSX no genero la traza")
    with open(out, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def _user_free(lines):
    """Tramos [inicio, longitud] de C000h.. que acabaron con el valor de relleno
    en todas las pasadas (la ultima captura de cada una)."""
    dumps = {}
    for ln in lines:
        if ln.startswith("M "):
            _, fill, hx = ln.split(" ", 2)
            dumps[int(fill)] = bytes.fromhex(hx)
    if not dumps:
        return None
    n = min(len(d) for d in dumps.values())
    free = [all(d[i] == f for f, d in dumps.items()) for i in range(n)]
    runs, i = [], 0
    while i < n:
        if free[i]:
            j = i
            while j < n and free[j]:
                j += 1
            if j - i >= 32:
                runs.append([0xC000 + i, j - i])
            i = j
        else:
            i += 1
    return runs


def parse(game, lines, machine, seconds):
    raw = game.raw
    ctxs, slices, accesses, writes, qslices = {}, {}, set(), set(), {}
    init = False
    for ln in lines:
        p = ln.split()
        if not p:
            continue
        if p[0] == "W" and len(p) == 4:
            ctxs[(int(p[1]), int(p[2]))] = bytes.fromhex(p[3])
        elif p[0] == "Q" and len(p) >= 5:
            qslices.setdefault((int(p[1]), int(p[2])), {})[int(p[3])] = int(p[4])
        elif p[0] == "S" and len(p) >= 5:
            slices.setdefault((int(p[1]), int(p[2])), {})[int(p[3])] = int(p[4])
        elif p[0] == "A" and len(p) >= 3:
            accesses.add(int(p[2]))
            if p[1] == "w":
                writes.add(int(p[2]))
        elif p[0] == "I":
            init = True
    sites = {}
    unresolved = 0
    for key, sl in slices.items():
        pc, blk = key
        ctx = ctxs.get(key)
        if ctx is None:
            continue
        off, in_rom = locate(raw, pc, blk, ctx)
        if off is None:
            # codigo que no esta en la ROM (BIOS, o generado por el juego)
            if any(0x4000 <= (s << 11) < 0xC000 for s in sl):
                unresolved += 1
            continue
        site = sites.setdefault(off, {"off": off, "pc": pc, "ram": not in_rom, "slices": {}})
        for s, v in sl.items():
            site["slices"][str(s)] = v
    # instrucciones del juego que escriben en 4000h-BFFFh cuando hay RAM ahi
    ram_sites = set()
    for key in qslices:
        ctx = ctxs.get(key)
        if ctx is not None:
            off, _ = locate(raw, key[0], key[1], ctx)
            if off is not None:
                ram_sites.add(off)
    return {
        "version": VERSION,
        "machine": machine,
        "seconds": seconds,
        "runs": 1,
        "init": init,
        "sites": sorted(sites.values(), key=lambda s: s["off"]),
        "ram_sites": sorted(ram_sites),
        "unresolved": unresolved,
        "ram_access": sorted(accesses),
        "ram_write": sorted(writes),
        "user_free": _user_free(lines),
    }


def locate(raw, pc, blk, ctx):
    """Offset en la ROM de la instruccion que se ejecuto en pc.
    Devuelve (offset, se_ejecuta_desde_la_rom)."""
    ins = ctx[CTX:]
    if blk >= 0 and 0x4000 <= pc < 0xC000:
        for unit in (0x2000, 0x4000):
            off = blk * unit + (pc & (unit - 1))
            if raw[off:off + len(ins)] == ins:
                return off, True
    # Codigo copiado a RAM (o en una pagina que no es del cartucho): buscarlo
    for pat, skip in ((ins, 0), (ctx, CTX)):
        i = raw.find(pat)
        if i >= 0 and raw.find(pat, i + 1) < 0:
            return i + skip, False
    return None, False


def merge(a, b):
    sites = {s["off"]: s for s in a.get("sites", [])}
    for s in b.get("sites", []):
        if s["off"] in sites:
            sites[s["off"]]["slices"].update(s["slices"])
        else:
            sites[s["off"]] = s
    return {
        "version": VERSION,
        "machine": b.get("machine"),
        "seconds": a.get("seconds", 0) + b.get("seconds", 0),
        "runs": a.get("runs", 1) + b.get("runs", 1),
        "init": a.get("init") or b.get("init"),
        "sites": sorted(sites.values(), key=lambda s: s["off"]),
        "unresolved": max(a.get("unresolved", 0), b.get("unresolved", 0)),
        "ram_sites": sorted(set(a.get("ram_sites", [])) | set(b.get("ram_sites", []))),
        "ram_access": sorted(set(a.get("ram_access", [])) | set(b.get("ram_access", []))),
        "ram_write": sorted(set(a.get("ram_write", [])) | set(b.get("ram_write", []))),
        "user_free": _merge_free(a.get("user_free"), b.get("user_free")),
    }


def _merge_free(a, b):
    """Interseccion de tramos libres (None = sin datos)."""
    if a is None or b is None:
        return a if b is None else b
    sa = {x for s, n in a for x in range(s, s + n)}
    sb = {x for s, n in b for x in range(s, s + n)}
    both = sorted(sa & sb)
    runs = []
    for x in both:
        if runs and runs[-1][0] + runs[-1][1] == x:
            runs[-1][1] += 1
        else:
            runs.append([x, 1])
    return [r for r in runs if r[1] >= 32]


def summary(an):
    """Texto corto para la interfaz."""
    if not an:
        return ""
    used = [name for name, (s, n) in mr.RAM_AREAS.items()
            if any(s <= a < s + n for a in an["ram_access"])]
    t = "%d escrituras al mapper" % len(an["sites"])
    if not an.get("init"):
        t += "; no se vio arrancar el juego"
    if used:
        t += "; usa RAM de " + ", ".join(used)
    return t
