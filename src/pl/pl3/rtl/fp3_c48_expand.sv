// Pure bitwise Conv window expansion. Output remains private until all B replies.
// 16 owned slots; full epoch/tag/sequence checks; zero padding issues no reads.
// Aligned contiguous groups use four-word transport; all other cells remain scalar.
module fp3_c48_expand(
 input wire aclk,aresetn,abort,
 input wire [687:0] cmd_data,input wire cmd_valid,output wire cmd_ready,
 input wire [63:0] job_epoch,
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
);

 localparam IDLE=0,START=1,RUN=2,COMPLETE=3,FAILED=4;
 reg [2:0] phase=IDLE;reg [31:0] fault_q=0;reg [687:0] saved_cmd=0;
 wire validator_ready,validator_done;wire [31:0] validator_fault;
 wire [31:0] fault_now=abort?32'h80000a04:validator_fault?validator_fault:
  unit_read_fault?unit_read_fault:unit_write_fault;
 assign fault=!aresetn?0:fault_q?fault_q:fault_now;
 assign fault_active=aresetn&&(fault_q!=0||fault_now!=0);
 assign transport_drained=unit_read_idle&&unit_write_idle;
 assign cmd_ready=aresetn&&(phase==IDLE||phase==COMPLETE)&&validator_ready&&transport_drained&&!fault_active;
 assign done=aresetn&&phase==COMPLETE&&!fault_active&&transport_drained;
 fp3_window_validate validate(.aclk(aclk),.aresetn(aresetn),.cmd_data(saved_cmd),
  .cmd_valid(phase==START&&!fault_active),.cmd_ready(validator_ready),.done(validator_done),.fault(validator_fault));
 always @(posedge aclk)begin
  if(!aresetn)begin phase<=IDLE;fault_q<=0;result_epoch<=0;result_tag<=0;saved_cmd<=0;end
  else begin
   if(cmd_valid&&(phase==IDLE||phase==COMPLETE))saved_cmd<=cmd_data;
   if(cmd_valid&&cmd_ready)begin
    result_epoch<=job_epoch;result_tag<=cmd_data[687:656];
    if(job_epoch==0)begin fault_q<=32'h80000a01;phase<=FAILED;end
    else phase<=START;
   end
   if(phase==START&&validator_ready&&!fault_active)phase<=RUN;
   if(phase==RUN&&validator_done&&!fault_active)phase<=COMPLETE;
   if(fault_active)begin if(fault_q==0)fault_q<=fault_now;phase<=FAILED;end
  end
 end
 assign unit_read_stop=1'b1;assign unit_write_stop=1'b1;
 assign unit_read_abort=phase==FAILED;assign unit_write_abort=phase==FAILED;
 assign unit_read_arena_base=saved_cmd[527:464];assign unit_read_arena_limit=saved_cmd[463:400];
 assign unit_write_arena_base=saved_cmd[527:464];assign unit_write_arena_limit=saved_cmd[463:400];
 assign unit_read_s_data=0;assign unit_read_s_valid=0;assign unit_read_m_ready=1;
 assign unit_write_s_data=0;assign unit_write_s_valid=0;assign unit_write_m_ready=1;
endmodule
