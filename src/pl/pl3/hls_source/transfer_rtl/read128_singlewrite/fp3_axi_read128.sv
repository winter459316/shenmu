`timescale 1ns/1ps
// 16-slot AXI4 read transport for the exact GEMM wide gather.
// Each request is one aligned 32-bit or 128-bit transfer (ARLEN=0).
// aresetn is a BUS reset: its use requires a reset/isolated downstream fabric.
// stop/abort never cancel an already presented AR or a held client response.
module fp3_axi_read128(
 input wire aclk,aresetn,
 input wire stop,abort,
 input wire [63:0] arena_base,arena_limit,
 input wire [223:0] s_data,input wire s_valid,output wire s_ready,
 output reg [287:0] m_data=0,output reg m_valid=0,input wire m_ready,
 output wire [31:0] fault,output wire idle,fenced,
 output wire [4:0] allocated_count,issued_count,
 output reg [3:0] m_axi_arid=0,output reg [63:0] m_axi_araddr=0,
 output wire [7:0] m_axi_arlen,output reg [2:0] m_axi_arsize=0,
 output wire [1:0] m_axi_arburst,output wire m_axi_arlock,
 output wire [3:0] m_axi_arcache,output wire [2:0] m_axi_arprot,
 output reg m_axi_arvalid=0,input wire m_axi_arready,
 input wire [3:0] m_axi_rid,input wire [127:0] m_axi_rdata,
 input wire [1:0] m_axi_rresp,input wire m_axi_rlast,
 input wire m_axi_rvalid,output wire m_axi_rready
);
 reg [15:0] allocated=0,issued=0,filled=0,bad_burst=0;
 reg [15:0] descriptor_reject=0;
 reg [31:0] fault_q=0;
 reg [127:0] identity[0:15],payload[0:15];
 reg [31:0] status[0:15];
 reg [1:0] lane[0:15];reg [15:0] quad=0;
 reg [3:0] output_slot=0,free_slot,filled_slot;
 reg free_found,filled_found;reg [4:0] allocated_sum,issued_sum;
 integer i;
 always_comb begin
  free_found=0;filled_found=0;free_slot=0;filled_slot=0;
  allocated_sum=0;issued_sum=0;
  for(i=15;i>=0;i=i-1)begin
   if(!allocated[i])begin free_found=1;free_slot=i;end
   if(filled[i])begin filled_found=1;filled_slot=i;end
   allocated_sum=allocated_sum+allocated[i];issued_sum=issued_sum+issued[i];
  end
 end
 assign allocated_count=allocated_sum;assign issued_count=issued_sum;
 wire [31:0] words=s_data[95:64];
 wire [64:0] end_address={1'b0,s_data[63:0]}+((words==4)?65'd16:65'd4);
 wire descriptor_bad=(words!=1&&words!=4)||s_data[1:0]!=0||
  (words==4&&s_data[3:0]!=0)||arena_limit<=arena_base||
  s_data[63:0]<arena_base||end_address>{1'b0,arena_limit};
 assign s_ready=aresetn&&!stop&&!abort&&fault==0&&free_found&&(!m_axi_arvalid||m_axi_arready);
 assign m_axi_arlen=0;assign m_axi_arburst=2'b01;assign m_axi_arlock=0;
 assign m_axi_arcache=4'b0010;assign m_axi_arprot=0;
 // Every issued read already owns a completion slot, so R never depends on
 // the client's readiness. An unexpected R is consumed, diagnosed, not stored.
 assign m_axi_rready=aresetn;
 assign idle=aresetn&&allocated==0&&!m_axi_arvalid&&!m_valid;
 assign fenced=stop&&idle&&fault==0&&!abort;
 wire r_fire=m_axi_rvalid&&m_axi_rready;
 wire known_response=allocated[m_axi_rid]&&issued[m_axi_rid];
 wire [127:0] shifted_payload=m_axi_rdata>>(32*lane[m_axi_rid]);
 wire [127:0] selected_payload=quad[m_axi_rid]?m_axi_rdata:{96'b0,shifted_payload[31:0]};
 wire [31:0] response_fault=!r_fire?32'b0:!known_response?32'h80000202:
  m_axi_rresp!=0?32'h80000203:!m_axi_rlast?32'h80000202:32'b0;
 assign fault=!aresetn?32'b0:fault_q!=0?fault_q:abort?32'h80000204:response_fault;
 always @(posedge aclk)begin
  if(!aresetn)begin
   allocated<=0;issued<=0;filled<=0;bad_burst<=0;quad<=0;descriptor_reject<=0;
   m_valid<=0;m_data<=0;output_slot<=0;fault_q<=0;
   m_axi_arvalid<=0;m_axi_arid<=0;m_axi_araddr<=0;m_axi_arsize<=0;
  end else begin
   if(fault_q==0&&(abort||response_fault!=0))fault_q<=abort?32'h80000204:response_fault;
   if(m_valid&&m_ready)begin allocated[output_slot]<=0;m_valid<=0;end
   if((!m_valid||m_ready)&&filled_found)begin
    m_data<={identity[filled_slot],status[filled_slot],(descriptor_reject[filled_slot]?128'b0:payload[filled_slot])};
    output_slot<=filled_slot;m_valid<=1;filled[filled_slot]<=0;
   end
   if(m_axi_arvalid&&m_axi_arready)begin
    issued[m_axi_arid]<=1;m_axi_arvalid<=0;
   end
   if(s_valid&&s_ready)begin
    allocated[free_slot]<=1;bad_burst[free_slot]<=0;descriptor_reject[free_slot]<=descriptor_bad;
    identity[free_slot]<=s_data[223:96];lane[free_slot]<=s_data[3:2];quad[free_slot]<=words==4;
    if(descriptor_bad)begin
     status[free_slot]<=32'h80000007;filled[free_slot]<=1;
     if(fault_q==0)fault_q<=32'h80000201;
    end else begin
     m_axi_arid<=free_slot;m_axi_araddr<=s_data[63:0];m_axi_arsize<=(words==4)?3'd4:3'd2;m_axi_arvalid<=1;
    end
   end
   if(r_fire)begin
    if(!known_response)begin
     if(fault_q==0)fault_q<=32'h80000202;
    end else begin
     if(!m_axi_rlast||m_axi_rresp!=0)begin
      bad_burst[m_axi_rid]<=1;
      if(fault_q==0)fault_q<=m_axi_rresp!=0?32'h80000203:32'h80000202;
     end
     // Never claim a malformed burst drained until its actual RLAST arrives.
     if(m_axi_rlast)begin
      issued[m_axi_rid]<=0;filled[m_axi_rid]<=1;
      status[m_axi_rid]<=(bad_burst[m_axi_rid]||m_axi_rresp!=0)?32'h80000007:32'd1;
      payload[m_axi_rid]<=selected_payload;
     end
    end
   end
  end
 end
endmodule
