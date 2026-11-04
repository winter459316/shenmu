`timescale 1ns/1ps
module tb_cache_lifetime;
 reg aclk=0;always #5 aclk=~aclk;
 reg aresetn=0,abort=0,start_valid=0,first_chunk=0,fill_bank=0;
 reg [63:0] generation=0;reg [31:0] command_tag=0;
 reg [15:0] chunk_id=0;
 wire start_ready;
 reg [775:0] s_window_data=0;reg [3:0] s_window_valid=0;
 wire [3:0] s_window_ready;
 wire [223:0] m_read_tdata;wire m_read_tvalid;reg m_read_tready=0;
 reg [287:0] s_read_tdata=0;reg s_read_tvalid=0;wire s_read_tready;
 wire cache_write,cache_bank;wire [15:0] cache_chunk;
 wire [12:0] cache_index;wire [2:0] cache_count;wire [127:0] cache_data;
 wire done,fault,rejecting_input,rejecting_reply,transport_drained;
 wire [31:0] fault_status;
 fp3_window_collect dut(.aclk(aclk),.aresetn(aresetn),.abort(abort),
  .start_valid(start_valid),.first_chunk(first_chunk),.start_ready(start_ready),
  .generation(generation),.arena_base_byte(64'h1000),.arena_limit_byte(64'h1100),
  .command_tag(command_tag),.columns(8'd4),.chunk_len(8'd32),
  .fill_bank(fill_bank),.chunk_id(chunk_id),.s_window_data(s_window_data),
  .s_window_valid(s_window_valid),.s_window_ready(s_window_ready),
  .m_read_tdata(m_read_tdata),.m_read_tvalid(m_read_tvalid),.m_read_tready(m_read_tready),
  .s_read_tdata(s_read_tdata),.s_read_tvalid(s_read_tvalid),.s_read_tready(s_read_tready),
  .cache_write(cache_write),.cache_bank(cache_bank),.cache_chunk(cache_chunk),
  .cache_index(cache_index),.cache_count(cache_count),.cache_data(cache_data),
  .done(done),.fault(fault),.fault_status(fault_status),.rejecting_input(rejecting_input),
  .rejecting_reply(rejecting_reply),.transport_drained(transport_drained));
 integer cycles=0,reads=0,outputs=0,reuses=0,runs=0,content=0;
 reg [15:0] pending=0;reg [287:0] replies[0:15];integer due[0:15];
 integer selected=-1,slot,ix,read_before,output_before,expected;
 reg inject_stale=0;
 always @(posedge aclk)begin
  cycles=cycles+1;
  if(aresetn)begin
   if(s_read_tvalid&&s_read_tready&&!inject_stale)pending[s_read_tdata[163:160]]=0;
   if(m_read_tvalid&&m_read_tready)begin
    slot=m_read_tdata[99:96];
    if(pending[slot])$fatal(1,"test reply slot reused");
    if(m_read_tdata[95:64]!=4||m_read_tdata[3:0]!=0||
       m_read_tdata[63:0]<64'h1000||m_read_tdata[63:0]>=64'h1100)$fatal(1,"bad physical read");
    replies[slot]={m_read_tdata[223:96],32'd1,128'd0};
    for(integer l=0;l<4;l=l+1)replies[slot][l*32+:32]=content+(m_read_tdata[63:0]>>2)+l;
    pending[slot]=1;due[slot]=cycles+13+(reads%7);reads=reads+1;
   end
   if(cache_write)begin
    if(cache_count!=4||cache_bank!=fill_bank||cache_chunk!=chunk_id||cache_index>=32)
     $fatal(1,"bad private group metadata");
    for(integer l=0;l<4;l=l+1)begin
     expected=content+1024+(cache_index%2)*4+l;
     if(cache_data[l*32+:32]!==expected)$fatal(1,"stale cache data run=%0d k=%0d lane=%0d got=%h want=%h",runs,cache_index,l,cache_data[l*32+:32],expected);
    end
    outputs=outputs+1;
   end
   if(dut.reuse)reuses=reuses+1;
  end
  if(cycles>10000)$fatal(1,"cache lifetime watchdog");
 end
 always @(negedge aclk)begin
  m_read_tready=aresetn&&cycles%3!=0;
  s_read_tvalid=0;selected=-1;
  if(aresetn)begin
   for(integer q=0;q<16;q=q+1)begin
    ix=(q+cycles*7)%16;
    if(pending[ix]&&due[ix]<=cycles)selected=ix;
   end
   if(selected>=0)begin s_read_tdata=replies[selected];s_read_tvalid=1;end
   if(inject_stale)begin s_read_tdata={64'h9999,32'h11,32'h80000000,32'd1,128'd0};s_read_tvalid=1;end
  end
 end
 task run_chunk(input [63:0] gen,input [31:0] tag,input integer first,input integer value,input integer must_hit);
  begin
   @(negedge aclk);generation=gen;command_tag=tag;first_chunk=first;content=value;
   fill_bank=~fill_bank;chunk_id=chunk_id+32;start_valid=1;
   read_before=reads;output_before=outputs;
   @(posedge aclk);while(!start_ready)@(posedge aclk);
   #1;@(negedge aclk);start_valid=0;
   for(integer k=0;k<32;k=k+1)begin
    for(integer l=0;l<4;l=l+1)
     s_window_data[l*194+:194]={tag,32'(k*4+l),64'(4096+(k%2)*16+l*4),64'd0,(k==31),1'b0};
    s_window_valid=4'hf;
    @(posedge aclk);while(s_window_ready!=4'hf)@(posedge aclk);
    #1;@(negedge aclk);s_window_valid=0;
   end
   while(!done)begin @(negedge aclk);if(fault)$fatal(1,"cache run fault %h",fault_status);end
   if(outputs-output_before!=32||!transport_drained||pending!=0)$fatal(1,"incomplete private result");
   if(must_hit&&reads!=read_before)$fatal(1,"same command next chunk missed cache");
   if(!must_hit&&(reads==read_before||reads-read_before>=32))$fatal(1,"cache invalidation/reuse not covered");
   runs=runs+1;repeat(3)@(negedge aclk);
  end
 endtask
 initial begin
  repeat(5)@(negedge aclk);aresetn=1;repeat(3)@(negedge aclk);
  run_chunk(1,32'h11,1,100,0);
  run_chunk(1,32'h11,0,100,1);
  run_chunk(1,32'h11,1,200,0);
  run_chunk(2,32'h11,0,300,0);
  run_chunk(2,32'h12,0,400,0);
  // An unsolicited stale completion must still fault even with a warm cache.
  inject_stale=1;@(negedge aclk);@(posedge aclk);#1;
  if(!fault||fault_status!=32'h80000d03||cache_write)$fatal(1,"warm cache hid stale reply");
  inject_stale=0;repeat(3)@(negedge aclk);
  if(start_ready||!transport_drained)$fatal(1,"stale reply did not quarantine");
  aresetn=0;repeat(3)@(negedge aclk);aresetn=1;repeat(3)@(negedge aclk);
  if(dut.read_cache_valid!=0||fault||!start_ready)$fatal(1,"bus reset retained cache");
  if(reuses<120)$fatal(1,"insufficient cache reuse coverage");
  $display("CACHE_LIFETIME_PASS runs=%0d groups=%0d reuses=%0d reads=%0d cycles=%0d",runs,outputs,reuses,reads,cycles);$finish;
 end
endmodule
