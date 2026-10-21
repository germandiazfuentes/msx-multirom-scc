# MSX MultiROM (Konami5 / Yamanooto)

Genera una ROM de 512KB, 2MB, 4MB u 8MB con un menú de selección y varios
juegos. Las ROMs con mapper ASCII8, ASCII16, Konami4, Konami5 y "genérico"
8K/16K se convierten automáticamente al mapper Konami5 del cartucho.

## Uso

1. Ejecuta `MultiROM.exe` (no necesita Python), o `MultiROM.bat` / `python multirom_gui.py`
   con Python 3 instalado. Para usar los botones de openMSX, pon la carpeta `openmsx`
   junto al `.exe` o elígela con **openMSX...**. El `.exe` se crea con `crear_exe.bat`
   (requiere `pip install pyinstaller`) y queda en `dist\`.
2. Elige el **cartucho** y el **tamaño**.
3. **Añadir ROMs...** o **Añadir carpeta...** (acepta `.rom` y `.zip`).
   - Doble clic en el **título** para cambiar el nombre que sale en el menú (30 caracteres).
   - Doble clic en el **mapper** si la detección es incorrecta. Si sale con `?`,
     la ROM no está en la base de datos y el mapper es deducido: compruébalo.
   - Doble clic en **Rutinas** para elegir dónde van las rutinas de conversión (ver más abajo).
   - **Analizar en openMSX** (recomendado con el RBSC): ver más abajo.
4. La barra inferior muestra el espacio ocupado por cada juego y el libre
   (pasa el ratón por encima para ver los detalles). Las filas en rojo no caben.
5. **Probar en openMSX** genera la ROM en un temporal y la abre en openMSX
   con el mapper correcto (`KonamiSCC` o `Yamanooto`).
6. **Generar ROM...** guarda la imagen final para grabarla en el cartucho.

Las listas se pueden guardar y abrir (`.json`) para rehacer la ROM más tarde.

También hay línea de comandos:

    python multirom.py --cart k5 --size 2048 -o salida.rom juego1.rom juego2.zip
    python multirom.py --cart yama --size 8192 -o salida.rom juego.rom:ASCII16

## El menú del MSX

- Cursores arriba/abajo para elegir, izquierda/derecha para pasar página,
  **ESPACIO** (o RETURN o el disparo del joystick) para jugar.
- MSX1: SCREEN 2 con colores degradados por línea.
- MSX2 y superiores: paleta propia y barra de selección animada (cambio de paleta).
  Antes de lanzar el juego se restaura la paleta estándar.
- En turbo R se pasa a modo Z80 antes de lanzar el juego.
- Hasta varios miles de juegos (170 por banco de tabla).

## Cartuchos

### Yamanooto (512KB - 8MB)
Tiene registro de offset por hardware, así que la compatibilidad es casi total:
- Konami5: sin cambios. Konami4 y genérico 8K: modo K4 nativo del cartucho.
- ASCII8 (y genérico 8K que cambia la página 4000h): solo se cambia la
  dirección de los registros (6000h→5000h, etc.), sin rutinas.
- ASCII16 y genérico 16K: necesitan rutinas de conversión (ver abajo).
- ROMs sin mapper: se activa MDIS para que escrituras accidentales no cambien de banco.

### Konami5 / RBSC Multimapper (512KB, 2MB)
No tiene registro de offset: todos los juegos con mapper se parchean para que
sumen su banco base en cada cambio de banco. Funciona con la mayoría de juegos,
pero no con los que calculan la dirección del registro (p. ej. Hydlide 3).

## Rutinas de conversión

Cada `LD (6000h),A` (o `LD HL,6000h / LD (HL),A`) se sustituye por un `CALL` a
una pequeña rutina que escribe el banco correcto en el registro Konami5. Por
defecto esas rutinas van en una zona de RAM del BASIC que los juegos en
cartucho no suelen usar (**PARM1**, F6E8h); el menú las copia antes de lanzar
el juego. Así funcionan aunque el juego ejecute desde RAM su código de cambio
de banco (Gradius, Dragon Quest 2...).

Si un juego usa esa zona de RAM, cambia el área en la columna **Rutinas**
(PARM1, HOOKS, KBUF, FNKSTR, BUF) o elige **ROM**, que las coloca en huecos
libres del propio juego (solo vale si el código que cambia de banco se ejecuta
desde ROM).

## Análisis en openMSX

Mirando solo el código no se ven todos los cambios de banco: hay juegos que
calculan la dirección del registro (Hydlide 3), que lo hacen con `LD (nn),HL`
(Super Laydock) o desde código copiado a RAM. Tampoco se sabe qué RAM usa
cada juego. El análisis ejecuta el juego **original** en openMSX y apunta:

- cada instrucción que escribe en los registros del mapper. Las que no se
  habían encontrado se parchean con un salto a una rutina en RAM que hace la
  escritura traducida (columna "Estado" del informe: "N gracias al análisis").
- qué RAM deja intacta el juego: las áreas del BASIC/BIOS (vigilando cada
  lectura y escritura) y la RAM de usuario C000h-F37Fh (se ejecuta dos veces,
  con esa RAM llena de 00h y de FFh, y se miran los bytes que no cambiaron).
- qué direcciones de las áreas de RAM candidatas lee o escribe el juego.
  Con análisis, la columna **Rutinas** pasa a "RAM auto": las rutinas se
  ponen en un tramo que el juego no toca. Si el juego escribe en todas (borra
  la RAM), se ponen en huecos de su ROM.

Botones:
- **Analizar en openMSX**: analiza los juegos seleccionados (o todos) sin
  ventana, 90 segundos de juego cada uno pulsando espacio, return y cursores.
  Tarda un par de segundos por juego.
- **Analizar jugando...**: abre openMSX con el juego seleccionado; juega
  pasando por el mayor número de pantallas posible y cierra openMSX. Así se
  encuentran cambios de banco que solo ocurren más adelante en el juego.
- **Borrar análisis**: olvida lo analizado del juego.

El análisis usa la máquina elegida en "Máquina". **Conviene usar una máquina
con BIOS real** (por ejemplo Sony HB-F1XD o Panasonic FS-A1WX, con las ROMs de
sistema instaladas en openMSX), mejor que C-BIOS: la BIOS y el BASIC reales
usan zonas de RAM que con C-BIOS no se tocan, y algunos juegos solo hacen
ciertas cosas con la BIOS real. Se pueden analizar en varias máquinas: los
resultados se suman (solo se usa la RAM libre en todas). La casilla
**Analizar en varias máquinas** lo hace solo con la máquina elegida más una
MSX1, una MSX2, una MSX2+ y una turbo R reales (las que tengan sus ROMs en
openMSX). Cada análisis tarda unos 20 segundos por juego y máquina.

Los análisis se suman y se guardan por juego en
`%USERPROFILE%\.msx_multirom\analisis`, así que solo hay que hacerlos una vez.
Lo que el juego no haga durante el análisis no se ve: si un juego falla más
adelante, analízalo jugando hasta ese punto.

## Detalles de la conversión

- Los juegos que arrancan el BASIC (cabecera con STATEMENT, como Kitten 2,
  Sonyc o Safari Kids) llevan las rutinas en DCC2h-DDFFh y el menú baja HIMEM hasta
  ahí antes de lanzarlos, como hace una disquetera.

- En ASCII8/ASCII16 los registros de las páginas 8000h y A000h están en
  6000h-7FFFh (página 1), pero en Konami5 están en 9000h/B000h (página 2),
  que puede ser RAM en ese momento (por ejemplo en el INIT). Las rutinas
  seleccionan un instante el cartucho en la página 2 para escribirlos.
- Algunos juegos suman los bytes de su ROM para detectar cambios (Young
  Artist). Después de parchear, cada banco de 8 KB se compensa en bytes
  libres para que su suma sea la original.
- Antes de saltar al juego, el menú borra sus variables (E000h-E0FFh) y vacía
  el buffer de teclado: algunos juegos leen RAM que esperan a cero (Sonyc
  creía tener un R800).
- Con análisis, los "cambios de banco" que no parecen código y nunca se ven
  ejecutar no se parchean: suelen ser datos (imágenes de disco en ROMs tipo
  Disk2ROM, como Sonyc).
- Con análisis, las direcciones que el juego usa como RAM (juegos que se
  copian a 4000h-BFFFh) no se toman por registros del mapper.

## Limitaciones conocidas

- Juegos con SRAM (Koei, Xanadu...): la partida no se puede grabar y algunos
  (Nobunaga no Yabou) no arrancan.
- Juegos de más de 2 MB (los registros Konami5 solo llegan a 256 bancos de 8 KB)
  y recopilatorios con mapper propio (Zemina, Al Alamiah 30-in-1, Manbow 2...).
- Juegos que borran toda la RAM y no tienen hueco libre en su ROM para las
  rutinas (Legend Compilation, y Auf Wiedersehen Monty en el RBSC): el
  informe lo marca como error.
- Safari Kids en el RBSC (detecta la RAM probando slots y acaba con la pila
  sobre el cartucho).
- Juegos que por un error o un truco escriben en direcciones que en su
  mapper son ROM pero en Konami5 son registros de banco, desde código que no
  se puede parchear (Nogalious en algunas máquinas al empezar a jugar).
- Si el cartucho está muy lleno, un juego puede quedar en una posición en la
  que un banco 63 (mod 64) active el SCC sin querer; la lista lo avisa.
- Juegos que usan las páginas 0 o 3 (ROMs de 48/64KB con datos en 0000h-3FFFh o C000h-FFFFh).
- ROMs de BASIC.
- En el RBSC (sin offset), juegos que calculan la dirección del registro del
  mapper, si no se han analizado o el análisis no llegó a esa parte del juego.
- Al pulsar reset se vuelve al menú solo si el cartucho reinicia su mapper con la señal de reset.

## Probado en openMSX 21.0 (C-BIOS MSX1 y MSX2)

Se han probado unos 120 juegos (los de `roms` y una muestra variada de
file-hunter en `roms2`) comparando capturas del juego original con las del
juego lanzado desde el menú, en los dos cartuchos. Fallan Nobunaga no Yabou
(SRAM) y Legend Compilation (borra la RAM); los de más de 2 MB se rechazan.
Unos 15 juegos de la muestra necesitan la BIOS/BASIC real y no arrancan con
C-BIOS ni siquiera solos, así que no se pudieron comprobar.

## Ficheros

- `multirom_gui.py`: interfaz gráfica.
- `multirom.py`: detección, conversión, colocación y generación de la imagen.
- `analyze.py`: análisis en openMSX. `z80.py`: longitudes de instrucciones Z80.
- `msx/menu.asm`: menú del MSX (Z80). `ensamblar_menu.bat` lo reensambla con pasmo.
- `data/romdb.tsv.gz`: tipos de mapper por SHA1, extraídos de la base de datos
  de openMSX (softwaredb.xml, GPL).
