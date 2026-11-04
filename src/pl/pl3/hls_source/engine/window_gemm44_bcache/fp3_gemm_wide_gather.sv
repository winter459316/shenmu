// One owner at a time on the private read stream. Already accepted physical
// requests remain owned until their matching reply; fault never starts B or C.
module fp3_gemm_wide_gather(
 input wire aclk,aresetn,abort,input wire [687:0] window_command,
 input wire start_valid,capture_valid,output wire start_ready,input wire first_chunk,
 input wire [63:0] generation,input wire [31:0] command_tag,
 input wire [7:0] rows,cols,chunk_len,input wire fill_bank,input wire [15:0] chunk_id,
 input wire [63:0] arena_base_word,arena_limit_word,a_first_word,b_first_word,
 input wire [31:0] a_row_stride,a_k_stride,b_k_stride,b_col_stride,
 output wire [223:0] m_read_tdata,output wire m_read_tvalid,input wire m_read_tready,
 input wire [287:0] s_read_tdata,input wire s_read_tvalid,output wire s_read_tready,
 output wire cache_write,cache_b,cache_bank,output wire [15:0] cache_chunk,
 output wire [2:0] cache_count,output wire [12:0] cache_index,output wire [127:0] cache_data,
 output wire done,fault,output wire [31:0] fault_status,
 output wire rejecting_reply,output wire [31:0] reject_status
/* OBSERVER_BEGIN */, output wire [415:0] debug_vector/* OBSERVER_END */
);
/* OBSERVER_BEGIN */wire [383:0] observer_a;
assign debug_vector={{24'd0,failed_owner,phase,bfault,afault,abort},observer_a};/* OBSERVER_END */

 localparam IDLE=0,A_START=1,A_WAIT=2,B_START=3,B_WAIT=4,COMPLETE=5,FAILED=6;
 reg [2:0] phase=IDLE;reg [31:0] fault_q=0;reg fault_latched=0;reg [1:0] failed_owner=0;
 reg [687:0] saved_window=0;reg [63:0] saved_generation=0;
 reg [15:0] saved_chunk=0;reg saved_first=0,saved_bank=0;
 wire ardy,adone,afault,adrained,areject,bcmd_ready,bdone,bfault,bdrained,breject,binput;
 wire [31:0] astatus,areject_status,bstatus;
 wire [223:0] areq,breq;wire av,bv,artake,brtake;
 wire acache,bcache,ab,abank,bbank;wire [15:0] achunk,bchunk;
 wire [2:0] acount,bcount;wire [12:0] aindex,bindex;wire [127:0] adata,bdata;
 wire owner_a=phase==A_START||phase==A_WAIT||(phase==FAILED&&failed_owner==1);
 wire owner_b=phase==B_START||phase==B_WAIT||(phase==FAILED&&failed_owner==2);
 assign rejecting_reply=(owner_a&&areject)||(owner_b&&breject);
 assign reject_status=owner_a?areject_status:bstatus;
 wire [31:0] fault_now=abort?32'h80000e01:afault?astatus:bfault?bstatus:
  rejecting_reply?reject_status:binput?32'h80000d06:0;
 wire fault_present=abort||afault||bfault||rejecting_reply||binput;
 assign fault=fault_latched||fault_present;
 assign fault_status=fault_q!=0?fault_q:fault_now;
 assign start_ready=aresetn&&phase==IDLE&&!fault&&ardy&&bcmd_ready&&adrained&&bdrained;
 wire accept=start_valid&&start_ready;
 assign done=aresetn&&phase==COMPLETE&&!fault&&adrained&&bdrained;
 assign m_read_tdata=owner_a?areq:breq;
 assign m_read_tvalid=aresetn&&!fault&&(owner_a?av:owner_b?bv:1'b0);
 assign s_read_tready=owner_a?artake:owner_b?brtake:1'b0;
 assign cache_write=aresetn&&!fault&&(owner_a?acache:owner_b?bcache:1'b0);
 assign cache_b=owner_b;
 assign cache_bank=owner_a?abank:bbank;assign cache_chunk=owner_a?achunk:bchunk;
 assign cache_count=owner_a?acount:bcount;assign cache_index=owner_a?aindex:bindex;
 assign cache_data=owner_a?adata:bdata;
 always @(posedge aclk)begin
  if(!aresetn)begin phase<=IDLE;fault_q<=0;fault_latched<=0;failed_owner<=0;end
  else begin
   if(capture_valid&&phase==IDLE&&adrained&&bdrained)begin
    saved_window<=window_command;saved_generation<=generation;saved_chunk<=chunk_id;
    saved_first<=first_chunk;saved_bank<=fill_bank;
   end
   case(phase)
    IDLE:if(accept)phase<=A_START;
    A_START:if(ardy&&!fault)phase<=A_WAIT;
    A_WAIT:if(adone&&adrained&&!fault)phase<=B_START;
    B_START:if(bcmd_ready&&!fault)phase<=B_WAIT;
    B_WAIT:if(bdone&&bdrained&&!fault)phase<=COMPLETE;
    COMPLETE:phase<=IDLE;
    default:begin end
   endcase
   if(fault)begin
    if(!fault_latched)begin fault_latched<=1;fault_q<=fault_now;failed_owner<=owner_a?1:owner_b?2:0;end
    phase<=FAILED;
   end
  end
 end
 fp3_weight_gather weights(.aclk(aclk)/* OBSERVER_BEGIN */,.debug_vector(observer_a)/* OBSERVER_END */,.aresetn(aresetn),
  .capture_valid(capture_valid&&phase==IDLE&&adrained&&bdrained),
  .start_valid(phase==A_START&&!fault),.start_ready(ardy),.first_chunk(first_chunk),
  .generation(generation),.command_tag(command_tag),.rows(rows),.cols(cols),.chunk_len(chunk_len),
  .fill_bank(fill_bank),.chunk_id(chunk_id),.arena_base_word(arena_base_word),.arena_limit_word(arena_limit_word),
  .a_first_word(a_first_word),.b_first_word(b_first_word),.a_row_stride(a_row_stride),.a_k_stride(a_k_stride),
  .b_k_stride(b_k_stride),.b_col_stride(b_col_stride),
  .m_read_tdata(areq),.m_read_tvalid(av),.m_read_tready(owner_a&&m_read_tready&&!fault),
  .s_read_tdata(s_read_tdata),.s_read_tvalid(owner_a&&s_read_tvalid),.s_read_tready(artake),
  .cache_write(acache),.cache_b(ab),.cache_bank(abank),.cache_chunk(achunk),.cache_count(acount),
  .cache_index(aindex),.cache_data(adata),.done(adone),.fault(afault),.fault_status(astatus),
  .transport_drained(adrained),.rejecting_reply(areject),.reject_status(areject_status));
 fp3_window_front windows(.aclk(aclk),.aresetn(aresetn),.abort(abort),
  .cmd_data(saved_window),.cmd_valid(phase==B_START&&!fault),.cmd_ready(bcmd_ready),
  .generation(saved_generation),.first_chunk(saved_first),.fill_bank(saved_bank),.chunk_id(saved_chunk),
  .m_read_tdata(breq),.m_read_tvalid(bv),.m_read_tready(owner_b&&m_read_tready&&!fault),
  .s_read_tdata(s_read_tdata),.s_read_tvalid(owner_b&&s_read_tvalid),.s_read_tready(brtake),
  .cache_write(bcache),.cache_bank(bbank),.cache_chunk(bchunk),.cache_count(bcount),
  .cache_index(bindex),.cache_data(bdata),.done(bdone),.fault(bfault),.fault_status(bstatus),
  .rejecting_input(binput),.rejecting_reply(breject),.transport_drained(bdrained));
endmodule
