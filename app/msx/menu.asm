; Copyright (C) 2026 Germán Díaz / MSX Calamar
; SPDX-License-Identifier: GPL-2.0-or-later
;===============================================================================
; MSX MultiROM - Menu (banco 0 del cartucho, 4000h-5FFFh)
;
; Cartuchos soportados:
;   0 = Konami5 generico (RBSC Multimapper 512KB/2MB): los juegos con mapper
;       vienen parcheados por el PC para sumar su banco base.
;   1 = Yamanooto (hasta 8MB): el offset lo pone el hardware (OFFR/SUBOFF).
;
; El PC rellena el bloque de configuracion (4020h) y la tabla de juegos,
; que empieza en el banco cfg_tablebank y se ve por la ventana 6000h-7FFFh.
;
; Entrada de la tabla (48 bytes, 170 entradas por banco de 8KB):
;   +0  nombre (30 caracteres ASCII)
;   +30 tamano en bancos de 8KB (word)
;   +32 valores para 5000h, 7000h, 9000h, B000h
;   +36 OFFR (Yamanooto)
;   +37 CFGR (Yamanooto: SUBOFF/K4/MDIS)
;   +38 flags (bit0: cabecera del juego en 8000h, bit1: bajar HIMEM al
;       destino de las rutinas para que el BASIC no use esa RAM)
;   +39 tipo de mapper (solo para mostrarlo)
;   +40 banco del bloque de rutinas de conversion (0 = no hay)
;   +41 (reservado)
;   +42 direccion del bloque (vista en 6000h-7FFFh)
;   +44 longitud del bloque
;   +46 direccion de RAM donde se copia
;
; Ensamblar: pasmo menu.asm menu.bin
;===============================================================================

; --- BIOS ---
CGTABL  equ 0004h
VDPDW   equ 0007h
MSXVER  equ 002Dh
ENASLT  equ 0024h
DISSCR  equ 0041h
ENASCR  equ 0044h
SETWRT  equ 0053h
FILVRM  equ 0056h
LDIRVM  equ 005Ch
CHGCLR  equ 0062h
INITXT  equ 006Ch
INIT32  equ 006Fh
INIGRP  equ 0072h
RSLREG  equ 0138h
SNSMAT  equ 0141h
KILBUF  equ 0156h
HIMEM   equ 0FC4Ah
GTSTCK  equ 00D5h
GTTRIG  equ 00D8h
CHGCPU  equ 0180h

; --- Area de trabajo del sistema ---
FORCLR  equ 0F3E9h
BAKCLR  equ 0F3EAh
BDRCLR  equ 0F3EBh
SCRMOD  equ 0FCAFh
EXPTBL  equ 0FCC1h
SLTTBL  equ 0FCC5h

; --- Yamanooto ---
Y_ENAR  equ 7FFFh
Y_OFFR  equ 7FFEh
Y_CFGR  equ 7FFDh

; --- Constantes del menu ---
ENTRY_SIZE  equ 48
ENTRIES_BANK equ 170
LIST_ROW    equ 3           ; primera fila de la lista
LIST_ROWS   equ 18          ; filas visibles
NAMTBL      equ 1800h
REP_DELAY   equ 18          ; frames antes de autorepetir
REP_RATE    equ 4           ; frames entre repeticiones
T_SPACE     equ 224         ; tile "espacio" del juego de caracteres del titulo
HL_OFF      equ 96          ; desplazamiento del juego de caracteres resaltado

; --- Variables en RAM ---
VARS        equ 0E000h
v_sp        equ VARS+0
v_cur       equ VARS+2
v_top       equ VARS+4
v_num       equ VARS+6
v_idx       equ VARS+8
v_lastdir   equ VARS+10
v_rep       equ VARS+11
v_msxver    equ VARS+12
v_slot1     equ VARS+13
v_slot2     equ VARS+14
v_scrmod    equ VARS+15
v_fg        equ VARS+16
v_bg        equ VARS+17
v_bd        equ VARS+18
v_ctype     equ VARS+19
v_colptr    equ VARS+20
v_frame     equ VARS+23
v_noyama    equ VARS+24     ; <>0: la ROM es para Yamanooto pero no lo hay
v_entry     equ VARS+64     ; 16 bytes
v_line      equ VARS+96     ; 32 bytes
TRAMP       equ 0E100h

        org 4000h

        db "AB"
        dw init
        dw 0, 0, 0
        ds 4010h-$, 0

init:   jp start

        ds 4020h-$, 0
; --- Bloque de configuracion (lo rellena el PC) ---
cfg_carttype:   db 0            ; 0 = Konami5 generico, 1 = Yamanooto
cfg_numgames:   dw 0
cfg_tablebank:  db 1
cfg_flags:      db 0
        ds 4030h-$, 0
cfg_title:      db "          MSX MULTIROM          "

;-------------------------------------------------------------------------------
start:
        ld (v_sp), sp
        xor a
        ld (v_noyama), a
        ld a, (cfg_carttype)
        ld (v_ctype), a
        or a
        call nz, yama_reset

        ld a, (MSXVER)
        ld (v_msxver), a
        ld c, 1
        call get_slot
        ld (v_slot1), a
        ld c, 2
        call get_slot
        ld (v_slot2), a

        ld a, (SCRMOD)
        ld (v_scrmod), a
        ld hl, (FORCLR)
        ld (v_fg), hl
        ld a, (BDRCLR)
        ld (v_bd), a

        ld hl, (cfg_numgames)
        ld (v_num), hl
        ld a, h
        or l
        ret z                   ; sin juegos: seguir arrancando normalmente

        ld hl, 0
        ld (v_cur), hl
        ld (v_top), hl
        xor a
        ld (v_lastdir), a

        call setup_screen
        call draw_list

;-------------------------------------------------------------------------------
main_loop:
        ei
        halt
        ld a, (v_msxver)
        or a
        call nz, glow
        call read_fire
        jr z, ml_dir
        ld a, (v_noyama)        ; sin Yamanooto los juegos no arrancarian
        or a
        jp z, launch
ml_dir: call read_dir
        ld hl, v_lastdir
        cp (hl)
        jr z, ml_same
        ld (hl), a
        ld a, REP_DELAY
        ld (v_rep), a
        jr ml_act
ml_same:
        or a
        jr z, main_loop
        ld hl, v_rep
        dec (hl)
        jr nz, main_loop
        ld (hl), REP_RATE
ml_act:
        ld a, (v_lastdir)
        cp 1
        jr z, k_up
        cp 5
        jr z, k_down
        cp 7
        jr z, k_pgup
        cp 3
        jr z, k_pgdn
        jr main_loop

k_up:   ld hl, (v_cur)
        ld a, h
        or l
        jr nz, k_up1
        ld hl, (v_num)
k_up1:  dec hl
        jr k_set

k_down: ld hl, (v_cur)
        inc hl
        ld de, (v_num)
        or a
        sbc hl, de
        add hl, de
        jr c, k_set
        ld hl, 0
        jr k_set

k_pgup: ld hl, (v_cur)
        ld de, LIST_ROWS
        or a
        sbc hl, de
        jr nc, k_set
        ld hl, 0
        jr k_set

k_pgdn: ld hl, (v_cur)
        ld de, LIST_ROWS
        add hl, de
        ld de, (v_num)
        or a
        sbc hl, de
        add hl, de
        jr c, k_set
        ex de, hl
        dec hl

k_set:  ld (v_cur), hl
        ; si cur < top -> top = cur
        ld de, (v_top)
        or a
        sbc hl, de
        jr nc, ks_1
        ld hl, (v_cur)
        ld (v_top), hl
        jr ks_draw
ks_1:   ; si cur - top >= LIST_ROWS -> top = cur - (LIST_ROWS-1)
        ld de, LIST_ROWS
        or a
        sbc hl, de
        jr c, ks_draw
        ld hl, (v_cur)
        ld de, LIST_ROWS-1
        or a
        sbc hl, de
        ld (v_top), hl
ks_draw:
        call draw_list
        jp main_loop

;-------------------------------------------------------------------------------
; Entrada: devuelve A = direccion (0, 1=arriba, 3=dcha, 5=abajo, 7=izda)
read_dir:
        xor a
        call GTSTCK
        or a
        jr nz, rd_1
        ld a, 1
        call GTSTCK
rd_1:   bit 0, a                ; las diagonales (pares) se ignoran
        ret nz
        xor a
        ret

; Devuelve NZ si se pulsa ESPACIO, RETURN o el boton del joystick
read_fire:
        xor a
        call GTTRIG
        or a
        ret nz
        ld a, 1
        call GTTRIG
        or a
        ret nz
        ld a, 7
        call SNSMAT
        cpl
        and 80h
        ret

;-------------------------------------------------------------------------------
; Slot de la pagina C (1 o 2). Devuelve A = ExxxSSPP
get_slot:
        call RSLREG
        ld b, c
gs_1:   rrca
        rrca
        djnz gs_1
        and 3
        ld e, a
        ld d, 0
        ld hl, EXPTBL
        add hl, de
        ld a, (hl)
        and 80h
        or e
        ld e, a
        ret p                   ; slot no expandido
        ld hl, SLTTBL
        ld a, e
        and 3
        ld d, 0
        push de
        ld e, a
        add hl, de
        pop de
        ld a, (hl)
        ld b, c
gs_2:   rrca
        rrca
        djnz gs_2
        and 3
        rlca
        rlca
        or e
        ret

; Deja los registros del Yamanooto en estado conocido (CFGR no se borra al
; hacer reset, asi que puede quedar K4/MDIS del juego anterior).
yama_reset:
        ld a, 1
        ld (Y_ENAR), a
        ld a, (Y_ENAR)          ; con los registros activos se leen: si no
        xor 1                   ; vuelve el 1 no hay Yamanooto (p. ej. openMSX
        ld (v_noyama), a        ; lo ha cargado como KonamiSCC)
        xor a
        ld (Y_CFGR), a
        ld (Y_OFFR), a
        ld (Y_ENAR), a
        ret

;-------------------------------------------------------------------------------
; Devuelve en HL la direccion de la entrada HL, con su banco mapeado en 6000h
get_entry:
        ld a, (cfg_tablebank)
        ld c, a
        ld de, ENTRIES_BANK
ge_1:   or a
        sbc hl, de
        jr c, ge_2
        inc c
        jr ge_1
ge_2:   add hl, de
        ld a, c
        ld (7000h), a
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl              ; x16
        ld d, h
        ld e, l
        add hl, hl              ; x32
        add hl, de              ; x48
        ld de, 6000h
        add hl, de
        ret

;-------------------------------------------------------------------------------
; Pantalla
setup_screen:
        ld a, (v_msxver)
        or a
        ld hl, colors_msx1
        ld a, 4
        jr z, ss_1
        ld hl, colors_msx2
        ld a, 2
ss_1:   ld (v_colptr), hl
        ld (BAKCLR), a
        ld (BDRCLR), a
        ld a, 15
        ld (FORCLR), a
        call INIGRP
        call DISSCR
        ld a, (v_msxver)
        or a
        ld hl, palette_menu
        call nz, set_palette

        ld hl, 0000h
        call load_font
        ld hl, 0800h
        call load_font
        ld hl, 1000h
        call load_font
        ld hl, 2000h
        call load_colors
        ld hl, 2800h
        call load_colors
        ld hl, 3000h
        call load_colors

        ld hl, NAMTBL
        ld bc, 768
        xor a
        call FILVRM
        ld hl, NAMTBL
        ld bc, 32
        ld a, T_SPACE
        call FILVRM
        ld hl, NAMTBL+64
        ld bc, 32
        ld a, T_SPACE
        call FILVRM
        ld hl, NAMTBL+20*32+32
        ld bc, 32
        ld a, T_SPACE
        call FILVRM

        ld hl, cfg_title
        ld de, NAMTBL+32
        call put_title
        ld hl, help_text
        ld a, (v_noyama)
        or a
        jr z, ss_2
        ld hl, noyama_text
ss_2:   ld de, NAMTBL+23*32
        call put_title
        jp ENASCR

; Copia 32 caracteres de HL a la fila VRAM DE con el juego de caracteres del titulo
put_title:
        push de
        ld de, v_line
        ld b, 32
pt_1:   ld a, (hl)
        inc hl
        cp 'a'
        jr c, pt_2
        cp 'z'+1
        jr nc, pt_2
        sub 32
pt_2:   cp 32
        jr c, pt_sp
        cp 96
        jr nc, pt_sp
        cp 64
        jr c, pt_3
        add a, 192-64
        jr pt_4
pt_3:   add a, 224-32
        jr pt_4
pt_sp:  ld a, T_SPACE
pt_4:   ld (de), a
        inc de
        djnz pt_1
        pop de
        ld hl, v_line
        ld bc, 32
        jp LDIRVM

; Patrones de un tercio de pantalla (HL = direccion VRAM)
;   0-95 normal, 96-191 resaltado (ASCII 32-127), 192-223 titulo (ASCII 64-95),
;   224-255 titulo (ASCII 32-63)
load_font:
        call SETWRT
        ld a, 32
        ld b, 96
        call out_glyphs
        ld a, 32
        ld b, 96
        call out_glyphs
        ld a, 64
        ld b, 32
        call out_glyphs
        ld a, 32
        ld b, 32
        ; sigue en out_glyphs

; Envia B caracteres desde el codigo A, en negrita (byte OR byte>>1)
out_glyphs:
        push bc
        push af
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld de, (CGTABL)
        add hl, de
        ld a, (VDPDW)
        ld c, a
        ld b, 8
og_1:   ld a, (hl)
        ld e, a
        srl a
        or e
        out (c), a
        inc hl
        djnz og_1
        pop af
        inc a
        pop bc
        djnz out_glyphs
        ret

; Colores de un tercio (HL = direccion VRAM)
load_colors:
        call SETWRT
        ld a, (VDPDW)
        ld c, a
        ld hl, (v_colptr)
        ld b, 96
        call out_colset
        ld b, 96
        call out_colset
        ld b, 64
        ; sigue en out_colset

; Repite B veces los 8 bytes de HL. Al acabar HL apunta al siguiente juego.
out_colset:
        push hl
        ld d, 8
oc_1:   ld a, (hl)
        out (c), a
        inc hl
        dec d
        jr nz, oc_1
        pop hl
        djnz out_colset
        ld de, 8
        add hl, de
        ret

; MSX2: anima los colores 12 y 13 (barra de seleccion) cambiando la paleta
glow:
        ld hl, v_frame
        inc (hl)
        ld a, (hl)
        and 3
        ret nz
        ld a, (hl)
        rrca
        rrca
        and 0Fh
        add a, a
        add a, a
        ld e, a
        ld d, 0
        ld hl, glow_table
        add hl, de
        ld a, (VDPDW)
        inc a
        ld c, a
        di
        ld a, 12
        out (c), a
        ld a, 80h+16
        out (c), a
        ei
        inc c
        ld b, 4
        otir
        ret

; Paleta MSX2: HL = 16 entradas de 2 bytes (0RRR0BBB, 00000GGG)
set_palette:
        ld a, (VDPDW)
        inc a
        ld c, a
        di
        xor a
        out (c), a
        ld a, 80h+16
        out (c), a
        ei
        inc c
        ld b, 32
        otir
        ret

;-------------------------------------------------------------------------------
; Dibuja las filas visibles y la linea de informacion
draw_list:
        ld hl, (v_top)
        ld (v_idx), hl
        ld de, NAMTBL+LIST_ROW*32
        ld b, LIST_ROWS
dl_1:   push bc
        push de
        ld hl, (v_idx)
        call build_row
        pop de
        push de
        ld hl, v_line
        ld bc, 32
        call LDIRVM
        pop hl
        ld de, 32
        add hl, de
        ex de, hl
        ld hl, (v_idx)
        inc hl
        ld (v_idx), hl
        pop bc
        djnz dl_1
        jp draw_info

; Construye en v_line la fila del juego HL
build_row:
        ld de, (v_num)
        or a
        sbc hl, de
        add hl, de
        jr c, br_1
        ld hl, v_line
        ld b, 32
br_0:   ld (hl), 0
        inc hl
        djnz br_0
        ret
br_1:   ld c, 0
        ld de, (v_cur)
        or a
        sbc hl, de
        add hl, de
        jr nz, br_2
        ld c, HL_OFF
br_2:   push bc
        call get_entry
        pop bc
        ld de, v_line
        ld a, c
        ld (de), a
        inc de
        ld b, 30
br_3:   ld a, (hl)
        inc hl
        call to_tile
        ld (de), a
        inc de
        djnz br_3
        ld a, c
        ld (de), a
        ret

; Caracter A -> tile normal + C
to_tile:
        cp 32
        jr c, tt_1
        cp 128
        jr c, tt_2
tt_1:   ld a, '?'
tt_2:   sub 32
        add a, c
        ret

; Linea de informacion: " 001/150   128KB   KONAMI SCC "
draw_info:
        ld hl, v_line
        ld b, 32
di_0:   ld (hl), 0
        inc hl
        djnz di_0
        ld de, v_line+1
        ld hl, (v_cur)
        inc hl
        call put_dec
        ld a, '/'-32
        ld (de), a
        inc de
        ld hl, (v_num)
        call put_dec
        ld hl, (v_cur)
        call get_entry
        push hl
        ld de, 30
        add hl, de
        ld e, (hl)
        inc hl
        ld d, (hl)
        ex de, hl
        add hl, hl
        add hl, hl
        add hl, hl              ; KB
        ld de, v_line+11
        call put_dec
        ld hl, txt_kb
        call put_str
        pop hl
        ld de, 39
        add hl, de
        ld a, (hl)
        cp 6
        jr c, di_1
        xor a
di_1:   add a, a
        ld l, a
        ld h, 0
        ld bc, mapper_names
        add hl, bc
        ld a, (hl)
        inc hl
        ld h, (hl)
        ld l, a
        ld de, v_line+19
        call put_str
        ld hl, v_line
        ld de, NAMTBL+22*32
        ld bc, 32
        jp LDIRVM

; Cadena terminada en 0 de HL a DE (tiles normales)
put_str:
        ld a, (hl)
        or a
        ret z
        sub 32
        ld (de), a
        inc hl
        inc de
        jr put_str

; Numero HL en decimal (sin ceros a la izquierda) en DE
put_dec:
        xor a
        ld (pd_flag), a         ; 0 = aun no se ha escrito ningun digito
        ld bc, -10000
        call pd_digit
        ld bc, -1000
        call pd_digit
        ld bc, -100
        call pd_digit
        ld bc, -10
        call pd_digit
        ld a, l
        add a, '0'-32
        ld (de), a
        inc de
        ret
pd_digit:
        ld a, -1
pd_1:   inc a
        add hl, bc
        jr c, pd_1
        sbc hl, bc
        or a
        jr nz, pd_2
        ld a, (pd_flag)
        or a
        ret z
        xor a
pd_2:   add a, '0'-32
        ld (de), a
        inc de
        ld a, 1
        ld (pd_flag), a
        ret

;-------------------------------------------------------------------------------
; Lanzar el juego seleccionado
launch:
        ei
        halt
        call read_fire
        jr nz, launch           ; esperar a que se suelte la tecla

        ld hl, (v_cur)
        call get_entry
        ld de, 32
        add hl, de
        ld de, v_entry
        ld bc, 16
        ldir

        call DISSCR
        ld a, (v_msxver)
        or a
        ld hl, palette_msx2
        call nz, set_palette
        ld hl, (v_fg)
        ld (FORCLR), hl
        ld a, (v_bd)
        ld (BDRCLR), a
        ld a, (v_scrmod)
        or a
        jr nz, la_1
        call INITXT
        jr la_2
la_1:   call INIT32
la_2:   call KILBUF
        ld a, (v_msxver)
        cp 3
        jr c, la_3
        ld a, 80h               ; turbo R: modo Z80 (con LED)
        call CHGCPU
la_3:
        ld a, (v_entry+6)       ; reservar la RAM de las rutinas bajo HIMEM
        and 2
        jr z, la_h
        ld de, (v_entry+14)
        ld hl, (HIMEM)
        or a
        sbc hl, de
        jr c, la_h
        ld (HIMEM), de
la_h:
        ld a, (v_entry+8)       ; rutinas de conversion a RAM
        or a
        jr z, la_4
        ld (7000h), a
        ld hl, (v_entry+10)
        ld bc, (v_entry+12)
        ld de, (v_entry+14)
        ldir
la_4:
        ld hl, tramp_src
        ld de, TRAMP
        ld bc, tramp_end-tramp_src
        ldir
        jp TRAMP

; Rutina reubicable que se ejecuta en RAM: programa el mapper y salta al juego
tramp_src:
        di
        ld a, (v_slot1)
        ld h, 80h
        call ENASLT             ; pagina 2 = cartucho
        ld a, (v_ctype)
        or a
        jr z, tr_1
        ld a, 1
        ld (Y_ENAR), a
        ld a, (v_entry+4)
        ld (Y_OFFR), a
        ld a, (v_entry+5)
        and 30h                 ; de momento solo SUBOFF
        ld (Y_CFGR), a
tr_1:   ld hl, v_entry
        ld a, (hl)
        ld (5000h), a
        inc hl
        ld a, (hl)
        ld (7000h), a
        inc hl
        ld a, (hl)
        ld (9000h), a
        inc hl
        ld a, (hl)
        ld (0B000h), a
        ld a, (v_ctype)
        or a
        jr z, tr_2
        ld a, (v_entry+5)
        ld (Y_CFGR), a          ; K4 / MDIS definitivos
        xor a
        ld (Y_ENAR), a          ; registros ocultos
        ld a, (v_entry+5)
        and 08h
        jr z, tr_2
        ld a, (v_entry+1)       ; en K4 las escrituras anteriores cambiaron 6000h
        ld (6000h), a
tr_2:   ld a, (v_entry+6)
        rrca
        jr c, tr_3
        ld a, (v_slot2)
        ld h, 80h
        call ENASLT             ; pagina 2 como la dejo la BIOS
        ld hl, (4002h)
        jr tr_4
tr_3:   ld hl, (8002h)
tr_4:   ld sp, (v_sp)
        push hl                 ; INIT del juego
        ld hl, VARS             ; borrar las variables del menu: el juego
        ld de, VARS+1           ; encuentra la RAM como tras un arranque normal
        ld bc, TRAMP-VARS-1
        ld (hl), 0
        ldir
        ld de, (0F3F8h)         ; PUTPNT -> GETPNT: vaciar el buffer de teclado
        ld (0F3FAh), de         ; (la tecla con que se eligio el juego)
        pop hl
        ei
        jp (hl)
tramp_end:

;-------------------------------------------------------------------------------
; Datos
pd_flag equ VARS+22

help_text:
        db "  CURSORES:ELEGIR  ESPACIO:JUGAR "
noyama_text:
        db " FALTA EL MAPPER YAMANOOTO !!!   "
txt_kb: db "KB", 0

mapper_names:
        dw mn_rom, mn_k4, mn_k5, mn_a8, mn_a16, mn_rom
mn_rom: db "ROM", 0
mn_k4:  db "KONAMI", 0
mn_k5:  db "KONAMI SCC", 0
mn_a8:  db "ASCII 8K", 0
mn_a16: db "ASCII 16K", 0

; Colores (8 lineas: FG<<4 | BG) para: normal, resaltado, titulo
colors_msx1:
        db 0F4h, 0F4h, 0F4h, 0F4h, 0F4h, 0E4h, 0E4h, 0E4h
        db 0F9h, 0F9h, 0F8h, 0F8h, 0F8h, 0F8h, 0F6h, 0F6h
        db 0B7h, 0B5h, 0B5h, 0A4h, 0A4h, 0A4h, 0A5h, 0A7h

colors_msx2:
        db 0F2h, 0F2h, 0F2h, 0F2h, 0E2h, 0E2h, 0E2h, 0E2h
        db 0FDh, 0FDh, 0FCh, 0FCh, 0FCh, 0FCh, 0FBh, 0FBh
        db 085h, 084h, 084h, 093h, 093h, 093h, 0A4h, 0A5h

; Paleta del menu en MSX2 (indice: R,G,B 0-7)
palette_menu:
        db 00h, 0       ; 0  negro
        db 00h, 0       ; 1  negro
        db 13h, 1       ; 2  azul muy oscuro (fondo)
        db 14h, 2       ; 3  azul
        db 25h, 3       ; 4  azul medio
        db 37h, 5       ; 5  celeste
        db 50h, 1       ; 6  rojo oscuro
        db 27h, 6       ; 7  cian
        db 71h, 6       ; 8  oro
        db 70h, 4       ; 9  naranja
        db 60h, 2       ; 10 naranja oscuro
        db 34h, 0       ; 11 purpura oscuro
        db 46h, 1       ; 12 violeta
        db 57h, 2       ; 13 lila
        db 56h, 5       ; 14 gris azulado
        db 77h, 7       ; 15 blanco

; Pulso de la barra de seleccion en MSX2 (colores 12 y 13, 16 pasos)
glow_table:
        db 035h, 0, 046h, 1
        db 035h, 0, 046h, 1
        db 035h, 0, 046h, 1
        db 046h, 1, 056h, 2
        db 046h, 1, 066h, 2
        db 056h, 1, 067h, 3
        db 067h, 2, 077h, 4
        db 067h, 2, 077h, 4
        db 067h, 2, 077h, 4
        db 067h, 2, 077h, 4
        db 067h, 2, 077h, 4
        db 056h, 1, 067h, 3
        db 046h, 1, 066h, 3
        db 046h, 1, 056h, 2
        db 035h, 0, 046h, 1
        db 035h, 0, 046h, 1

; Paleta por defecto del MSX2 (para devolverla antes de lanzar el juego)
palette_msx2:
        db 00h, 0, 00h, 0, 11h, 6, 33h, 7
        db 17h, 1, 27h, 3, 51h, 1, 27h, 6
        db 71h, 1, 73h, 3, 61h, 6, 64h, 6
        db 11h, 4, 65h, 2, 55h, 5, 77h, 7

        ds 6000h-$, 0FFh
