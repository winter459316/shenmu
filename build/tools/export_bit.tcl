# Export from a routed checkpoint in a fresh process; no board access.
if {[catch {
set work [file normalize [lindex $argv 0]]
set mode [lindex $argv 1]
set_param general.maxThreads 2
# Process-local workaround for the 2026.1 post-bitgen telemetry collector.
set_param debug.enable_data_collection false
puts "SHENMU_EXPORT_DATA_COLLECTION [get_param debug.enable_data_collection]"
set output [file join $work artifacts]
if {[llength $argv]>2} {set output [file normalize [lindex $argv 2]]}
file mkdir $output
open_checkpoint [file join $work artifacts reviewed_routed.dcp]
puts "CHECKPOINT_READY debug_cores=[llength [get_debug_cores -quiet]]"
set_param debug.enable_data_collection false
write_bitstream -force [file join $output system_wrapper.bit]
if {![file exists [file join $output system_wrapper.bit]]} {error "Bitstream missing"}
puts "SHENMU_2026_BIT_EXPORT_PASS $mode"
close_design
} message]} {puts stderr "$message\n$::errorInfo";exit 1}
exit 0
