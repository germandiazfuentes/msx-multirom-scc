# uso: openmsx ... -script shot.tcl  (variables via env: SHOT_T, SHOT_OUT, SHOT_KEYS)
set throttle off
set t [expr {$::env(SHOT_T)}]
set out $::env(SHOT_OUT)
set keys {}
catch {set keys $::env(SHOT_KEYS)}
proc pressat {time key} { after time $time "keymatrixdown [lindex $key 0] [lindex $key 1]"; after time [expr {$time+0.15}] "keymatrixup [lindex $key 0] [lindex $key 1]" }
foreach {kt row mask} $keys { pressat $kt [list $row $mask] }
after time [expr {$t-0.5}] { set throttle on }
after time $t "screenshot [file normalize $out]; exit"
