`timescale 1ns/1ps
// Linux's existing gpio-keys bindings use EMIO 0 and 1 for PL_KEY1/2.
// Unconnected active-low factory keys stay released, including EMIO3/9.
module usb_pl_keys (
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 clk CLK", X_INTERFACE_PARAMETER="XIL_INTERFACENAME clk, FREQ_HZ 99999992, ASSOCIATED_RESET resetn" *) input wire clk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 resetn RST", X_INTERFACE_PARAMETER="XIL_INTERFACENAME resetn, POLARITY ACTIVE_LOW" *) input wire resetn,
    input wire key1_n,
    input wire key2_n,
    output wire [9:0] emio_input
);
    wire filtered1, filtered2;
    key_debounce k1 (.sys_clk(clk), .sys_rst_n(resetn), .key(key1_n), .key_filter(filtered1));
    key_debounce k2 (.sys_clk(clk), .sys_rst_n(resetn), .key(key2_n), .key_filter(filtered2));
    assign emio_input = {8'hff, filtered2, filtered1};
endmodule
