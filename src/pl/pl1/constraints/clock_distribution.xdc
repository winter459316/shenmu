# Balance the related MMCM output clocks, including OSERDESE3 CLK/CLKDIV.
# This is a physical routing constraint, not a timing exception.
set hdmi_clock_pins [get_pins -hier -filter {NAME =~ */hdmi_clocks/inst/pixel_buffer/O || NAME =~ */hdmi_clocks/inst/serial_div_buffer/O || NAME =~ */hdmi_clocks/inst/serial_buffer/O}]
set_property CLOCK_DELAY_GROUP hdmi_related_clocks [get_nets -of_objects $hdmi_clock_pins]
