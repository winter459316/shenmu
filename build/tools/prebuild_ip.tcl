# Build only out-of-context IP runs, reusing a matching 2026.1 cache when given.
if {[catch {
set work [file normalize [lindex $argv 0]]
set mode [lindex $argv 1]
set cache [lindex $argv 2]
set_param general.maxThreads 2
open_project [file join $work project shenmu_${mode}.xpr]
if {$cache ne ""} {config_ip_cache -use_cache_location [file normalize $cache]}
create_ip_run [get_files system.bd]
foreach ip [get_files -quiet *.xci] {
 if {[string first /bd/ $ip]<0} {
  generate_target all $ip
  if {[get_property GENERATE_SYNTH_CHECKPOINT $ip]} {create_ip_run $ip}
 }
}
set todo {}
set total 0
foreach run [get_runs -filter {IS_SYNTHESIS == 1}] {
 if {$run ne "synth_1"} {
  incr total
  if {[get_property PROGRESS $run] ne "100%"} {lappend todo $run}
 }
}
if {$total==0} {error "No out-of-context IP runs were created"}
if {[llength $todo]} {
 launch_runs $todo -jobs 1
 foreach run $todo {
  wait_on_run $run
  if {[get_property PROGRESS $run] ne "100%"} {error "IP synthesis failed: $run"}
 }
}
puts "SHENMU_2026_IP_SYNTH_PASS $mode runs=$total"
close_project
} message]} {puts stderr "$message\n$::errorInfo"; exit 1}
exit 0
