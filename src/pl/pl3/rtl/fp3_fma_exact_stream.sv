// Independent external-C FMA stream: request={tag,c,b,a}, response={tag,status,result}.
// status=1 finite success, 80000002 nonfinite input, 80000005 finite overflow.
// Errors return result=0 and retain their tag/order. Reset aborts in-flight work.
module fp3_fma_exact_stream(
 input wire aclk,aresetn,
 input wire [127:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,
 output wire [95:0] m_axis_tdata,output wire m_axis_tvalid,input wire m_axis_tready
);
 localparam LATENCY=19;
 reg [LATENCY-1:0] pending=0,invalid=0;
 reg [127:0] history[0:LATENCY-1];
 reg correction_inflight=0,corrected_valid=0;
 reg [31:0] corrected_result=0;
 wire fma_valid;
 wire [31:0] fma_data;
 wire head_valid=pending[LATENCY-1]&&fma_valid;
 wire head_invalid=invalid[LATENCY-1];
 wire [31:0] a=history[LATENCY-1][31:0],b=history[LATENCY-1][63:32],c=history[LATENCY-1][95:64];
 wire sub_a=a[30:23]==0&&a[22:0]!=0,sub_b=b[30:23]==0&&b[22:0]!=0,sub_c=c[30:23]==0&&c[22:0]!=0;
 wire exceptional=sub_a||sub_b||sub_c||((fma_data[30:23]==0)&&a[30:0]!=0&&b[30:0]!=0)||fma_data[30:0]==31'h00800000;
 wire unresolved=head_valid&&!head_invalid&&exceptional&&!corrected_valid;
 assign m_axis_tvalid=aresetn&&head_valid&&!unresolved;
 (* clock_buffer_type="NONE" *) wire advance=aresetn&&!unresolved&&(!head_valid||m_axis_tready);
 assign s_axis_tready=advance;
 wire accept=s_axis_tvalid&&s_axis_tready;
 wire input_invalid=s_axis_tdata[30:23]==8'hff||s_axis_tdata[62:55]==8'hff||s_axis_tdata[94:87]==8'hff;
 wire [31:0] selected_result=corrected_valid?corrected_result:fma_data;
 wire result_overflow=selected_result[30:23]==8'hff;
 wire [31:0] status=head_invalid?32'h80000002:(result_overflow?32'h80000005:32'd1);
 assign m_axis_tdata={history[LATENCY-1][127:96],status,(status==1)?selected_result:32'b0};
 // Invalid tokens pass through a harmless FMA, and the parallel flag generates
 // an explicit error response in the correct stream position.
 fp32_fma arithmetic(.aclk(aclk),.aclken(advance),
  .s_axis_a_tvalid(accept),.s_axis_a_tdata(input_invalid?32'b0:s_axis_tdata[31:0]),
  .s_axis_b_tvalid(accept),.s_axis_b_tdata(input_invalid?32'b0:s_axis_tdata[63:32]),
  .s_axis_c_tvalid(accept),.s_axis_c_tdata(input_invalid?32'b0:s_axis_tdata[95:64]),
  .m_axis_result_tvalid(fma_valid),.m_axis_result_tdata(fma_data));
 wire correction_start=aresetn&&unresolved&&!correction_inflight;
 wire correction_done,correction_idle,correction_ready;
 wire [31:0] correction_result;
 fp3_fma_exact correction(.ap_clk(aclk),.ap_rst(!aresetn),.ap_start(correction_start),
  .ap_done(correction_done),.ap_idle(correction_idle),.ap_ready(correction_ready),
  .a_V(a),.b_V(b),.c_V(c),.ap_return(correction_result));
 integer i;
 always @(posedge aclk)begin
  if(!aresetn)begin pending<=0;invalid<=0;correction_inflight<=0;corrected_valid<=0;end
  else begin
   if(correction_start)correction_inflight<=1;
   if(correction_inflight&&correction_done)begin
    corrected_result<=correction_result;corrected_valid<=1;correction_inflight<=0;
   end
   if(advance)begin
    corrected_valid<=0;
    for(i=LATENCY-1;i>0;i=i-1)begin
     pending[i]<=pending[i-1];invalid[i]<=invalid[i-1];history[i]<=history[i-1];
    end
    pending[0]<=accept;invalid[0]<=input_invalid;history[0]<=s_axis_tdata;
   end
  end
 end
endmodule
