set throttle off
after time 14 { set throttle on }
after time 15 { screenshot [file normalize out/smoke3.png] ; exit }
