# Build a fresh project using only packaged sources. Never opens hardware.
if {[catch {
set package [file normalize [lindex $argv 0]]
set mode [lindex $argv 1]
set work [file normalize [lindex $argv 2]]
set step [lindex $argv 3]
if {$mode ni {pl1 pl2 pl3}} {error "Unknown profile"}
if {![string match 2026.1* [version -short]]} {error "Requires Vivado 2026.1"}
set src [file join $package src pl $mode]
file mkdir $work
cd $work
set_param general.maxThreads 4
create_project shenmu_$mode [file join $work project] -part xczu4ev-sfvc784-2-i -force
if {[llength $argv]>4 && [lindex $argv 4] ne ""} {
 set cache [file normalize [lindex $argv 4]]
 file mkdir $cache
 config_ip_cache -use_cache_location $cache
}
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set repositories [glob -nocomplain -directory [file join $src ip_repo] *]
lappend repositories [file join $package src pl interfaces]
set_property ip_repo_paths $repositories [current_project]
update_ip_catalog
add_files -norecurse [glob -nocomplain [file join $src rtl *]]
set xci [glob -nocomplain [file join $src ip *.xci]]
if {[llength $xci]} {import_ip -files $xci; upgrade_ip [get_ips]}
add_files -fileset constrs_1 -norecurse [glob -nocomplain [file join $src constraints *.xdc]]
foreach f [get_files -quiet *clock_distribution.xdc] {set_property USED_IN_SYNTHESIS false $f}
# Vivado 2026.1 cannot deserialize a 2018.2 BD without the unavailable 3.2
# PS XCI. Recreate its explicit connectivity/parameters using current catalog
# versions instead; retain both original recipe and recorded version mapping.
if {[file exists [file join $src bd system_2026.tcl]]} {
 source [file join $src bd system_2026.tcl]
} else {
set input [open [file join $src bd legacy_bd.tcl] r]
set recipe [read $input];close $input
set begin [string first "set scripts_vivado_version " $recipe]
set finish [string first "# START" $recipe $begin]
if {$begin<0 || $finish<$begin} {error "Unsupported legacy recipe header"}
set recipe "[string range $recipe 0 [expr {$begin-1}]]# Version gate replaced by explicit current-catalog migration below.\n[string range $recipe $finish end]"
set identities [lsort -unique [regexp -all -inline {xilinx\.com:ip:[A-Za-z0-9_]+:[0-9.]+} $recipe]]
set mapping [open [file join $work ip_version_mapping.tsv] w]
foreach identity $identities {
 set family [join [lrange [split $identity :] 0 2] :]
 set candidates [get_ipdefs -all -quiet ${family}:*]
 if {![llength $candidates]} {error "No current IP definition for $identity"}
 set replacement [lindex [lsort -dictionary $candidates] end]
 puts $mapping "$identity\t$replacement"
 set recipe [string map [list $identity $replacement] $recipe]
}
close $mapping
set recipe [string map [list "CONFIG.PRIM_IN_FREQ {99.999999}" "CONFIG.PRIM_IN_FREQ {99.999992}"] $recipe]
set migrated [file join $work reconstructed_bd.tcl]
set f [open $migrated w];puts $f $recipe;close $f
source $migrated
}
open_bd_design [get_files system.bd]
validate_bd_design
save_bd_design
source [file join $package build tools audit_contract.tcl]
report_ip_status -file [file join $work ip_after.rpt]
write_bd_tcl -force [file join $work system_2026.tcl]
generate_target all [get_files system.bd]
set wrapper [make_wrapper -files [get_files system.bd] -top -force]
add_files -norecurse $wrapper
set_property top system_wrapper [get_filesets sources_1]
update_compile_order -fileset sources_1
write_project_tcl -force -use_bd_files -no_copy_sources [file join $work project_2026.tcl]
puts "SHENMU_2026_PROJECT_PASS $mode"
if {$step in {synth bit}} {
 launch_runs synth_1 -jobs 1
 wait_on_run synth_1
 if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed"}
 open_run synth_1
 if {[llength [get_cells -hier -filter {IS_BLACKBOX}]]} {error "Unresolved black boxes"}
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
 launch_runs impl_1 -to_step route_design -jobs 1
 wait_on_run impl_1
 if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation failed"}
 open_run impl_1
 report_timing_summary -report_unconstrained -file [file join $work timing.rpt]
 report_drc -file [file join $work drc.rpt]
 report_cdc -details -file [file join $work cdc.rpt]
 report_utilization -file [file join $work utilization.rpt]
 foreach delay {max min} {
  set paths [get_timing_paths -delay_type $delay -max_paths 1]
  if {![llength $paths] || [get_property SLACK $paths]<0} {error "Timing failed: $delay"}
 }
 puts "SHENMU_2026_ROUTE_TIMING_PASS $mode"
}
close_project
} message]} {puts stderr "$message\n$::errorInfo"; exit 1}
exit 0
