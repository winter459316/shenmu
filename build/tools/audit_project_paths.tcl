set root [string tolower [file normalize [lindex $argv 0]]]
set work [string tolower [file normalize [lindex $argv 1]]]
set vendor [string tolower [file normalize [lindex $argv 2]]]
set output [open [file join $root sim results project_path_audit.tsv] w]
foreach profile {pl1 pl2 pl3} {
 open_project [file join $work $profile project shenmu_${profile}.xpr]
 set count 0
 foreach item [get_files -all -quiet] {
  set file [string tolower [file normalize $item]]
  set allowed 0
  foreach base [list $root $work $vendor] {
   if {[string first ${base}/ ${file}/]==0} {set allowed 1}
  }
  if {!$allowed} {error "Unexpected external dependency: $item"}
  incr count
 }
 puts $output "$profile\t$count\tPASS"
 close_project
}
close $output
puts SHENMU_PORTABLE_PROJECT_PATHS_PASS
exit 0
