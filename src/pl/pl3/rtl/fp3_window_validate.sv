// Complete header validation, no window output and no memory interface.
module fp3_window_validate(
 input wire aclk,aresetn,input wire [687:0] cmd_data,input wire cmd_valid,output wire cmd_ready,
 output reg done=0,output reg [31:0] fault=0
);
 localparam IDLE=0,V0=1,V1=2,V2=3,V3=4,V4=5;
 reg [2:0] state=IDLE;
 reg [31:0] tag,ks,ns;
 reg [63:0] src,dst,arena_lo,arena_hi;
 reg [15:0] cin,id,ih,iw,od,oh,ow,kd,kh,kw,sd,sh,sw,dd,dh,dw,pd,ph,pw,kcount,ncount;
 reg [31:0] in_hw,out_hw,k_hw,total;
 reg [47:0] in_size,out_size,k_size;
 reg [63:0] source_words,k_total;
 reg [64:0] source_end,dest_end;

 assign cmd_ready=aresetn&&state==IDLE&&fault==0;
 always @(posedge aclk)begin
  if(!aresetn)begin state<=IDLE;done<=0;fault<=0;end
  else begin
   done<=0;
   if(fault==0)case(state)
    IDLE:if(cmd_valid&&cmd_ready)begin
     {tag,src,dst,arena_lo,arena_hi,cin,id,ih,iw,od,oh,ow,kd,kh,kw,sd,sh,sw,dd,dh,dw,pd,ph,pw,ks,kcount,ns,ncount}<=cmd_data;
     state<=V0;
    end
     V0:begin
      if(cin==0||id==0||ih==0||iw==0||od==0||oh==0||ow==0||kd==0||kh==0||kw==0||
       sd==0||sh==0||sw==0||dd==0||dh==0||dw==0||kcount==0||ncount==0||kcount>2048||ncount>256||
       src[1:0]!=0||dst[1:0]!=0||arena_lo>=arena_hi||arena_lo[3:0]!=0||arena_hi[3:0]!=0||arena_hi>64'h400000000) fault<=32'h80000901;
      else begin in_hw<=ih*iw;out_hw<=oh*ow;k_hw<=kh*kw;total<=kcount*ncount;state<=V1;end
     end
     V1:begin in_size<=in_hw*id;out_size<=out_hw*od;k_size<=k_hw*kd;state<=V2;end
     V2:begin source_words<=in_size*cin;k_total<=k_size*cin;state<=V3;end
     V3:begin source_end<={1'b0,src}+({1'b0,source_words}<<2);dest_end<={1'b0,dst}+({33'b0,total}<<2);state<=V4;end
     V4:begin
      // Bound all accepted products before any low-bit use in the streaming path.
      if(source_words>64'h40000000||k_total>64'h40000000||out_size>48'h40000000||
       {1'b0,ks}+kcount>k_total||{1'b0,ns}+ncount>out_size||
       source_end[64]||dest_end[64]||src<arena_lo||dst<arena_lo||source_end>{1'b0,arena_hi}||dest_end>{1'b0,arena_hi}||
       ({1'b0,src}<dest_end&&{1'b0,dst}<source_end)) fault<=32'h80000901;
      else begin done<=1;state<=IDLE;end
     end
    default:begin end
   endcase
  end
 end
endmodule
