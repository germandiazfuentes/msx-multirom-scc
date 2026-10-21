; ROM de prueba de mapper. Se incluye desde un fichero que define:
;   A16     1 si es ASCII16, 0 si es de 8KB
;   REG_P1  registro de la pagina 6000h (8KB) / 4000h (A16)
;   REG_P2  registro de la pagina 8000h
;   REG_P3  registro de la pagina A000h (solo 8KB)
;   NB      numero de bancos (de 8KB o 16KB)
; Resultado en RAM: C000h = 2 OK, 3 fallo (C001h = banco, C002h = prueba)
; Cada banco tiene en +1F01h su numero (y +3F01h en ASCII16).

CHPUT   equ 00A2h
INITXT  equ 006Ch
ENASLT  equ 0024h
RSLREG  equ 0138h
EXPTBL  equ 0FCC1h
SLTTBL  equ 0FCC5h
RESULT     equ 0C000h

        org 4000h
        db "AB"
        dw init
        ds 4010h-$, 0
init:
        ld a, 1
        ld (RESULT), a
        call INITXT
        ; pagina 2 = nuestro slot
        call RSLREG
        rrca
        rrca
        and 3
        ld c, a
        ld hl, EXPTBL
        ld b, 0
        add hl, bc
        ld a, (hl)
        and 80h
        or c
        ld c, a
        jp p, noexp
        inc hl
        inc hl
        inc hl
        inc hl
        ld a, (hl)
        rrca
        rrca
        and 0Ch
        or c
        ld c, a
noexp:  ld a, c
        ld h, 80h
        call ENASLT
        ei

; Prueba 1: todos los bancos en la pagina 8000h con LD (nn),A
        ld a, 1
        ld (RESULT+2), a
        ld b, 0
t1:     ld a, b
        ld (REG_P2), a
        ld a, (9F01h)
        cp b
        jp nz, fail
        if A16
        ld a, (0BF01h)
        cp b
        jp nz, fail
        endif
        inc b
        ld a, b
        cp NB
        jr nz, t1

; Prueba 2: LD HL,reg / LD (HL),A
        ld a, 2
        ld (RESULT+2), a
        ld b, NB-1
t2:     ld a, b
        if A16
        ld hl, REG_P2
        ld (hl), a
        ld a, (9F01h)
        else
        ld hl, REG_P3
        ld (hl), a
        ld a, (0BF01h)
        endif
        cp b
        jp nz, fail
        dec b
        jp p, t2

; Prueba 3: codigo de otro banco que cambia de banco
        ld a, 3
        ld (RESULT+2), a
        if A16
        ld a, 1
        ld (REG_P2), a
        call farcode            ; en el banco 1 (8000h): cambia la pagina 4000h
        cp 3
        jp nz, fail
        else
        ld a, 1
        ld (REG_P1), a
        call farcode            ; en el banco 1 (6000h): cambia la pagina 8000h
        cp 5
        jp nz, fail
        endif

        ld a, 2
        ld (RESULT), a
        ld hl, txt_ok
        jr print
fail:   ld a, b
        ld (RESULT+1), a
        ld a, 3
        ld (RESULT), a
        ld hl, txt_fail
print:  ld a, (hl)
        or a
        jr z, $
        call CHPUT
        inc hl
        jr print

txt_ok:   db "MAPPER TEST OK", 0
txt_fail: db "MAPPER TEST FAIL", 0

        if A16
        ds 8000h-$, 0FFh
        else
        ds 6000h-$, 0FFh
        endif

; ---- banco 1 ----
farcode:
        call fc_sub
        ret
fc_sub:
        if A16
        ld a, 3
        ld (REG_P1), a
        ld a, (5F01h)
        ld b, a
        xor a
        ld (REG_P1), a          ; devolver el banco 0 a 4000h
        ld a, b
        else
        ld a, 5
        ld (REG_P2), a
        ld a, (9F01h)
        endif
        ret

        if A16
        ds 0C000h-$, 0FFh
        else
        ds 8000h-$, 0FFh
        endif
