`timescale 1ns/1ps
module tb_conv48_direct;
 `include "counts.vh"
 reg aclk=0;always #2.5 aclk=~aclk;
 reg aresetn=0,abort=0,cmd_valid=0;
 reg [687:0] expand_command=0;reg [319:0] gemm_command=0;
 reg [31:0] output_row_stride_words=0;reg [63:0] output_base_byte=0,job_epoch=1;
 wire fault_active;
 wire cmd_ready,done,transport_drained;wire [31:0] fault,result_tag;wire [63:0] result_epoch;
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
 wire [511:0] debug_vector;
 fp3_conv48_capture #(.LANES(44)) dut(.*);
 reg [687:0] expansions[0:N_CASE-1];reg [319:0] matrices[0:N_CASE-1];
 reg [63:0] destinations[0:N_CASE-1];reg [31:0] strides[0:N_CASE-1];
 reg [31:0] memory[0:N_MEMORY-1],golden[0:N_MEMORY-1];reg [3:0] permission[0:N_MEMORY-1];reg visible[0:N_MEMORY-1];
 reg [15:0] read_pending=0,write_pending=0,data_done=0;
 reg [127:0] read_data[0:15],staged_write[0:15];reg [63:0] addresses[0:15];
 integer read_due[0:15],write_due[0:15],counts[0:15],order[0:15];
 integer cycles=0,reads=0,writes=0,write_words=0,outputs=0,panels=0,completed=0,negative=0,fences=0;
 integer head=0,tail=0,queued=0,rs,bs,j,k,ix,lane,valid_words,active_case=0,output_file;
 integer max_reads=0,max_writes=0,owner_switches=0,quad_writes=0,scalar_writes=0;
 reg hold_ar=0,hold_b=0,read_error=0,write_error=0,normal_check=0;
 reg old_owner=0,old_drained=1,ar_held=0,aw_held=0,w_held=0;
 reg [70:0] ar_old,aw_old;reg [144:0] w_old;
 reg [319:0] saved_matrix;reg [63:0] saved_dest;integer before_reads,before_writes;
 function integer index_of(input [63:0] address);
  begin index_of=(address>=BASE&&address<LIMIT)?(address-BASE)/4:-1;end
 endfunction
 // Both edges: immediate failure presence must be equivalent to the
 // unchanged diagnostic priority code, including abort and reset cases.
 always @(negedge aclk)begin
  #1;
  if(fault_active!==(fault!=0))$fatal(1,"top presence/code mismatch");
  if(dut.expand.fault_active!==(dut.e_fault!=0))$fatal(1,"expand presence/code mismatch");
  if(dut.matrix.fault_active!==(dut.g_fault!=0))$fatal(1,"matrix presence/code mismatch");
 end
 always @(posedge aclk)begin
  cycles=cycles+1;if(cycles>2000000)$fatal(1,"pipeline timeout phase=%0d fault=%h",dut.phase,fault);
  if(!aresetn)begin read_pending=0;write_pending=0;data_done=0;head=0;tail=0;queued=0;ar_held=0;aw_held=0;w_held=0;old_owner=0;old_drained=1;end
  else begin
   if($isunknown({cmd_ready,done,fault,transport_drained,m_axi_arvalid,m_axi_awvalid,m_axi_wvalid}))$fatal(1,"unknown pipeline control");
   if(normal_check&&fault)$fatal(1,"normal fault case=%0d phase=%0d code=%h",active_case,dut.phase,fault);
   if(done&&(fault||!transport_drained||read_pending||write_pending||queued))$fatal(1,"completion before AXI fence");
   if(dut.owner!=old_owner)begin
    if(!old_drained||read_pending||write_pending||queued)$fatal(1,"owner switched with in-flight AXI");
    if(dut.owner)owner_switches=owner_switches+1;
   end
   old_owner=dut.owner;old_drained=transport_drained;
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
     if(!dut.owner)$fatal(1,"validation owner issued a read");
    end
    read_data[m_axi_arid]=0;
    for(integer q=0;q<4;q=q+1)begin ix=index_of((m_axi_araddr&64'hfffffffffffffff0)+q*4);if(ix>=0&&ix<N_MEMORY)read_data[m_axi_arid][q*32+:32]=memory[ix];end
    read_pending[m_axi_arid]=1;read_due[m_axi_arid]=cycles+7+(reads*7)%29;reads=reads+1;
   end
   if(m_axi_rvalid&&m_axi_rready)begin
    if(!read_pending[m_axi_rid])$fatal(1,"R without request");read_pending[m_axi_rid]=0;if(m_axi_rresp)read_error=0;
   end
   if(m_axi_awvalid&&m_axi_awready)begin
    if(m_axi_awsize==4)quad_writes=quad_writes+1;else scalar_writes=scalar_writes+1;
    if(write_pending[m_axi_awid]||m_axi_awlen!=0||m_axi_awburst!=1||m_axi_awlock||(m_axi_awsize!=2&&m_axi_awsize!=4)||m_axi_awaddr[1:0]!=0||(m_axi_awsize==4&&m_axi_awaddr[3:0]!=0)||queued>=16)$fatal(1,"bad AW");
    valid_words=m_axi_awsize==4?4:1;
    for(integer q=0;q<valid_words;q=q+1)begin
     ix=index_of(m_axi_awaddr+q*4);
     if(ix<0||ix>=N_MEMORY||permission[ix]!=4||!dut.owner)$fatal(1,"write escaped stage destination");
     if(!dut.owner&&(m_axi_awaddr+q*4<expand_command[591:528]||m_axi_awaddr+q*4>=expand_command[591:528]+expand_command[63:48]*expand_command[15:0]*4))$fatal(1,"write to another panel");
     if(dut.owner&&(m_axi_awaddr+q*4<output_base_byte||m_axi_awaddr+q*4>=output_base_byte+((gemm_command[7:0]-1)*output_row_stride_words+gemm_command[15:8])*4))$fatal(1,"write to another tensor");
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
     if(normal_check&&memory[ix]!==golden[ix])$fatal(1,"PL convolution mismatch case=%0d stage=%0d address=%h got=%h want=%h",active_case,dut.owner,addresses[j]+q*4,memory[ix],golden[ix]);
     if(permission[ix]==2)visible[ix]=1;
    end
    write_pending[j]=0;data_done[j]=0;if(m_axi_bresp)write_error=0;
   end
  end
 end
 always @(negedge aclk)begin
  if(!aresetn)begin m_axi_arready=0;m_axi_awready=0;m_axi_wready=0;m_axi_rvalid=0;m_axi_bvalid=0;end
  else begin
   m_axi_arready=!hold_ar&&cycles%17<13;m_axi_awready=cycles%13<8;m_axi_wready=cycles%19<9;
   m_axi_rvalid=0;rs=-1;
   for(integer q=0;q<16;q=q+1)begin j=(q+cycles*7)%16;if(read_pending[j]&&read_due[j]<=cycles)rs=j;end
   if(rs>=0)begin m_axi_rid=rs;m_axi_rdata=read_data[rs];m_axi_rresp=read_error?2:0;m_axi_rlast=1;m_axi_rvalid=1;end
   m_axi_bvalid=0;bs=-1;
   if(!hold_b)for(integer q=0;q<16;q=q+1)begin j=(q+cycles*11)%16;if(write_pending[j]&&data_done[j]&&write_due[j]<=cycles)bs=j;end
   if(bs>=0)begin m_axi_bid=bs;m_axi_bresp=write_error?2:0;m_axi_bvalid=1;end
  end
 end
 task reset_bus;
  begin @(negedge aclk);aresetn=0;abort=0;cmd_valid=0;hold_ar=0;hold_b=0;read_error=0;write_error=0;normal_check=0;
   repeat(8)@(negedge aclk);aresetn=1;repeat(3)@(negedge aclk);if(fault||!transport_drained||!cmd_ready)$fatal(1,"reset failure");end
 endtask
 task submit(input integer n);
  integer t;begin
   @(negedge aclk);active_case=n;expand_command=expansions[n];gemm_command=matrices[n];output_base_byte=destinations[n];output_row_stride_words=strides[n];job_epoch=64'h2026102600000001+n;cmd_valid=1;t=0;
   @(posedge aclk);while(!cmd_ready)begin @(posedge aclk);t=t+1;if(t>1000)$fatal(1,"submit timeout");end
   #1;@(negedge aclk);cmd_valid=0;
  end
 endtask
 task wait_done;
  integer t;begin t=0;while(!done)begin @(posedge aclk);t=t+1;if(fault||t>200000)$fatal(1,"done missing %h",fault);end end
 endtask
 task wait_failed(input [31:0] code);
  integer t;begin
   #1;t=0;while(!fault)begin @(negedge aclk);#1;t=t+1;if(t>200000)$fatal(1,"missing fault");end
   if(fault!=code)$fatal(1,"wrong fault %h expected %h",fault,code);
   t=0;while(!transport_drained)begin @(negedge aclk);t=t+1;if(t>30000)$fatal(1,"fault did not drain");end
   repeat(8)@(negedge aclk);if(done||cmd_ready||m_axi_arvalid||m_axi_awvalid||m_axi_wvalid)$fatal(1,"fault not quarantined");negative=negative+1;
  end
 endtask
 initial begin
  $readmemh("expand.hex",expansions);$readmemh("gemm.hex",matrices);$readmemh("dest.hex",destinations);$readmemh("strides.hex",strides);
  $readmemh("memory.hex",memory);$readmemh("golden_memory.hex",golden);$readmemh("permissions.hex",permission);
  for(integer q=0;q<N_MEMORY;q=q+1)visible[q]=permission[q]==1;
  output_file=$fopen("pipeline_outputs.hex","w");reset_bus();
  for(integer n=0;n<N_CASE;n=n+1)begin
   normal_check=1;if(n==0)hold_b=1;submit(n);
   if(n==0)begin
    wait(dut.writer.allocated_count==16);repeat(120)@(negedge aclk);
    if(!dut.owner||done||cmd_ready||transport_drained||fault)$fatal(1,"completed before final Y B fence");
    hold_b=0;fences=fences+1;
   end
   wait_done();
   if(result_epoch!=job_epoch||result_tag!=gemm_command[127:96])$fatal(1,"completed wrong owner");
   for(integer r=0;r<gemm_command[7:0];r=r+1)
    for(integer c=0;c<gemm_command[15:8];c=c+1)begin
     ix=index_of(output_base_byte+(r*output_row_stride_words+c)*4);
     if(memory[ix]!==golden[ix])$fatal(1,"incomplete output tensor");$fwrite(output_file,"%08x\n",memory[ix]);outputs=outputs+1;
    end
   panels=panels+expand_command[63:48]*expand_command[15:0];completed=completed+1;normal_check=0;
  end
  $fclose(output_file);
  // Check every immutable source and every row gap / guard in the whole arena.
  for(integer q=0;q<N_MEMORY;q=q+1)if(memory[q]!==golden[q])$fatal(1,"arena mismatch word=%0d",q);
  for(integer v=0;v<5;v=v+1)begin
   reset_bus();saved_matrix=matrices[0];saved_dest=destinations[0];before_reads=reads;before_writes=writes;
   case(v)
    0:matrices[0][127:96]=matrices[0][127:96]+1;
    1:matrices[0][255:224]=matrices[0][255:224]+1;
    2:matrices[0][287:256]=matrices[0][287:256]+1;
    3:matrices[0][159:128]=matrices[0][255:224];
    4:destinations[0]=expansions[0][655:592];
   endcase
   submit(0);wait_failed(32'h80000b01);
   if(reads!=before_reads||writes!=before_writes)$fatal(1,"invalid combined descriptor issued DMA");matrices[0]=saved_matrix;destinations[0]=saved_dest;
  end
  reset_bus();read_error=1;submit(0);wait_failed(32'h80000203);if(done)$fatal(1,"read failure published output");
  reset_bus();write_error=1;submit(0);wait_failed(32'h80000303);if(done)$fatal(1,"write failure published output");
  reset_bus();hold_ar=1;submit(0);wait(m_axi_arvalid);@(negedge aclk);abort=1;repeat(20)@(negedge aclk);
  if(!m_axi_arvalid||transport_drained||!dut.owner)$fatal(1,"abort withdrew direct compute AR");hold_ar=0;wait_failed(32'h80000b02);
  reset_bus();submit(0);wait(dut.owner);@(negedge aclk);hold_b=1;wait(write_pending!=0&&data_done!=0);@(negedge aclk);abort=1;repeat(20)@(negedge aclk);
  if(transport_drained||done||!dut.owner)$fatal(1,"abort ignored GEMM B");hold_b=0;wait_failed(32'h80000b02);
  // Abort on the expansion-to-matrix boundary must veto the owner switch.
  reset_bus();submit(0);wait(dut.phase==2&&dut.e_done&&transport_drained);
  @(negedge aclk);abort=1;#1;if(done||fault!=32'h80000b02)$fatal(1,"handoff abort not immediately visible");
  wait_failed(32'h80000b02);if(dut.owner)$fatal(1,"fault edge switched owner");
  // Queue occupancy is part of the fence even after the physical
  // reader has retired a reply. Discard buffered replies when aborting.
  reset_bus();force dut.shared_read_m_valid=1'b0;force dut.shared_read_m_ready=1'b0;
  submit(0);wait(dut.reply_count==2);@(negedge aclk);#1;
  if(transport_drained)$fatal(1,"buffered replies reported drained");
  abort=1;release dut.shared_read_m_valid;release dut.shared_read_m_ready;
  wait_failed(32'h80000b02);if(dut.reply_count!=0)$fatal(1,"abort did not drain reply queue");
  // Physical B retirement alone is insufficient: buffered completion
  // identities still belong to this owner and must quarantine a new command.
  reset_bus();force dut.shared_write_m_valid=1'b0;force dut.shared_write_m_ready=1'b0;
  submit(0);wait(dut.write_reply_count==2);@(negedge aclk);#1;
  if(transport_drained||cmd_ready||!dut.owner)$fatal(1,"buffered writes escaped fence");
  abort=1;release dut.shared_write_m_valid;release dut.shared_write_m_ready;
  wait_failed(32'h80000b02);
  if(dut.write_reply_count!=0||dut.reply_count!=0)$fatal(1,"abort did not drain both queues");
  if(completed!=N_CASE||outputs!=N_EXPECTED||fences!=1||negative!=12)$fatal(1,"insufficient pipeline coverage");
  if(quad_writes==0||scalar_writes==0)$fatal(1,"missing packed and scalar coverage");
  $display("CONV48_DIRECT_PASS commands=%0d outputs=%0d logical_window_words=%0d negatives=%0d fence_stalls=%0d owner_switches=%0d reads=%0d writes=%0d max_reads=%0d max_writes=%0d cycles=%0d quad_writes=%0d scalar_writes=%0d",completed,outputs,panels,negative,fences,owner_switches,reads,writes,max_reads,max_writes,cycles,quad_writes,scalar_writes);$finish;
 end
endmodule
