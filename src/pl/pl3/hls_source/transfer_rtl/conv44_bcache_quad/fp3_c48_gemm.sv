`timescale 1ns/1ps
// Exact affine GEMM through real AXI4 read/write transports. No PS arithmetic.
// All output addresses MUST refer to private staging storage. Publish only
// when done && fault==0 with matching result_epoch/result_tag. This local
// completion is not a CPU-cache fence nor permission to reset other masters.
module fp3_c48_gemm #(parameter LANES=4)(
 input wire aclk,aresetn,abort,
 input wire [687:0] window_command,
 input wire [31:0] output_row_stride_words,
 input wire [319:0] cmd_data,input wire cmd_valid,output wire cmd_ready,
 input wire [63:0] job_epoch,output_base_byte,arena_base_word,arena_limit_word,
 output wire done,output wire [31:0] fault,output wire transport_drained,
 output wire fault_active,
 output reg [63:0] result_epoch=0,output reg [31:0] result_tag=0,
 output wire unit_read_stop,
 output wire unit_read_abort,
 output wire [63:0] unit_read_arena_base,
 output wire [63:0] unit_read_arena_limit,
 output wire [223:0] unit_read_s_data,
 output wire unit_read_s_valid,
 input wire unit_read_s_ready,
 input wire [287:0] unit_read_m_data,
 input wire unit_read_m_valid,
 output wire unit_read_m_ready,
 input wire [31:0] unit_read_fault,
 input wire unit_read_idle,
 input wire unit_read_fenced,
 input wire [4:0] unit_read_allocated_count,
 input wire [4:0] unit_read_issued_count,
 output wire unit_write_stop,
 output wire unit_write_abort,
 output wire [63:0] unit_write_arena_base,
 output wire [63:0] unit_write_arena_limit,
 output wire [351:0] unit_write_s_data,
 output wire unit_write_s_valid,
 input wire unit_write_s_ready,
 input wire [159:0] unit_write_m_data,
 input wire unit_write_m_valid,
 output wire unit_write_m_ready,
 input wire [31:0] unit_write_fault,
 input wire unit_write_idle,
 input wire unit_write_fenced,
 input wire [4:0] unit_write_allocated_count,
 input wire [4:0] unit_write_issued_count,
 input wire [4:0] unit_write_write_pending
/* OBSERVER_BEGIN */, output wire [511:0] debug_vector/* OBSERVER_END */
);
 localparam IDLE=0,START=1,RUN=2,DRAIN=3,COMPLETE=4,FAILED=5,CHECK1=6,CHECK2=7,CHECK3=8,CHECK4=9;
 reg [3:0] phase=IDLE;reg [319:0] saved_cmd=0;
 reg [63:0] owned_base_word=0,owned_limit_word=0,next_output_byte=0,row_step_byte=0;
 reg [15:0] expected_cells=0,core_cells=0,write_sent=0,write_received=0;
 reg [7:0] columns=0;reg [15:0] output_row=0,output_col=0;
 reg [31:0] fault_q=0;localparam MAX_CELLS=32*LANES, ACK_INDEX_W=$clog2(MAX_CELLS);
 reg [MAX_CELLS-1:0] writes_acked=0;
 reg [63:0] output_saved=0,a_row_span=0,a_k_span=0,b_k_span=0,b_col_span=0,output_row_span=0;
 reg [31:0] stride_saved=0;
 wire [63:0] a_first={32'b0,saved_cmd[159:128]},b_first={32'b0,saved_cmd[255:224]};
 reg [63:0] a_last=0;
 reg [63:0] b_last=0;
 reg [63:0] cells=0;
 reg [63:0] output_span_words=0;
 reg [64:0] output_end=0;
 wire [63:0] output_first_word=output_saved>>2;
 wire [64:0] output_end_word=output_end>>2;
 wire descriptor_bad=stride_saved<saved_cmd[15:8]||result_epoch==0||saved_cmd[7:0]==0||saved_cmd[7:0]>32||saved_cmd[15:8]==0||saved_cmd[15:8]>LANES||
  saved_cmd[31:16]==0||owned_limit_word<=owned_base_word||owned_limit_word>=64'h4000000000000000||
  output_saved[1:0]!=0||output_first_word<owned_base_word||output_end_word>{1'b0,owned_limit_word}||
  (output_first_word<=a_last&&output_end_word>{1'b0,a_first})||
  (output_first_word<=b_last&&output_end_word>{1'b0,b_first});
 wire core_ready,core_out_valid,core_out_ready,core_out_last,core_fault;
 wire [127:0] core_out;wire [223:0] read_req;wire read_req_valid,read_req_ready;
 wire [287:0] read_rsp;wire read_rsp_valid,read_rsp_ready;
 reg pending_write=0;reg [351:0] write_req=0;wire write_req_ready;
 // Request identities count physical packets, independently of accepted Y cells.
 // Never pack across a row, alignment boundary, or descriptor. An incomplete
 // packet stays private and is discarded on immediate fault/abort.
 reg [15:0] write_queued=0;
 reg [1:0] pack_count=0;
 reg [95:0] pack_data=0;
 reg [63:0] pack_base=0;
 wire begin_quad=next_output_byte[3:0]==0&&{1'b0,output_col}+9'd4<={1'b0,columns};
 wire [159:0] write_rsp;wire write_rsp_valid;
 wire [31:0] read_fault,write_fault;wire read_idle,write_idle,read_fenced,write_fenced;
 wire [4:0] rd_alloc,rd_issued,wr_alloc,wr_issued,wr_queue;
 wire [31:0] reply_seq=write_rsp[63:32];
 wire write_reply_bad=write_rsp_valid&&(write_rsp[159:96]!=result_epoch||write_rsp[95:64]!=result_tag||
  write_rsp[31:0]!=1||reply_seq>=expected_cells||reply_seq>=write_sent||writes_acked[reply_seq[ACK_INDEX_W-1:0]]);
 wire core_output_bad=phase==RUN&&core_out_valid&&(core_out[127:96]!=result_tag||core_out[63:32]!=1||
  core_out[95:64]!={output_row,output_col}||core_out_last!=(core_cells+1==expected_cells));
 wire [31:0] fault_now=abort?32'h80000404:read_fault!=0?read_fault:write_fault!=0?write_fault:
  core_fault?32'h80000402:write_reply_bad?32'h80000403:core_output_bad?32'h80000405:32'b0;
 assign fault_active=aresetn&&(fault_q!=0||abort||read_fault!=0||write_fault!=0||core_fault||write_reply_bad||core_output_bad);
 assign fault=!aresetn?0:fault_q!=0?fault_q:fault_now;
 assign done=aresetn&&phase==COMPLETE&&!fault_active;
 assign transport_drained=read_idle&&write_idle;
 assign cmd_ready=aresetn&&(phase==IDLE||phase==COMPLETE)&&!fault_active&&transport_drained&&core_ready;
 wire read_stop=phase!=START&&phase!=RUN;
 wire write_stop=phase==IDLE||phase==COMPLETE||phase==FAILED||(phase==DRAIN&&pack_count==0&&!pending_write&&write_sent==write_queued);
 // On failure, accepted physical reads/writes still drain. The private source
 // stream may be discarded by abort; public AXI valids remain stable in adapters.
 // Private arithmetic may retire one more result on the fault-detection edge.
 // Bookkeeping/write admission already prioritizes immediate fault, so that
 // result is discarded. Public done/fault and adapter AXI fences stay immediate.
 assign core_out_ready=phase==FAILED?1'b1:phase==RUN&&fault_q==0&&(!pending_write||write_req_ready);
 wire read_sink_ready=phase==FAILED?1'b1:read_rsp_ready;
 wire core_rsp_valid=read_rsp_valid&&phase!=FAILED;
 fp3_gemm_wide #(.LANES(LANES),.PREFETCH(1)) core(.window_command(window_command),.external_abort(abort||phase==FAILED),
  .aclk(aclk)/* OBSERVER_BEGIN */,.debug_vector(debug_vector)/* OBSERVER_END */,.aresetn(aresetn),.s_cmd_tdata(saved_cmd),.s_cmd_tvalid(phase==START&&fault_q==0),.s_cmd_tready(core_ready),
  .arena_base_word(owned_base_word),.arena_limit_word(owned_limit_word),
  .m_read_tdata(read_req),.m_read_tvalid(read_req_valid),.m_read_tready(read_req_ready),
  .s_read_tdata(read_rsp),.s_read_tvalid(core_rsp_valid),.s_read_tready(read_rsp_ready),
  .m_axis_tdata(core_out),.m_axis_tvalid(core_out_valid),.m_axis_tready(core_out_ready),.m_axis_tlast(core_out_last),.fault(core_fault));


 always @(posedge aclk)begin
  if(!aresetn)begin
   phase<=IDLE;saved_cmd<=0;owned_base_word<=0;owned_limit_word<=0;next_output_byte<=0;row_step_byte<=0;expected_cells<=0;
   core_cells<=0;write_sent<=0;write_received<=0;columns<=0;output_row<=0;output_col<=0;
   fault_q<=0;writes_acked<=0;pending_write<=0;write_req<=0;result_epoch<=0;result_tag<=0;
   write_queued<=0;pack_count<=0;pack_data<=0;pack_base<=0;
  end else if(fault_q!=0)begin
   if(fault_q==0)fault_q<=fault;phase<=FAILED;pending_write<=0;pack_count<=0;
  end else begin
   // Speculative private operands only. Acceptance and public identity below
   // still require full immediate fault/ready validation on this same edge.
   if(cmd_valid&&(phase==IDLE||phase==COMPLETE))begin
    saved_cmd<=cmd_data;owned_base_word<=arena_base_word;owned_limit_word<=arena_limit_word;
    output_saved<=output_base_byte;stride_saved<=output_row_stride_words;
   end
   if(cmd_valid&&cmd_ready)begin
    result_epoch<=job_epoch;result_tag<=cmd_data[127:96];
    
    next_output_byte<=output_base_byte;
    core_cells<=0;write_sent<=0;write_received<=0;output_row<=0;output_col<=0;writes_acked<=0;phase<=CHECK1;
    write_queued<=0;pack_count<=0;pack_data<=0;pack_base<=0;
   end
   if(phase==CHECK1)begin
    a_row_span<={56'b0,(saved_cmd[7:0]-8'd1)}*saved_cmd[191:160];
    a_k_span<={48'b0,(saved_cmd[31:16]-16'd1)}*saved_cmd[223:192];
    b_k_span<={48'b0,(saved_cmd[31:16]-16'd1)}*saved_cmd[287:256];
    b_col_span<={56'b0,(saved_cmd[15:8]-8'd1)}*saved_cmd[319:288];
    output_row_span<={56'b0,(saved_cmd[7:0]-8'd1)}*{32'b0,stride_saved};
    cells<={56'b0,saved_cmd[7:0]}*{56'b0,saved_cmd[15:8]};
    row_step_byte<=({32'b0,stride_saved}-{56'b0,saved_cmd[15:8]}+64'd1)<<2;
    columns<=saved_cmd[15:8];phase<=CHECK2;
   end
   if(phase==CHECK2)begin
    a_last<=a_first+a_row_span+a_k_span;b_last<=b_first+b_k_span+b_col_span;
    output_span_words<=output_row_span+{56'b0,saved_cmd[15:8]};phase<=CHECK3;
   end
   if(phase==CHECK3)begin output_end<={1'b0,output_saved}+({1'b0,output_span_words}<<2);phase<=CHECK4;end
   if(phase==CHECK4)begin
    if(descriptor_bad)begin fault_q<=32'h80000401;phase<=FAILED;end
    else begin expected_cells<=cells;phase<=START;end
   end
   if(phase==START&&core_ready)phase<=RUN;
   if(pending_write&&write_req_ready)begin pending_write<=0;write_sent<=write_sent+1'b1;end
   if(core_out_valid&&core_out_ready&&phase==RUN)begin
    if(pack_count!=0)begin
     if(pack_count==3)begin
      write_req<={result_epoch,result_tag,16'b0,write_queued,32'd4,pack_base,core_out[31:0],pack_data};
      pending_write<=1;write_queued<=write_queued+1'b1;pack_count<=0;
     end else begin
      pack_data[pack_count*32+:32]<=core_out[31:0];pack_count<=pack_count+1'b1;
     end
    end else if(begin_quad)begin
     pack_base<=next_output_byte;pack_data[31:0]<=core_out[31:0];pack_count<=1;
    end else begin
     write_req<={result_epoch,result_tag,16'b0,write_queued,32'd1,next_output_byte,96'b0,core_out[31:0]};
     pending_write<=1;write_queued<=write_queued+1'b1;
    end
    next_output_byte<=next_output_byte+(output_col+1==columns?row_step_byte:64'd4);core_cells<=core_cells+1'b1;
    if(output_col+1==columns)begin output_col<=0;output_row<=output_row+1'b1;end else output_col<=output_col+1'b1;
    if(core_out_last)phase<=DRAIN;
   end
   if(write_rsp_valid)begin writes_acked[reply_seq[ACK_INDEX_W-1:0]]<=1;write_received<=write_received+1'b1;end
   if(phase==DRAIN&&read_fenced&&write_fenced&&pack_count==0&&!pending_write&&core_cells==expected_cells&&write_sent==write_queued&&write_received==write_queued)phase<=COMPLETE;
  
   // Public fault/done remain immediate; discard all private work on this edge.
   if(fault_active)begin
   if(fault_q==0)fault_q<=fault;phase<=FAILED;pending_write<=0;pack_count<=0;
  end
  end
 end
 assign unit_read_stop=read_stop;
 assign unit_read_abort=phase==FAILED;
 assign unit_read_arena_base=owned_base_word<<2;
 assign unit_read_arena_limit=owned_limit_word<<2;
 assign unit_read_s_data=read_req;
 assign unit_read_s_valid=read_req_valid;
 assign read_req_ready=unit_read_s_ready;
 assign read_rsp=unit_read_m_data;
 assign read_rsp_valid=unit_read_m_valid;
 assign unit_read_m_ready=read_sink_ready;
 assign read_fault=unit_read_fault;
 assign read_idle=unit_read_idle;
 assign read_fenced=unit_read_fenced;
 assign rd_alloc=unit_read_allocated_count;
 assign rd_issued=unit_read_issued_count;
 assign unit_write_stop=write_stop;
 assign unit_write_abort=phase==FAILED;
 assign unit_write_arena_base=owned_base_word<<2;
 assign unit_write_arena_limit=owned_limit_word<<2;
 assign unit_write_s_data=write_req;
 assign unit_write_s_valid=pending_write&&phase!=FAILED;
 assign write_req_ready=unit_write_s_ready;
 assign write_rsp=unit_write_m_data;
 assign write_rsp_valid=unit_write_m_valid;
 assign unit_write_m_ready=1'b1;
 assign write_fault=unit_write_fault;
 assign write_idle=unit_write_idle;
 assign write_fenced=unit_write_fenced;
 assign wr_alloc=unit_write_allocated_count;
 assign wr_issued=unit_write_issued_count;
 assign wr_queue=unit_write_write_pending;
endmodule
