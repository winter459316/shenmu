# Verified MPSoC-P4 HDMI and physical PL buttons; no DVP camera pins.
set_property -dict {PACKAGE_PIN G3 IOSTANDARD LVDS} [get_ports {TMDS_tmds_data_p[2]}]
set_property -dict {PACKAGE_PIN F2 IOSTANDARD LVDS} [get_ports {TMDS_tmds_data_p[1]}]
set_property -dict {PACKAGE_PIN G1 IOSTANDARD LVDS} [get_ports {TMDS_tmds_data_p[0]}]
set_property -dict {PACKAGE_PIN E1 IOSTANDARD LVDS} [get_ports TMDS_tmds_clk_p]
set_property -dict {PACKAGE_PIN AD11 IOSTANDARD LVCMOS33 PULLUP true} [get_ports pl_key1_n]
set_property -dict {PACKAGE_PIN AD10 IOSTANDARD LVCMOS33 PULLUP true} [get_ports pl_key2_n]
# Mechanical button inputs are asynchronous; only their first synchronizer
# stages are excepted. ASYNC_REG keeps each actual two-flop chain together.
set key_first_stages [get_cells -hier -filter {NAME =~ */pl_keys/inst/k*/key_d0_reg}]
set_false_path -from [get_ports {pl_key1_n pl_key2_n}] -to [get_pins -of_objects $key_first_stages -filter {REF_PIN_NAME == D}]
