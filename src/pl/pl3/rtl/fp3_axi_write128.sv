`timescale 1ns/1ps
// AXI4 writer with 16 independent response slots and an ordered AW-to-W FIFO.
// Input352 = {generation64, tag32, sequence32, words32, byte_address64, data128}.
// Completion160 = {generation64, tag32, sequence32, status32}.
// aresetn resets the physical bus domain. stop/abort are non-canceling controls.
module fp3_axi_write128(
 input wire aclk,aresetn,stop,abort,
 input wire [63:0] arena_base,arena_limit,
 input wire [351:0] s_data,input wire s_valid,output wire s_ready,
 output reg [159:0] m_data=0,output reg m_valid=0,input wire m_ready,
 output wire [31:0] fault,output wire idle,fenced,
 output wire [4:0] allocated_count,issued_count,write_pending,
 output reg [3:0] m_axi_awid=0,output reg [63:0] m_axi_awaddr=0,
 output wire [7:0] m_axi_awlen,output reg [2:0] m_axi_awsize=0,
 output wire [1:0] m_axi_awburst,output wire m_axi_awlock,
 output wire [3:0] m_axi_awcache,output wire [2:0] m_axi_awprot,
 output reg m_axi_awvalid=0,input wire m_axi_awready,
 output wire [127:0] m_axi_wdata,output wire [15:0] m_axi_wstrb,
 output wire m_axi_wlast,m_axi_wvalid,input wire m_axi_wready,
 input wire [3:0] m_axi_bid,input wire [1:0] m_axi_bresp,
 input wire m_axi_bvalid,output wire m_axi_bready
);
 reg [15:0] allocated=0,issued=0,w_done=0,filled=0;
 reg [127:0] identity[0:15],payload[0:15];reg [15:0] strobe[0:15];reg [31:0] status[0:15];
 reg [3:0] w_order[0:15];reg [3:0] w_head=0,w_tail=0;reg [4:0] w_count=0;
 reg [3:0] output_slot=0,free_slot,filled_slot;reg free_found,filled_found;
 reg [4:0] allocated_sum,issued_sum;reg [31:0] fault_q=0;integer i;
 always_comb begin
  free_found=0;filled_found=0;free_slot=0;filled_slot=0;allocated_sum=0;issued_sum=0;
  for(i=15;i>=0;i=i-1)begin
   if(!allocated[i])begin free_found=1;free_slot=i;end
   if(filled[i])begin filled_found=1;filled_slot=i;end
   allocated_sum=allocated_sum+allocated[i];issued_sum=issued_sum+issued[i];
  end
 end
 assign allocated_count=allocated_sum;assign issued_count=issued_sum;assign write_pending=w_count;
 wire [31:0] words=s_data[223:192];wire [63:0] address=s_data[191:128];
 wire [64:0] end_address={1'b0,address}+((words==4)?65'd16:65'd4);
 wire descriptor_bad=(words!=1&&words!=4)||address[1:0]!=0||(words==4&&address[3:0]!=0)||
  arena_limit<=arena_base||address<arena_base||end_address>{1'b0,arena_limit};
 wire b_fire=m_axi_bvalid&&m_axi_bready;
 wire known_response=allocated[m_axi_bid]&&issued[m_axi_bid]&&w_done[m_axi_bid];
 wire [31:0] response_fault=!b_fire?0:!known_response?32'h80000302:m_axi_bresp!=0?32'h80000303:0;
 assign fault=!aresetn?0:fault_q!=0?fault_q:abort?32'h80000304:response_fault;
 assign s_ready=aresetn&&!stop&&!abort&&fault==0&&free_found&&(!m_axi_awvalid||m_axi_awready);
 assign m_axi_awlen=0;assign m_axi_awburst=1;assign m_axi_awlock=0;
 assign m_axi_awcache=4'b0010;assign m_axi_awprot=0;
 assign m_axi_wvalid=aresetn&&w_count!=0;
 assign m_axi_wdata=payload[w_order[w_head]];assign m_axi_wstrb=strobe[w_order[w_head]];assign m_axi_wlast=1;
 assign m_axi_bready=aresetn;
 wire aw_fire=m_axi_awvalid&&m_axi_awready,w_fire=m_axi_wvalid&&m_axi_wready;
 assign idle=aresetn&&allocated==0&&!m_axi_awvalid&&w_count==0&&!m_valid;
 assign fenced=stop&&idle&&fault==0&&!abort;
 always @(posedge aclk)begin
  if(!aresetn)begin
   allocated<=0;issued<=0;w_done<=0;filled<=0;w_head<=0;w_tail<=0;w_count<=0;
   m_valid<=0;m_data<=0;output_slot<=0;fault_q<=0;
   m_axi_awvalid<=0;m_axi_awid<=0;m_axi_awaddr<=0;m_axi_awsize<=0;
  end else begin
   if(fault_q==0&&(abort||response_fault!=0))fault_q<=abort?32'h80000304:response_fault;
   if(m_valid&&m_ready)begin allocated[output_slot]<=0;m_valid<=0;end
   if((!m_valid||m_ready)&&filled_found)begin
    m_data<={identity[filled_slot],status[filled_slot]};output_slot<=filled_slot;m_valid<=1;filled[filled_slot]<=0;
   end
   case({aw_fire,w_fire})
    2'b10:w_count<=w_count+1'b1;
    2'b01:w_count<=w_count-1'b1;
   endcase
   if(aw_fire)begin
    issued[m_axi_awid]<=1;m_axi_awvalid<=0;
    w_order[w_tail]<=m_axi_awid;w_tail<=w_tail+1'b1;
   end
   if(w_fire)begin w_done[w_order[w_head]]<=1;w_head<=w_head+1'b1;end
   if(s_valid&&s_ready)begin
    allocated[free_slot]<=1;w_done[free_slot]<=0;identity[free_slot]<=s_data[351:224];
    payload[free_slot]<=(words==4)?s_data[127:0]:({96'b0,s_data[31:0]}<<(32*address[3:2]));
    strobe[free_slot]<=(words==4)?16'hffff:(16'h000f<<(4*address[3:2]));
    if(descriptor_bad)begin
     status[free_slot]<=32'h80000007;filled[free_slot]<=1;
     if(fault_q==0)fault_q<=32'h80000301;
    end else begin
     m_axi_awid<=free_slot;m_axi_awaddr<=address;m_axi_awsize<=(words==4)?3'd4:3'd2;m_axi_awvalid<=1;
    end
   end
   if(b_fire)begin
    if(!known_response)begin if(fault_q==0)fault_q<=32'h80000302;end
    else begin
     issued[m_axi_bid]<=0;filled[m_axi_bid]<=1;
     status[m_axi_bid]<=m_axi_bresp==0?32'd1:32'h80000007;
     if(m_axi_bresp!=0&&fault_q==0)fault_q<=32'h80000303;
    end
   end
  end
 end
endmodule
