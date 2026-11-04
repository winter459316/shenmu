`timescale 1ns/1ps
module tb_float;
 reg clk=0;always #5 clk=~clk;
 reg valid=0;reg [63:0] a=0,b=0,u=0;reg [31:0] f=0;
 wire va,vm,vd,ve,vt,vu;
 wire [63:0] ya,ym,yd,ye,yu;wire [31:0] yt;
 reg [63:0] ma[0:127],mb[0:127],mu[0:127],ea[0:127],em[0:127],ed[0:127],ee[0:127],eu[0:127];
 reg [31:0] mf[0:127],et[0:127];
 integer ca=0,cm=0,cd=0,ce=0,ct=0,cu=0,i;
 fast_geometry_ap_dadd_3_full_dsp_64 add(.aclk(clk),.aclken(1'b1),.s_axis_a_tvalid(valid),.s_axis_a_tdata(a),.s_axis_b_tvalid(valid),.s_axis_b_tdata(b),.m_axis_result_tvalid(va),.m_axis_result_tdata(ya));
 fast_geometry_ap_dmul_3_max_dsp_64 mul(.aclk(clk),.aclken(1'b1),.s_axis_a_tvalid(valid),.s_axis_a_tdata(a),.s_axis_b_tvalid(valid),.s_axis_b_tdata(b),.m_axis_result_tvalid(vm),.m_axis_result_tdata(ym));
 fast_geometry_ap_ddiv_15_no_dsp_64 div(.aclk(clk),.aclken(1'b1),.s_axis_a_tvalid(valid),.s_axis_a_tdata(a),.s_axis_b_tvalid(valid),.s_axis_b_tdata(b),.m_axis_result_tvalid(vd),.m_axis_result_tdata(yd));
 fast_geometry_ap_fpext_0_no_dsp_32 ext(.s_axis_a_tvalid(valid),.s_axis_a_tdata(f),.m_axis_result_tvalid(ve),.m_axis_result_tdata(ye));
 fast_geometry_ap_fptrunc_0_no_dsp_64 trunc(.s_axis_a_tvalid(valid),.s_axis_a_tdata(a),.m_axis_result_tvalid(vt),.m_axis_result_tdata(yt));
 fast_geometry_ap_uitodp_2_no_dsp_32 uint64(.aclk(clk),.aclken(1'b1),.s_axis_a_tvalid(valid),.s_axis_a_tdata(u),.m_axis_result_tvalid(vu),.m_axis_result_tdata(yu));
 always @(posedge clk) begin
  #1;
  if(va===1'b1)begin if(ya!==ea[ca])$fatal(1,"FP64 add %0d %h != %h",ca,ya,ea[ca]);ca=ca+1;end
  if(vm===1'b1)begin if(ym!==em[cm])$fatal(1,"FP64 mul %0d",cm);cm=cm+1;end
  if(vd===1'b1)begin if(yd!==ed[cd])$fatal(1,"FP64 div %0d %h != %h",cd,yd,ed[cd]);cd=cd+1;end
  if(ve===1'b1)begin if(ye!==ee[ce])$fatal(1,"FP32 extend %0d",ce);ce=ce+1;end
  if(vt===1'b1)begin if(yt!==et[ct])$fatal(1,"FP64 truncate %0d",ct);ct=ct+1;end
  if(vu===1'b1)begin if(yu!==eu[cu])$fatal(1,"Unsigned conversion %0d",cu);cu=cu+1;end
 end
 initial begin
  $readmemh("a.hex",ma);$readmemh("b.hex",mb);$readmemh("f.hex",mf);$readmemh("u.hex",mu);
  $readmemh("add.hex",ea);$readmemh("mul.hex",em);$readmemh("div.hex",ed);$readmemh("extend.hex",ee);$readmemh("truncate.hex",et);$readmemh("unsigned.hex",eu);
  repeat(4)@(negedge clk);
  for(i=0;i<128;i=i+1)begin valid=1;a=ma[i];b=mb[i];f=mf[i];u=mu[i];@(negedge clk);end
  valid=0;repeat(30)@(negedge clk);
  if(ca!=128||cm!=128||cd!=128||ce!=128||ct!=128||cu!=128)$fatal(1,"Missing results %d %d %d %d %d %d",ca,cm,cd,ce,ct,cu);
  $display("FLOAT_NUMERICAL_PASS operators=6 cases=128 results=768");$finish;
 end
endmodule
