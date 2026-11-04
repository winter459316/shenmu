`timescale 1ns/1ps
module tb_conv48_shell;
 `include "counts.vh"
 reg aclk=0;always #2.5 aclk=~aclk;
 reg aresetn=0;
 reg [11:0] s_axi_awaddr=0,s_axi_araddr=0;
 reg s_axi_awvalid=0,s_axi_wvalid=0,s_axi_bready=0,s_axi_arvalid=0,s_axi_rready=0;
 reg [31:0] s_axi_wdata=0;reg [3:0] s_axi_wstrb=0;
 wire s_axi_awready,s_axi_wready,s_axi_bvalid,s_axi_arready,s_axi_rvalid,irq;
 wire [1:0] s_axi_bresp,s_axi_rresp;wire [31:0] s_axi_rdata;
 reg [687:0] expand_command=0;reg [319:0] gemm_command=0;
 reg [31:0] output_row_stride_words=0;
 reg [63:0] output_base_byte=0,job_epoch=0,result_epoch=0;
 reg fault_active=0;
 reg cmd_ready=0,done=0,transport_drained=0;
 reg [31:0] fault=0,result_tag=0;
 wire [3:0] m_axi_arid;
 wire [63:0] m_axi_araddr;
 wire [7:0] m_axi_arlen;
 wire [2:0] m_axi_arsize;
 wire [1:0] m_axi_arburst;
 wire  m_axi_arlock;
 wire [3:0] m_axi_arcache;
 wire [2:0] m_axi_arprot;
 wire  m_axi_arvalid;
 reg  m_axi_arready=0;
 reg [3:0] m_axi_rid=0;
 reg [127:0] m_axi_rdata=0;
 reg [1:0] m_axi_rresp=0;
 reg  m_axi_rlast=0;
 reg  m_axi_rvalid=0;
 wire  m_axi_rready;
 wire [3:0] m_axi_awid;
 wire [63:0] m_axi_awaddr;
 wire [7:0] m_axi_awlen;
 wire [2:0] m_axi_awsize;
 wire [1:0] m_axi_awburst;
 wire  m_axi_awlock;
 wire [3:0] m_axi_awcache;
 wire [2:0] m_axi_awprot;
 wire  m_axi_awvalid;
 reg  m_axi_awready=0;
 wire [127:0] m_axi_wdata;
 wire [15:0] m_axi_wstrb;
 wire  m_axi_wlast;
 wire  m_axi_wvalid;
 reg  m_axi_wready=0;
 reg [3:0] m_axi_bid=0;
 reg [1:0] m_axi_bresp=0;
 reg  m_axi_bvalid=0;
 wire  m_axi_bready;
 decalper_eb_ot_sdeen_pot_pi_dehcac_xnilix dut(.*);
 reg [687:0] expansions[0:N_CASE-1];reg [319:0] matrices[0:N_CASE-1];
 reg [63:0] destinations[0:N_CASE-1];reg [31:0] strides[0:N_CASE-1];
 reg [31:0] memory[0:N_MEMORY-1],golden[0:N_MEMORY-1];reg [3:0] permission[0:N_MEMORY-1];reg visible[0:N_MEMORY-1];
 reg [15:0] read_pending=0,write_pending=0,data_done=0;
 reg [127:0] read_data[0:15],staged_write[0:15];reg [63:0] addresses[0:15];
 integer read_due[0:15],write_due[0:15],counts[0:15],order[0:15];
 integer cycles=0,reads=0,writes=0,write_words=0,outputs=0,panels=0,completed=0,negative=0,fences=0;
 integer head=0,tail=0,queued=0,rs,bs,j,k,ix,lane,valid_words,active_case=0,output_file;
 integer max_reads=0,max_writes=0,owner_switches=0;
 reg hold_ar=0,hold_b=0,read_error=0,write_error=0,normal_check=0;
 reg old_owner=0,old_drained=1,ar_held=0,aw_held=0,w_held=0;
 reg [70:0] ar_old,aw_old;reg [144:0] w_old;
 reg [319:0] saved_matrix;reg [63:0] saved_dest;integer before_reads,before_writes;
 function integer index_of(input [63:0] address);
  begin index_of=(address>=BASE&&address<LIMIT)?(address-BASE)/4:-1;end
 endfunction
 always @(posedge aclk)begin
  cycles=cycles+1;if(cycles>2000000)$fatal(1,"pipeline timeout phase=%0d fault=%h",0,fault);
  if(!aresetn)begin read_pending=0;write_pending=0;data_done=0;head=0;tail=0;queued=0;ar_held=0;aw_held=0;w_held=0;old_owner=0;old_drained=1;end
  else begin
   if(ar_held&&(!m_axi_arvalid||{m_axi_arid,m_axi_araddr,m_axi_arsize}!==ar_old))$fatal(1,"AR changed under stall");
   if(aw_held&&(!m_axi_awvalid||{m_axi_awid,m_axi_awaddr,m_axi_awsize}!==aw_old))$fatal(1,"AW changed under stall");
   if(w_held&&(!m_axi_wvalid||{m_axi_wlast,m_axi_wstrb,m_axi_wdata}!==w_old))$fatal(1,"W changed under stall");
   ar_held=m_axi_arvalid&&!m_axi_arready;ar_old={m_axi_arid,m_axi_araddr,m_axi_arsize};
   aw_held=m_axi_awvalid&&!m_axi_awready;aw_old={m_axi_awid,m_axi_awaddr,m_axi_awsize};
   w_held=m_axi_wvalid&&!m_axi_wready;w_old={m_axi_wlast,m_axi_wstrb,m_axi_wdata};
   if($countones(read_pending)>max_reads)max_reads=$countones(read_pending);
   if($countones(write_pending)>max_writes)max_writes=$countones(write_pending);
   if(m_axi_arvalid&&m_axi_arready)begin
    if(read_pending[m_axi_arid]||m_axi_arlen!=0||m_axi_arburst!=1||m_axi_arlock||(m_axi_arsize!=2&&m_axi_arsize!=4)||m_axi_araddr[1:0]!=0||(m_axi_arsize==4&&m_axi_araddr[3:0]!=0))$fatal(1,"bad AR");
    valid_words=m_axi_arsize==4?4:1;
    for(integer q=0;q<valid_words;q=q+1)begin
     ix=index_of(m_axi_araddr+q*4);
     if(ix<0||ix>=N_MEMORY||(permission[ix]!=0&&permission[ix]!=1))$fatal(1,"read escaped original source/owned alignment halo %h",m_axi_araddr+q*4);
    end
    read_data[m_axi_arid]=0;
    for(integer q=0;q<4;q=q+1)begin ix=index_of((m_axi_araddr&64'hfffffffffffffff0)+q*4);if(ix>=0&&ix<N_MEMORY)read_data[m_axi_arid][q*32+:32]=memory[ix];end
    read_pending[m_axi_arid]=1;read_due[m_axi_arid]=cycles+17;reads=reads+1;
   end
   if(m_axi_rvalid&&m_axi_rready)begin
    if(!read_pending[m_axi_rid])$fatal(1,"R without request");read_pending[m_axi_rid]=0;if(m_axi_rresp)read_error=0;
   end
   if(m_axi_awvalid&&m_axi_awready)begin
    if(write_pending[m_axi_awid]||m_axi_awlen!=0||m_axi_awburst!=1||m_axi_awlock||(m_axi_awsize!=2&&m_axi_awsize!=4)||m_axi_awaddr[1:0]!=0||(m_axi_awsize==4&&m_axi_awaddr[3:0]!=0)||queued>=16)$fatal(1,"bad AW");
    valid_words=m_axi_awsize==4?4:1;
    for(integer q=0;q<valid_words;q=q+1)begin
     ix=index_of(m_axi_awaddr+q*4);
    end
    write_pending[m_axi_awid]=1;data_done[m_axi_awid]=0;addresses[m_axi_awid]=m_axi_awaddr;counts[m_axi_awid]=valid_words;order[tail]=m_axi_awid;tail=(tail+1)%16;queued=queued+1;
   end
   if(m_axi_wvalid&&m_axi_wready)begin
    if(!queued||!m_axi_wlast)$fatal(1,"W without AW");j=order[head];head=(head+1)%16;queued=queued-1;
    if(!write_pending[j]||data_done[j])$fatal(1,"W order mismatch");lane=addresses[j][3:2];
    if(m_axi_wstrb!==(counts[j]==4?16'hffff:(16'h000f<<(lane*4))))$fatal(1,"bad W strobe");
    staged_write[j]=m_axi_wdata;data_done[j]=1;writes=writes+1;write_words=write_words+counts[j];write_due[j]=cycles+9+(writes*13)%41;
   end
   if(m_axi_bvalid&&m_axi_bready)begin
    j=m_axi_bid;if(!write_pending[j]||!data_done[j])$fatal(1,"B without W");
    // Make panel words readable only on accepted B, deliberately stricter
    // than early physical visibility. A premature stage handoff must fail.
    for(integer q=0;q<counts[j];q=q+1)begin
     ix=index_of(addresses[j]+q*4);lane=addresses[j][3:2]+q;memory[ix]=staged_write[j][lane*32+:32];
     if(permission[ix]==2)visible[ix]=1;
    end
    write_pending[j]=0;data_done[j]=0;if(m_axi_bresp)write_error=0;
   end
  end
 end
 always @(negedge aclk)begin
  if(!aresetn)begin m_axi_arready=0;m_axi_awready=0;m_axi_wready=0;m_axi_rvalid=0;m_axi_bvalid=0;end
  else begin
   m_axi_arready=!hold_ar&&cycles%17<13&&$countones(read_pending)<4;m_axi_awready=cycles%13<8;m_axi_wready=cycles%19<9;
   m_axi_rvalid=0;rs=-1;
   for(integer q=0;q<16;q=q+1)begin j=(q+cycles*7)%16;if(read_pending[j]&&read_due[j]<=cycles)rs=j;end
   if(rs>=0)begin m_axi_rid=rs;m_axi_rdata=read_data[rs];m_axi_rresp=read_error?2:0;m_axi_rlast=1;m_axi_rvalid=1;end
   m_axi_bvalid=0;bs=-1;
   if(!hold_b)for(integer q=0;q<16;q=q+1)begin j=(q+cycles*11)%16;if(write_pending[j]&&data_done[j]&&write_due[j]<=cycles)bs=j;end
   if(bs>=0)begin m_axi_bid=bs;m_axi_bresp=write_error?2:0;m_axi_bvalid=1;end
  end
 end
reg [31:0] observer_read;
task read_reg(input [11:0] address,output [31:0] value);
 begin
  @(negedge aclk);s_axi_araddr=address;s_axi_arvalid=1;
  @(posedge aclk);while(!s_axi_arready)@(posedge aclk);
  @(negedge aclk);s_axi_arvalid=0;wait(s_axi_rvalid);
  if(s_axi_rresp!=0)$fatal(1,"diagnostic read response");value=s_axi_rdata;
  s_axi_rready=1;@(negedge aclk);s_axi_rready=0;
 end
endtask
 task reset_bus;
  begin @(negedge aclk);aresetn=0;hold_ar=0;hold_b=0;read_error=0;write_error=0;normal_check=0;
   repeat(8)@(negedge aclk);aresetn=1;repeat(3)@(negedge aclk);end
 endtask
 task write_reg(input [11:0] address,input [31:0] value);
  begin
   @(negedge aclk);s_axi_awaddr=address;s_axi_awvalid=1;
   @(posedge aclk);while(!s_axi_awready)@(posedge aclk);
   @(negedge aclk);s_axi_awvalid=0;s_axi_wdata=value;s_axi_wstrb=15;s_axi_wvalid=1;
   @(posedge aclk);while(!s_axi_wready)@(posedge aclk);
   @(negedge aclk);s_axi_wvalid=0;wait(s_axi_bvalid);
   if(s_axi_bresp!=0)$fatal(1,"AXI control write failed %h",address);
   @(negedge aclk);s_axi_bready=1;@(negedge aclk);s_axi_bready=0;
  end
 endtask
 task submit(input integer n);
  reg [703:0] descriptor;reg [63:0] epoch;
  begin
   expand_command=expansions[n];gemm_command=matrices[n];output_base_byte=destinations[n];output_row_stride_words=strides[n];
   active_case=n;descriptor={16'b0,expansions[n]};epoch=64'h2026102703000001+n;
   for(integer w=0;w<22;w=w+1)write_reg(12'h100+4*w,descriptor[w*32+:32]);
   for(integer w=0;w<10;w=w+1)write_reg(12'h158+4*w,matrices[n][w*32+:32]);
   write_reg(12'h180,destinations[n][31:0]);write_reg(12'h184,destinations[n][63:32]);
   write_reg(12'h188,strides[n]);write_reg(12'h18c,epoch[31:0]);write_reg(12'h190,epoch[63:32]);
   write_reg(12'h00c,1);
  end
 endtask
 task wait_done;
  reg [31:0] st,err,v;integer polls;
  begin
   st=0;polls=0;
   while(!st[2])begin
    read_reg(12'h004,st);polls=polls+1;
    if(st[3])begin
     read_reg(12'h008,err);$display("NETLIST_OBSERVED_FAULT status=%h fault=%h",st,err);
     for(integer i=0;i<16;i=i+1)begin read_reg(12'h040+4*i,v);$display("DBG %0d %h",i,v);end
     $fatal(1,"netlist first-command failed");
    end
    if(polls>30000)$fatal(1,"netlist poll timeout");
   end
  end
 endtask
 initial begin
  #200;
  $readmemh("expand.hex",expansions);$readmemh("gemm.hex",matrices);$readmemh("dest.hex",destinations);$readmemh("strides.hex",strides);
  $readmemh("memory.hex",memory);$readmemh("golden_memory.hex",golden);$readmemh("permissions.hex",permission);
  reset_bus();read_reg(12'h000,observer_read);if(observer_read!==32'h31435046)$fatal(1,"FPC1 missing in netlist");
  normal_check=1;submit(0);wait_done();
  for(integer r=0;r<5;r=r+1)for(integer c=0;c<35;c=c+1)begin
   ix=index_of(output_base_byte+(r*output_row_stride_words+c)*4);
   if(memory[ix]!==golden[ix])$fatal(1,"netlist exact Y mismatch");
  end
  $display("NETLIST_FIRST_COMMAND_PASS outputs=175 cycles=%0d",cycles);$finish;
 end
 initial begin #20000000;$fatal(1,"shell timeout");end
endmodule
