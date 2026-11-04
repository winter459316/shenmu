// Parameterized array. Exactly ONE serial correction core, regardless of LANES.
// Scanner round-robin arbitration: at most LANES idle scan cycles between heads.
module fp3_mac_array #(parameter LANES=32,parameter LATENCY=19)(
 input wire aclk,aresetn,external_hold,
 input wire [LANES-1:0] use_seed_c,input wire [LANES*32-1:0] seed_c,
 input wire [LANES*104-1:0] s_axis_tdata,input wire [LANES-1:0] s_axis_tvalid,
 output wire [LANES-1:0] s_axis_tready,
 output wire [LANES*64-1:0] m_axis_tdata,output wire [LANES-1:0] m_axis_tvalid,
 input wire [LANES-1:0] m_axis_tready,output wire arithmetic_fault,output wire hold_request,
 output wire [LANES-1:0] dbg_commit,output wire [LANES*37-1:0] dbg_commit_data
);
 localparam INDEX_W=LANES<=1?1:$clog2(LANES);
 wire [LANES-1:0] fault,repair_request,output_wait;
 wire [LANES*96-1:0] repair_operands;
 wire [LANES-1:0] repair_valid;
 assign arithmetic_fault=|fault;
 assign hold_request=aresetn&&((|repair_request)||(|output_wait)||arithmetic_fault);
 // A synchronous data/CE net. It is never used as a clock.
 (* clock_buffer_type="NONE" *) wire advance=aresetn&&!external_hold&&!hold_request;
 reg [INDEX_W-1:0] scan=0,owner=0;
 reg [1:0] state=0;
 reg [95:0] captured_operands=0;
 wire core_done,core_idle,core_ready;
 wire [31:0] core_result;
 wire launch=aresetn&&!arithmetic_fault&&state==1;
 wire reply=aresetn&&!arithmetic_fault&&state==2&&core_done;
 fp3_fma_exact correction(.ap_clk(aclk),.ap_rst(!aresetn),.ap_start(launch),
  .ap_done(core_done),.ap_idle(core_idle),.ap_ready(core_ready),
  .a_V(captured_operands[31:0]),.b_V(captured_operands[63:32]),.c_V(captured_operands[95:64]),.ap_return(core_result));
 always @(posedge aclk)begin
  if(!aresetn)begin state<=0;scan<=0;owner<=0;end
  else if(!arithmetic_fault)begin
   case(state)
    0:begin
     if(repair_request[scan])begin
      captured_operands<=repair_operands[scan*96+:96];owner<=scan;state<=1;
     end
     scan<=scan==LANES-1?0:scan+1'b1;
    end
    1:state<=2;
    2:if(core_done)state<=0;
    default:state<=0;
   endcase
  end
 end
 genvar g;
 generate for(g=0;g<LANES;g=g+1)begin:lanes
  assign repair_valid[g]=reply&&owner==g;
  // Private FMA/history may advance independently. Public acceptance and
  // publication still stop immediately on any lane's arithmetic fault.
  wire local_ready;
  (* clock_buffer_type="NONE" *) wire local_advance=aresetn&&!external_hold&&
      !repair_request[g]&&!output_wait[g]&&!fault[g];
  assign s_axis_tready[g]=local_ready&&!arithmetic_fault;
  fp3_array_lane #(.LATENCY(LATENCY)) lane(.aclk(aclk),.aresetn(aresetn),.advance(local_advance),.array_fault(arithmetic_fault),.use_seed_c(use_seed_c[g]),.seed_c(seed_c[g*32+:32]),
   .s_data(s_axis_tdata[g*104+:104]),.s_valid(s_axis_tvalid[g]&&!arithmetic_fault),.s_ready(local_ready),
   .m_data(m_axis_tdata[g*64+:64]),.m_valid(m_axis_tvalid[g]),.m_ready(m_axis_tready[g]),
   .fault(fault[g]),.repair_request(repair_request[g]),.output_wait(output_wait[g]),
   .repair_operands(repair_operands[g*96+:96]),.repair_valid(repair_valid[g]),.repair_result(core_result),
   .dbg_commit(dbg_commit[g]),.dbg_commit_data(dbg_commit_data[g*37+:37]));
 end endgenerate
endmodule
