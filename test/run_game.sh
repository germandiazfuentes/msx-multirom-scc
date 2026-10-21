#!/bin/sh
# run_game.sh rom romtype machine index out [time]
rom=$1; rt=$2; mach=$3; idx=$4; out=$5; t=${6:-14}
keys=""; tt=3
i=0; while [ $i -lt $idx ]; do keys="$keys $tt 8 64"; tt=$(echo "$tt+0.4"|bc); i=$((i+1)); done
keys="$keys $(echo "$tt+0.5"|bc) 8 1"
SHOT_T=$t SHOT_OUT=$out SHOT_KEYS="$keys" timeout 120 ../tools/openmsx/openmsx.exe -machine $mach -cart $rom -romtype $rt -script shot.tcl
