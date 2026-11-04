// One lane, without a local correction core. advance is shared by the array.
module fp3_array_lane #(parameter LATENCY=19)(
 input wire aclk,aresetn,advance,array_fault,
 input wire use_seed_c,input wire [31:0] seed_c,
 input wire [103:0] s_data,input wire s_valid,output wire s_ready,
 output wire [63:0] m_data,output wire m_valid,input wire m_ready,
 output reg fault=0,output wire repair_request,output wire output_wait,
 output wire [95:0] repair_operands,input wire repair_valid,input wire [31:0] repair_result,
 output wire dbg_commit,output wire [36:0] dbg_commit_data
);
 reg [31:0] accum[0:31];
 reg [31:0] busy=0;
 reg [LATENCY-1:0] pending=0,last=0,relu=0;
 reg [4:0] ctx_pipe[0:LATENCY-1];
 reg [31:0] address[0:LATENCY-1];
 reg [31:0] a_pipe[0:LATENCY-1],b_pipe[0:LATENCY-1],c_pipe[0:LATENCY-1];
 reg corrected_valid=0,head_committed=0;
 reg [31:0] corrected_data=0;
 wire [4:0] incoming=s_data[68:64];
 wire [31:0] fma_c=use_seed_c?seed_c:s_data[69]?32'b0:accum[incoming];
 wire fma_valid;
 wire [31:0] fma_data;
 wire head_valid=pending[LATENCY-1]&&fma_valid;
 wire [31:0] head_a=a_pipe[LATENCY-1],head_b=b_pipe[LATENCY-1],head_c=c_pipe[LATENCY-1];
 // Only classification moves in time; all raw operand histories and
 // floating-point arithmetic remain unchanged. Both predicates stall on the
 // same local advance as pending, context and A/B/C metadata.
 reg [LATENCY-1:0] operand_special=0,product_nonzero=0;
 wire input_special=(s_data[30:23]==0&&s_data[22:0]!=0)||
  (s_data[62:55]==0&&s_data[54:32]!=0)||(fma_c[30:23]==0&&fma_c[22:0]!=0);
 wire exceptional=operand_special[LATENCY-1]||
  ((fma_data[30:23]==0)&&product_nonzero[LATENCY-1])||fma_data[30:0]==31'h00800000;
 assign repair_request=aresetn&&head_valid&&exceptional&&!corrected_valid;
 assign repair_operands={head_c,head_b,head_a};
 assign output_wait=aresetn&&head_valid&&last[LATENCY-1]&&!head_committed&&!m_ready;
 assign s_ready=advance&&!busy[incoming];
 wire accept=s_valid&&s_ready;
 wire input_nonfinite=s_data[30:23]==8'hff||s_data[62:55]==8'hff||fma_c[30:23]==8'hff;
 wire [31:0] selected_result=corrected_valid?corrected_data:fma_data;
 assign m_valid=aresetn&&!array_fault&&head_valid&&last[LATENCY-1]&&!repair_request&&!head_committed;
 wire is_nan=selected_result[30:23]==8'hff&&selected_result[22:0]!=0;
 assign m_data={address[LATENCY-1],(relu[LATENCY-1]&&selected_result[31]&&!is_nan)?32'b0:selected_result};
 wire final_handshake=m_valid&&m_ready;
 wire commit=head_valid&&!head_committed&&!repair_request&&!array_fault&&
  (last[LATENCY-1]?final_handshake:advance);
 assign dbg_commit=commit;
 assign dbg_commit_data={ctx_pipe[LATENCY-1],selected_result};
 fp32_fma arithmetic(.aclk(aclk),.aclken(advance),
  .s_axis_a_tvalid(accept),.s_axis_a_tdata(s_data[31:0]),
  .s_axis_b_tvalid(accept),.s_axis_b_tdata(s_data[63:32]),
  .s_axis_c_tvalid(accept),.s_axis_c_tdata(fma_c),
  .m_axis_result_tvalid(fma_valid),.m_axis_result_tdata(fma_data));
 integer i;
 reg [31:0] next_busy;
 always @(posedge aclk)begin
  if(!aresetn)begin
   operand_special<=0;product_nonzero<=0;pending<=0;last<=0;relu<=0;busy<=0;fault<=0;corrected_valid<=0;head_committed<=0;
  end else begin
   if(accept&&input_nonfinite)fault<=1;
   if(repair_valid)begin corrected_data<=repair_result;corrected_valid<=1;end
   next_busy=busy;
   if(commit)begin accum[ctx_pipe[LATENCY-1]]<=selected_result;next_busy[ctx_pipe[LATENCY-1]]=0;end
   if(accept)next_busy[incoming]=1;
   busy<=next_busy;
   if(advance)begin
    head_committed<=0;corrected_valid<=0;
    for(i=LATENCY-1;i>0;i=i-1)begin
     pending[i]<=pending[i-1];last[i]<=last[i-1];relu[i]<=relu[i-1];
     operand_special[i]<=operand_special[i-1];product_nonzero[i]<=product_nonzero[i-1];
     ctx_pipe[i]<=ctx_pipe[i-1];address[i]<=address[i-1];
     a_pipe[i]<=a_pipe[i-1];b_pipe[i]<=b_pipe[i-1];c_pipe[i]<=c_pipe[i-1];
    end
    pending[0]<=accept;last[0]<=s_data[70];relu[0]<=s_data[71];
    operand_special[0]<=accept&&input_special;
    product_nonzero[0]<=accept&&s_data[30:0]!=0&&s_data[62:32]!=0;
    ctx_pipe[0]<=incoming;address[0]<=s_data[103:72];
    a_pipe[0]<=s_data[31:0];b_pipe[0]<=s_data[63:32];c_pipe[0]<=fma_c;
   end else if(final_handshake)head_committed<=1;
  end
 end
endmodule
