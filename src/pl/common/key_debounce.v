
module key_debounce(
    input        sys_clk   ,
    input        sys_rst_n ,

    input        key       ,   //外部输入的按键值
    output  reg  key_filter    //按键消抖后的值
);

// Adapted for 100 MHz: 20 ms = 2,000,000 cycles; use only synchronized button data.
//parameter define
parameter  CNT_MAX = 32'd200_0000;    //消抖时间20ms

//reg define
reg key_previous;
reg [31:0] cnt ;
(* ASYNC_REG = "TRUE" *) reg key_d0;            //将按键信号延迟一个时钟周期
(* ASYNC_REG = "TRUE" *) reg key_d1;            //将按键信号延迟两个时钟周期

//*****************************************************
//**                    main code
//*****************************************************

//对按键端口的数据延迟两个时钟周期
always @ (posedge sys_clk or negedge sys_rst_n) begin
    if(!sys_rst_n) begin
        key_d0 <= 1'b1;
        key_d1 <= 1'b1;
        key_previous <= 1'b1;
    end
    else begin
        key_d0 <= key;
        key_d1 <= key_d0;
        key_previous <= key_d1;
    end 
end

//按键值消抖
always @ (posedge sys_clk or negedge sys_rst_n) begin
    if(!sys_rst_n) 
        cnt <= 32'd0;
    else begin
        if(key_d1 != key_previous)    //检测到按键状态发生变化
            cnt <= CNT_MAX;     //则开始20ms倒计时
        else begin              //如果当前按键值和前一个按键值一样，即按键没有发生变化
            if(cnt > 32'd0)     //则计数器递减到0
                cnt <= cnt - 32'b1;  
            else
                cnt <= 32'd0;
        end
    end
end

//将消抖后的最终的按键值送出去
always @ (posedge sys_clk or negedge sys_rst_n) begin
    if(!sys_rst_n)
        key_filter <= 1'b1;
    //在计数器递减到1时送出按键值
    else if(cnt == 32'd1) 
        key_filter <= key_d1;
    else
        key_filter <= key_filter;
end

endmodule