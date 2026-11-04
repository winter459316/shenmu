# Run with the current block design open. Verify the legacy software ABI.
proc address_integer {value} {
 if {[regexp {^([0-9]+)([KMGT])$} $value -> number unit]} {
  return [expr {$number*(1024**([string first $unit KMGT]+1))}]
 }
 return [expr {$value+0}]
}
set f [open [file join $src bd legacy_bd.tcl] r];set legacy [read $f];close $f
set addresses [open [file join $work address_contract.tsv] w]
set count 0
foreach line [split $legacy \n] {
 if {[string match #* [string trim $line]]} {continue}
 if {[regexp {create_bd_addr_seg -range (\S+) -offset (\S+) \[get_bd_addr_spaces ([^\]]+)\] \[get_bd_addr_segs ([^\]]+)\] (\S+)} $line -> range offset space target name]} {
  set excluded [expr {[string first "exclude_bd_addr_seg \[get_bd_addr_segs $space/$name\]" $legacy]>=0}]
  if {$excluded} {
   set mapped {}
   foreach seg [get_bd_addr_segs -quiet -excluded -of_objects [get_bd_addr_spaces $space]] {
    if {[string trimleft $seg /] eq "$space/$name"} {lappend mapped $seg}
   }
  } else {set mapped [get_bd_addr_segs -quiet $space/$name]}
  if {[llength $mapped]!=1} {error "Address segment missing: $space/$name"}
  set actual_offset [get_property OFFSET $mapped];set actual_range [get_property RANGE $mapped]
  if {[address_integer $offset]!=[address_integer $actual_offset] || [address_integer $range]!=[address_integer $actual_range]} {error "Address changed: $space/$name"}
  puts $addresses "$space/$name\t$actual_offset\t$actual_range\texcluded=$excluded"
  incr count
 }
}
close $addresses
if {$count<5} {error "Insufficient address contract checks"}
set clocks [open [file join $work clock_contract.tsv] w]
foreach {pin nominal} {ps/pl_clk0 100000000 video_mmcm/clk_out1 375000000 hdmi_clocks/pixel_clk 75000000 hdmi_clocks/serial_clk 375000000} {
 set freq [get_property CONFIG.FREQ_HZ [get_bd_pins $pin]]
 if {$freq eq ""} {set freq [get_property FREQ_HZ [get_bd_pins $pin]]}
 if {$freq eq "" || abs($freq-$nominal)>100} {error "Unexpected clock $pin: $freq"}
 puts $clocks "$pin\t$freq"
}
if {$mode ne "pl1"} {
 set nominal [expr {$mode eq "pl2" ? 115000000 : 160000000}]
 set freq [get_property CONFIG.FREQ_HZ [get_bd_pins compute_clock/clk_out1]]
 if {$freq eq "" || abs($freq-$nominal)>100} {error "Compute clock changed: $freq"}
 puts $clocks "compute_clock/clk_out1\t$freq"
}
close $clocks
if {$mode eq "pl3" && [get_property CONFIG.C_Latency [get_ips fp32_fma]]!=19} {error "FMA latency must remain 19"}
puts "SHENMU_2026_ABI_PASS $mode addresses=$count"
