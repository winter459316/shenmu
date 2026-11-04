// Raw Conv tile: validate geometry -> direct window fill/GEMM -> output B fence.
// Switching the internal owner does not reconfigure PL and is not a CPU-cache fence.
module fp3_conv48_capture #(parameter LANES=4)(
 input wire aclk,aresetn,abort,
 input wire [687:0] expand_command,
 input wire [319:0] gemm_command,
 input wire [31:0] output_row_stride_words,
 input wire [63:0] output_base_byte,job_epoch,
 input wire cmd_valid,output wire cmd_ready,
 output wire done,output wire [31:0] fault,output wire transport_drained,
 output wire fault_active,
 output reg [63:0] result_epoch=0,output reg [31:0] result_tag=0,
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
/* OBSERVER_BEGIN */, output wire [511:0] debug_vector/* OBSERVER_END */
);
 localparam IDLE=0,EXPAND_START=1,EXPAND_RUN=2,GEMM_START=3,GEMM_RUN=4,COMPLETE=5,FAILED=6,CHECK1=7,CHECK2=8,CHECK3=9,CHECK4=10;
 reg [3:0] phase=IDLE;reg owner=0;reg [31:0] fault_q=0;
 reg [687:0] expand_saved=0;reg [319:0] gemm_saved=0;
 reg [63:0] output_saved=0;reg [31:0] stride_saved=0;
 wire e_ready,g_ready,e_done,g_done,e_drained,g_drained,e_fault_active,g_fault_active;
 wire [31:0] e_fault,g_fault,e_tag,g_tag;wire [63:0] e_epoch,g_epoch;
 wire [31:0] tag;wire [63:0] src,panel,lo,hi;
 wire [15:0] cin,id,ih,iw,od,oh,ow,kd,kh,kw,sd,sh,sw,dd,dh,dw,pd,ph,pw,kcount,ncount;
 wire [31:0] ks,ns;
 assign {tag,src,panel,lo,hi,cin,id,ih,iw,od,oh,ow,kd,kh,kw,sd,sh,sw,dd,dh,dw,pd,ph,pw,ks,kcount,ns,ncount}=expand_saved;
 reg [63:0] source_xy=0,source_xyz=0,source_words=0;
 wire [64:0] source_end={1'b0,src}+({1'b0,source_words}<<2);
 reg [31:0] panel_words=0;
 wire [64:0] panel_end={1'b0,panel}+({33'b0,panel_words}<<2);
 wire [63:0] a_first={32'b0,gemm_saved[159:128]};
 reg [63:0] a_row_span=0,a_k_span=0,a_last=0;
 reg [63:0] output_span=0,output_words=0;
 wire [64:0] output_end={1'b0,output_saved}+({1'b0,output_words}<<2);
 // Validate both stage identities and every cross-stage source/destination hazard
 // before allowing expansion to write its private panel. The child controllers
 // additionally validate their complete local command geometry and K contracts.
 wire bad=result_epoch==0||tag!=gemm_saved[127:96]||lo[1:0]!=0||hi[1:0]!=0||hi<=lo||
  source_words>64'h40000000||source_end>{1'b0,hi}||src<lo||
  kcount!=gemm_saved[31:16]||ncount!=gemm_saved[15:8]||
  gemm_saved[49:48]!=0||panel[1:0]!=0||panel_end>{1'b0,hi}||panel<lo||
  (panel>>2)!={32'b0,gemm_saved[255:224]}||gemm_saved[287:256]!=ncount||gemm_saved[319:288]!=1||
  stride_saved<gemm_saved[15:8]||output_saved[1:0]!=0||output_saved<lo||output_end>{1'b0,hi}||
  gemm_saved[7:0]==0||gemm_saved[7:0]>32||gemm_saved[15:8]==0||gemm_saved[15:8]>LANES||
  a_first<(lo>>2)||a_last>=(hi>>2)||
  ((panel>>2)<=a_last&&(panel_end>>2)>{1'b0,a_first})||
  (output_saved<source_end&&output_end>{1'b0,src})||
  (output_saved<panel_end&&output_end>{1'b0,panel})||
  ((output_saved>>2)<=a_last&&(output_end>>2)>{1'b0,a_first});
 wire identity_bad=(phase==EXPAND_RUN&&e_done&&(e_epoch!=result_epoch||e_tag!=result_tag))||
  (phase==GEMM_RUN&&g_done&&(g_epoch!=result_epoch||g_tag!=result_tag));
 wire [31:0] fault_now=abort?32'h80000b02:e_fault?e_fault:g_fault?g_fault:identity_bad?32'h80000b03:0;
 assign fault_active=aresetn&&(fault_q!=0||abort||e_fault_active||g_fault_active||identity_bad);
 assign fault=!aresetn?0:fault_q?fault_q:fault_now;
 assign transport_drained=e_drained&&g_drained;
 assign cmd_ready=aresetn&&(phase==IDLE||phase==COMPLETE)&&transport_drained&&e_ready&&g_ready&&!fault_active;
 assign done=aresetn&&phase==COMPLETE&&!fault_active&&transport_drained;
 always @(posedge aclk)begin
  if(!aresetn)begin phase<=IDLE;owner<=0;fault_q<=0;result_epoch<=0;result_tag<=0;end
  else if(fault_q!=0)begin if(!fault_q)fault_q<=fault;phase<=FAILED;end
  else begin
   // Speculative private operands only. Acceptance and public identity below
   // still require full immediate fault/ready validation on this same edge.
   if(cmd_valid&&(phase==IDLE||phase==COMPLETE))begin
    expand_saved<=expand_command;gemm_saved<=gemm_command;output_saved<=output_base_byte;stride_saved<=output_row_stride_words;
   end
   if(cmd_valid&&cmd_ready)begin
    result_epoch<=job_epoch;result_tag<=expand_command[687:656];
    
    owner<=0;phase<=CHECK1;
   end
   if(phase==CHECK1)begin
    source_xy<={48'b0,cin}*id;panel_words<={16'b0,kcount}*ncount;
    a_row_span<={56'b0,(gemm_saved[7:0]-8'd1)}*gemm_saved[191:160];
    a_k_span<={48'b0,(gemm_saved[31:16]-16'd1)}*gemm_saved[223:192];
    output_span<={56'b0,(gemm_saved[7:0]-8'd1)}*{32'b0,stride_saved};phase<=CHECK2;
   end
   if(phase==CHECK2)begin
    source_xyz<=source_xy*ih;a_last<=a_first+a_row_span+a_k_span;
    output_words<=output_span+gemm_saved[15:8];phase<=CHECK3;
   end
   if(phase==CHECK3)begin source_words<=source_xyz*iw;phase<=CHECK4;end
   if(phase==CHECK4)begin
    if(bad)begin fault_q<=32'h80000b01;phase<=FAILED;end
    else phase<=EXPAND_START;
   end
   if(phase==EXPAND_START&&e_ready)phase<=EXPAND_RUN;
   if(phase==EXPAND_RUN&&e_done&&transport_drained&&!fault_active)begin owner<=1;phase<=GEMM_START;end
   if(phase==GEMM_START&&g_ready)phase<=GEMM_RUN;
   if(phase==GEMM_RUN&&g_done&&transport_drained)phase<=COMPLETE;
  
   // Public fault/done remain immediate; discard all private work on this edge.
   if(fault_active)begin if(!fault_q)fault_q<=fault;phase<=FAILED;end
  end
 end
 wire shared_read_stop;
 wire c0_read_stop;
 wire c1_read_stop;
 assign shared_read_stop=owner?c1_read_stop:c0_read_stop;
 wire shared_read_abort;
 wire c0_read_abort;
 wire c1_read_abort;
 assign shared_read_abort=owner?c1_read_abort:c0_read_abort;
 wire [63:0] shared_read_arena_base;
 wire [63:0] c0_read_arena_base;
 wire [63:0] c1_read_arena_base;
 assign shared_read_arena_base=owner?c1_read_arena_base:c0_read_arena_base;
 wire [63:0] shared_read_arena_limit;
 wire [63:0] c0_read_arena_limit;
 wire [63:0] c1_read_arena_limit;
 assign shared_read_arena_limit=owner?c1_read_arena_limit:c0_read_arena_limit;
 wire [223:0] shared_read_s_data;
 wire [223:0] c0_read_s_data;
 wire [223:0] c1_read_s_data;
 assign shared_read_s_data=owner?c1_read_s_data:c0_read_s_data;
 wire shared_read_s_valid;
 wire c0_read_s_valid;
 wire c1_read_s_valid;
 assign shared_read_s_valid=owner?c1_read_s_valid:c0_read_s_valid;
 wire shared_read_s_ready;
 wire [287:0] shared_read_m_data;
 wire shared_read_m_valid;
 wire shared_read_m_ready;
 wire c0_read_m_ready;
 wire c1_read_m_ready;
 assign shared_read_m_ready=owner?c1_read_m_ready:c0_read_m_ready;
 wire [31:0] shared_read_fault;
 wire shared_read_idle;
 wire shared_read_fenced;
 wire [4:0] shared_read_allocated_count;
 wire [4:0] shared_read_issued_count;
 wire shared_write_stop;
 wire c0_write_stop;
 wire c1_write_stop;
 assign shared_write_stop=owner?c1_write_stop:c0_write_stop;
 wire shared_write_abort;
 wire c0_write_abort;
 wire c1_write_abort;
 assign shared_write_abort=owner?c1_write_abort:c0_write_abort;
 wire [63:0] shared_write_arena_base;
 wire [63:0] c0_write_arena_base;
 wire [63:0] c1_write_arena_base;
 assign shared_write_arena_base=owner?c1_write_arena_base:c0_write_arena_base;
 wire [63:0] shared_write_arena_limit;
 wire [63:0] c0_write_arena_limit;
 wire [63:0] c1_write_arena_limit;
 assign shared_write_arena_limit=owner?c1_write_arena_limit:c0_write_arena_limit;
 wire [351:0] shared_write_s_data;
 wire [351:0] c0_write_s_data;
 wire [351:0] c1_write_s_data;
 assign shared_write_s_data=owner?c1_write_s_data:c0_write_s_data;
 wire shared_write_s_valid;
 wire c0_write_s_valid;
 wire c1_write_s_valid;
 assign shared_write_s_valid=owner?c1_write_s_valid:c0_write_s_valid;
 wire shared_write_s_ready;
 wire [159:0] shared_write_m_data;
 wire shared_write_m_valid;
 wire shared_write_m_ready;
 wire c0_write_m_ready;
 wire c1_write_m_ready;
 assign shared_write_m_ready=owner?c1_write_m_ready:c0_write_m_ready;
 wire [31:0] shared_write_fault;
 wire shared_write_idle;
 wire shared_write_fenced;
 wire [4:0] shared_write_allocated_count;
 wire [4:0] shared_write_issued_count;
 wire [4:0] shared_write_write_pending;
 fp3_c48_expand expand(
  .aclk(aclk),
  .aresetn(aresetn),
  .abort((phase==FAILED||abort)),
  .cmd_data(expand_saved),
  .cmd_valid(phase==EXPAND_START&&fault_q==0),
  .cmd_ready(e_ready),
  .job_epoch(result_epoch),
  .done(e_done),
  .fault(e_fault),.fault_active(e_fault_active),
  .transport_drained(e_drained),
  .result_epoch(e_epoch),
  .result_tag(e_tag),
  .unit_read_stop(c0_read_stop),
  .unit_read_abort(c0_read_abort),
  .unit_read_arena_base(c0_read_arena_base),
  .unit_read_arena_limit(c0_read_arena_limit),
  .unit_read_s_data(c0_read_s_data),
  .unit_read_s_valid(c0_read_s_valid),
  .unit_read_s_ready(owner==0?shared_read_s_ready:1'b1),
  .unit_read_m_data(owner==0?shared_read_m_data:288'b0),
  .unit_read_m_valid(owner==0?shared_read_m_valid:1'b0),
  .unit_read_m_ready(c0_read_m_ready),
  .unit_read_fault(owner==0?shared_read_fault:32'b0),
  .unit_read_idle(owner==0?shared_read_idle:1'b1),
  .unit_read_fenced(owner==0?shared_read_fenced:1'b1),
  .unit_read_allocated_count(owner==0?shared_read_allocated_count:5'b0),
  .unit_read_issued_count(owner==0?shared_read_issued_count:5'b0),
  .unit_write_stop(c0_write_stop),
  .unit_write_abort(c0_write_abort),
  .unit_write_arena_base(c0_write_arena_base),
  .unit_write_arena_limit(c0_write_arena_limit),
  .unit_write_s_data(c0_write_s_data),
  .unit_write_s_valid(c0_write_s_valid),
  .unit_write_s_ready(owner==0?shared_write_s_ready:1'b1),
  .unit_write_m_data(owner==0?shared_write_m_data:160'b0),
  .unit_write_m_valid(owner==0?shared_write_m_valid:1'b0),
  .unit_write_m_ready(c0_write_m_ready),
  .unit_write_fault(owner==0?shared_write_fault:32'b0),
  .unit_write_idle(owner==0?shared_write_idle:1'b1),
  .unit_write_fenced(owner==0?shared_write_fenced:1'b1),
  .unit_write_allocated_count(owner==0?shared_write_allocated_count:5'b0),
  .unit_write_issued_count(owner==0?shared_write_issued_count:5'b0),
  .unit_write_write_pending(owner==0?shared_write_write_pending:5'b0));
 fp3_c48_gemm #(.LANES(LANES)) matrix(.window_command(expand_saved),
  .aclk(aclk)/* OBSERVER_BEGIN */,.debug_vector(debug_vector)/* OBSERVER_END */,
  .aresetn(aresetn),
  .abort((phase==FAILED||abort)),
  .cmd_data(gemm_saved),
  .cmd_valid(phase==GEMM_START&&fault_q==0),
  .cmd_ready(g_ready),
  .job_epoch(result_epoch),
  .output_base_byte(output_saved),
  .output_row_stride_words(stride_saved),
  .arena_base_word(expand_saved[527:464]>>2),
  .arena_limit_word(expand_saved[463:400]>>2),
  .done(g_done),
  .fault(g_fault),.fault_active(g_fault_active),
  .transport_drained(g_drained),
  .result_epoch(g_epoch),
  .result_tag(g_tag),
  .unit_read_stop(c1_read_stop),
  .unit_read_abort(c1_read_abort),
  .unit_read_arena_base(c1_read_arena_base),
  .unit_read_arena_limit(c1_read_arena_limit),
  .unit_read_s_data(c1_read_s_data),
  .unit_read_s_valid(c1_read_s_valid),
  .unit_read_s_ready(owner==1?shared_read_s_ready:1'b1),
  .unit_read_m_data(owner==1?shared_read_m_data:288'b0),
  .unit_read_m_valid(owner==1?shared_read_m_valid:1'b0),
  .unit_read_m_ready(c1_read_m_ready),
  .unit_read_fault(owner==1?shared_read_fault:32'b0),
  .unit_read_idle(owner==1?shared_read_idle:1'b1),
  .unit_read_fenced(owner==1?shared_read_fenced:1'b1),
  .unit_read_allocated_count(owner==1?shared_read_allocated_count:5'b0),
  .unit_read_issued_count(owner==1?shared_read_issued_count:5'b0),
  .unit_write_stop(c1_write_stop),
  .unit_write_abort(c1_write_abort),
  .unit_write_arena_base(c1_write_arena_base),
  .unit_write_arena_limit(c1_write_arena_limit),
  .unit_write_s_data(c1_write_s_data),
  .unit_write_s_valid(c1_write_s_valid),
  .unit_write_s_ready(owner==1?shared_write_s_ready:1'b1),
  .unit_write_m_data(owner==1?shared_write_m_data:160'b0),
  .unit_write_m_valid(owner==1?shared_write_m_valid:1'b0),
  .unit_write_m_ready(c1_write_m_ready),
  .unit_write_fault(owner==1?shared_write_fault:32'b0),
  .unit_write_idle(owner==1?shared_write_idle:1'b1),
  .unit_write_fenced(owner==1?shared_write_fenced:1'b1),
  .unit_write_allocated_count(owner==1?shared_write_allocated_count:5'b0),
  .unit_write_issued_count(owner==1?shared_write_issued_count:5'b0),
  .unit_write_write_pending(owner==1?shared_write_write_pending:5'b0));
 wire [287:0] raw_reply;
 wire raw_reply_valid,raw_reply_ready,raw_read_idle,raw_read_fenced;
 wire [1:0] reply_count;
 fp3_request_fifo #(.WIDTH(288)) replies(.aclk(aclk),.aresetn(aresetn),
  .s_data(raw_reply),.s_valid(raw_reply_valid),.s_ready(raw_reply_ready),
  .m_data(shared_read_m_data),.m_valid(shared_read_m_valid),
  .m_ready((phase==FAILED||fault_q!=0)||shared_read_m_ready),.count(reply_count));
 assign shared_read_idle=raw_read_idle&&reply_count==0;
 assign shared_read_fenced=raw_read_fenced&&reply_count==0;
 fp3_axi_read128 reader(
  .aclk(aclk),
  .aresetn(aresetn),
  .stop(shared_read_stop),
  .abort(shared_read_abort),
  .arena_base(shared_read_arena_base),
  .arena_limit(shared_read_arena_limit),
  .s_data(shared_read_s_data),
  .s_valid(shared_read_s_valid),
  .s_ready(shared_read_s_ready),
  .m_data(raw_reply),
  .m_valid(raw_reply_valid),
  .m_ready(raw_reply_ready),
  .fault(shared_read_fault),
  .idle(raw_read_idle),
  .fenced(raw_read_fenced),
  .allocated_count(shared_read_allocated_count),
  .issued_count(shared_read_issued_count),
  .m_axi_arid(m_axi_arid),
  .m_axi_araddr(m_axi_araddr),
  .m_axi_arlen(m_axi_arlen),
  .m_axi_arsize(m_axi_arsize),
  .m_axi_arburst(m_axi_arburst),
  .m_axi_arlock(m_axi_arlock),
  .m_axi_arcache(m_axi_arcache),
  .m_axi_arprot(m_axi_arprot),
  .m_axi_arvalid(m_axi_arvalid),
  .m_axi_arready(m_axi_arready),
  .m_axi_rid(m_axi_rid),
  .m_axi_rdata(m_axi_rdata),
  .m_axi_rresp(m_axi_rresp),
  .m_axi_rlast(m_axi_rlast),
  .m_axi_rvalid(m_axi_rvalid),
  .m_axi_rready(m_axi_rready));
 // Register B-completion identity before client validation.
 wire [159:0] raw_write_reply;
 wire raw_write_reply_valid,raw_write_reply_ready,raw_write_idle,raw_write_fenced;
 wire [1:0] write_reply_count;
 fp3_request_fifo #(.WIDTH(160)) write_replies(.aclk(aclk),.aresetn(aresetn),
  .s_data(raw_write_reply),.s_valid(raw_write_reply_valid),.s_ready(raw_write_reply_ready),
  .m_data(shared_write_m_data),.m_valid(shared_write_m_valid),
  .m_ready((phase==FAILED||fault_q!=0)||shared_write_m_ready),.count(write_reply_count));
 assign shared_write_idle=raw_write_idle&&write_reply_count==0;
 assign shared_write_fenced=raw_write_fenced&&write_reply_count==0;
 fp3_axi_write128 writer(
  .aclk(aclk),
  .aresetn(aresetn),
  .stop(shared_write_stop),
  .abort(shared_write_abort),
  .arena_base(shared_write_arena_base),
  .arena_limit(shared_write_arena_limit),
  .s_data(shared_write_s_data),
  .s_valid(shared_write_s_valid),
  .s_ready(shared_write_s_ready),
  .m_data(raw_write_reply),
  .m_valid(raw_write_reply_valid),
  .m_ready(raw_write_reply_ready),
  .fault(shared_write_fault),
  .idle(raw_write_idle),
  .fenced(raw_write_fenced),
  .allocated_count(shared_write_allocated_count),
  .issued_count(shared_write_issued_count),
  .write_pending(shared_write_write_pending),
  .m_axi_awid(m_axi_awid),
  .m_axi_awaddr(m_axi_awaddr),
  .m_axi_awlen(m_axi_awlen),
  .m_axi_awsize(m_axi_awsize),
  .m_axi_awburst(m_axi_awburst),
  .m_axi_awlock(m_axi_awlock),
  .m_axi_awcache(m_axi_awcache),
  .m_axi_awprot(m_axi_awprot),
  .m_axi_awvalid(m_axi_awvalid),
  .m_axi_awready(m_axi_awready),
  .m_axi_wdata(m_axi_wdata),
  .m_axi_wstrb(m_axi_wstrb),
  .m_axi_wlast(m_axi_wlast),
  .m_axi_wvalid(m_axi_wvalid),
  .m_axi_wready(m_axi_wready),
  .m_axi_bid(m_axi_bid),
  .m_axi_bresp(m_axi_bresp),
  .m_axi_bvalid(m_axi_bvalid),
  .m_axi_bready(m_axi_bready));
endmodule
