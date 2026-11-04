`timescale 1ns/1ps
// Single outstanding AXI-Lite transaction per direction, independent AW/W.
// Experimental control shell. No address map/board deployment is assigned yet.
// 0x000 ID; 0x004 status; 0x008 fault; 0x00c command (1 start, 2 abort).
// 0x010/014 completion epoch; 0x018 completion tag; 0x020/024 active cycles.
// 0x100..190: 37 full-word descriptor registers, low word first:
// expand[0..21] (word21 high16 reserved), gemm[22..31], output[32..33],
// row stride[34], epoch[35..36]. All words must be initialized before start.
// Descriptor writes only when idle/completed AND transport drained. No soft
// reset: a fault cannot erase outstanding AXI ownership; recover externally.
module fp3_conv_axil(
 input wire aclk,aresetn,
 input wire [11:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
 input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
 input wire s_axi_wvalid,output wire s_axi_wready,
 output reg [1:0] s_axi_bresp=0,output reg s_axi_bvalid=0,input wire s_axi_bready,
 input wire [11:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
 output reg [31:0] s_axi_rdata=0,output reg [1:0] s_axi_rresp=0,
 output reg s_axi_rvalid=0,input wire s_axi_rready,
 output wire [687:0] expand_command,output wire [319:0] gemm_command,
 output wire [31:0] output_row_stride_words,output wire [63:0] output_base_byte,job_epoch,
 output wire cmd_valid,input wire cmd_ready,
 output reg abort=0,input wire done,transport_drained,input wire [31:0] fault,
 input wire fault_active,
 input wire [63:0] result_epoch,input wire [31:0] result_tag,
 output wire irq
/* OBSERVER_BEGIN */, input wire [511:0] debug_vector/* OBSERVER_END */
);
/* OBSERVER_BEGIN */wire [3:0] observer_index=(s_axi_araddr-12'h040)>>2;/* OBSERVER_END */

 localparam IDLE=0,PENDING=1,ACTIVE=2,COMPLETE=3,FAILED=4;
 reg [2:0] state=IDLE;
 reg [31:0] descriptor[0:36];reg [36:0] initialized=0;
 reg [31:0] sticky_fault=0;reg [63:0] complete_epoch=0,cycle_count=0;
 reg [31:0] complete_tag=0;
 reg aw_saved=0,w_saved=0;reg [11:0] address_q=0;
 reg [31:0] data_q=0;reg [3:0] strobe_q=0;
 wire [31:0] visible_fault=sticky_fault!=0?sticky_fault:fault;
 wire visible_fault_active=sticky_fault!=0||fault_active;
 wire editable=(state==IDLE||state==COMPLETE)&&transport_drained&&!visible_fault_active&&!abort;
 // Present the registered pending request without the deep fault cone.
 // The compute endpoint still gates cmd_ready with immediate fault/abort.
 // Thus no faulted request can be accepted; speculative private capture has
 // no memory or public completion side effect. Sticky controller faults
 // enter FAILED with priority and cannot persist in PENDING.
 assign cmd_valid=aresetn&&state==PENDING;
 assign irq=aresetn&&(state==COMPLETE||visible_fault_active||abort);
 assign s_axi_awready=aresetn&&!aw_saved&&!s_axi_bvalid;
 assign s_axi_wready=aresetn&&!w_saved&&!s_axi_bvalid;
 assign s_axi_arready=aresetn&&!s_axi_rvalid;
 genvar g;
 generate for(g=0;g<21;g=g+1)begin:e
  assign expand_command[g*32+:32]=descriptor[g];
 end endgenerate
 assign expand_command[687:672]=descriptor[21][15:0];
 generate for(g=0;g<10;g=g+1)begin:m
  assign gemm_command[g*32+:32]=descriptor[g+22];
 end endgenerate
 assign output_base_byte={descriptor[33],descriptor[32]};
 assign output_row_stride_words=descriptor[34];
 assign job_epoch={descriptor[36],descriptor[35]};
 integer i;
 always @(posedge aclk)begin
  if(!aresetn)begin
   state<=IDLE;abort<=0;sticky_fault<=0;complete_epoch<=0;complete_tag<=0;cycle_count<=0;
   initialized<=0;aw_saved<=0;w_saved<=0;s_axi_bvalid<=0;s_axi_rvalid<=0;
   s_axi_bresp<=0;s_axi_rresp<=0;s_axi_rdata<=0;
   for(i=0;i<37;i=i+1)descriptor[i]<=0;
  end else begin
   if(s_axi_bvalid&&s_axi_bready)s_axi_bvalid<=0;
   if(s_axi_rvalid&&s_axi_rready)s_axi_rvalid<=0;
   if(s_axi_awvalid&&s_axi_awready)begin address_q<=s_axi_awaddr;aw_saved<=1;end
   if(s_axi_wvalid&&s_axi_wready)begin data_q<=s_axi_wdata;strobe_q<=s_axi_wstrb;w_saved<=1;end
   if(cmd_valid&&cmd_ready)state<=ACTIVE;
   if(state==ACTIVE)begin
    cycle_count<=cycle_count+1'b1;
    if(done&&transport_drained)begin
     if(result_epoch!=job_epoch||result_tag!=expand_command[687:656])begin
      sticky_fault<=32'h80000c03;state<=FAILED;
     end else begin complete_epoch<=result_epoch;complete_tag<=result_tag;state<=COMPLETE;end
    end
   end
   if(aw_saved&&w_saved&&!s_axi_bvalid)begin
    aw_saved<=0;w_saved<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
    if(strobe_q==0)begin end // AXI byte-enable no-op, including unknown addresses.
    else if(address_q[1:0]!=0||strobe_q!=4'hf)s_axi_bresp<=2'b10;
    else if(address_q>=12'h100&&address_q<=12'h190)begin
     if(!editable||(address_q==12'h154&&data_q[31:16]!=0))s_axi_bresp<=2'b10;
     else begin descriptor[(address_q-12'h100)>>2]<=data_q;initialized[(address_q-12'h100)>>2]<=1;end
    end else if(address_q==12'h00c)begin
     if(data_q==1)begin
      if(!editable||!(&initialized)||job_epoch==0)s_axi_bresp<=2'b10;
      else begin state<=PENDING;cycle_count<=0;complete_epoch<=0;complete_tag<=0;end
     end else if(data_q==2)begin
      abort<=1;state<=FAILED;if(sticky_fault==0)sticky_fault<=32'h80000c02;
     end else s_axi_bresp<=2'b10;
    end else s_axi_bresp<=2'b10;
   end
   if(s_axi_arvalid&&s_axi_arready)begin
    s_axi_rvalid<=1;s_axi_rresp<=0;s_axi_rdata<=0;
    if(s_axi_araddr[1:0]!=0)s_axi_rresp<=2'b10;
    else if(s_axi_araddr>=12'h100&&s_axi_araddr<=12'h190)s_axi_rdata<=descriptor[(s_axi_araddr-12'h100)>>2];
/* OBSERVER_BEGIN */    else if(s_axi_araddr>=12'h040&&s_axi_araddr<=12'h07c)s_axi_rdata<=debug_vector[observer_index*32+:32];
/* OBSERVER_END */    else case(s_axi_araddr)
/* OBSERVER_BEGIN */     12'h028:s_axi_rdata<=32'h44424731; // DBG1 observer ABI
/* OBSERVER_END */     12'h000:s_axi_rdata<=32'h31435046; // FPC1
     12'h004:s_axi_rdata<={26'b0,(state==PENDING),transport_drained,(visible_fault_active||abort),
                         (state==COMPLETE),(state==PENDING||state==ACTIVE),editable};
     12'h008:s_axi_rdata<=visible_fault;
     12'h010:s_axi_rdata<=complete_epoch[31:0];
     12'h014:s_axi_rdata<=complete_epoch[63:32];
     12'h018:s_axi_rdata<=complete_tag;
     12'h020:s_axi_rdata<=cycle_count[31:0];
     12'h024:s_axi_rdata<=cycle_count[63:32];
     default:s_axi_rresp<=2'b10;
    endcase
   end
   // Core failure has priority over normal completion/start on the same edge.
   if(fault_active)begin if(sticky_fault==0)sticky_fault<=fault;state<=FAILED;end
  end
 end
endmodule
