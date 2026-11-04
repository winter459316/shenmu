// Two-entry queue; direct registered head data and occupancy-only upstream ready.
// No head-address mux/LUTRAM read sits before the consumer's identity lookup.
module fp3_request_fifo #(parameter WIDTH=128)(
 input wire aclk,aresetn,
 input wire [WIDTH-1:0] s_data,input wire s_valid,output wire s_ready,
 output wire [WIDTH-1:0] m_data,output wire m_valid,input wire m_ready,
 output reg [1:0] count=0
);
 reg [WIDTH-1:0] first=0,second=0;
 assign s_ready=aresetn&&count<2;
 assign m_valid=aresetn&&count!=0;
 assign m_data=first;
 wire push=s_valid&&s_ready,pop=m_valid&&m_ready;
 always @(posedge aclk)begin
  if(!aresetn)begin count<=0;first<=0;second<=0;end
  else begin
   if(push)begin
    if(count==0||pop)first<=s_data;
    else second<=s_data;
   end else if(pop&&count==2)first<=second;
   case({push,pop})
    2'b10:count<=count+1'b1;
    2'b01:count<=count-1'b1;
    default:count<=count;
   endcase
  end
 end
endmodule
