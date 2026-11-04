#include <ap_int.h>
#include <hls_stream.h>
#include "tone_lut.h"
typedef ap_uint<128> word;
typedef ap_uint<24> rgb;
typedef ap_uint<72> triple;
#include "vessel_core.h"
// PXP1 is display-only; the model input and calibrated photo path are unchanged.
static void read_stream(word *p,hls::stream<word>&s,unsigned n){
#pragma HLS INLINE off
    for(unsigned i=0;i<n;i++){
#pragma HLS PIPELINE II=1
        s.write(p[i]);
    }
}
static void write_stream(hls::stream<word>&s,word*p,unsigned n){
#pragma HLS INLINE off
    for(unsigned i=0;i<n;i++){
#pragma HLS PIPELINE II=1
        p[i]=s.read();
    }
}
static void pixel_op(hls::stream<word>&a,hls::stream<word>&b,unsigned command,unsigned w,unsigned h){
#pragma HLS INLINE off
    for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x+=4){
#pragma HLS PIPELINE II=1
        word v=a.read(),out=0;
        for(int k=0;k<4;k++){
#pragma HLS UNROLL
            ap_uint<32> p=v.range(32*k+31,32*k),q=p;
            if(command==1){
                for(int c=0;c<3;c++){
#pragma HLS UNROLL
                    q.range(8*c+7,8*c)=tone_lut[(unsigned)p.range(8*c+7,8*c)];
                }
            }else{
                if(y>0 && y%(h/6)==0)q=0x0000dc00;
                if(x+k==w/2)q=0x00dcdcdc;
            }
            out.range(32*k+31,32*k)=q;
        }
        b.write(out);
    }
}
static void pixels(word*input,word*output,unsigned command,unsigned w,unsigned h){
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream<word> a,b;
#pragma HLS STREAM variable=a depth=64
#pragma HLS STREAM variable=b depth=64
    read_stream(input,a,w*h/4);pixel_op(a,b,command,w,h);write_stream(b,output,w*h/4);
}
static rgb sample(triple *area,int x,int y){
#pragma HLS INLINE
    if(x<0||x>=320||y<0||y>=360)return 0;
    unsigned i=y*320+x;triple p=area[i/3];
    return p.range((i%3)*24+23,(i%3)*24);
}
static void rectify(word*input,word*output,ap_uint<64>*maps){
#pragma HLS INLINE off
    triple area[38400];
#pragma HLS RESOURCE variable=area core=XPM_MEMORY uram
    word rows[4][160];
#pragma HLS ARRAY_PARTITION variable=rows complete dim=1
#pragma HLS RESOURCE variable=rows core=RAM_2P_BRAM
    word outrow[80];ap_uint<64> maprow[320];
#pragma HLS RESOURCE variable=outrow core=RAM_2P_BRAM
#pragma HLS RESOURCE variable=maprow core=RAM_2P_BRAM
    for(unsigned eye=0;eye<2;eye++){
        triple packed=0;
        for(unsigned group=0;group<120;group++){
            for(unsigned r=0;r<4;r++)for(unsigned i=0;i<160;i++){
#pragma HLS PIPELINE II=1
                rows[r][i]=input[(group*4+r)*320+eye*160+i];
            }
            for(unsigned k=0;k<3;k++)for(unsigned x=0;x<320;x++){
#pragma HLS PIPELINE II=1
                word a=rows[k][x/2],b=rows[k+1][x/2];rgb p;
                for(int c=0;c<3;c++){
#pragma HLS UNROLL
                    unsigned sh=(x%2)*64+c*8;
                    unsigned sum=((unsigned)a.range(sh+7,sh)+(unsigned)a.range(sh+39,sh+32))*(3-k)
                                +((unsigned)b.range(sh+7,sh)+(unsigned)b.range(sh+39,sh+32))*(1+k);
                    p.range(8*c+7,8*c)=(sum+3+((sum>>3)&1))>>3;
                }
                unsigned i=(group*3+k)*320+x;
                packed.range((i%3)*24+23,(i%3)*24)=p;
                if(i%3==2)area[i/3]=packed;
            }
        }
        for(unsigned y=0;y<360;y++){
            for(unsigned x=0;x<320;x++){
#pragma HLS PIPELINE II=1
                maprow[x]=maps[eye*115200+y*320+x];
            }
            word pack=0;
            for(unsigned x=0;x<320;x++){
#pragma HLS PIPELINE II=4
                ap_uint<64> m=maprow[x];int sx=(ap_int<16>)m.range(15,0),sy=(ap_int<16>)m.range(31,16);
                unsigned fx=m.range(36,32),fy=m.range(41,37);
                rgb p0=sample(area,sx,sy),p1=sample(area,sx+1,sy),p2=sample(area,sx,sy+1),p3=sample(area,sx+1,sy+1);
                ap_uint<32> out=0;
                for(int c=0;c<3;c++){
#pragma HLS UNROLL
                    unsigned s=(unsigned)p0.range(8*c+7,8*c)*(32-fx)*(32-fy)
                              +(unsigned)p1.range(8*c+7,8*c)*fx*(32-fy)
                              +(unsigned)p2.range(8*c+7,8*c)*(32-fx)*fy
                              +(unsigned)p3.range(8*c+7,8*c)*fx*fy;
                    out.range(8*c+7,8*c)=(s+512)>>10;
                }
                pack.range((x%4)*32+31,(x%4)*32)=out;
                if(x%4==3)outrow[x/4]=pack;
            }
            for(unsigned i=0;i<80;i++){
#pragma HLS PIPELINE II=1
                output[y*160+eye*80+i]=outrow[i];
            }
        }
    }
}
static float luma(ap_uint<32> p){
#pragma HLS INLINE off
    float b=(unsigned)p.range(7,0),g=(unsigned)p.range(15,8),r=(unsigned)p.range(23,16);
    float x=.114f*b,y=.587f*g,z=.299f*r;
    float xy=x+y;return xy+z;
}
static void meter(word*input,word*output){
#pragma HLS INLINE off
    double values[10];
    for(unsigned eye=0;eye<2;eye++){
        float chunks[32];unsigned bright=0,dark=0;
        for(unsigned block=0;block<32;block++){
            float lanes[8];
#pragma HLS ARRAY_PARTITION variable=lanes complete
            for(unsigned i=0;i<96;i++){
#pragma HLS PIPELINE II=12
                unsigned n=block*96+i,y=48+(n/64)*8,x=eye*640+64+(n%64)*8;
                word p=input[y*320+x/4];float v=luma(p.range(31,0));
                if(i<8)lanes[i]=v;else lanes[i%8]=lanes[i%8]+v;
                if(v>245.f)bright++;if(v<12.f)dark++;
            }
            chunks[block]=((lanes[0]+lanes[1])+(lanes[2]+lanes[3]))+((lanes[4]+lanes[5])+(lanes[6]+lanes[7]));
        }
        for(unsigned count=32;count>1;count/=2)for(unsigned i=0;i<count/2;i++)chunks[i]=chunks[2*i]+chunks[2*i+1];
        float mean=chunks[0]/3072.f;
        values[eye*3]=mean;values[eye*3+1]=(double)bright/3072.;values[eye*3+2]=(double)dark/3072.;
    }
    values[6]=(values[0]+values[3])/2.;values[7]=values[1]>values[4]?values[1]:values[4];
    double diff=values[0]-values[3];values[8]=diff<0?-diff:diff;values[9]=0.;
    for(unsigned i=0;i<5;i++){
        union{double f;unsigned long long u;} a,b;a.f=values[2*i];b.f=values[2*i+1];
        word p=0;p.range(63,0)=a.u;p.range(127,64)=b.u;output[i]=p;
    }
}
unsigned preview_extra(word*input,word*output,ap_uint<64>*maps,unsigned command,unsigned width,unsigned height){
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=readmem depth=153600 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS INTERFACE m_axi port=maps offset=slave bundle=mapmem depth=230400 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=writemem depth=153600 max_write_burst_length=64 num_write_outstanding=4
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=maps bundle=control
#pragma HLS INTERFACE s_axilite port=command bundle=control
#pragma HLS INTERFACE s_axilite port=width bundle=control
#pragma HLS INTERFACE s_axilite port=height bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    if(command==0)return 0x50585031;
    if(command==5){
        if(width<32||width>1280||width%16||height<9||height>480)return 0;
        vessels(input,output,width,height);
    }else if(command==2||command==4){
        if(width!=1280||height!=480)return 0;
        if(command==2)rectify(input,output,maps);else meter(input,output);
    }else if(command==1||command==3){
        if(width<16||width>1280||width%16||height<6||height>480)return 0;
        pixels(input,output,command,width,height);
    }else return 0;
    return 1;
}
