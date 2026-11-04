// PL-managed affine gather and <=128-word K chunks; MLAS boundaries unchanged.
module fp3_gemm_wide #(parameter LANES=4, parameter PREFETCH=1)(
 input wire aclk,aresetn,external_abort,
 input wire [687:0] window_command,
 input wire [319:0] s_cmd_tdata,input wire s_cmd_tvalid,output wire s_cmd_tready,
 input wire [63:0] arena_base_word,arena_limit_word,
 output wire [223:0] m_read_tdata,output wire m_read_tvalid,input wire m_read_tready,
 input wire [287:0] s_read_tdata,input wire s_read_tvalid,output wire s_read_tready,
 output wire [127:0] m_axis_tdata,output wire m_axis_tvalid,input wire m_axis_tready,
 output wire m_axis_tlast,output wire fault
/* OBSERVER_BEGIN */, output wire [511:0] debug_vector/* OBSERVER_END */
);
/* OBSERVER_BEGIN */wire [415:0] observer_gather;
wire [31:0] observer_flags={16'd0,producer_state,state,3'd0,cache_nonfinite,gather_reject,gather_fault,output_overflow,array_fault,external_abort};
assign debug_vector={error_status,gather_status,observer_flags,observer_gather};/* OBSERVER_END */

 // command low->high: rows8,cols8,K16,Kstride16,flags8,reserved8,alpha32,tag32.
 // flags: bit0 packed, bit1 source transB, bit2 finite GEMV (rows=1, alpha=1, Kstride=K).
 // Kstride is from the ORIGINAL MLAS thread partition, never the lane tile.
 localparam IDLE=0,START=1,CHUNK_PREP=2,LOAD_START=3,FETCH=4,ISSUE=5,DRAIN=6,
            MERGE_REQ=7,LOAD_WAIT=8,OUTPUT_C=9,ERROR_RSP=10,LOCKED=11,ERROR_DRAIN=12,VALIDATE_MUL=13,VALIDATE_SUM=14,VALIDATE_END=15,VALIDATE_CHECK=16;
 reg [4:0] state=IDLE;
 reg [7:0] rows=0,cols=0;
 reg [15:0] k_total=0,k_stride=0,block_start=0,block_count=0,k_offset=0,chunk_start=0;
 reg [7:0] chunk_count=0;
 reg [31:0] alpha=0,tag=0,a_index=0;
 reg [31:0] a_base=0,a_rs=0,a_ks=0,b_base=0,b_ks=0,b_cs=0;
 reg [7:0] row=0,merge_row=0,merge_col=0;
 reg [7:0] response_row=0,response_col=0;
 wire [LANES-1:0] merge_lane_retired;
 reg [LANES-1:0] merge_lane_sent=0;
 reg [5:0] merge_expected_row[0:LANES-1];
 wire merge_mode=state==MERGE_REQ;
 wire [LANES*32-1:0] merge_seed;
 wire merge_issue_complete=merge_row<rows&&(&(merge_lane_sent|array_take|~active_mask));
 wire [LANES-1:0] merge_reply_bad_lane;
 wire merge_reply_bad=|merge_reply_bad_lane;
 reg [15:0] received=0;
 reg [LANES-1:0] sent=0;
 reg invalid_input=0,lock_after_error=0,arithmetic_started=0,output_error_pending=0;
 reg [31:0] error_status=0;
 // This counter deliberately survives logical reset. Full FPGA configuration
 // initializes it; the external transport must be torn down for reconfiguration.
 reg [63:0] generation_counter=0,active_generation=0;
 reg previous_resetn=0;
 wire command_accept=s_cmd_tvalid&&s_cmd_tready;
 always @(posedge aclk)begin
  previous_resetn<=aresetn;
  if((previous_resetn&&!aresetn)||command_accept)
   if(generation_counter!=64'hffffffffffffffff)generation_counter<=generation_counter+1;
 end
 wire [31:0] a_word;
 wire [LANES*32-1:0] b_words;
 wire [LANES*32-1:0] partial_values,prior_values;
 // Four validation stages remove the multiply/add/range chain from
 // command acceptance. No memory request or MAC starts before VALIDATE_CHECK.
 reg header_bad_q=0,nonfinite_q=0,generation_exhausted_q=0;
 reg [63:0] a_row_product=0,a_k_product=0,b_k_product=0,b_col_product=0;
 reg [63:0] a_span=0,b_span=0,cmd_a_last=0,cmd_b_last=0;
 wire range_bad=owned_upper<=owned_lower||owned_upper>64'h4000000000000000||
  {32'b0,a_base}<owned_lower||{32'b0,b_base}<owned_lower||cmd_a_last>=owned_upper||cmd_b_last>=owned_upper;
 wire command_bad=header_bad_q||range_bad;
 wire command_nonfinite=nonfinite_q;
 wire header_bad=s_cmd_tdata[7:0]==0||s_cmd_tdata[7:0]>32||
  s_cmd_tdata[15:8]==0||s_cmd_tdata[15:8]>LANES||s_cmd_tdata[31:16]==0||
  s_cmd_tdata[63:56]!=0||
  s_cmd_tdata[55:51]!=0||
  (s_cmd_tdata[50]&&(s_cmd_tdata[7:0]!=1||s_cmd_tdata[49:48]!=0||s_cmd_tdata[95:64]!=32'h3f800000||s_cmd_tdata[47:32]!=s_cmd_tdata[31:16]))||
  (!s_cmd_tdata[50]&&!(s_cmd_tdata[47:32]==4||s_cmd_tdata[47:32]==16||s_cmd_tdata[47:32]==32||s_cmd_tdata[47:32]==64||
    s_cmd_tdata[47:32]==128||s_cmd_tdata[47:32]==256||
    s_cmd_tdata[47:32]==512||s_cmd_tdata[47:32]==1024))||
  (s_cmd_tdata[48]&&s_cmd_tdata[47:32]!=256);
 wire gather_ready,gather_done,gather_fault,gather_reject,cache_write,cache_b;
 wire [31:0] gather_status,gather_reject_status;wire [127:0] cache_data;wire [12:0] cache_index;
 wire [2:0] cache_count;wire cache_bank;wire [15:0] cache_chunk;
 localparam P_IDLE=0,P_FREE=1,P_START=2,P_WAIT=3;
 reg [1:0] producer_state=P_IDLE;
 reg load_bank=0,compute_bank=0;
 reg [15:0] producer_k=0;
 reg [7:0] producer_len=0;
 reg [1:0] bank_ready=0,bank_bad=0;
 reg [15:0] bank_start[0:1];reg [7:0] bank_length[0:1];
 reg [63:0] owned_lower=0,owned_upper=0;
 wire producer_stop=state==ERROR_DRAIN||state==ERROR_RSP||state==LOCKED||gather_fault||gather_reject||array_fault||output_overflow;
 wire command_start=state==VALIDATE_CHECK&&!command_bad&&!command_nonfinite&&!generation_exhausted_q;
 wire chunk_release=state==ISSUE&&issue_complete&&row+1==rows&&k_offset+1==chunk_count;
 wire [7:0] max_load_len=k_stride<128?k_stride[7:0]:8'd128;
 wire [7:0] expected_chunk_len=block_start+block_count-chunk_start>128?8'd128:block_start+block_count-chunk_start;
 wire gather_launch=producer_state==P_START&&!producer_stop;
 reg cache_nonfinite;
 always @*begin
  cache_nonfinite=0;
  for(integer w=0;w<4;w=w+1)if(w<cache_count&&cache_data[w*32+23+:8]==8'hff)cache_nonfinite=1;
 end
 // Capture ownership with the accepted descriptor, never live later ports.
 always @(posedge aclk)if(command_accept)begin
  owned_lower<=arena_base_word;owned_upper<=arena_limit_word;
 end
 // Bank-ready has one owner; simultaneous fill and release affect disjoint banks.
 always @(posedge aclk)begin
  if(!aresetn||command_start)bank_ready<=0;
  else begin
   if(producer_state==P_WAIT&&gather_done)bank_ready[load_bank]<=1;
   if(chunk_release)bank_ready[compute_bank]<=0;
  end
 end
 always @(posedge aclk)begin
  if(!aresetn)begin producer_state<=P_IDLE;bank_bad<=0;load_bank<=0;producer_k<=0;end
  else if(command_start)begin
   producer_state<=P_FREE;bank_bad<=0;load_bank<=0;producer_k<=0;
  end else begin
   if(cache_write&&cache_nonfinite)bank_bad[cache_bank]<=1;
   case(producer_state)
    P_IDLE:producer_state<=P_IDLE;
    P_FREE:begin
     if(producer_stop||producer_k==k_total)producer_state<=P_IDLE;
     else if(!bank_ready[load_bank]&&(PREFETCH||(state==CHUNK_PREP&&producer_k==chunk_start)))begin
      producer_len<=k_total-producer_k<max_load_len?k_total-producer_k:max_load_len;
      producer_state<=P_START;
     end
    end
    P_START:begin
     if(producer_stop)producer_state<=P_IDLE;
     else if(gather_ready)begin bank_bad[load_bank]<=0;producer_state<=P_WAIT;end
    end
    P_WAIT:if(gather_done)begin
     bank_start[load_bank]<=producer_k;bank_length[load_bank]<=producer_len;
     producer_k<=producer_k+producer_len;load_bank<=!load_bank;
     producer_state<=producer_stop?P_IDLE:P_FREE;
    end
   endcase
  end
 end
 wire [63:0] a_chunk_first={32'b0,a_base}+({48'b0,producer_k}*a_ks);
 wire [63:0] b_chunk_first={32'b0,b_base}+({48'b0,producer_k}*b_ks);
 wire [687:0] chunk_window={window_command[687:96],window_command[95:64]+{16'b0,producer_k},8'b0,producer_len,window_command[47:0]};
 // Public fault below remains combinational. Only the private
 // gather cancellation travels through a register; any extra private cache
 // write on the rejecting edge is discarded with this whole command.
 reg window_abort=0;
 always @(posedge aclk)begin
  if(!aresetn)window_abort<=0;
  else window_abort<=external_abort||array_fault||output_overflow||state==ERROR_DRAIN||state==ERROR_RSP||state==LOCKED;
 end
 fp3_gemm_wide_gather gather(.abort(window_abort),.window_command(chunk_window),.aclk(aclk)/* OBSERVER_BEGIN */,.debug_vector(observer_gather)/* OBSERVER_END */,.aresetn(aresetn),
  .start_valid(gather_launch),.capture_valid(producer_state==P_START),.start_ready(gather_ready),.first_chunk(producer_k==0),
  .generation(active_generation),.command_tag(tag),.rows(rows),.cols(cols),.chunk_len(producer_len),
  .fill_bank(load_bank),.chunk_id(producer_k),.arena_base_word(owned_lower),.arena_limit_word(owned_upper),
  .a_first_word(a_chunk_first),.b_first_word(b_chunk_first),
  .a_row_stride(a_rs),.a_k_stride(a_ks),.b_k_stride(b_ks),.b_col_stride(b_cs),
  .m_read_tdata(m_read_tdata),.m_read_tvalid(m_read_tvalid),.m_read_tready(m_read_tready),
  .s_read_tdata(s_read_tdata),.s_read_tvalid(s_read_tvalid),.s_read_tready(s_read_tready),
  .cache_write(cache_write),.cache_b(cache_b),.cache_index(cache_index),.cache_data(cache_data),
  .cache_bank(cache_bank),.cache_chunk(cache_chunk),.cache_count(cache_count),
  .done(gather_done),.fault(gather_fault),.fault_status(gather_status),
  .rejecting_reply(gather_reject),.reject_status(gather_reject_status));
 assign s_cmd_tready=aresetn&&state==IDLE&&!gather_fault&&!gather_reject;
 // Consumer must include !fault in its whole-tile commit condition. This
 // combinational reject indication also covers a bad reply on the final beat.
 assign fault=external_abort||array_fault||output_overflow||gather_fault||gather_reject||state==LOCKED||(state==ERROR_RSP&&lock_after_error);
 // Credit includes the one synchronous BRAM read already in flight.
 // No array ready/hold signal reaches these read enables or read addresses.
 reg [7:0] fetch_row=0,fetch_k=0;
 reg [11:0] fetch_a_index=0;
 reg [12:0] fetched_groups=0;
 wire [15:0] total_groups=rows*chunk_count;
 reg read_pending=0;
 reg [2:0] operand_count=0;
 reg [1:0] operand_head=0,operand_tail=0;
 (* ram_style="distributed" *) reg [LANES*32+31:0] operand_queue[0:3];
 wire [LANES*32+31:0] operand_head_data=operand_queue[operand_head];
 wire operand_pop=state==ISSUE&&issue_complete;
 wire [3:0] operand_reserved={1'b0,operand_count}+read_pending;
 wire a_read_en=aresetn&&(state==FETCH||state==ISSUE)&&fetched_groups<total_groups&&operand_reserved<4;
 wire [31:0] a_read_address={20'b0,fetch_a_index};
 wire b_read_en=a_read_en;
 wire [15:0] b_read_address={8'b0,fetch_k};
 always @(posedge aclk)begin
  if(!aresetn||state==CHUNK_PREP)begin
   fetch_row<=0;fetch_k<=0;fetch_a_index<=0;fetched_groups<=0;
   read_pending<=0;operand_count<=0;operand_head<=0;operand_tail<=0;
  end else begin
   read_pending<=a_read_en;
   if(a_read_en)begin
    fetched_groups<=fetched_groups+1'b1;
    if(fetch_row+1==rows)begin fetch_row<=0;fetch_k<=fetch_k+1'b1;fetch_a_index<={4'b0,fetch_k}+1'b1;end
    else begin fetch_row<=fetch_row+1'b1;fetch_a_index<=fetch_a_index+12'd128;end
   end
   if(read_pending)begin operand_queue[operand_tail]<={b_words,a_word};operand_tail<=operand_tail+1'b1;end
   if(operand_pop)operand_head<=operand_head+1'b1;
   case({read_pending,operand_pop})
    2'b10:operand_count<=operand_count+1'b1;
    2'b01:operand_count<=operand_count-1'b1;
    default:operand_count<=operand_count;
   endcase
  end
 end
 // Four A RAM write banks by K low2 bits; all reads share one aligned address.
 wire [127:0] a_bank_words;reg [1:0] a_select=0;
 always @(posedge aclk)if(a_read_en)a_select<=a_read_address[1:0];
 assign a_word=a_bank_words[a_select*32+:32];
 genvar g;
 generate for(g=0;g<4;g=g+1)begin:a_cache
  (* ram_style="block" *) reg [31:0] a_mem[0:2047];
  reg [31:0] word_out;
  reg write_en;reg [10:0] write_address;reg [31:0] write_data;reg [12:0] index;
  always @*begin
   write_en=0;write_address=0;write_data=0;index=0;
   for(integer w=0;w<4;w=w+1)begin
    index=cache_index+w;
    if(cache_write&&!cache_b&&w<cache_count&&index[1:0]==g)begin
     write_en=1;write_address={cache_bank,index[11:2]};write_data=cache_data[w*32+:32];
    end
   end
  end
  always @(posedge aclk)begin
   if(write_en)a_mem[write_address]<=write_data;
   if(a_read_en)word_out<=a_mem[{compute_bank,a_read_address[11:2]}];
  end
  assign a_bank_words[g*32+:32]=word_out;
 end endgenerate
 generate for(g=0;g<LANES;g=g+1)begin:b_cache
  (* ram_style="block" *) reg [31:0] b_mem[0:255];reg [31:0] b_word;
  wire write_en=cache_write&&cache_b&&g>=cache_index[12:7]&&g<cache_index[12:7]+cache_count;
  wire [31:0] write_data=cache_data[(g-cache_index[12:7])*32+:32];
  always @(posedge aclk)begin
   if(write_en)b_mem[{cache_bank,cache_index[6:0]}]<=write_data;
   if(b_read_en)b_word<=b_mem[{compute_bank,b_read_address[6:0]}];
  end
  assign b_words[g*32+:32]=b_word;
 end endgenerate
 wire [LANES*104-1:0] array_data;
 wire [LANES-1:0] array_valid,array_ready,array_out_valid;
 wire [LANES*64-1:0] array_out_data;
 wire array_fault,array_hold;
 wire [LANES-1:0] array_take=array_valid&array_ready;
 // Decode columns once at admission, before any gather or arithmetic.
 reg [LANES-1:0] active_mask=0;
 generate for(g=0;g<LANES;g=g+1)begin:mask_decode
  always @(posedge aclk)begin
   if(!aresetn)active_mask[g]<=0;
   else if(command_accept)active_mask[g]<=g<s_cmd_tdata[15:8];
  end
 end endgenerate
 wire issue_complete=operand_count!=0&&(&(sent|array_take|~active_mask));
 generate for(g=0;g<LANES;g=g+1)begin:issue_lane
  wire [31:0] part=partial_values[g*32+:32],prior=prior_values[g*32+:32];
  assign merge_seed[g*32+:32]=block_start==0?((part^alpha)&32'h80000000):prior;
  assign array_data[g*104+:104]=merge_mode?
   {24'b0,merge_row,1'b0,1'b1,1'b0,merge_row[4:0],alpha,part}:
   {24'b0,row,1'b0,(chunk_start+k_offset+1==block_start+block_count),
    (chunk_start==block_start&&k_offset==0),row[4:0],operand_head_data[32+g*32+:32],operand_head_data[31:0]};
  assign array_valid[g]=aresetn&&active_mask[g]&&(merge_mode?
   (merge_row<rows&&!merge_lane_sent[g]):(state==ISSUE&&operand_count!=0&&!sent[g]));
  assign merge_lane_retired[g]=!active_mask[g]||merge_expected_row[g]==rows;
  assign merge_reply_bad_lane[g]=merge_mode&&array_out_valid[g]&&
   (!active_mask[g]||array_out_data[g*64+32+:32]!={26'b0,merge_expected_row[g]}||merge_expected_row[g]>=rows);
  always @(posedge aclk)begin
   if(!aresetn||state==DRAIN)merge_expected_row[g]<=0;
   else if(merge_mode&&array_out_valid[g])merge_expected_row[g]<=merge_expected_row[g]+1'b1;
  end
 end endgenerate
 fp3_mac_array #(.LANES(LANES)) dot_array(.aclk(aclk),.aresetn(aresetn),.external_hold(1'b0),
  .use_seed_c({LANES{merge_mode}}),.seed_c(merge_seed),
  .s_axis_tdata(array_data),.s_axis_tvalid(array_valid),.s_axis_tready(array_ready),
  .m_axis_tdata(array_out_data),.m_axis_tvalid(array_out_valid),.m_axis_tready({LANES{1'b1}}),
  .arithmetic_fault(array_fault),.hold_request(array_hold),.dbg_commit(),.dbg_commit_data());
 // Explicit balanced reduction. No 48-entry priority/count chain
 // may feed public error qualification or the received counter.
 localparam COUNT_W=$clog2(LANES+1),COUNT_LEAVES=2**$clog2(LANES);
 wire [COUNT_W-1:0] result_count[1:COUNT_LEAVES*2-1];
 wire [LANES-1:0] result_nonfinite;
 generate for(genvar c=0;c<COUNT_LEAVES;c=c+1)begin:count_leaf
  if(c<LANES)begin
   assign result_count[COUNT_LEAVES+c]={{(COUNT_W-1){1'b0}},array_out_valid[c]};
   assign result_nonfinite[c]=array_out_valid[c]&&array_out_data[c*64+23+:8]==8'hff;
  end else assign result_count[COUNT_LEAVES+c]=0;
 end
 for(genvar c=1;c<COUNT_LEAVES;c=c+1)begin:count_branch
  assign result_count[c]=result_count[c*2]+result_count[c*2+1];
 end endgenerate
 wire [COUNT_W-1:0] outputs_now=result_count[1];
 wire output_overflow=|result_nonfinite;
 wire [31:0] part_word=partial_values[merge_col*32+:32];
 wire [31:0] prior_word=prior_values[merge_col*32+:32];
 // Signed zero is required: FMA(part,alpha,+0) is NOT a separate MUL for -0.
 wire [31:0] merge_c=block_start==0?((part_word^alpha)&32'h80000000):prior_word;
 wire [31:0] merge_tag={16'b0,merge_row,merge_col};
 wire [31:0] expected_merge_tag={16'b0,response_row,response_col};
 wire [15:0] tile_cells=rows*cols;
 // Disjoint lane banks have one write port each. A monolithic partial[][]
 // with LANES dynamic write ports dissolves into FFs in Vivado 2018.2.
 generate for(g=0;g<LANES;g=g+1)begin:result_bank
  (* ram_style="distributed" *) reg [31:0] partial_mem[0:31],prior_mem[0:31];
  always @(posedge aclk)begin
   if(!merge_mode&&array_out_valid[g])partial_mem[array_out_data[g*64+32+:5]]<=array_out_data[g*64+:32];
   if(merge_mode&&array_out_valid[g]&&!merge_reply_bad)
    prior_mem[array_out_data[g*64+32+:5]]<=array_out_data[g*64+:32];
  end
  assign partial_values[g*32+:32]=partial_mem[merge_row[4:0]];
  assign prior_values[g*32+:32]=prior_mem[merge_row[4:0]];
 end endgenerate
 assign m_axis_tvalid=aresetn&&(state==OUTPUT_C||state==ERROR_RSP);
 assign m_axis_tlast=state==ERROR_RSP||(merge_row+1==rows&&merge_col+1==cols);
 assign m_axis_tdata=state==ERROR_RSP?{tag,32'hffffffff,error_status,32'b0}:
  {tag,8'b0,merge_row,8'b0,merge_col,32'd1,prior_word};
 always @(posedge aclk)begin
  if(!aresetn)begin state<=IDLE;received<=0;sent<=0;lock_after_error<=0;output_error_pending<=0;compute_bank<=0;merge_lane_sent<=0;end
  else begin
   if(outputs_now!=0&&!merge_mode)begin
    received<=received+outputs_now;
   end
   case(state)
    IDLE:if(command_accept)begin
     tag<=s_cmd_tdata[127:96];alpha<=s_cmd_tdata[95:64];
     rows<=s_cmd_tdata[7:0];cols<=s_cmd_tdata[15:8];
     k_total<=s_cmd_tdata[31:16];k_stride<=s_cmd_tdata[47:32];
     a_base<=s_cmd_tdata[159:128];a_rs<=s_cmd_tdata[191:160];a_ks<=s_cmd_tdata[223:192];
     b_base<=s_cmd_tdata[255:224];b_ks<=s_cmd_tdata[287:256];b_cs<=s_cmd_tdata[319:288];
     active_generation<=generation_counter+1;
     invalid_input<=0;lock_after_error<=0;arithmetic_started<=0;output_error_pending<=0;compute_bank<=0;
     header_bad_q<=header_bad;nonfinite_q<=s_cmd_tdata[94:87]==8'hff;
     generation_exhausted_q<=generation_counter==64'hffffffffffffffff;
     state<=VALIDATE_MUL;
    end
    VALIDATE_MUL:begin
     a_row_product<={56'b0,(rows-8'd1)}*a_rs;a_k_product<={48'b0,(k_total-16'd1)}*a_ks;
     b_k_product<={48'b0,(k_total-16'd1)}*b_ks;b_col_product<={56'b0,(cols-8'd1)}*b_cs;
     state<=VALIDATE_SUM;
    end
    VALIDATE_SUM:begin a_span<=a_row_product+a_k_product;b_span<=b_k_product+b_col_product;state<=VALIDATE_END;end
    VALIDATE_END:begin cmd_a_last<={32'b0,a_base}+a_span;cmd_b_last<={32'b0,b_base}+b_span;state<=VALIDATE_CHECK;end
    VALIDATE_CHECK:begin
     if(generation_exhausted_q)begin error_status<=32'h80000009;lock_after_error<=1;state<=ERROR_RSP;end
     else if(command_bad||command_nonfinite)begin error_status<=command_nonfinite?32'h80000002:32'h80000001;state<=ERROR_RSP;end
     else begin block_start<=0;state<=START;end
    end
    START:begin
     block_count<=(k_total-block_start<k_stride)?k_total-block_start:k_stride;
     chunk_start<=block_start;received<=0;state<=CHUNK_PREP;
    end
    CHUNK_PREP:begin
     chunk_count<=expected_chunk_len;
     if(bank_ready[compute_bank])begin
      if(bank_start[compute_bank]!=chunk_start||bank_length[compute_bank]!=expected_chunk_len)begin
       error_status<=32'h80000006;lock_after_error<=1;state<=ERROR_DRAIN;
      end else if(bank_bad[compute_bank])begin
       error_status<=32'h80000002;lock_after_error<=arithmetic_started;state<=ERROR_DRAIN;
      end else begin k_offset<=0;row<=0;a_index<=0;sent<=0;state<=FETCH;end
     end
    end
    ERROR_DRAIN:if(gather_ready&&producer_state!=P_START)state<=ERROR_RSP;
    FETCH:begin sent<=0;state<=ISSUE;end
    ISSUE:begin
     if(|array_take)arithmetic_started<=1;
     sent<=sent|array_take;
     if(issue_complete)begin
      sent<=0;
      if(row+1==rows)begin
       row<=0;k_offset<=k_offset+1;a_index<=k_offset+1;
       if(k_offset+1==chunk_count)begin
        compute_bank<=!compute_bank;
        if(chunk_start+chunk_count==block_start+block_count)state<=DRAIN;
        else begin chunk_start<=chunk_start+chunk_count;state<=CHUNK_PREP;end
       end else state<=ISSUE;
      end else begin row<=row+1;a_index<=a_index+128;state<=ISSUE;end
     end
    end
    DRAIN:if(received==tile_cells)begin
     merge_row<=0;merge_col<=0;response_row<=0;response_col<=0;
     merge_lane_sent<=0;state<=MERGE_REQ;
    end
    MERGE_REQ:begin
     merge_lane_sent<=merge_lane_sent|array_take;
     if(merge_issue_complete)begin merge_lane_sent<=0;merge_row<=merge_row+1'b1;end
     // Each active lane independently enforces row 0..rows-1 and rejects
     // duplicates/out-of-range replies immediately. With every count <= rows,
     // sum(counts)==rows*cols iff every active count==rows. Test the registered
     // per-lane counts on the following cycle, removing the FMA-data -> valid
     // -> popcount -> sum -> equality -> high-fanout retire chain. Public
     // arithmetic/identity errors still reject on their original edge.
     if(merge_reply_bad)begin
      error_status<=32'h80000006;lock_after_error<=1;state<=ERROR_RSP;
     end else if(&merge_lane_retired)begin
      merge_row<=0;merge_col<=0;merge_lane_sent<=0;
      if(block_start+block_count==k_total)state<=OUTPUT_C;
      else begin block_start<=block_start+block_count;state<=START;end
     end
    end
    OUTPUT_C:if(m_axis_tready)begin
     if(output_error_pending)state<=ERROR_RSP;
     else if(merge_col+1==cols)begin
      merge_col<=0;
      if(merge_row+1==rows)state<=IDLE;else merge_row<=merge_row+1;
     end else merge_col<=merge_col+1;
    end
    ERROR_RSP:if(m_axis_tready)state<=lock_after_error?LOCKED:IDLE;
    LOCKED:state<=LOCKED;
    default:state<=LOCKED;
   endcase
   if((array_fault||output_overflow)&&state>=START&&state<=LOAD_WAIT)begin
    error_status<=output_overflow?32'h80000005:32'h80000006;
    lock_after_error<=1;state<=ERROR_RSP;
   end
   if(cache_write&&(cache_bank!=load_bank||cache_chunk!=producer_k))begin
    lock_after_error<=1;error_status<=32'h80000006;state<=ERROR_DRAIN;
   end
   if((gather_fault||gather_reject)&&state!=ERROR_RSP&&state!=LOCKED)begin
    lock_after_error<=1;error_status<=gather_reject?gather_reject_status:gather_status;
    if(state==OUTPUT_C&&!m_axis_tready)begin
     // Never change an already presented AXIS beat while the sink is stalled.
     // Keep it until accepted with fault asserted, then emit error termination.
     output_error_pending<=1;state<=OUTPUT_C;
    end else state<=state==IDLE?LOCKED:ERROR_RSP;
   end
  end
 end
endmodule
