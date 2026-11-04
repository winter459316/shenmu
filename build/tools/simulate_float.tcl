if {[catch {
set package [file normalize [lindex $argv 0]]
set work [file normalize [lindex $argv 1]]
open_project [file join $work project float_probe.xpr]
set_property simulator_language Mixed [current_project]
set fixture [file join $package src pl tests float]
add_files -fileset sim_1 -norecurse [glob [file join $package src pl pl1 ip_repo shenmu_stereo_fast_geometry_1_0 hdl ip *.vhd]]
add_files -fileset sim_1 -norecurse [file join $fixture tb_float.sv]
set_property top tb_float [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set_property -name xsim.elaborate.xelab.more_options -value {-L floating_point_v7_1_22} -objects [get_filesets sim_1]
set simdir [file join $work project float_probe.sim sim_1 behav xsim]
file mkdir $simdir
foreach file [glob [file join $fixture *.hex]] {file copy -force $file $simdir}
launch_simulation
close_sim
set f [open [file join $simdir simulate.log] r];set result [read $f];close $f
if {![string match {*FLOAT_NUMERICAL_PASS operators=6 cases=128 results=768*} $result] || [regexp {(?i)fatal:|error:} $result]} {error "Floating-point assertions failed"}
puts "SHENMU_2026_FLOAT_NUMERICAL_PASS results=768"
close_project
} message]} {puts stderr "$message\n$::errorInfo"; exit 1}
exit 0
