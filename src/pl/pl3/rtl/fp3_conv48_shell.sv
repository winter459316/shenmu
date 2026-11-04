`timescale 1ns/1ps
module fp3_conv48_shell #(parameter LANES=48)(
 input wire aclk,aresetn,
 input wire [11:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
 input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
 input wire s_axi_wvalid,output wire s_axi_wready,
 output wire [1:0] s_axi_bresp,output wire s_axi_bvalid,input wire s_axi_bready,
 input wire [11:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
 output wire [31:0] s_axi_rdata,output wire [1:0] s_axi_rresp,
 output wire s_axi_rvalid,input wire s_axi_rready,
 output wire irq,
 output wire [3:0] m_axi_arid,output wire [63:0] m_axi_araddr,
 output wire [7:0] m_axi_arlen,output wire [2:0] m_axi_arsize,
 output wire [1:0] m_axi_arburst,output wire m_axi_arlock,
 output wire [3:0] m_axi_arcache,output wire [2:0] m_axi_arprot,
 output wire m_axi_arvalid,input wire m_axi_arready,
 input wire [3:0] m_axi_rid,input wire [127:0] m_axi_rdata,
 input wire [1:0] m_axi_rresp,input wire m_axi_rlast,m_axi_rvalid,output wire m_axi_rready,
 output wire [3:0] m_axi_awid,output wire [63:0] m_axi_awaddr,
 output wire [7:0] m_axi_awlen,output wire [2:0] m_axi_awsize,
 output wire [1:0] m_axi_awburst,output wire m_axi_awlock,
 output wire [3:0] m_axi_awcache,output wire [2:0] m_axi_awprot,
 output wire m_axi_awvalid,input wire m_axi_awready,
 output wire [127:0] m_axi_wdata,output wire [15:0] m_axi_wstrb,
 output wire m_axi_wlast,m_axi_wvalid,input wire m_axi_wready,
 input wire [3:0] m_axi_bid,input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,
 output wire m_axi_bready
);
/* OBSERVER_BEGIN */wire [511:0] debug_vector;/* OBSERVER_END */

 wire fault_active;
 wire [687:0] expand_command;wire [319:0] gemm_command;
 wire [31:0] output_row_stride_words;wire [63:0] output_base_byte,job_epoch;
 wire cmd_valid,cmd_ready,abort,done,transport_drained;
 wire [31:0] fault,result_tag;wire [63:0] result_epoch;
 fp3_conv_axil control(.*);
 fp3_conv48_capture #(.LANES(LANES)) compute(.*);
endmodule
