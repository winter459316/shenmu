`timescale 1ns/1ps
// Related HDMI clocks share one MMCM output. Parallel global buffers avoid
// the MMCM-output skew seen at OSERDESE3 CLK and CLKDIV on this device.
module video_clock_tree (
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 clk_in CLK", X_INTERFACE_PARAMETER="XIL_INTERFACENAME clk_in, FREQ_HZ 374999970" *) input wire clk_in,
    input wire locked,
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 pixel_clk CLK", X_INTERFACE_PARAMETER="XIL_INTERFACENAME pixel_clk, FREQ_HZ 74999994" *) output wire pixel_clk,
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 serial_div_clk CLK", X_INTERFACE_PARAMETER="XIL_INTERFACENAME serial_div_clk, FREQ_HZ 187499985" *) output wire serial_div_clk,
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 serial_clk CLK", X_INTERFACE_PARAMETER="XIL_INTERFACENAME serial_clk, FREQ_HZ 374999970" *) output wire serial_clk
);
    BUFGCE serial_buffer (.I(clk_in), .CE(1'b1), .O(serial_clk));
    BUFGCE_DIV #(.BUFGCE_DIVIDE(2)) serial_div_buffer (
        .I(clk_in), .CE(1'b1), .CLR(~locked), .O(serial_div_clk));
    BUFGCE_DIV #(.BUFGCE_DIVIDE(5)) pixel_buffer (
        .I(clk_in), .CE(1'b1), .CLR(~locked), .O(pixel_clk));
endmodule
