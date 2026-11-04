// Four logical B columns -> unique aligned 128-bit reads -> one B-cache group.
// No intermediate DDR panel stores. All slots remain private until complete.
module fp3_window_collect(
 input wire aclk,aresetn,abort,start_valid,first_chunk,
 output wire start_ready,
 input wire [63:0] generation,arena_base_byte,arena_limit_byte,
 input wire [31:0] command_tag,input wire [7:0] columns,chunk_len,
 input wire fill_bank,input wire [15:0] chunk_id,
 input wire [775:0] s_window_data,input wire [3:0] s_window_valid,output wire [3:0] s_window_ready,
 output wire [223:0] m_read_tdata,output wire m_read_tvalid,input wire m_read_tready,
 input wire [287:0] s_read_tdata,input wire s_read_tvalid,output wire s_read_tready,
 output wire cache_write,cache_bank,output wire [15:0] cache_chunk,
 output wire [12:0] cache_index,output wire [2:0] cache_count,output wire [127:0] cache_data,
 output reg done=0,fault=0,output reg [31:0] fault_status=0,
 output wire rejecting_input,rejecting_reply,output wire transport_drained
);
 reg active=0,all_input=0,bank=0;
 reg [15:0] chunk=0;
 reg [32:0] owned_lo=0,owned_hi=0;reg [63:0] active_generation=0;
 reg [31:0] tag=0;
 // Maximum accepted chunk is 128*48=6144 values; inactive tail lanes
 // may expect at most 6147, still exactly representable in 13 bits.
 reg [12:0] expected_index[0:3];
 reg [5:0] last_column_start=0;reg [6:0] last_kernel_row=0;

 reg [7:0] cols=0,k_count=0;
 reg [6:0] next_k=0;reg [5:0] next_col=0;
 wire [2:0] input_words=cols-next_col>=4?3'd4:cols-next_col;
 reg [7:0] group_busy=0;
 reg [3:0] wanted[0:7],requested[0:7],arrived[0:7];
 reg [31:0] source_word[0:7][0:3];
 reg [2:0] request_scan=0;
 reg [127:0] values[0:7];
 reg [5:0] group_col[0:7];reg [6:0] group_k[0:7];
 reg [2:0] group_head=0,group_tail=0;
 reg [3:0] group_count=0;
 reg [30:0] next_sequence=0;
 reg [15:0] pending=0,issued=0;
 // Only successfully validated B replies populate this private read cache.
 // An accepted command owns immutable input until completion. Invalidate on
 // every first chunk, generation/tag change and bus reset; never reuse across
 // descriptors or host uploads. Logical cache hits allocate no AXI identity.
 (* ram_style="distributed" *) reg [127:0] read_cache_data[0:31];
 (* ram_style="distributed" *) reg [24:0] read_cache_tag[0:31];
 reg [31:0] read_cache_valid=0;
 reg [63:0] read_cache_generation=0;
 reg [31:0] read_cache_command_tag=0;
 reg [29:0] saved_beat[0:15];
 reg [31:0] saved_sequence[0:15];reg [2:0] saved_group[0:15];
 reg [3:0] saved_mask[0:15];reg [7:0] saved_lanes[0:15];
 reg hold_valid=0;reg [223:0] hold_data=0;
 reg [3:0] hold_slot=0;
 wire [3:0] reply_slot=s_read_tdata[163:160];
 wire identity_known=pending[reply_slot]&&issued[reply_slot]&&
  saved_sequence[reply_slot]==s_read_tdata[191:160]&&
  s_read_tdata[287:224]==active_generation&&s_read_tdata[223:192]==tag;
 assign s_read_tready=aresetn;
 wire reply=s_read_tvalid&&s_read_tready;
 assign rejecting_reply=reply&&(!identity_known||s_read_tdata[159:128]!=1);
 wire good_reply=reply&&identity_known&&s_read_tdata[159:128]==1;
 reg [3:0] input_mask,input_zeros;
 reg input_bad;
 wire all_heads=(s_window_valid&input_mask)==input_mask;
 always @*begin
  input_mask=0;input_zeros=0;input_bad=0;
  for(integer l=0;l<4;l=l+1)begin
   if({1'b0,next_col}+l[6:0]<{1'b0,cols})begin
    input_mask[l]=1;
    input_zeros[l]=s_window_data[l*194];
    if(s_window_data[l*194+162+:32]!=tag||
       s_window_data[l*194+130+:32]!={19'b0,expected_index[l]}||
       s_window_data[l*194+1]!=((next_k==last_kernel_row)&&({1'b0,next_col}+l[6:0]>={1'b0,last_column_start})))input_bad=1;
    if(!s_window_data[l*194]&&
       (s_window_data[l*194+66+:2]!=0||s_window_data[l*194+100+:30]!=0||
        {1'b0,s_window_data[l*194+68+:32]}<owned_lo||{1'b0,s_window_data[l*194+68+:32]}>=owned_hi))input_bad=1;
   end
  end
 end
 assign rejecting_input=aresetn&&active&&!all_input&&group_count<8&&all_heads&&input_bad;
 wire push=aresetn&&active&&!all_input&&group_count<8&&all_heads&&
  !input_bad&&!fault&&!abort&&!rejecting_reply;
 assign s_window_ready=push?input_mask:4'b0;
 wire head_complete=group_busy[group_head]&&((arrived[group_head]&wanted[group_head])==wanted[group_head]);
 assign cache_write=aresetn&&active&&!fault&&!abort&&!rejecting_input&&!rejecting_reply&&head_complete;
 assign cache_bank=bank;assign cache_chunk=chunk;
 assign cache_index={group_col[group_head],group_k[group_head]};
 assign cache_count={2'b0,wanted[group_head][0]}+{2'b0,wanted[group_head][1]}+
                    {2'b0,wanted[group_head][2]}+{2'b0,wanted[group_head][3]};
 assign cache_data=values[group_head];
 // Reserve a read identity when filling the request register, before admission
 // to the physical reader. Distinct words sharing a beat reserve one request.
 reg candidate_found;wire [2:0] candidate_group=request_scan;
 reg [31:0] candidate_word;reg [3:0] candidate_mask;reg [7:0] candidate_lanes;
 wire [63:0] candidate_address={30'd0,candidate_word[31:2],4'd0};
 always @*begin
  candidate_found=0;candidate_word=0;candidate_mask=0;candidate_lanes=0;
  for(integer l=0;l<4;l=l+1)begin
   if(!candidate_found&&group_busy[request_scan]&&wanted[request_scan][l]&&!requested[request_scan][l])begin
    candidate_found=1;candidate_word=source_word[request_scan][l];
   end
  end
  for(integer l=0;l<4;l=l+1)begin
   if(candidate_found&&wanted[request_scan][l]&&!requested[request_scan][l]&&
      source_word[request_scan][l][31:2]==candidate_word[31:2])begin
    candidate_mask[l]=1;candidate_lanes[l*2+:2]=source_word[request_scan][l][1:0];
   end
  end
 end
 assign m_read_tdata=hold_data;
 assign m_read_tvalid=aresetn&&hold_valid&&!fault&&!abort&&!rejecting_input&&!rejecting_reply;
 wire issue=m_read_tvalid&&m_read_tready;
 wire [3:0] allocate_slot=next_sequence[3:0];
 wire sequence_exhausted=active&&candidate_found&&next_sequence==31'h7fffffff;
 wire [4:0] lookup_index=candidate_word[6:2];
 wire read_cache_hit=read_cache_valid[lookup_index]&&read_cache_tag[lookup_index]==candidate_word[31:7];
 wire [127:0] lookup_data=read_cache_data[lookup_index];
 // A physical reply and a hit must never overwrite arrived/values for the
 // same group. Physical replies have priority; retry the hit next cycle.
 wire reuse=aresetn&&active&&!fault&&!abort&&!rejecting_input&&!rejecting_reply&&
  candidate_found&&read_cache_hit&&!good_reply;
 wire reserve=aresetn&&active&&!fault&&!abort&&!rejecting_input&&!rejecting_reply&&!read_cache_hit&&
  candidate_found&&(!hold_valid||issue)&&!pending[allocate_slot]&&!sequence_exhausted;
 always @(posedge aclk)begin
  if(!aresetn)begin
   read_cache_valid<=0;read_cache_generation<=0;read_cache_command_tag<=0;
  end else if(start_valid&&start_ready&&
     (first_chunk||generation!=read_cache_generation||command_tag!=read_cache_command_tag))begin
   read_cache_valid<=0;read_cache_generation<=generation;read_cache_command_tag<=command_tag;
  end else if(good_reply&&!fault&&!abort&&!rejecting_input)begin
   read_cache_valid[saved_beat[reply_slot][4:0]]<=1;
   read_cache_tag[saved_beat[reply_slot][4:0]]<=saved_beat[reply_slot][29:5];
   read_cache_data[saved_beat[reply_slot][4:0]]<=s_read_tdata[127:0];
  end
 end
 reg [15:0] next_pending,next_issued;
 always @*begin
  next_pending=pending;next_issued=issued;
  if(reply&&identity_known)begin next_pending[reply_slot]=0;next_issued[reply_slot]=0;end
  if(issue)next_issued[hold_slot]=1;
  if(reserve)begin next_pending[allocate_slot]=1;next_issued[allocate_slot]=0;end
  // Abort cancels only a request not yet admitted to the physical reader.
  // Already issued identities stay owned until their actual replies arrive.
  if((abort||fault||rejecting_input||rejecting_reply)&&hold_valid&&!issue)begin
   next_pending[hold_slot]=0;next_issued[hold_slot]=0;
  end
 end
 assign transport_drained=aresetn&&pending==0&&!hold_valid&&group_count==0;
 assign start_ready=aresetn&&!active&&!fault&&!abort&&transport_drained;
 wire start=start_valid&&start_ready;
 always @(posedge aclk)begin
  if(!aresetn)begin
   active<=0;all_input<=0;group_busy<=0;group_count<=0;group_head<=0;group_tail<=0;
   request_scan<=0;pending<=0;issued<=0;hold_valid<=0;next_sequence<=0;fault<=0;fault_status<=0;done<=0;
  end else begin
   done<=0;pending<=next_pending;issued<=next_issued;
   if(start)begin
    if(generation==0||columns==0||columns>48||chunk_len==0||chunk_len>128||arena_base_byte>=arena_limit_byte||
       arena_base_byte[3:0]!=0||arena_limit_byte[3:0]!=0||arena_limit_byte>64'h400000000)begin fault<=1;fault_status<=32'h80000d01;end
    else begin
     active<=1;all_input<=0;bank<=fill_bank;chunk<=chunk_id;
     owned_lo<=arena_base_byte[34:2];owned_hi<=arena_limit_byte[34:2];active_generation<=generation;tag<=command_tag;
     cols<=columns;k_count<=chunk_len;next_col<=0;next_k<=0;
     last_column_start<=columns>4?columns-4:0;last_kernel_row<=chunk_len-1'b1;
     for(integer l=0;l<4;l=l+1)expected_index[l]<=l[12:0];
     group_head<=0;group_tail<=0;request_scan<=0;
     if(first_chunk)next_sequence<=0;
    end
   end
   if(push)begin
    for(integer l=0;l<4;l=l+1)expected_index[l]<=expected_index[l]+input_words;
    group_busy[group_tail]<=1;wanted[group_tail]<=input_mask;
    requested[group_tail]<=input_zeros;arrived[group_tail]<=input_zeros;
    values[group_tail]<=0;group_col[group_tail]<=next_col;group_k[group_tail]<=next_k;
    for(integer l=0;l<4;l=l+1)source_word[group_tail][l]<=s_window_data[l*194+68+:32];
    group_tail<=group_tail+1'b1;
    if(next_col+4>=cols)begin
     next_col<=0;next_k<=next_k+1'b1;
     if(next_k+1==k_count)all_input<=1;
    end else next_col<=next_col+4;
   end
   if(cache_write)begin group_busy[group_head]<=0;group_head<=group_head+1'b1;end
   case({push,cache_write})
    2'b10:group_count<=group_count+1'b1;
    2'b01:group_count<=group_count-1'b1;
    default:group_count<=group_count;
   endcase
   if(active&&!fault&&!abort&&!rejecting_input&&!rejecting_reply)begin
    if(!candidate_found||((reserve||reuse)&&((requested[candidate_group]|candidate_mask)&wanted[candidate_group])==wanted[candidate_group]))
     request_scan<=request_scan+1'b1;
   end
   if(issue)hold_valid<=0;
   if(reserve)begin
    hold_valid<=1;hold_slot<=allocate_slot;
    hold_data<={active_generation,tag,1'b1,next_sequence,32'd4,candidate_address};
    saved_beat[allocate_slot]<=candidate_word[31:2];
    saved_sequence[allocate_slot]<={1'b1,next_sequence};saved_group[allocate_slot]<=candidate_group;
    saved_mask[allocate_slot]<=candidate_mask;saved_lanes[allocate_slot]<=candidate_lanes;
    requested[candidate_group]<=requested[candidate_group]|candidate_mask;
    next_sequence<=next_sequence+1'b1;
   end
   if(reuse)begin
    for(integer l=0;l<4;l=l+1)if(candidate_mask[l])
     values[candidate_group][l*32+:32]<=lookup_data[candidate_lanes[l*2+:2]*32+:32];
    requested[candidate_group]<=requested[candidate_group]|candidate_mask;
    arrived[candidate_group]<=arrived[candidate_group]|candidate_mask;
   end
   if(good_reply&&!fault&&!abort&&!rejecting_input)begin
    for(integer l=0;l<4;l=l+1)if(saved_mask[reply_slot][l])
     values[saved_group[reply_slot]][l*32+:32]<=s_read_tdata[saved_lanes[reply_slot][l*2+:2]*32+:32];
    arrived[saved_group[reply_slot]]<=arrived[saved_group[reply_slot]]|saved_mask[reply_slot];
   end
   if(active&&all_input&&group_count==0&&pending==0&&!hold_valid&&!fault&&!abort&&
      !rejecting_input&&!rejecting_reply)begin active<=0;done<=1;end
   if(abort||rejecting_input||rejecting_reply||sequence_exhausted||fault)begin
    active<=0;group_busy<=0;group_count<=0;hold_valid<=0;
    if(!fault)begin
     fault<=1;
     fault_status<=abort?32'h80000d02:rejecting_input?32'h80000d06:
       rejecting_reply?(!identity_known?32'h80000d03:32'h80000d05):32'h80000d07;
    end
   end
  end
 end
endmodule
