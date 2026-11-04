# Independent routed-design checks. No board connection, no bitstream loading.
if {[catch {
set work [file normalize [lindex $argv 0]]
set mode [lindex $argv 1]
set_param general.maxThreads 2
open_checkpoint [file join $work project shenmu_${mode}.runs impl_1 system_wrapper_routed.dcp]
source [file join [file dirname [info script]] normalize_clocks.tcl]
report_timing_summary -report_unconstrained -file [file join $work review_timing.rpt]
report_drc -file [file join $work review_drc.rpt]
report_methodology -file [file join $work review_methodology.rpt]
set mf [open [file join $work review_methodology.rpt] r];set mt [read $mf];close $mf
if {[regexp -line {^\|\s*[^|]+\|\s*Critical Warning} $mt]} {error "Critical methodology checks require correction"}
report_cdc -details -file [file join $work review_cdc.rpt]
set cdcFile [open [file join $work review_cdc.rpt] r]
set cdcText [read $cdcFile]
close $cdcFile
if {[regexp -line {^CDC-[0-9]+\s+Critical} $cdcText]} {error "Critical CDC paths require review"}
report_bus_skew -file [file join $work review_bus_skew.rpt]
report_clock_interaction -file [file join $work review_clocks.rpt]
report_utilization -file [file join $work review_utilization.rpt]
check_timing -verbose -file [file join $work review_check_timing.rpt]
set failures [get_drc_violations -quiet -filter {SEVERITY == Error || SEVERITY == "Critical Warning"}]
if {[llength $failures]} {error "Unresolved critical DRC violations: $failures"}
foreach delay {max min} {
 set paths [get_timing_paths -delay_type $delay -max_paths 1]
 if {![llength $paths] || [get_property SLACK $paths]<0} {error "Routed timing failed $delay"}
}
set keys [get_cells -hier -quiet -filter {NAME =~ */pl_keys/inst/k*/key_d0_reg || NAME =~ */pl_keys/inst/k*/key_d1_reg}]
if {[llength $keys]!=4} {error "Key synchronizer stage count changed"}
foreach cell $keys {if {![get_property ASYNC_REG $cell]} {error "Missing key ASYNC_REG"}}
set timingFile [open [file join $work review_timing.rpt] r]
set timingText [read $timingFile]
close $timingFile
set summaryStart [string first "WNS(ns)" $timingText]
if {$summaryStart<0} {error "Timing summary missing"}
set summaryRow [lindex [split [string range $timingText $summaryStart end] "\n"] 2]
set values [regexp -all -inline {\S+} $summaryRow]
set pulseSlack [lindex $values 8]
if {![string is double -strict $pulseSlack] || $pulseSlack<0} {error "Pulse-width timing failed: $pulseSlack"}
file mkdir [file join $work artifacts]
write_checkpoint -force [file join $work artifacts reviewed_routed.dcp]
puts "SHENMU_2026_IMPLEMENTATION_REVIEW_PASS $mode"
close_design
} message]} {puts stderr "$message\n$::errorInfo"; exit 1}
exit 0
