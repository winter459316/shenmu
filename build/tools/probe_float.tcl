if {[catch {
set package [file normalize [lindex $argv 0]]
set work [file normalize [lindex $argv 1]]
file mkdir $work
set_param general.maxThreads 2
create_project float_probe [file join $work project] -part xczu4ev-sfvc784-2-i -force
set_property ip_repo_paths [list [file join $package src pl pl1 ip_repo codex_local_stereo_fast_geometry_1_0]] [current_project]
update_ip_catalog
create_ip -vlnv codex.local:stereo:fast_geometry:1.0 -module_name float_probe
generate_target all [get_ips float_probe]
create_ip_run [get_files float_probe.xci]
launch_runs float_probe_synth_1 -jobs 1
wait_on_run float_probe_synth_1
open_run float_probe_synth_1
set boxes [get_cells -hier -quiet -filter {IS_BLACKBOX}]
if {[llength $boxes]} {error "Float library unresolved: $boxes"}
report_utilization -file [file join $work utilization.rpt]
puts "FLOAT_LIBRARY_SYNTH_PASS"
close_project
} message]} {puts stderr "$message\n$::errorInfo"; exit 1}
exit 0
