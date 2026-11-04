// One validated/divided window state, four adjacent logical columns per group.
// The downstream collector consumes every enabled column atomically.
module fp3_window_vector(
 input wire aclk,aresetn,
 input wire [687:0] cmd_data,input wire cmd_valid,output wire cmd_ready,
 output wire [775:0] out_data,output wire [3:0] out_valid,input wire [3:0] out_ready,
 output reg done=0,output reg [31:0] fault=0
);
 localparam IDLE=0,V0=1,V1=2,V2=3,V3=4,V4=5,DIV=6,SETUP=7,RUN=8,DRAIN=9;
 reg [3:0] state=IDLE;reg [5:0] valid=0;
 reg [31:0] tag,ks,ns;
 reg [63:0] src,dst,arena_lo,arena_hi;
 reg [15:0] cin,id,ih,iw,od,oh,ow,kd,kh,kw,sd,sh,sw,dd,dh,dw,pd,ph,pw,kcount,ncount;
 reg [31:0] in_hw,out_hw,k_hw,total;
 reg [47:0] in_size,out_size,k_size;
 reg [63:0] source_words,k_total;
 reg [64:0] source_end,dest_end;
 reg [31:0] div_q;reg [16:0] div_r;reg [15:0] divisor;
 reg [5:0] div_bit;reg [2:0] div_stage;
 wire [16:0] shifted={div_r[15:0],div_q[31]};
 wire div_take=shifted>={1'b0,divisor};
 wire [16:0] next_r=div_take?shifted-{1'b0,divisor}:shifted;
 wire [31:0] next_q={div_q[30:0],div_take};
 reg [15:0] kx,ky,kz,nx,ny,nz,nx_start,ny_start,nz_start;
 reg [31:0] channel,channel_offset,index;
 reg [5:0] column=0;reg [7:0] kernel_row=0;
 reg [3:0] mask_pipe[0:5],last_pipe[0:5];reg [5:0] ending=0;
 reg [47:0] pos0[0:3];reg [15:0] kx0,ky0,kz0;
 reg [31:0] xa1[0:3],xb1[0:3],ya1[0:3],yb1[0:3],za1[0:3],zb1[0:3];
 reg signed [33:0] x2[0:3],y2[0:3],z2[0:3];
 reg [31:0] channel_pipe[0:4],index_pipe[0:5];
 reg [31:0] row3[0:3];reg [15:0] x3[0:3];
 reg [47:0] spatial4[0:3];reg [63:0] source5[0:3],dest5;
 reg [3:0] zero3,zero4,zero5;
 wire group_ready=(|mask_pipe[5])&&((out_ready&mask_pipe[5])==mask_pipe[5]);
 wire advance=!valid[5]||group_ready;
 wire [2:0] group_words=ncount-column>=4?3'd4:ncount-column;
 wire final_group=index+group_words==total;
 assign cmd_ready=aresetn&&state==IDLE&&fault==0;
 assign out_valid=aresetn&&valid[5]&&fault==0?mask_pipe[5]:4'b0;

 function automatic signed [33:0] coordinate;
  input [15:0] pos,stride,kernel,dilation,pad;
  reg [31:0] a,b;
  begin a=pos*stride;b=kernel*dilation;
   coordinate=$signed({2'b0,a})+$signed({2'b0,b})-$signed({18'b0,pad});end
 endfunction
 // nx<ow and ny<oh are guaranteed by accepted global-N bounds. At most
 // four columns advance, so narrow widths/heights admit constant small cases.
 function automatic [47:0] move_n;
  input [15:0] x,y,z,width,height;input [2:0] step;
  reg [16:0] xs,ys,xx,yy,zz;reg [2:0] xr,yr;
  begin
   xs={1'b0,x}+step;xr=0;xx=xs;
   if(width==1)begin xx=0;xr=step;end
   else if(width==2)begin xx={16'b0,xs[0]};xr=xs>>1;end
   else if(width==3)begin
    if(xs>=6)begin xx=xs-6;xr=2;end
    else if(xs>=3)begin xx=xs-3;xr=1;end
   end else if(xs>={1'b0,width})begin xx=xs-width;xr=1;end
   ys={1'b0,y}+xr;yr=0;yy=ys;
   if(height==1)begin yy=0;yr=xr;end
   else if(height==2)begin yy={16'b0,ys[0]};yr=ys>>1;end
   else if(height==3)begin
    if(ys>=6)begin yy=ys-6;yr=2;end
    else if(ys>=3)begin yy=ys-3;yr=1;end
   end else if(ys>={1'b0,height})begin yy=ys-height;yr=1;end
   zz={1'b0,z}+yr;move_n={zz[15:0],yy[15:0],xx[15:0]};
  end
 endfunction
 wire [47:0] next_position=move_n(nx,ny,nz,ow,oh,3'd4);
 wire [47:0] position[0:3];
 genvar g;
 generate for(g=0;g<4;g=g+1)begin:columns_out
  assign position[g]=move_n(nx,ny,nz,ow,oh,g);
  assign out_data[g*194+:194]={tag,index_pipe[5]+g,source5[g],dest5+g*4,last_pipe[5][g],zero5[g]};
 end endgenerate
 always @(posedge aclk)begin
  if(!aresetn)begin
   state<=IDLE;fault<=0;done<=0;valid<=0;ending<=0;
   tag<=0;index<=0;div_r<=0;div_q<=0;divisor<=1;div_bit<=0;div_stage<=0;
  end else begin
   done<=0;
   if(fault!=0)valid<=0;
   else begin
    if(advance)begin
     valid<={valid[4:0],state==RUN};ending<={ending[4:0],state==RUN&&final_group};
     for(integer p=5;p>0;p=p-1)begin
      mask_pipe[p]<=mask_pipe[p-1];last_pipe[p]<=last_pipe[p-1];
      index_pipe[p]<=index_pipe[p-1];
     end
     for(integer p=4;p>0;p=p-1)channel_pipe[p]<=channel_pipe[p-1];
     if(state==RUN)begin
      kx0<=kx;ky0<=ky;kz0<=kz;
      for(integer l=0;l<4;l=l+1)begin
       pos0[l]<=position[l];
       mask_pipe[0][l]<=column+l<ncount;
       last_pipe[0][l]<=column+l<ncount&&kernel_row+1==kcount&&ncount-1-column-l<4;
      end
      channel_pipe[0]<=channel_offset;index_pipe[0]<=index;index<=index+group_words;
      if(final_group)state<=DRAIN;
      else if(column+4>=ncount)begin
       column<=0;kernel_row<=kernel_row+1'b1;nx<=nx_start;ny<=ny_start;nz<=nz_start;
       if(kx==kw-1)begin
        kx<=0;
        if(ky==kh-1)begin
         ky<=0;
         if(kz==kd-1)begin kz<=0;channel_offset<=channel_offset+in_size[31:0];end
         else kz<=kz+1;
        end else ky<=ky+1;
       end else kx<=kx+1;
      end else begin column<=column+4;{nz,ny,nx}<=next_position;end
     end
     if(valid[0])begin
      for(integer l=0;l<4;l=l+1)begin
       xa1[l]<=pos0[l][15:0]*sw;xb1[l]<=kx0*dw;
       ya1[l]<=pos0[l][31:16]*sh;yb1[l]<=ky0*dh;
       za1[l]<=pos0[l][47:32]*sd;zb1[l]<=kz0*dd;
      end
     end
     if(valid[1])begin
      for(integer l=0;l<4;l=l+1)begin
       x2[l]<=$signed({2'b0,xa1[l]})+$signed({2'b0,xb1[l]})-$signed({18'b0,pw});
       y2[l]<=$signed({2'b0,ya1[l]})+$signed({2'b0,yb1[l]})-$signed({18'b0,ph});
       z2[l]<=$signed({2'b0,za1[l]})+$signed({2'b0,zb1[l]})-$signed({18'b0,pd});
      end
     end
     if(valid[2])begin
      for(integer l=0;l<4;l=l+1)begin
       if(x2[l]<0||y2[l]<0||z2[l]<0||x2[l]>=$signed({18'b0,iw})||
          y2[l]>=$signed({18'b0,ih})||z2[l]>=$signed({18'b0,id}))begin
        zero3[l]<=1;row3[l]<=0;x3[l]<=0;
       end else begin zero3[l]<=0;row3[l]<=z2[l][15:0]*ih+y2[l][15:0];x3[l]<=x2[l][15:0];end
      end
     end
     if(valid[3])begin
      for(integer l=0;l<4;l=l+1)spatial4[l]<=row3[l]*iw+x3[l];
      zero4<=zero3;
     end
     if(valid[4])begin
      for(integer l=0;l<4;l=l+1)source5[l]<=zero4[l]?0:src+(({16'b0,spatial4[l]}+{32'b0,channel_pipe[4]})<<2);
      dest5<=dst+({32'b0,index_pipe[4]}<<2);zero5<=zero4;
     end
    end
    if(valid[5]&&group_ready&&ending[5])begin done<=1;state<=IDLE;end
    case(state)
     IDLE:if(cmd_valid&&cmd_ready)begin
      {tag,src,dst,arena_lo,arena_hi,cin,id,ih,iw,od,oh,ow,kd,kh,kw,sd,sh,sw,dd,dh,dw,pd,ph,pw,ks,kcount,ns,ncount}<=cmd_data;
      state<=V0;
     end
     V0:begin
      if(cin==0||id==0||ih==0||iw==0||od==0||oh==0||ow==0||kd==0||kh==0||kw==0||
         sd==0||sh==0||sw==0||dd==0||dh==0||dw==0||kcount==0||ncount==0||kcount>128||ncount>48||
         src[1:0]!=0||dst[1:0]!=0||arena_lo>=arena_hi)fault<=32'h80000901;
      else begin in_hw<=ih*iw;out_hw<=oh*ow;k_hw<=kh*kw;total<=kcount*ncount;state<=V1;end
     end
     V1:begin in_size<=in_hw*id;out_size<=out_hw*od;k_size<=k_hw*kd;state<=V2;end
     V2:begin source_words<=in_size*cin;k_total<=k_size*cin;state<=V3;end
     V3:begin source_end<={1'b0,src}+({1'b0,source_words}<<2);dest_end<={1'b0,dst}+({33'b0,total}<<2);state<=V4;end
     V4:begin
      if(source_words>64'h40000000||k_total>64'h40000000||out_size>48'h40000000||
         {1'b0,ks}+kcount>k_total||{1'b0,ns}+ncount>out_size||
         source_end[64]||dest_end[64]||src<arena_lo||dst<arena_lo||source_end>{1'b0,arena_hi}||dest_end>{1'b0,arena_hi}||
         ({1'b0,src}<dest_end&&{1'b0,dst}<source_end))fault<=32'h80000901;
      else begin div_q<=ks;div_r<=0;divisor<=kw;div_bit<=0;div_stage<=0;state<=DIV;end
     end
     DIV:begin
      div_r<=next_r;div_q<=next_q;div_bit<=div_bit+1;
      if(div_bit==31)begin
       div_r<=0;div_bit<=0;div_stage<=div_stage+1;
       case(div_stage)
        0:begin kx<=next_r[15:0];divisor<=kh;end
        1:begin ky<=next_r[15:0];divisor<=kd;end
        2:begin kz<=next_r[15:0];channel<=next_q;div_q<=ns;divisor<=ow;end
        3:begin nx_start<=next_r[15:0];divisor<=oh;end
        4:begin ny_start<=next_r[15:0];nz_start<=next_q[15:0];state<=SETUP;end
       endcase
      end
     end
     SETUP:begin channel_offset<=channel*in_size[31:0];nx<=nx_start;ny<=ny_start;nz<=nz_start;
      index<=0;column<=0;kernel_row<=0;state<=RUN;end
     default:begin end
    endcase
   end
  end
 end
endmodule
