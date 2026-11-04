# Behavioral RTL regression with the freshly upgraded 2026.1 FMA simulation IP.
if {[catch {
set package [file normalize [lindex $argv 0]]
set work [file normalize [lindex $argv 1]]
file mkdir $work
set_param general.maxThreads 2
create_project numerical [file join $work project] -part xczu4ev-sfvc784-2-i -force
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set rtl [file join $package src pl pl3 rtl]
add_files -norecurse [glob [file join $rtl *.v] [file join $rtl *.sv]]
import_ip -files [file join $package src pl pl3 ip fp32_fma.xci]
upgrade_ip [get_ips fp32_fma]
if {[get_property CONFIG.C_Latency [get_ips fp32_fma]]!=19} {error "FMA latency changed"}
generate_target simulation [get_ips fp32_fma]
set fixture [file join $package src pl tests pl3]
add_files -fileset sim_1 -norecurse [file join $fixture tb_conv48_shell_v2.sv]
set_property include_dirs [list $fixture] [get_filesets sim_1]
set_property top tb_conv48_shell [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
set simdir [file join $work project numerical.sim sim_1 behav xsim]
file mkdir $simdir
foreach file [glob [file join $fixture *.hex]] {file copy -force $file $simdir}
launch_simulation
close_sim
set f [open [file join $simdir simulate.log] r];set simulation_log [read $f];close $f
if {![regexp {CONV48_SHELL_PASS commands=2 outputs=350 panel_words=1190 negatives=1 fence_stalls=1} $simulation_log] || [regexp {(?i)fatal:|error:} $simulation_log]} {error "RTL control or numerical assertions failed"}
set output [file join $simdir pipeline_outputs.hex]
if {![file exists $output]} {error "No RTL outputs"}
set f [open $output r];set actual [regexp -all -inline {\S+} [read $f]];close $f
set f [open [file join $fixture expected.hex] r];set expected [regexp -all -inline {\S+} [read $f]];close $f
if {[string tolower $actual] ne [string tolower $expected]} {error "RTL output differs from preserved expected values"}
file copy -force $output [file join $work pipeline_outputs.hex]
puts "SHENMU_2026_PL3_NUMERICAL_PASS outputs=[llength $actual]"
close_project
} message]} {puts stderr "$message\n$::errorInfo"; exit 1}
exit 0
