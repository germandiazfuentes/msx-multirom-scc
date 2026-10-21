#!/bin/bash
# Prueba rapida (menu, primer y ultimo juego) en mas maquinas: ./quickall.sh
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8
for M in Sanyo_MPC-100 Sanyo_PHC-28S Sony_HB-F9S Sony_HB-F700S Canon_V-20 Philips_NMS_8245 Philips_VG_8020; do
  for c in k5:2048 yama:8192; do
    python quicktest.py ${c%:*} ${c#*:} $M
  done
done
echo FIN
