// Address lanes and collector accept one immutable window command atomically.
module fp3_window_front(
 input wire aclk,aresetn,abort,
 input wire [687:0] cmd_data,input wire cmd_valid,output wire cmd_ready,
 input wire [63:0] generation,input wire first_chunk,fill_bank,input wire [15:0] chunk_id,
 output wire [223:0] m_read_tdata,output wire m_read_tvalid,input wire m_read_tready,
 input wire [287:0] s_read_tdata,input wire s_read_tvalid,output wire s_read_tready,
 output wire cache_write,cache_bank,output wire [15:0] cache_chunk,
 output wire [12:0] cache_index,output wire [2:0] cache_count,output wire [127:0] cache_data,
 output wire done,fault,output wire [31:0] fault_status,
 output wire rejecting_input,rejecting_reply,output wire transport_drained
);
 wire vector_ready;wire [3:0] lane_valid,lane_take;
 wire [775:0] lane_data;wire [31:0] vector_fault;
 wire collect_ready,collect_done,collect_fault;wire [31:0] collect_status;
 reg [31:0] fault_q=0;
 wire lanes_faulted=vector_fault!=0;
 wire [31:0] fault_now=collect_fault?collect_status:vector_fault?vector_fault:
  rejecting_input?32'h80000d06:rejecting_reply?32'h80000d03:abort?32'h80000d02:0;
 always @(posedge aclk)begin
  if(!aresetn)fault_q<=0;
  else if(fault_q==0&&fault_now!=0)fault_q<=fault_now;
 end
 assign fault=fault_q!=0||collect_fault||lanes_faulted;
 assign fault_status=fault_q!=0?fault_q:fault_now;
 assign cmd_ready=aresetn&&collect_ready&&vector_ready&&!fault&&!abort&&!rejecting_input&&!rejecting_reply;
 wire accept=cmd_valid&&cmd_ready;
 assign done=collect_done&&!fault&&!abort&&!rejecting_input&&!rejecting_reply;
 fp3_window_vector vector_source(.aclk(aclk),.aresetn(aresetn),.cmd_data(cmd_data),
  .cmd_valid(accept),.cmd_ready(vector_ready),.out_data(lane_data),.out_valid(lane_valid),
  .out_ready(lane_take),.done(),.fault(vector_fault));
 fp3_window_collect collect(.aclk(aclk),.aresetn(aresetn),.abort(abort||lanes_faulted),
  .start_valid(accept),.first_chunk(first_chunk),.start_ready(collect_ready),
  .generation(generation),.arena_base_byte(cmd_data[527:464]),.arena_limit_byte(cmd_data[463:400]),
  .command_tag(cmd_data[687:656]),.columns(cmd_data[7:0]),.chunk_len(cmd_data[55:48]),
  .fill_bank(fill_bank),.chunk_id(chunk_id),.s_window_data(lane_data),.s_window_valid(lane_valid),.s_window_ready(lane_take),
  .m_read_tdata(m_read_tdata),.m_read_tvalid(m_read_tvalid),.m_read_tready(m_read_tready),
  .s_read_tdata(s_read_tdata),.s_read_tvalid(s_read_tvalid),.s_read_tready(s_read_tready),
  .cache_write(cache_write),.cache_bank(cache_bank),.cache_chunk(cache_chunk),
  .cache_index(cache_index),.cache_count(cache_count),.cache_data(cache_data),
  .done(collect_done),.fault(collect_fault),.fault_status(collect_status),
  .rejecting_input(rejecting_input),.rejecting_reply(rejecting_reply),.transport_drained(transport_drained));
endmodule
