#include <ap_int.h>
#include <hls_stream.h>
typedef ap_uint<128> word;
typedef ap_uint<8> byte;
static byte gray(ap_uint<32> p){
#pragma HLS INLINE
    // Match the board's OpenCV 3.4.3 NEON conversion exactly.
    ap_uint<24> s=1868*ap_uint<8>(p.range(7,0))+9617*ap_uint<8>(p.range(15,8))+4899*ap_uint<8>(p.range(23,16))+8192;
    return s>>14;
}
template<int Phase> static void sort_stage(const byte in[9],byte out[9]){
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
#pragma HLS LATENCY min=1 max=1
#pragma HLS ARRAY_PARTITION variable=in complete
#pragma HLS ARRAY_PARTITION variable=out complete
    for(int j=0;j<9;j++){
#pragma HLS UNROLL
        if((Phase%2==0&&j==8)||(Phase%2==1&&j==0))out[j]=in[j];
        else if(j%2==Phase%2)out[j]=in[j]<in[j+1]?in[j]:in[j+1];
        else out[j]=in[j]>in[j-1]?in[j]:in[j-1];
    }
}
static byte median9(byte win[3][3]){
#pragma HLS INLINE
    // Registered single-assignment stages prevent Vivado 2018.2 from
    // merging several compare/exchange levels into a cyclic carry network.
    byte a[10][9];
#pragma HLS ARRAY_PARTITION variable=a complete dim=0
    for(int i=0;i<9;i++){
#pragma HLS UNROLL
        a[0][i]=win[i/3][i%3];
    }
    sort_stage<0>(a[0],a[1]);sort_stage<1>(a[1],a[2]);sort_stage<2>(a[2],a[3]);
    sort_stage<3>(a[3],a[4]);sort_stage<4>(a[4],a[5]);sort_stage<5>(a[5],a[6]);
    sort_stage<6>(a[6],a[7]);sort_stage<7>(a[7],a[8]);sort_stage<8>(a[8],a[9]);
    return a[9][4];
}
static byte sobel(byte w[3][3]){
#pragma HLS INLINE
    int gx=int(w[0][2])+2*int(w[1][2])+int(w[2][2])-int(w[0][0])-2*int(w[1][0])-int(w[2][0]);
    int gy=int(w[2][0])+2*int(w[2][1])+int(w[2][2])-int(w[0][0])-2*int(w[0][1])-int(w[0][2]);
    unsigned ax=gx<0?-gx:gx,ay=gy<0?-gy:gy;unsigned s=(ax>255?255:ax)+(ay>255?255:ay);
    // OpenCV 3.4.3 on this A53 uses nearest, positive half up.
    return (s+1)>>1;
}
static void process(hls::stream<word>&input,hls::stream<word>&output,unsigned command,unsigned width,unsigned height){
#pragma HLS INLINE off
    byte r0[1280],r1[1280],r2[1280];
#pragma HLS RESOURCE variable=r0 core=RAM_2P_BRAM
#pragma HLS RESOURCE variable=r1 core=RAM_2P_BRAM
#pragma HLS RESOURCE variable=r2 core=RAM_2P_BRAM
    if(command==1){
        word pack=0;
        for(unsigned i=0;i<width*height/4;i++){
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=8 max=153600
            word raw=input.read();ap_uint<32> four;
            for(int k=0;k<4;k++){
#pragma HLS UNROLL
                four.range(k*8+7,k*8)=gray(raw.range(k*32+31,k*32));
            }
            pack.range((i%4)*32+31,(i%4)*32)=four;
            if(i%4==3)output.write(pack);
        }
        return;
    }
    word raw=0;
    for(unsigned k=0;k<width;k++){
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=16 max=1280
        if(k%4==0)raw=input.read();
        byte v=gray(raw.range((k%4)*32+31,(k%4)*32));r0[k]=v;r1[k]=v;
    }
    for(unsigned k=0;k<width;k++){
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=16 max=1280
        if(k%4==0)raw=input.read();
        byte v=gray(raw.range((k%4)*32+31,(k%4)*32));r2[k]=v;if(command==3)r0[k]=v;
    }
    for(unsigned y=0;y<height;y++){
#pragma HLS LOOP_TRIPCOUNT min=2 max=480
        byte w[3][3];
#pragma HLS ARRAY_PARTITION variable=w complete dim=0
        w[0][0]=command==3?r0[1]:r0[0];w[0][1]=r0[0];w[0][2]=r0[1];
        w[1][0]=command==3?r1[1]:r1[0];w[1][1]=r1[0];w[1][2]=r1[1];
        w[2][0]=command==3?r2[1]:r2[0];w[2][1]=r2[0];w[2][2]=r2[1];
        word pack=0;
        for(unsigned x=0;x<width;x++){
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=16 max=1280
#pragma HLS DEPENDENCE variable=r0 inter false
#pragma HLS DEPENDENCE variable=r1 inter false
#pragma HLS DEPENDENCE variable=r2 inter false
            byte v=command==2?median9(w):sobel(w);
            pack.range((x%16)*8+7,(x%16)*8)=v;
            if(x%16==15)output.write(pack);
            // Read the unconsumed column before advancing the three row banks.
            // Border columns already in the window never reread overwritten RAM.
            unsigned col=x+2<width?x+2:width-1;
            bool from_window=(x+2>=width)&&(command==3||x+1==width);
            byte n0=from_window?w[0][1]:r0[col],n1=from_window?w[1][1]:r1[col],n2=from_window?w[2][1]:r2[col];
            if(y+1<height){
                byte future;
                if(y+2<height){
                    if(x%4==0)raw=input.read();
                    future=gray(raw.range((x%4)*32+31,(x%4)*32));
                }else future=command==3?w[1][1]:w[2][1];
                r0[x]=w[1][1];r1[x]=w[2][1];r2[x]=future;
            }
            for(int r=0;r<3;r++){
#pragma HLS UNROLL
                w[r][0]=w[r][1];w[r][1]=w[r][2];
            }
            w[0][2]=n0;w[1][2]=n1;w[2][2]=n2;
        }
    }
}
static void read_pixels(word*input,hls::stream<word>&stream,unsigned n){
#pragma HLS INLINE off
    for(unsigned i=0;i<n;i++){
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=8 max=153600
        stream.write(input[i]);
    }
}
static void write_pixels(hls::stream<word>&stream,word*output,unsigned n){
#pragma HLS INLINE off
    for(unsigned i=0;i<n;i++){
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=2 max=38400
        output[i]=stream.read();
    }
}
static void pipeline(word*input,word*output,unsigned command,unsigned width,unsigned height){
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream<word> incoming,outgoing;
#pragma HLS STREAM variable=incoming depth=64
#pragma HLS STREAM variable=outgoing depth=64
    read_pixels(input,incoming,width*height/4);
    process(incoming,outgoing,command,width,height);
    write_pixels(outgoing,output,width*height/16);
}
unsigned preview_filters(word *input,word *output,unsigned command,unsigned width,unsigned height){
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=readmem depth=153600 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=writemem depth=38400 max_write_burst_length=64 num_write_outstanding=4
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=command bundle=control
#pragma HLS INTERFACE s_axilite port=width bundle=control
#pragma HLS INTERFACE s_axilite port=height bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    if(command==0)return 0x50464C31;
    if(command>3||width<16||width>1280||(width%16)||height<2||height>480)return 0;
    pipeline(input,output,command,width,height);
    return 1;
}
