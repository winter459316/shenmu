// One aligned128-bit beat or one scalar word; no AXI adapter in this prototype.
module fp3_weight_gather(
 input wire aclk,aresetn,start_valid,capture_valid,output wire start_ready,input wire first_chunk,
 input wire [63:0] generation,input wire [31:0] command_tag,
 input wire [7:0] rows,cols,chunk_len,input wire fill_bank,input wire [15:0] chunk_id,
 input wire [63:0] arena_base_word,arena_limit_word,a_first_word,b_first_word,
 input wire [31:0] a_row_stride,a_k_stride,b_k_stride,b_col_stride,
 output wire [223:0] m_read_tdata,output wire m_read_tvalid,input wire m_read_tready,
 input wire [287:0] s_read_tdata,input wire s_read_tvalid,output wire s_read_tready,
 output wire cache_write,cache_b,cache_bank,output wire [15:0] cache_chunk,
 output wire [2:0] cache_count,output wire [12:0] cache_index,output wire [127:0] cache_data,
 output wire transport_drained,output reg done=0,fault=0,output reg [31:0] fault_status=0,
 output wire rejecting_reply,output wire [31:0] reject_status
/* OBSERVER_BEGIN */, output wire [383:0] debug_vector/* OBSERVER_END */
);
/* OBSERVER_BEGIN */reg [159:0] observer_last_reply=0;
always @(posedge aclk)begin
 if(!aresetn)observer_last_reply<=0;
 else if(reply)observer_last_reply<=s_read_tdata[287:128];
end
assign debug_vector={address_word,active_generation,active_tag,next_sequence,pending,load_row,load_k,observer_last_reply[31:0],observer_last_reply[159:32]};/* OBSERVER_END */

 reg active=0,all_sent=0,source_b=0,bank=0;
 reg [15:0] chunk=0;
 reg [63:0] active_generation=0,address_word=0,a_row_base=0,b_k_base=0,b_initial=0;
 reg [63:0] lower_word=0,upper_word=0;
 reg [31:0] active_tag=0,next_sequence=0,a_rs=0,a_ks=0,b_ks=0,b_cs=0;
 reg [7:0] m_count=0,n_count=0,k_count=0,load_row=0,load_col=0,load_k=0;
 reg [15:0] pending=0;
 reg saved_b[0:15],saved_bank[0:15];
 reg [15:0] saved_chunk[0:15];reg [12:0] saved_index[0:15];reg [2:0] saved_count[0:15];
 wire [3:0] issue_slot=next_sequence[3:0];
 wire [31:0] reply_sequence=s_read_tdata[191:160];
 wire [3:0] reply_slot=reply_sequence[3:0];
 wire four_logical=source_b?(b_cs==1&&load_col+4<=n_count):(a_ks==1&&load_k+4<=k_count);
 reg [63:0] upper_minus_four=0;reg upper_has_four=0;
 wire quad=four_logical&&address_word[1:0]==0&&address_word[9:0]<=1020&&upper_has_four&&address_word<=upper_minus_four;
 wire [2:0] issue_count=quad?3'd4:3'd1;
 wire address_bad=address_word<lower_word||address_word>=upper_word||address_word>=64'h4000000000000000;
 assign transport_drained=pending==0;
 assign start_ready=aresetn&&!fault&&!active&&pending==0;
 assign m_read_tvalid=aresetn&&!fault&&active&&!all_sent&&!pending[issue_slot]&&!next_sequence[31]&&!address_bad;
 assign m_read_tdata={active_generation,active_tag,next_sequence,29'd0,issue_count,(address_word<<2)};
 assign s_read_tready=aresetn&&!fault;
 wire issue=m_read_tvalid&&m_read_tready;
 wire reply=s_read_tvalid&&s_read_tready;
 wire stale=s_read_tdata[287:224]!=active_generation||s_read_tdata[223:192]!=active_tag;
 // A valid slot was issued with low sequence bits equal to its index.
 // Store the remaining bits in separately owned flip-flop banks. This avoids
 // the dynamic self-indexed memory which Vivado2018.2 folded to sequence==0.
 wire [15:0] sequence_slot_matches;
 genvar sequence_slot;
 generate for(sequence_slot=0;sequence_slot<16;sequence_slot=sequence_slot+1)begin:sequence_slots
  (* DONT_TOUCH="true" *) reg [27:0] sequence_high=0;
  always @(posedge aclk)begin
   if(aresetn&&issue&&issue_slot==sequence_slot)sequence_high<=next_sequence[31:4];
  end
  assign sequence_slot_matches[sequence_slot]=pending[sequence_slot]&&reply_slot==sequence_slot&&
      sequence_high==reply_sequence[31:4];
 end endgenerate
 wire known_reply=active&&(|sequence_slot_matches);
 wire good_reply=reply&&!stale&&known_reply&&s_read_tdata[159:128]==1;
 assign rejecting_reply=reply&&!good_reply;
 assign reject_status=stale?32'h80000008:(!known_reply?32'h80000006:32'h80000007);
 assign cache_write=good_reply;
 assign cache_b=saved_b[reply_slot];assign cache_bank=saved_bank[reply_slot];assign cache_chunk=saved_chunk[reply_slot];
 assign cache_index=saved_index[reply_slot];assign cache_count=saved_count[reply_slot];assign cache_data=s_read_tdata[127:0];
 reg [15:0] next_pending;
 always @*begin next_pending=pending;
  if(good_reply)next_pending[reply_slot]=0;if(issue)next_pending[issue_slot]=1;
 end
 always @(posedge aclk)begin
  if(!aresetn)begin active<=0;pending<=0;fault<=0;done<=0;next_sequence<=0;end
  else begin
   done<=0;pending<=next_pending;
   // Speculation cannot publish a request: active remains owned solely by
   // the original accepted start. An arithmetic stop may discard these values.
   if(capture_valid&&!active&&pending==0)begin
    all_sent<=0;source_b<=0;active_generation<=generation;active_tag<=command_tag;
    bank<=fill_bank;chunk<=chunk_id;lower_word<=arena_base_word;upper_word<=arena_limit_word;
    upper_minus_four<=arena_limit_word-4;upper_has_four<=arena_limit_word>=4;
    m_count<=rows;n_count<=cols;k_count<=chunk_len;load_row<=0;load_col<=0;load_k<=0;
    address_word<=a_first_word;a_row_base<=a_first_word;b_initial<=b_first_word;b_k_base<=b_first_word;
    a_rs<=a_row_stride;a_ks<=a_k_stride;b_ks<=b_k_stride;b_cs<=b_col_stride;
    if(first_chunk)next_sequence<=0;
   end
   if(start_valid&&start_ready)active<=1;
   if(issue)begin
    saved_b[issue_slot]<=source_b;
    saved_bank[issue_slot]<=bank;saved_chunk[issue_slot]<=chunk;saved_count[issue_slot]<=issue_count;
    saved_index[issue_slot]<=source_b?{load_col[5:0],load_k[6:0]}:{1'b0,load_row[4:0],load_k[6:0]};
    next_sequence<=next_sequence+1;
    if(!source_b)begin
     if(load_k+issue_count==k_count)begin
      load_k<=0;
      if(load_row+1==m_count)all_sent<=1;
      else begin load_row<=load_row+1;a_row_base<=a_row_base+a_rs;address_word<=a_row_base+a_rs;end
     end else begin load_k<=load_k+issue_count;address_word<=address_word+(quad?({32'd0,a_ks}<<2):{32'd0,a_ks});end
    end else begin
     if(load_col+issue_count==n_count)begin
      load_col<=0;
      if(load_k+1==k_count)all_sent<=1;
      else begin load_k<=load_k+1;b_k_base<=b_k_base+b_ks;address_word<=b_k_base+b_ks;end
     end else begin load_col<=load_col+issue_count;address_word<=address_word+(quad?({32'd0,b_cs}<<2):{32'd0,b_cs});end
    end
   end
   if(active&&all_sent&&pending==0)begin active<=0;done<=1;end
   if(rejecting_reply)begin fault<=1;active<=0;fault_status<=reject_status;end
   if(active&&!all_sent&&next_sequence[31])begin fault<=1;active<=0;fault_status<=32'h80000009;end
   if(active&&!all_sent&&address_bad)begin fault<=1;active<=0;fault_status<=32'h80000001;end
  end
 end
endmodule
