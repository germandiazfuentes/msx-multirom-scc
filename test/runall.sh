#!/bin/bash
# Bateria completa en maquinas reales: ./runall.sh
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8
run() { # maquina etiquetas...
  M=$1; shift
  for c in k5:2048 yama:8192; do
    for T in "$@"; do
      case $T in orig) P="../roms/*.zip";; *) P="../roms2/$T/*.zip";; esac
      python realtest.py ${c%:*} ${c#*:} $M - "$P" $T > "out/rt_${c%:*}_${T}_$M.txt" 2>&1
    done
  done
}
run Sony_HB-75P orig MSX1 SCC
run Toshiba_HX-10 orig MSX1 SCC
run Sony_HB-F1XD orig MSX1 SCC MSX2
run Panasonic_FS-A1WX orig MSX1 SCC MSX2 MSX2P
run Panasonic_FS-A1GT orig MSX1 SCC MSX2 MSX2P TR
echo FIN
