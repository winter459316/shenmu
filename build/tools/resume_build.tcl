# Continue an already-created migration project without rebuilding its inputs.
if {[catch {
set package [file normalize [lindex $argv 0]]
set mode [lindex $argv 1]
set work [file normalize [lindex $argv 2]]
set step [lindex $argv 3]
if {$mode ni {pl1 pl2 pl3} || $step ni {audit synth bit}} {error "Invalid arguments"}
if {![string match 2026.1* [version -short]]} {error "Requires 2026.1"}
set src [file join $package src pl $mode]
set_param general.maxThreads 4
open_project [file join $work project shenmu_${mode}.xpr]
open_bd_design [get_files system.bd]
validate_bd_design
source [file join $package build tools audit_contract.tcl]
if {$step ne "audit"} {
 foreach run [get_runs -filter {IS_SYNTHESIS == 1}] {
  if {[get_property PROGRESS $run] eq "100%" && [lsearch -exact [list_property $run] NEEDS_REFRESH]>=0 && [get_property NEEDS_REFRESH $run]} {
   error "Inputs changed for $run; use a fresh WorkRoot or explicitly review/reset the affected run"
  }
 }
 if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
  launch_runs synth_1 -jobs 1
  wait_on_run synth_1
 }
 if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed"}
 open_run synth_1
 if {[llength [get_cells -quiet -hier -filter {IS_BLACKBOX}]]} {error "Unresolved black boxes"}
 report_utilization -file [file join $work synth_utilization.rpt]
 report_timing_summary -file [file join $work synth_timing.rpt]
 puts "SHENMU_2026_SYNTH_PASS $mode"
}
if {$step eq "bit"} {
 # Release the synthesis netlist before the implementation child starts.
 # This keeps sequential builds practical on 16 GB development computers.
 close_design
 set_property strategy Performance_Explore [get_runs impl_1]
 set_property STEPS.OPT_DESIGN.TCL.PRE [file join $package build tools normalize_clocks.tcl] [get_runs impl_1]
 set impl [get_runs impl_1]
 set routed [file join [get_property DIRECTORY $impl] system_wrapper_routed.dcp]
 set routeDone [file join [get_property DIRECTORY $impl] .route_design.end.rst]
 if {![file exists $routed] || ![file exists $routeDone]} {
  launch_runs impl_1 -to_step route_design -jobs 1
  wait_on_run impl_1
 }
 if {![file exists $routed] || ![file exists $routeDone]} {error "Routing incomplete"}
 open_run impl_1
 report_timing_summary -report_unconstrained -file [file join $work timing.rpt]
 foreach {command name} {report_drc drc report_cdc cdc report_utilization utilization report_clock_interaction clocks report_bus_skew bus_skew} {$command -file [file join $work ${name}.rpt]}
 report_cdc -details -file [file join $work cdc_details.rpt]
 write_checkpoint -force [file join $work routed.dcp]
 foreach delay {max min} {
  set paths [get_timing_paths -delay_type $delay -max_paths 1]
  if {![llength $paths] || [get_property SLACK $paths]<0} {error "Timing failed: $delay"}
 }
 puts "SHENMU_2026_ROUTE_TIMING_PASS $mode"
}
close_project
} message]} {puts stderr "$message\n$::errorInfo"; exit 1}
exit 0
