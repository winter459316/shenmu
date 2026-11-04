# The compute MMCM is driven by PS PLCLK0, not an external primary clock.
# Preserve every other timing constraint while removing the legacy alias.
proc shenmu_normalize_clocks {directory} {
 set alias [get_clocks -quiet system_i/compute_clock/inst/clk_in1]
 if {![llength $alias]} {puts "SHENMU_CLOCK_SOURCE_ALREADY_NORMALIZED";return}
 set ps [get_clocks -quiet clk_pl_0]
 if {[llength $alias]!=1 || [llength $ps]!=1 || abs([get_property PERIOD $alias]-[get_property PERIOD $ps])>0.0001} {error "Unexpected compute input clock relationship"}
 set expected [dict create]
 foreach clock [get_clocks] {
  if {$clock eq $alias} {continue}
  dict set expected [get_property SOURCE_PINS $clock] [list [get_property PERIOD $clock] [get_property WAVEFORM $clock]]
 }
 file mkdir $directory
 set before [file join $directory timing_before_clock_normalization.xdc]
 set after [file join $directory timing_after_clock_normalization.xdc]
 write_xdc -force -exclude_physical $before
 set fp [open $before r];set text [read $fp];close $fp
 set fp [open $after w]
 set scope "";set removedClock 0;set removedJitter 0
 foreach line [split $text "\n"] {
  if {[regexp {^\s*current_instance\s+(\S+)} $line -> value]} {set scope $value}
  if {$scope eq "system_i/compute_clock/inst" && [regexp {^\s*create_clock\s} $line]} {
   incr removedClock
  } elseif {$scope eq "system_i/compute_clock/inst" && [regexp {^\s*set_input_jitter\s} $line]} {
   incr removedJitter
  } else {puts $fp $line}
 }
 puts $fp {current_instance}
 puts $fp {set_input_jitter [get_clocks clk_pl_0] 0.100}
 close $fp
 if {$removedClock!=1 || $removedJitter!=1} {error "Unexpected legacy clock constraint count"}
 reset_timing -invalid
 read_xdc $after
 set actual [dict create]
 foreach clock [get_clocks] {dict set actual [get_property SOURCE_PINS $clock] [list [get_property PERIOD $clock] [get_property WAVEFORM $clock]]}
 if {[dict size $actual]!=[dict size $expected]} {error "Clock network count changed beyond removal of the duplicate"}
 dict for {source values} $expected {
  if {![dict exists $actual $source]} {error "Clock source disappeared: $source"}
  set old [concat [lindex $values 0] [lindex $values 1]]
  set new [concat [lindex [dict get $actual $source] 0] [lindex [dict get $actual $source] 1]]
  if {[llength $old]!=[llength $new]} {error "Clock waveform shape changed"}
  foreach a $old b $new {if {abs($a-$b)>0.0001} {error "Clock frequency/waveform changed: $source"}}
 }
 report_clocks -file [file join $directory normalized_clocks.rpt]
 puts "SHENMU_COMPUTE_CLOCK_DERIVED_FROM_PS"
}
if {[info exists work]} {shenmu_normalize_clocks [file join $work clock_normalization]} else {shenmu_normalize_clocks [file join [pwd] clock_normalization]}
